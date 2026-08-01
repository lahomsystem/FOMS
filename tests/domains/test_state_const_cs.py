"""시공 attempt 전이·CS 완료 canonical 계약 (STATE-CONST-CS-01, SSOT §2.3·§5.2).

construction start/complete/rework + cs/complete 를 OrderConstructionAttempt 상태기계로
재배선한 뒤 다음을 고정한다(SQLite domain lane — partial-unique current 강제·실 FOR UPDATE
경합은 PGTEST-00 lane test_state_const_cs.py):

* 시공 시작 = 새 UUID attempt(IN_PROGRESS·is_current)·evidence 격리(이전 attempt 혼입 0).
* 시공 완료 = attempt IN_PROGRESS→READY + main CONSTRUCTION→**CS**(direct COMPLETED 금지).
* 재작업 = 현재 attempt REWORKED 봉인 + 다음 시작이 **새 attempt append**(과거 immutable·override 0).
* CS 완료 = CS quest + hold + AS gate 통과 시에만 COMPLETED, generic upload count 로 판정 0.
"""

from __future__ import annotations

from datetime import date

from werkzeug.security import generate_password_hash

from db import db_session
from models import (
    Order,
    OrderAttachment,
    OrderConstructionAttempt,
    OrderEvent,
    OrderMutationReceipt,
    User,
)
from foms.services.orders.order_transition_service import (
    COMMAND_REGISTRY,
    InvalidTransitionError,
    transition_order,
)


def _make_user(username: str, *, role: str = "ADMIN", team: str | None = None) -> User:
    user = User(username=username, password=generate_password_hash("pw"), role=role,
                team=team, name=f"{username} 이름", is_active=True)
    db_session.add(user)
    db_session.commit()
    return user


def _login(client, user: User) -> None:
    with client.session_transaction() as sess:
        sess["user_id"] = user.id
        sess["username"] = user.username
        sess["role"] = user.role


def _make_order(stage_code: str, *, structured_data: dict | None = None) -> Order:
    sd = {"workflow": {"stage": stage_code}}
    if structured_data:
        sd = {**sd, **structured_data}
        sd.setdefault("workflow", {})["stage"] = stage_code
    order = Order(received_date=date.today().isoformat(), customer_name="전이 고객",
                  phone="010-0000-0000", address="Seoul", product="붙박이장", status=stage_code,
                  manager_name="Bob", is_erp_order=True, structured_data=sd, erp_stage_code=stage_code)
    db_session.add(order)
    db_session.commit()
    return order


def _attempts(order_id: int) -> list[OrderConstructionAttempt]:
    return (
        db_session.query(OrderConstructionAttempt)
        .filter(OrderConstructionAttempt.order_id == order_id)
        .order_by(OrderConstructionAttempt.created_at.asc())
        .all()
    )


def _current(order_id: int) -> OrderConstructionAttempt | None:
    return (
        db_session.query(OrderConstructionAttempt)
        .filter(OrderConstructionAttempt.order_id == order_id,
                OrderConstructionAttempt.is_current.is_(True))
        .first()
    )


def _cs_quest(approved: bool) -> dict:
    return {"stage": "CS", "status": "OPEN", "required_approvals": ["CS"],
            "team_approvals": {"CS": {"approved": approved, "approved_by": None, "approved_at": None}}}


def _active_as_cycle() -> dict:
    """current RECEIVED AS cycle(진행 중 AS) — read_as_status → RECEIVED."""
    return {"as_lifecycle": {"current_cycle_id": "c1", "cycles": [{"cycle_id": "c1", "transitions": []}]}}


# --------------------------------------------------------------------------- #
# 1. 시공 시작 = 새 UUID attempt(IN_PROGRESS·is_current)·evidence 격리
# --------------------------------------------------------------------------- #
def test_start_mints_fresh_uuid_in_progress_attempt(client):
    """CONSTRUCTION 에서 start → 새 UUID attempt IN_PROGRESS·is_current, 빈 evidence."""
    _login(client, _make_user("cc_start", role="STAFF", team="CONSTRUCTION"))
    oid = _make_order("CONSTRUCTION").id

    resp = client.post(f"/api/orders/{oid}/construction/start", json={})
    assert resp.status_code == 200, resp.get_data(as_text=True)
    body = resp.get_json()
    assert body["success"] is True and body["attempt_id"]

    db_session.expire_all()
    attempt = _current(oid)
    assert attempt is not None
    assert attempt.status == "IN_PROGRESS" and attempt.is_current is True
    assert attempt.id == body["attempt_id"] and len(attempt.id) == 36  # UUID
    assert attempt.evidence == {"before": [], "after": []}
    # REV-00: version bump + CONSTRUCTION_STARTED event.
    assert db_session.get(Order, oid).mutation_version == 2
    assert db_session.query(OrderEvent).filter_by(order_id=oid, event_type="CONSTRUCTION_STARTED").count() == 1


def test_start_rejected_when_attempt_already_open(client):
    """이미 열린 attempt 가 있으면 두 번째 start 409 ALREADY_STARTED(override 금지·중복 발급 0)."""
    _login(client, _make_user("cc_start2", role="STAFF", team="CONSTRUCTION"))
    oid = _make_order("CONSTRUCTION").id
    assert client.post(f"/api/orders/{oid}/construction/start", json={}).status_code == 200

    resp = client.post(f"/api/orders/{oid}/construction/start", json={})
    assert resp.status_code == 409 and resp.get_json()["code"] == "ALREADY_STARTED"

    db_session.expire_all()
    assert len(_attempts(oid)) == 1  # 중복 발급 0


def test_start_rejected_outside_construction_stage(client):
    """시공 대기(CONSTRUCTION) 아님 → start 409 INVALID_STAGE, attempt 미발급."""
    _login(client, _make_user("cc_start3", role="STAFF", team="CONSTRUCTION"))
    oid = _make_order("PRODUCTION").id
    resp = client.post(f"/api/orders/{oid}/construction/start", json={})
    assert resp.status_code == 409 and resp.get_json()["code"] == "INVALID_STAGE"
    db_session.expire_all()
    assert _attempts(oid) == []


# --------------------------------------------------------------------------- #
# 2. 시공 완료 = attempt IN_PROGRESS→READY + main CONSTRUCTION→CS(direct COMPLETED 금지)
# --------------------------------------------------------------------------- #
def test_complete_advances_to_cs_and_attempt_ready(client):
    """시공 완료 → main CS(NOT COMPLETED), current attempt READY 봉인."""
    _login(client, _make_user("cc_done", role="STAFF", team="CONSTRUCTION"))
    oid = _make_order("CONSTRUCTION").id
    assert client.post(f"/api/orders/{oid}/construction/start", json={}).status_code == 200

    resp = client.post(f"/api/orders/{oid}/construction/complete", json={"completion_note": "끝"})
    assert resp.status_code == 200 and resp.get_json()["new_status"] == "CS"

    db_session.expire_all()
    saved = db_session.get(Order, oid)
    assert saved.erp_stage_code == "CS" and saved.status == "CS"  # direct COMPLETED 금지
    assert saved.structured_data["workflow"]["stage"] == "CS"
    attempt = _current(oid)
    assert attempt is not None and attempt.status == "READY"
    assert db_session.query(OrderEvent).filter_by(order_id=oid, event_type="CONSTRUCTION_COMPLETED").count() == 1
    assert db_session.query(OrderMutationReceipt).filter_by(policy_id="STATE_CONSTRUCTION_COMPLETE").count() == 1


def test_direct_construction_to_completed_is_structurally_rejected(client):
    """CONSTRUCTION_COMPLETE 는 CS 만 허용 — direct COMPLETED target 은 엔진이 거부."""
    assert COMMAND_REGISTRY["CONSTRUCTION_COMPLETE"].to_values == ("CS",)
    _login(client, _make_user("cc_direct", role="STAFF", team="CONSTRUCTION"))
    oid = _make_order("CONSTRUCTION").id
    try:
        transition_order(
            db_session, command_id="CONSTRUCTION_COMPLETE", order_id=oid, actor_user_id=1,
            expected_from="CONSTRUCTION", target_value="COMPLETED", scope_hash="h" * 64,
            request_hash="h" * 64,
        )
        assert False, "direct CONSTRUCTION→COMPLETED must be rejected"
    except InvalidTransitionError:
        db_session.rollback()
    db_session.expire_all()
    assert db_session.get(Order, oid).erp_stage_code == "CONSTRUCTION"  # 상태 불변


def test_complete_rejected_outside_construction_stage(client):
    """시공중 아님(CS 에서 재완료) → complete 409 INVALID_STAGE."""
    _login(client, _make_user("cc_done2", role="STAFF", team="CONSTRUCTION"))
    oid = _make_order("CS").id
    resp = client.post(f"/api/orders/{oid}/construction/complete", json={})
    assert resp.status_code == 409 and resp.get_json()["code"] == "INVALID_STAGE"


# --------------------------------------------------------------------------- #
# 3. 재작업 = 새 attempt append(과거 immutable·override 0)·evidence 격리
# --------------------------------------------------------------------------- #
def test_rework_seals_current_attempt_reworked_and_clears_current(client):
    """start→evidence→fail(site_issue): 현재 attempt REWORKED 봉인(evidence 스냅샷)·is_current 해제.

    새 attempt append(부분 unique 필요)는 PGTEST-00 lane(test_state_const_cs.py)에서 검증한다
    — SQLite 는 partial-unique(``WHERE is_current``)를 full unique 로 격하해 attempt 1개만 허용.
    """
    _login(client, _make_user("cc_rw", role="STAFF", team="CONSTRUCTION"))
    oid = _make_order("CONSTRUCTION").id
    assert client.post(f"/api/orders/{oid}/construction/start", json={}).status_code == 200

    a1 = OrderAttachment(order_id=oid, filename="a1.jpg", file_type="image", category="construction",
                         file_size=1, storage_key=f"orders/{oid}/a1.jpg")
    db_session.add(a1)
    db_session.commit()
    a1_id = a1.id  # 요청 후 detach 회피용 primitive 캡처
    assert client.post(f"/api/orders/{oid}/construction/evidence",
                       json={"kind": "after", "attachment_id": a1_id}).status_code == 200

    db_session.expire_all()
    first_id = _current(oid).id

    resp = client.post(f"/api/orders/{oid}/construction/fail",
                       json={"reason": "site_issue", "detail": "현장 재방문"})
    assert resp.status_code == 200 and resp.get_json()["new_status"] == "CONSTRUCTION"

    db_session.expire_all()
    reworked = db_session.get(OrderConstructionAttempt, first_id)
    assert reworked.status == "REWORKED" and reworked.is_current is False  # terminal·override 대상 아님
    assert reworked.fail_reason == "site_issue"
    assert reworked.evidence.get("after") == [a1_id]  # 봉인 스냅샷 보존(immutable)
    assert _current(oid) is None  # 열린 attempt 없음 → 다음 start 가 새 attempt append
    assert len(_attempts(oid)) == 1  # 과거 attempt 덮어쓰기 0
    assert db_session.query(OrderEvent).filter_by(order_id=oid, event_type="CONSTRUCTION_REWORKED").count() == 1


# --------------------------------------------------------------------------- #
# 4. CS 완료 = CS quest + hold + AS gate 통과 시에만 COMPLETED
# --------------------------------------------------------------------------- #
def test_cs_complete_succeeds_when_gates_clear(client):
    """CS quest 완료·hold 없음·AS 없음 → cs/complete 200, COMPLETED, current attempt COMPLETED 봉인."""
    _login(client, _make_user("cs_ok", role="STAFF", team="CS"))
    oid = _make_order("CS", structured_data={"quests": [_cs_quest(approved=True)]}).id
    ready = OrderConstructionAttempt(order_id=oid, status="READY", is_current=True,
                                     evidence={"before": [], "after": []})
    db_session.add(ready)
    db_session.commit()
    ready_id = ready.id  # 요청 후 detach 회피용 primitive 캡처

    resp = client.post(f"/api/orders/{oid}/cs/complete", json={})
    assert resp.status_code == 200 and resp.get_json()["new_status"] == "COMPLETED"

    db_session.expire_all()
    saved = db_session.get(Order, oid)
    assert saved.erp_stage_code == "COMPLETED" and saved.status == "COMPLETED"
    assert db_session.query(OrderEvent).filter_by(order_id=oid, event_type="CS_COMPLETED").count() == 1
    attempt = db_session.get(OrderConstructionAttempt, ready_id)
    assert attempt.status == "COMPLETED" and attempt.is_current is False


def test_cs_complete_blocked_when_cs_quest_incomplete(client):
    """CS quest 미완 → cs/complete 409 QUEST_INCOMPLETE, 전이·상태 불변."""
    _login(client, _make_user("cs_q", role="STAFF", team="CS"))
    oid = _make_order("CS", structured_data={"quests": [_cs_quest(approved=False)]}).id

    resp = client.post(f"/api/orders/{oid}/cs/complete", json={})
    assert resp.status_code == 409 and resp.get_json()["code"] == "QUEST_INCOMPLETE"

    db_session.expire_all()
    saved = db_session.get(Order, oid)
    assert saved.erp_stage_code == "CS" and saved.mutation_version == 1  # 전이·bump 0
    assert db_session.query(OrderEvent).filter_by(order_id=oid, event_type="CS_COMPLETED").count() == 0


def test_cs_complete_blocked_when_as_active(client):
    """진행 중 AS(RECEIVED) → cs/complete 409 AS_ACTIVE, 상태 불변."""
    _login(client, _make_user("cs_as", role="STAFF", team="CS"))
    oid = _make_order("CS", structured_data=_active_as_cycle()).id
    resp = client.post(f"/api/orders/{oid}/cs/complete", json={})
    assert resp.status_code == 409 and resp.get_json()["code"] == "AS_ACTIVE"
    db_session.expire_all()
    assert db_session.get(Order, oid).erp_stage_code == "CS"


def test_cs_complete_blocked_when_hold_active(client):
    """보류 active → cs/complete 409 HOLD_ACTIVE, 상태 불변."""
    _login(client, _make_user("cs_hold", role="STAFF", team="CS"))
    oid = _make_order("CS", structured_data={"workflow": {"hold": {"active": True, "reason": "대기"}}}).id
    resp = client.post(f"/api/orders/{oid}/cs/complete", json={})
    assert resp.status_code == 409 and resp.get_json()["code"] == "HOLD_ACTIVE"
    db_session.expire_all()
    assert db_session.get(Order, oid).erp_stage_code == "CS"


def test_cs_complete_not_gated_by_upload_count(client):
    """완료 판정은 quest gate — 첨부(upload) 0건이어도 quest 완료면 200(generic upload count 아님)."""
    _login(client, _make_user("cs_up1", role="STAFF", team="CS"))
    oid = _make_order("CS", structured_data={"quests": [_cs_quest(approved=True)]}).id
    # 첨부 0건.
    assert db_session.query(OrderAttachment).filter_by(order_id=oid).count() == 0
    assert client.post(f"/api/orders/{oid}/cs/complete", json={}).status_code == 200

    # 역: 첨부가 많아도 quest 미완이면 완료 불가(upload count 로 통과하지 않음).
    _login(client, _make_user("cs_up2", role="STAFF", team="CS"))
    oid2 = _make_order("CS", structured_data={"quests": [_cs_quest(approved=False)]}).id
    for i in range(3):
        db_session.add(OrderAttachment(order_id=oid2, filename=f"f{i}.jpg", file_type="image",
                                       category="construction", file_size=1,
                                       storage_key=f"orders/{oid2}/f{i}.jpg"))
    db_session.commit()
    r = client.post(f"/api/orders/{oid2}/cs/complete", json={})
    assert r.status_code == 409 and r.get_json()["code"] == "QUEST_INCOMPLETE"
