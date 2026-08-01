"""ASSIGNMENT-00 PostgreSQL 계약 테스트 (PGTEST-00 lane).

order_assignments 배정 정본의 partial unique(active 중복·SALES 1-owner·released 재배정),
CLAIM/SET/BATCH/RELEASE command mechanics, batch all-or-none 동시성, legacy 이름
audit/backfill(자동 승격 0)을 실 PostgreSQL 다중 커밋 세션으로 검증한다.

``FOMS_TEST_DATABASE_URL`` 미설정이면 lane 자체가 skip 된다(conftest). 커밋 파일에는
비밀번호를 넣지 않는다(env 로 주입). service 는 아직 route/AUTH 에 배선되지 않았다
(ASSIGNMENT-00 경계) — 이 테스트가 AUTH-01 이 의존할 계약을 정본으로 고정한다.
"""
from __future__ import annotations

import threading
import time

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from foms.services.orders.assignment import (
    AssignmentNotActiveError,
    AssignmentValidationError,
    ClaimConflictError,
    active_assignee_ids,
    batch_set_drawing_assignees,
    can_release_assignment,
    claim_drawing,
    release_assignment,
    resolve_assignee_ids,
    set_construction_assignees,
    set_drawing_assignees,
    set_sales_assignee,
)
from foms.services.orders.assignment_backfill import (
    MULTIPLE_MATCH,
    NO_MATCH,
    apply_safe_backfill,
    audit_legacy_names,
    to_manual_csv,
)
from foms.services.orders.revision import (
    OrderNotFoundError,
    PreconditionRequiredError,
    RevisionConflictError,
)
from models import Order, OrderAssignment, OrderEvent, User

_H = "a" * 64  # sha256-hex placeholder
_SEQ = [0]


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def _session(pg_engine):
    return sessionmaker(bind=pg_engine)()


def _uid_suffix() -> str:
    _SEQ[0] += 1
    return f"{_SEQ[0]}_{int(time.time() * 1000) % 1000000}"


def _make_user(session, *, name=None, role="STAFF", team=None, is_active=True):
    sfx = _uid_suffix()
    u = User(
        username=f"asg_{sfx}",
        password="pw-not-committed",
        name=name if name is not None else f"작업자_{sfx}",
        role=role,
        team=team,
        is_active=is_active,
    )
    session.add(u)
    session.commit()
    return u


def _make_order(session):
    o = Order(
        received_date="2026-07-24",
        customer_name="홍길동",
        phone="010-0000-0000",
        address="서울",
        product="침대",
    )
    session.add(o)
    session.commit()
    return o


def _active(session, order_id, domain):
    return (
        session.query(OrderAssignment)
        .filter_by(order_id=order_id, domain=domain, active=True)
        .all()
    )


def _events(session, order_id, event_type):
    return (
        session.query(OrderEvent)
        .filter_by(order_id=order_id, event_type=event_type)
        .count()
    )


# --------------------------------------------------------------------------- #
# 1. partial unique (DB 제약)
# --------------------------------------------------------------------------- #
def test_active_duplicate_rejected(pg_engine):
    s = _session(pg_engine)
    try:
        u = _make_user(s)
        o = _make_order(s)
        s.add(OrderAssignment(order_id=o.id, domain="DRAWING", user_id=u.id,
                              source="SELF_CLAIM", active=True, assigned_by_user_id=u.id,
                              assigned_at=_now()))
        s.commit()
        s.add(OrderAssignment(order_id=o.id, domain="DRAWING", user_id=u.id,
                              source="TEAM_REPLACE", active=True, assigned_by_user_id=u.id,
                              assigned_at=_now()))
        with pytest.raises(IntegrityError):
            s.commit()
        s.rollback()
    finally:
        s.close()


def test_sales_single_owner_enforced(pg_engine):
    s = _session(pg_engine)
    try:
        u1 = _make_user(s)
        u2 = _make_user(s)
        o = _make_order(s)
        s.add(OrderAssignment(order_id=o.id, domain="SALES", user_id=u1.id,
                              source="INITIAL_OWNER", active=True, assigned_by_user_id=u1.id,
                              assigned_at=_now()))
        s.commit()
        s.add(OrderAssignment(order_id=o.id, domain="SALES", user_id=u2.id,
                              source="TEAM_REPLACE", active=True, assigned_by_user_id=u1.id,
                              assigned_at=_now()))
        with pytest.raises(IntegrityError):
            s.commit()
        s.rollback()
    finally:
        s.close()


def test_released_row_allows_reassignment(pg_engine):
    s = _session(pg_engine)
    try:
        u = _make_user(s)
        o = _make_order(s)
        first = OrderAssignment(order_id=o.id, domain="DRAWING", user_id=u.id,
                                source="SELF_CLAIM", active=True, assigned_by_user_id=u.id,
                                assigned_at=_now())
        s.add(first)
        s.commit()
        first.active = False
        first.released_at = _now()
        first.released_by_user_id = u.id
        first.release_reason = "done"
        s.commit()
        # 같은 (order,domain,user) 재배정 — partial unique 는 active 만 세므로 허용.
        s.add(OrderAssignment(order_id=o.id, domain="DRAWING", user_id=u.id,
                              source="TEAM_REPLACE", active=True, assigned_by_user_id=u.id,
                              assigned_at=_now()))
        s.commit()
        assert len(_active(s, o.id, "DRAWING")) == 1
    finally:
        s.close()


# --------------------------------------------------------------------------- #
# 2. CLAIM_DRAWING
# --------------------------------------------------------------------------- #
def test_claim_drawing_and_event(pg_engine):
    s = _session(pg_engine)
    try:
        actor = _make_user(s, team="DRAWING")
        o = _make_order(s)
        res = claim_drawing(s, actor_user_id=actor.id, order_id=o.id,
                            scope_hash=_H, request_hash=_H)
        s.commit()
        assert res.replayed is False
        rows = _active(s, o.id, "DRAWING")
        assert [r.user_id for r in rows] == [actor.id]
        assert rows[0].source == "SELF_CLAIM"
        assert _events(s, o.id, "DRAWING_ASSIGNED") == 1
        assert active_assignee_ids(s, o.id, "DRAWING") == [actor.id]
    finally:
        s.close()


def test_claim_replay_same_key_and_conflict_new_key(pg_engine):
    s = _session(pg_engine)
    try:
        actor = _make_user(s, team="DRAWING")
        other = _make_user(s, team="DRAWING")
        o = _make_order(s)
        key = f"claim-{_uid_suffix()}"
        claim_drawing(s, actor_user_id=actor.id, order_id=o.id, idempotency_key=key,
                      scope_hash=_H, request_hash=_H)
        s.commit()
        # 같은 key replay → 저장 응답, 새 row 0.
        r2 = claim_drawing(s, actor_user_id=actor.id, order_id=o.id, idempotency_key=key,
                           scope_hash=_H, request_hash=_H)
        s.commit()
        assert r2.replayed is True
        assert len(_active(s, o.id, "DRAWING")) == 1
        # 새 key 로 이미 claim 된 주문 재claim → 409(active != 0).
        with pytest.raises(ClaimConflictError):
            claim_drawing(s, actor_user_id=other.id, order_id=o.id,
                          idempotency_key=f"claim-{_uid_suffix()}",
                          scope_hash=_H, request_hash=_H)
        s.rollback()
        assert len(_active(s, o.id, "DRAWING")) == 1
    finally:
        s.close()


# --------------------------------------------------------------------------- #
# 3. SET / replace
# --------------------------------------------------------------------------- #
def test_set_drawing_replace_release_and_add_one_tx(pg_engine):
    s = _session(pg_engine)
    try:
        actor = _make_user(s, team="DRAWING")
        a = _make_user(s, team="DRAWING")
        b = _make_user(s, team="DRAWING")
        c = _make_user(s, team="DRAWING")
        o = _make_order(s)
        r1 = set_drawing_assignees(s, actor_user_id=actor.id, order_id=o.id,
                                   user_ids=[a.id, b.id], scope_hash=_H, request_hash=_H)
        s.commit()
        v1 = r1.body["resources"][0]["resulting_version"]
        assert active_assignee_ids(s, o.id, "DRAWING") == sorted([a.id, b.id])

        # [a,b] -> [b,c]: a release, b 유지, c 추가 — 한 tx, event 1(추가분).
        set_drawing_assignees(s, actor_user_id=actor.id, order_id=o.id,
                              user_ids=[b.id, c.id], expected_version=v1,
                              scope_hash=_H, request_hash=_H)
        s.commit()
        assert active_assignee_ids(s, o.id, "DRAWING") == sorted([b.id, c.id])
        released = (s.query(OrderAssignment)
                    .filter_by(order_id=o.id, domain="DRAWING", user_id=a.id, active=False)
                    .one())
        assert released.released_by_user_id == actor.id
        assert _events(s, o.id, "DRAWING_ASSIGNMENTS_REPLACED") == 2  # 최초 + replace
    finally:
        s.close()


def test_set_drawing_count_bounds(pg_engine):
    s = _session(pg_engine)
    try:
        actor = _make_user(s, team="DRAWING")
        o = _make_order(s)
        with pytest.raises(AssignmentValidationError):
            set_drawing_assignees(s, actor_user_id=actor.id, order_id=o.id, user_ids=[],
                                  scope_hash=_H, request_hash=_H)
        s.rollback()
        # 21명 초과 거부.
        ids = list(range(1, 22))
        with pytest.raises(AssignmentValidationError):
            set_drawing_assignees(s, actor_user_id=actor.id, order_id=o.id, user_ids=ids,
                                  scope_hash=_H, request_hash=_H)
        s.rollback()
    finally:
        s.close()


def test_resolve_rejects_inactive_and_duplicates(pg_engine):
    s = _session(pg_engine)
    try:
        active_u = _make_user(s)
        inactive_u = _make_user(s, is_active=False)
        with pytest.raises(AssignmentValidationError):
            resolve_assignee_ids(s, [active_u.id, inactive_u.id])
        with pytest.raises(AssignmentValidationError):
            resolve_assignee_ids(s, [active_u.id, active_u.id])
        assert resolve_assignee_ids(s, [active_u.id]) == [active_u.id]
    finally:
        s.close()


def test_set_sales_initial_then_replace_requires_reason(pg_engine):
    s = _session(pg_engine)
    try:
        actor = _make_user(s, team="SALES")
        owner1 = _make_user(s, team="SALES")
        owner2 = _make_user(s, team="SALES")
        o = _make_order(s)
        # 최초 지정 — reason 불필요.
        r1 = set_sales_assignee(s, actor_user_id=actor.id, order_id=o.id, user_id=owner1.id,
                                scope_hash=_H, request_hash=_H)
        s.commit()
        assert active_assignee_ids(s, o.id, "SALES") == [owner1.id]
        v1 = r1.body["resources"][0]["resulting_version"]
        # 다른 owner 로 교체 — reason 없으면 422.
        with pytest.raises(AssignmentValidationError):
            set_sales_assignee(s, actor_user_id=actor.id, order_id=o.id, user_id=owner2.id,
                               expected_version=v1, scope_hash=_H, request_hash=_H)
        s.rollback()
        set_sales_assignee(s, actor_user_id=actor.id, order_id=o.id, user_id=owner2.id,
                           reason="영업 담당 인수인계", expected_version=v1,
                           scope_hash=_H, request_hash=_H)
        s.commit()
        assert active_assignee_ids(s, o.id, "SALES") == [owner2.id]
    finally:
        s.close()


def test_set_construction_assignees(pg_engine):
    s = _session(pg_engine)
    try:
        actor = _make_user(s, role="MANAGER")
        w1 = _make_user(s, team="CONSTRUCTION")
        w2 = _make_user(s, team="CONSTRUCTION")
        o = _make_order(s)
        set_construction_assignees(s, actor_user_id=actor.id, order_id=o.id,
                                   user_ids=[w1.id, w2.id], scope_hash=_H, request_hash=_H)
        s.commit()
        assert active_assignee_ids(s, o.id, "CONSTRUCTION") == sorted([w1.id, w2.id])
        assert _events(s, o.id, "CONSTRUCTION_ASSIGNMENTS_REPLACED") == 1
    finally:
        s.close()


# --------------------------------------------------------------------------- #
# 4. BATCH all-or-none
# --------------------------------------------------------------------------- #
def test_batch_set_drawing_all_success(pg_engine):
    s = _session(pg_engine)
    try:
        actor = _make_user(s, team="DRAWING")
        d = _make_user(s, team="DRAWING")
        orders = [_make_order(s) for _ in range(3)]
        res = batch_set_drawing_assignees(
            s, actor_user_id=actor.id,
            orders=[{"order_id": o.id, "mutation_version": 1} for o in orders],
            user_ids=[d.id], scope_hash=_H, request_hash=_H,
        )
        s.commit()
        assert len(res.body["resources"]) == 3
        for o in orders:
            assert active_assignee_ids(s, o.id, "DRAWING") == [d.id]
    finally:
        s.close()


def test_batch_stale_version_aborts_whole(pg_engine):
    s = _session(pg_engine)
    try:
        actor = _make_user(s, team="DRAWING")
        d = _make_user(s, team="DRAWING")
        o1, o2, o3 = (_make_order(s) for _ in range(3))
        with pytest.raises(RevisionConflictError):
            batch_set_drawing_assignees(
                s, actor_user_id=actor.id,
                orders=[{"order_id": o1.id, "mutation_version": 1},
                        {"order_id": o2.id, "mutation_version": 999},  # stale
                        {"order_id": o3.id, "mutation_version": 1}],
                user_ids=[d.id], scope_hash=_H, request_hash=_H,
            )
        s.rollback()
        # 전체 변화 0: 어떤 주문에도 배정/이벤트/버전 변경 없음.
        for o in (o1, o2, o3):
            assert _active(s, o.id, "DRAWING") == []
            assert _events(s, o.id, "DRAWING_ASSIGNMENTS_REPLACED") == 0
            s.refresh(o)
            assert o.mutation_version == 1
    finally:
        s.close()


def test_batch_missing_order_aborts_whole(pg_engine):
    s = _session(pg_engine)
    try:
        actor = _make_user(s, team="DRAWING")
        d = _make_user(s, team="DRAWING")
        o1 = _make_order(s)
        with pytest.raises(OrderNotFoundError):
            batch_set_drawing_assignees(
                s, actor_user_id=actor.id,
                orders=[{"order_id": o1.id, "mutation_version": 1},
                        {"order_id": 999_000_111, "mutation_version": 1}],
                user_ids=[d.id], scope_hash=_H, request_hash=_H,
            )
        s.rollback()
        assert _active(s, o1.id, "DRAWING") == []
    finally:
        s.close()


def test_batch_missing_version_precondition(pg_engine):
    s = _session(pg_engine)
    try:
        actor = _make_user(s, team="DRAWING")
        d = _make_user(s, team="DRAWING")
        o1, o2 = _make_order(s), _make_order(s)
        with pytest.raises(PreconditionRequiredError):
            batch_set_drawing_assignees(
                s, actor_user_id=actor.id,
                orders=[{"order_id": o1.id, "mutation_version": 1},
                        {"order_id": o2.id}],  # version 누락 → 428
                user_ids=[d.id], scope_hash=_H, request_hash=_H,
            )
        s.rollback()
        assert _active(s, o1.id, "DRAWING") == []
        assert _active(s, o2.id, "DRAWING") == []
    finally:
        s.close()


def test_batch_sorted_lock_no_deadlock(pg_engine):
    """겹치는 주문을 역순 입력으로 동시 batch — ID 정렬 lock 이라 deadlock 0.

    naive(입력 순서) lock 이면 A[o0,o1]·B[o1,o0] 가 교차 대기 → PostgreSQL deadlock.
    REV-00 이 ID 순으로 lock 하므로 순환 대기가 없어 둘 다 정상 종료하고, 같은 expected
    version 이라 하나는 성공·하나는 REVISION_CONFLICT 로 직렬화된다(deadlock 예외 0).
    """
    setup = _session(pg_engine)
    try:
        actor = _make_user(setup, team="DRAWING")
        d1 = _make_user(setup, team="DRAWING")
        d2 = _make_user(setup, team="DRAWING")
        o1, o2 = _make_order(setup), _make_order(setup)
        ids = sorted([o1.id, o2.id])
        actor_id, d1_id, d2_id = actor.id, d1.id, d2.id
    finally:
        setup.close()

    outcome = {}

    def _run(tag, order_seq, drawer):
        sess = _session(pg_engine)
        try:
            batch_set_drawing_assignees(
                sess, actor_user_id=actor_id,
                orders=[{"order_id": oid, "mutation_version": 1} for oid in order_seq],
                user_ids=[drawer], scope_hash=_H, request_hash=_H,
            )
            sess.commit()
            outcome[tag] = "ok"
        except RevisionConflictError:
            sess.rollback()
            outcome[tag] = "conflict"
        finally:
            sess.close()

    # A: [id0,id1], B: [id1,id0] — naive 순서면 교차 lock deadlock.
    ta = threading.Thread(target=_run, args=("A", ids, d1_id))
    tb = threading.Thread(target=_run, args=("B", list(reversed(ids)), d2_id))
    ta.start(); tb.start(); ta.join(10.0); tb.join(10.0)
    # 두 스레드 모두 종료(deadlock 예외/hang 0) + 정확히 하나 성공·하나 conflict(직렬화).
    assert sorted(outcome.values()) == ["conflict", "ok"], outcome
    check = _session(pg_engine)
    try:
        for oid in ids:  # 이긴 쪽 결과만 일관되게 남음(부분 결과 0).
            assert len(active_assignee_ids(check, oid, "DRAWING")) == 1
    finally:
        check.close()


# --------------------------------------------------------------------------- #
# 5. RELEASE
# --------------------------------------------------------------------------- #
def test_release_self_claim_and_history(pg_engine):
    s = _session(pg_engine)
    try:
        actor = _make_user(s, team="DRAWING")
        o = _make_order(s)
        claim_drawing(s, actor_user_id=actor.id, order_id=o.id, scope_hash=_H, request_hash=_H)
        s.commit()
        release_assignment(s, actor_user_id=actor.id, order_id=o.id, domain="DRAWING",
                           user_id=actor.id, reason="이관 전 해제", scope_hash=_H, request_hash=_H)
        s.commit()
        assert _active(s, o.id, "DRAWING") == []
        row = (s.query(OrderAssignment)
               .filter_by(order_id=o.id, domain="DRAWING", user_id=actor.id).one())
        assert row.active is False and row.release_reason == "이관 전 해제"
        assert row.released_by_user_id == actor.id
        assert _events(s, o.id, "ASSIGNMENT_RELEASED") == 1
    finally:
        s.close()


def test_release_missing_is_409(pg_engine):
    s = _session(pg_engine)
    try:
        actor = _make_user(s, team="DRAWING")
        o = _make_order(s)
        with pytest.raises(AssignmentNotActiveError):
            release_assignment(s, actor_user_id=actor.id, order_id=o.id, domain="DRAWING",
                               user_id=actor.id, reason="x", scope_hash=_H, request_hash=_H)
        s.rollback()
    finally:
        s.close()


def test_release_reason_required(pg_engine):
    s = _session(pg_engine)
    try:
        actor = _make_user(s, team="DRAWING")
        o = _make_order(s)
        claim_drawing(s, actor_user_id=actor.id, order_id=o.id, scope_hash=_H, request_hash=_H)
        s.commit()
        with pytest.raises(AssignmentValidationError):
            release_assignment(s, actor_user_id=actor.id, order_id=o.id, domain="DRAWING",
                               user_id=actor.id, reason="   ", scope_hash=_H, request_hash=_H)
        s.rollback()
    finally:
        s.close()


def test_release_works_when_target_user_inactive(pg_engine):
    s = _session(pg_engine)
    try:
        admin = _make_user(s, role="ADMIN")
        target = _make_user(s, team="CONSTRUCTION")
        o = _make_order(s)
        set_construction_assignees(s, actor_user_id=admin.id, order_id=o.id,
                                   user_ids=[target.id], scope_hash=_H, request_hash=_H)
        s.commit()
        target.is_active = False  # 대상 User 비활성화
        s.commit()
        # active 배정 row 는 여전히 release 가능(user 활성 여부가 아니라 배정 row 를 봄).
        release_assignment(s, actor_user_id=admin.id, order_id=o.id, domain="CONSTRUCTION",
                           user_id=target.id, reason="퇴사 정리", scope_hash=_H, request_hash=_H)
        s.commit()
        assert _active(s, o.id, "CONSTRUCTION") == []
    finally:
        s.close()


def test_can_release_predicate_matrix(pg_engine):
    """ID-row 기반 release 자격 판정(AUTH-01 이 enforce; JSONB 이름 미사용)."""
    self_claim = OrderAssignment(order_id=1, domain="DRAWING", user_id=10,
                                 source="SELF_CLAIM", active=True, assigned_by_user_id=10)
    team_row = OrderAssignment(order_id=1, domain="DRAWING", user_id=10,
                               source="TEAM_REPLACE", active=True, assigned_by_user_id=99)
    # SELF_CLAIM: owner 만(또는 ADMIN/MANAGER).
    assert can_release_assignment(self_claim, actor_user_id=10, actor_role="STAFF", actor_team="DRAWING")
    assert not can_release_assignment(self_claim, actor_user_id=11, actor_role="STAFF", actor_team="DRAWING")
    assert can_release_assignment(self_claim, actor_user_id=11, actor_role="ADMIN", actor_team=None)
    # TEAM_REPLACE drawing: DRAWING team STAFF 만, 타 팀 STAFF 불가, MANAGER 가능.
    assert can_release_assignment(team_row, actor_user_id=10, actor_role="STAFF", actor_team="DRAWING")
    assert not can_release_assignment(team_row, actor_user_id=10, actor_role="STAFF", actor_team="CS")
    assert can_release_assignment(team_row, actor_user_id=1, actor_role="MANAGER", actor_team=None)


# --------------------------------------------------------------------------- #
# 6. legacy 이름 backfill (자동 승격 0)
# --------------------------------------------------------------------------- #
def test_legacy_audit_and_safe_backfill(pg_engine):
    s = _session(pg_engine)
    try:
        actor = _make_user(s, role="ADMIN")
        sfx = _uid_suffix()
        solo = f"김철수_{sfx}"
        dup = f"이영희_{sfx}"
        ghost = f"박외주_{sfx}"
        solo_u = _make_user(s, name=solo, team="DRAWING")
        _make_user(s, name=dup, team="DRAWING")
        _make_user(s, name=dup, team="DRAWING")  # 동명이인 → MULTIPLE_MATCH
        o = _make_order(s)

        audit = audit_legacy_names(s, [solo, dup, ghost, "  ", solo])
        assert audit.safe == {solo: solo_u.id}
        assert audit.ambiguous == {dup: MULTIPLE_MATCH, ghost: NO_MATCH}

        csv_text = to_manual_csv(audit)
        assert dup in csv_text and ghost in csv_text and solo not in csv_text

        # safe 명시 승인 → source=BACKFILL 배정 1건.
        apply_safe_backfill(s, order_id=o.id, domain="DRAWING", audit=audit,
                            approved_names=[solo], assigned_by_user_id=actor.id)
        s.commit()
        rows = _active(s, o.id, "DRAWING")
        assert [r.user_id for r in rows] == [solo_u.id]
        assert rows[0].source == "BACKFILL"

        # ambiguous / non-safe 는 승인돼도 거부(자동 승격 0).
        with pytest.raises(AssignmentValidationError):
            apply_safe_backfill(s, order_id=o.id, domain="DRAWING", audit=audit,
                                approved_names=[dup], assigned_by_user_id=actor.id)
        s.rollback()
        with pytest.raises(AssignmentValidationError):
            apply_safe_backfill(s, order_id=o.id, domain="DRAWING", audit=audit,
                                approved_names=[ghost], assigned_by_user_id=actor.id)
        s.rollback()
    finally:
        s.close()


# --------------------------------------------------------------------------- #
# schema: partial 인덱스 존재
# --------------------------------------------------------------------------- #
def test_partial_indexes_exist(pg_engine):
    with pg_engine.connect() as conn:
        rows = conn.execute(text(
            "SELECT indexname FROM pg_indexes WHERE tablename = 'order_assignments'"
        )).fetchall()
    names = {r[0] for r in rows}
    assert "uq_order_assignment_active" in names, names
    assert "uq_order_assignment_sales_owner" in names, names
    assert "ix_order_assignment_active_lookup" in names, names


def _now():
    from foms.services.datetime_kst import now_utc_naive
    return now_utc_naive()
