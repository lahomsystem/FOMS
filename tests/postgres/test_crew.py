"""CREW-00 PostgreSQL 계약 테스트 (PGTEST-00 lane).

설치 작업자 마스터(:class:`~models.InstallationWorker`) 와 주문 배정 registry
(:class:`~models.OrderInstallationAssignment`) 의 external ID lifecycle, 0..20 배정
replace/release history, partial unique/concurrency(``FOR UPDATE``), linked user
validation, in-use deactivate 409, display projection, audit, free-name backfill,
그리고 **auth 무영향**(crew 변경이 배정 authorization SSOT 에 영향 0)을 실 PostgreSQL
다중 커밋 세션으로 검증한다.

``FOMS_TEST_DATABASE_URL`` 미설정이면 lane 자체가 skip 된다(conftest). 커밋 파일에는
비밀번호를 넣지 않는다(dev DSN 은 env). service 는 아직 route/AUTH 에 배선되지 않았다
(CREW-00 경계) — 이 테스트가 하류(SHIPMENT-REFERENCE-01)가 의존할 계약을 정본으로 고정한다.
"""
from __future__ import annotations

import threading
import time

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from foms.services.crew import (
    AssignmentCapExceededError,
    AssignmentNotActiveError,
    DuplicateExternalWorkerIdError,
    InactiveWorkerError,
    LinkedUserInvalidError,
    WorkerAlreadyAssignedError,
    WorkerInUseError,
    active_worker_ids,
    apply_backfill,
    assign_worker,
    assignment_history,
    audit_free_names,
    create_worker,
    deactivate_worker,
    list_active_workers,
    release_worker,
    replace_workers,
    update_worker,
)
from foms.services.orders.assignment import active_assignee_ids
from models import InstallationWorker, Order, OrderInstallationAssignment, User

_SEQ = [0]


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def _session(pg_engine):
    """독립 연결/세션(동시성 테스트용 다중 커밋)."""
    return sessionmaker(bind=pg_engine)()


def _suffix() -> str:
    _SEQ[0] += 1
    return f"{_SEQ[0]}_{int(time.time() * 1000) % 100000}"


def _make_user(session, *, is_active=True) -> User:
    s = _suffix()
    u = User(
        username=f"crewuser_{s}", password="pw-not-committed", name="계정",
        role="STAFF", team=None, is_active=is_active,
    )
    session.add(u)
    session.flush()
    return u


def _make_order(session) -> Order:
    o = Order(
        received_date="2026-07-24", customer_name="홍길동", phone="010-0000-0000",
        address="서울", product="침대",
    )
    session.add(o)
    session.flush()
    return o


def _make_worker(session, *, name=None, ext=None, user_id=None) -> InstallationWorker:
    s = _suffix()
    return create_worker(
        session, external_worker_id=ext or f"EXT-{s}",
        display_name=name or f"작업자-{s}", phone="010-1111-2222", user_id=user_id,
    )


# --------------------------------------------------------------------------- #
# 1. external worker ID lifecycle (create/update/deactivate)
# --------------------------------------------------------------------------- #
def test_worker_lifecycle_create_update_deactivate(pg_session):
    w = _make_worker(pg_session, name="김설치", ext="EXT-LC1")
    assert w.id is not None and w.is_active is True

    update_worker(pg_session, w.id, display_name="김설치2", phone="010-9999-8888")
    pg_session.refresh(w)
    assert w.display_name == "김설치2"
    assert w.phone == "010-9999-8888"

    deactivate_worker(pg_session, w.id)
    pg_session.refresh(w)
    assert w.is_active is False
    assert w.deactivated_at is not None


def test_active_external_id_unique_but_reregister_after_deactivate(pg_session):
    w1 = _make_worker(pg_session, ext="EXT-DUP")
    # 활성 상태에서 같은 external_worker_id 재등록 → 409.
    with pytest.raises(DuplicateExternalWorkerIdError):
        create_worker(pg_session, external_worker_id="EXT-DUP", display_name="중복")
    # 비활성화 후에는 같은 external_worker_id 재등록 허용(partial unique).
    deactivate_worker(pg_session, w1.id)
    w2 = create_worker(pg_session, external_worker_id="EXT-DUP", display_name="재등록")
    assert w2.id != w1.id and w2.is_active is True


def test_partial_unique_backstop_rejects_two_active_same_external(pg_session):
    _make_worker(pg_session, ext="EXT-RAW")
    # service 우회 raw insert 로 두 번째 활성 같은 external → partial unique 위반.
    with pytest.raises(IntegrityError):
        pg_session.execute(text(
            "INSERT INTO installation_workers "
            "(external_worker_id, display_name, is_active) "
            "VALUES ('EXT-RAW', 'raw', true)"))
        pg_session.flush()
    pg_session.rollback()


# --------------------------------------------------------------------------- #
# 2. linked user validation
# --------------------------------------------------------------------------- #
def test_linked_user_must_exist_and_be_active(pg_session):
    active = _make_user(pg_session, is_active=True)
    inactive = _make_user(pg_session, is_active=False)

    w = _make_worker(pg_session, user_id=active.id)
    assert w.user_id == active.id

    with pytest.raises(LinkedUserInvalidError):
        create_worker(pg_session, external_worker_id="EXT-LU1",
                      display_name="x", user_id=inactive.id)
    with pytest.raises(LinkedUserInvalidError):
        create_worker(pg_session, external_worker_id="EXT-LU2",
                      display_name="y", user_id=9_999_999)
    # update 로 link 해제/재검증도 동일.
    with pytest.raises(LinkedUserInvalidError):
        update_worker(pg_session, w.id, user_id=inactive.id)
    update_worker(pg_session, w.id, user_id=None)
    pg_session.refresh(w)
    assert w.user_id is None


# --------------------------------------------------------------------------- #
# 3. in-use deactivate → 409
# --------------------------------------------------------------------------- #
def test_in_use_worker_deactivate_conflict_then_release(pg_session):
    o = _make_order(pg_session)
    w = _make_worker(pg_session)
    assign_worker(pg_session, order_id=o.id, worker_id=w.id)

    with pytest.raises(WorkerInUseError) as ei:
        deactivate_worker(pg_session, w.id)
    assert ei.value.status_code == 409

    # release 후에는 비활성화 가능.
    release_worker(pg_session, order_id=o.id, worker_id=w.id, reason="완료")
    deactivate_worker(pg_session, w.id)
    pg_session.refresh(w)
    assert w.is_active is False


# --------------------------------------------------------------------------- #
# 4. 0..20 배정 replace/release history
# --------------------------------------------------------------------------- #
def test_assign_cap_20_and_reject_21st(pg_session):
    o = _make_order(pg_session)
    workers = [_make_worker(pg_session) for _ in range(21)]
    for w in workers[:20]:
        assign_worker(pg_session, order_id=o.id, worker_id=w.id)
    assert len(active_worker_ids(pg_session, o.id)) == 20
    with pytest.raises(AssignmentCapExceededError):
        assign_worker(pg_session, order_id=o.id, worker_id=workers[20].id)
    assert len(active_worker_ids(pg_session, o.id)) == 20


def test_duplicate_active_assign_rejected(pg_session):
    o = _make_order(pg_session)
    w = _make_worker(pg_session)
    assign_worker(pg_session, order_id=o.id, worker_id=w.id)
    with pytest.raises(WorkerAlreadyAssignedError):
        assign_worker(pg_session, order_id=o.id, worker_id=w.id)


def test_release_then_reassign_preserves_history(pg_session):
    o = _make_order(pg_session)
    w = _make_worker(pg_session)
    assign_worker(pg_session, order_id=o.id, worker_id=w.id)
    release_worker(pg_session, order_id=o.id, worker_id=w.id, reason="교체")
    assert active_worker_ids(pg_session, o.id) == []
    # released 뒤 같은 worker 재배정 허용.
    assign_worker(pg_session, order_id=o.id, worker_id=w.id)
    assert active_worker_ids(pg_session, o.id) == [w.id]

    hist = assignment_history(pg_session, o.id)
    assert len(hist) == 2  # released 1 + active 1 (이력 보존)
    statuses = [h["status"] for h in hist]
    assert statuses.count("RELEASED") == 1 and statuses.count("ACTIVE") == 1
    released = next(h for h in hist if h["status"] == "RELEASED")
    assert released["release_reason"] == "교체"


def test_release_missing_active_conflicts(pg_session):
    o = _make_order(pg_session)
    w = _make_worker(pg_session)
    with pytest.raises(AssignmentNotActiveError):
        release_worker(pg_session, order_id=o.id, worker_id=w.id, reason="없음")


def test_replace_workers_set_semantics(pg_session):
    o = _make_order(pg_session)
    a, b, c = [_make_worker(pg_session) for _ in range(3)]
    assign_worker(pg_session, order_id=o.id, worker_id=a.id)
    assign_worker(pg_session, order_id=o.id, worker_id=b.id)
    # {a,b} → {b,c}: a release, c assign, b 유지.
    replace_workers(pg_session, order_id=o.id, worker_ids=[b.id, c.id], reason="재편성")
    assert active_worker_ids(pg_session, o.id) == sorted([b.id, c.id])
    # replace 로 전부 비우기(0 허용).
    replace_workers(pg_session, order_id=o.id, worker_ids=[], reason="비움")
    assert active_worker_ids(pg_session, o.id) == []


def test_replace_over_cap_rejected(pg_session):
    o = _make_order(pg_session)
    workers = [_make_worker(pg_session) for _ in range(21)]
    with pytest.raises(AssignmentCapExceededError):
        replace_workers(pg_session, order_id=o.id,
                        worker_ids=[w.id for w in workers])


def test_assign_inactive_worker_rejected(pg_session):
    o = _make_order(pg_session)
    w = _make_worker(pg_session)
    deactivate_worker(pg_session, w.id)
    with pytest.raises(InactiveWorkerError):
        assign_worker(pg_session, order_id=o.id, worker_id=w.id)


# --------------------------------------------------------------------------- #
# 5. partial unique / concurrency (FOR UPDATE 직렬화 → 하나만 active)
# --------------------------------------------------------------------------- #
def test_concurrent_assign_same_worker_yields_one_active(pg_engine):
    setup = _session(pg_engine)
    o = _make_order(setup)
    w = _make_worker(setup)
    setup.commit()
    order_id, worker_id = o.id, w.id
    setup.close()

    errors: list = []
    start = threading.Event()

    def _worker():
        s = _session(pg_engine)
        start.wait()
        try:
            assign_worker(s, order_id=order_id, worker_id=worker_id)
            s.commit()
        except Exception as exc:  # noqa: BLE001 — 스레드 예외 수집(삼키지 않고 기록)
            s.rollback()
            errors.append(exc)
        finally:
            s.close()

    threads = [threading.Thread(target=_worker) for _ in range(2)]
    for t in threads:
        t.start()
    start.set()
    for t in threads:
        t.join()

    check = _session(pg_engine)
    try:
        n = (
            check.query(OrderInstallationAssignment)
            .filter(
                OrderInstallationAssignment.order_id == order_id,
                OrderInstallationAssignment.status == 'ACTIVE',
            )
            .count()
        )
        assert n == 1  # FOR UPDATE 직렬화 → 정확히 하나만 active.
        # 한 스레드는 깨끗한 도메인 오류(또는 partial unique backstop)로 거부됐다.
        assert len(errors) == 1
        assert isinstance(errors[0], (WorkerAlreadyAssignedError, IntegrityError))
        # cleanup(공유 pg_engine 오염 방지).
        check.query(OrderInstallationAssignment).filter(
            OrderInstallationAssignment.order_id == order_id).delete()
        check.query(Order).filter(Order.id == order_id).delete()
        check.query(InstallationWorker).filter(
            InstallationWorker.id == worker_id).delete()
        check.commit()
    finally:
        check.close()


# --------------------------------------------------------------------------- #
# 6. display projection (활성 worker 만·정렬)
# --------------------------------------------------------------------------- #
def test_list_active_workers_projection_sorted(pg_session):
    pfx = f"ZPROJ-{_suffix()}-"
    wb = create_worker(pg_session, external_worker_id=f"{pfx}B", display_name=f"{pfx}b")
    wa = create_worker(pg_session, external_worker_id=f"{pfx}A", display_name=f"{pfx}a")
    wc = create_worker(pg_session, external_worker_id=f"{pfx}C", display_name=f"{pfx}c")
    deactivate_worker(pg_session, wc.id)

    projected = [p for p in list_active_workers(pg_session)
                 if p["display_name"].startswith(pfx)]
    names = [p["display_name"] for p in projected]
    assert names == sorted(names)  # display_name asc.
    ids = {p["id"] for p in projected}
    assert wa.id in ids and wb.id in ids
    assert wc.id not in ids  # 비활성 제외.
    # projection 은 내부 상태 컬럼(is_active/created_at)을 노출하지 않는다.
    assert set(projected[0].keys()) == {
        "id", "external_worker_id", "display_name", "phone", "user_id"}


# --------------------------------------------------------------------------- #
# 7. free-name backfill (audit 분류 + 명시 apply; 자동 승격 0)
# --------------------------------------------------------------------------- #
def test_backfill_audit_and_apply(pg_session):
    w = _make_worker(pg_session, name="박기사")
    o1 = _make_order(pg_session)
    o2 = _make_order(pg_session)
    # 기존 free-name 데이터(구조: shipment.construction_workers).
    o1.structured_data = {"shipment": {"construction_workers": ["박기사", "외주철수"]}}
    o2.structured_data = {"shipment": {"construction_workers": ["박기사"]}}
    pg_session.flush()

    audit = audit_free_names(pg_session)
    # 매치: '박기사' → worker.id. unmatched: '외주철수'(마스터 없음).
    assert audit.matched.get("박기사") == w.id
    assert "외주철수" in audit.unmatched
    assert "박기사" not in audit.unmatched  # matched 는 unmatched 에 없다.
    # audit 는 아무 배정도 만들지 않는다(자동 승격 0).
    assert active_worker_ids(pg_session, o1.id) == []

    # 명시 apply: 사람이 검토한 (order, worker) 만 배정.
    created = apply_backfill(pg_session, [(o1.id, w.id), (o2.id, w.id)])
    assert created == 2
    assert active_worker_ids(pg_session, o1.id) == [w.id]
    assert active_worker_ids(pg_session, o2.id) == [w.id]
    # idempotent: 재적용은 0 신규.
    assert apply_backfill(pg_session, [(o1.id, w.id)]) == 0


def test_backfill_noop_when_no_free_name_data(pg_session):
    _make_order(pg_session)  # structured_data 없음.
    audit = audit_free_names(pg_session)
    assert audit.matched == {} and audit.unmatched == []
    assert apply_backfill(pg_session, []) == 0


# --------------------------------------------------------------------------- #
# 8. auth 무영향 (crew 배정이 배정 authorization SSOT 에 영향 0)
# --------------------------------------------------------------------------- #
def test_crew_assignment_has_zero_auth_effect(pg_session):
    o = _make_order(pg_session)
    w = _make_worker(pg_session)
    assign_worker(pg_session, order_id=o.id, worker_id=w.id)
    # crew 배정은 order_assignments(ASSIGNMENT-00 auth SSOT) 를 만들지 않는다.
    for domain in ("SALES", "DRAWING", "CONSTRUCTION"):
        assert active_assignee_ids(pg_session, o.id, domain) == []
