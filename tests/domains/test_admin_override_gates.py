"""ADMIN-OVERRIDE-01 — 업무 게이트를 관리자가 뚫는 길(그리고 못 뚫는 길).

게이트마다 두 갈래로 고정한다.

* **평소(음성 대조군)**: `admin_override` 없이 보내면 지금 그대로 막힌다(409/400 원문 동일).
* **관리자 강제 진행**: ADMIN 이 `admin_override: true` + 사유를 실으면 통과하고,
  주문 이력에 `ADMIN_OVERRIDE_USED` 1행이 남는다.

못 뚫는 것도 함께 못박는다 — 중복 발급(ALREADY_STARTED·이미 제작중)은 권한 문제가 아니라
잘못된 데이터이고, 비관리자의 `admin_override` 는 403 이며, 잠금 아래 `expected_from`
재확인은 관리자도 못 뚫는다(동시 편집을 조용히 덮지 않는다).
"""

from __future__ import annotations

import copy
from datetime import date

import pytest
from sqlalchemy.orm.attributes import flag_modified
from werkzeug.security import generate_password_hash

from db import db_session
from foms.services.orders.cs_complete_service import scope_hash, request_hash
from foms.services.orders.order_transition_service import (
    StageConflictError,
    transition_order,
)
from models import Order, OrderConstructionAttempt, OrderEvent, ProductionRun, User

_REASON = "고객 일정 때문에 관리자가 직접 진행"


def _make_user(username: str, *, role: str = "ADMIN", team: str = "PRODUCTION") -> User:
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
    sd: dict = {"workflow": {"stage": stage_code}}
    if structured_data:
        sd = {**sd, **structured_data}
        sd.setdefault("workflow", {})["stage"] = stage_code
    order = Order(received_date=date.today().isoformat(), customer_name="강제 진행 고객",
                  phone="010-0000-0000", address="Seoul", product="붙박이장", status=stage_code,
                  manager_name="Bob", is_erp_order=True, structured_data=sd,
                  erp_stage_code=stage_code)
    db_session.add(order)
    db_session.commit()
    return order


def _saved(order_id: int) -> Order:
    db_session.expire_all()
    return db_session.get(Order, order_id)


def _override_events(order_id: int) -> list[OrderEvent]:
    return (
        db_session.query(OrderEvent)
        .filter(OrderEvent.order_id == order_id,
                OrderEvent.event_type == "ADMIN_OVERRIDE_USED")
        .all()
    )


def _punch(extra: dict | None = None) -> dict:
    """관리자 강제 진행 본문(공통 모양)."""
    body = {"admin_override": True, "override_reason": _REASON}
    if extra:
        body.update(extra)
    return body


def _held(reason: str = "자재 지연") -> dict:
    """보류 중(production.hold.active) structured_data 조각."""
    return {"production": {"hold": {"active": True, "reason": reason}}}


def _open_production_quest() -> dict:
    """승인이 하나도 안 된 생산 quest(필수 팀 PRODUCTION)."""
    return {
        "stage": "PRODUCTION",
        "status": "OPEN",
        "approval_mode": "team",
        "required_approvals": ["PRODUCTION"],
        "team_approvals": {
            "PRODUCTION": {"approved": False, "approved_by": None, "approved_at": None}
        },
    }


def _active_as_cycle() -> dict:
    """진행 중 AS(RECEIVED) — read_as_status → RECEIVED."""
    return {"as_lifecycle": {"current_cycle_id": "c1",
                             "cycles": [{"cycle_id": "c1", "transitions": []}]}}


def _mint_run(order_id: int) -> ProductionRun:
    run = ProductionRun(order_id=order_id, status="IN_PROGRESS", steps=[], defects=[],
                        is_current=True)
    db_session.add(run)
    db_session.commit()
    return run


def _seed_construction_evidence(order_id: int) -> None:
    """시공 완료 증빙(after 2장·서명)을 채운다."""
    order = db_session.get(Order, order_id)
    sd = copy.deepcopy(order.structured_data or {})
    construction = sd.get("construction") or {}
    construction["evidence"] = {"before": [], "after": [9001, 9002], "signature_att_id": 9003}
    sd["construction"] = construction
    order.structured_data = sd
    flag_modified(order, "structured_data")
    db_session.commit()


# --------------------------------------------------------------------------- #
# 1. 보류(HOLD_ACTIVE) — 제작 완료
# --------------------------------------------------------------------------- #
def test_hold_blocks_production_complete_without_override(client):
    """평소에는 관리자도 막힌다 — 보류 중 주문의 제작 완료는 409 HOLD_ACTIVE."""
    _login(client, _make_user("ov_hold_control"))
    oid = _make_order("PRODUCTION", structured_data=_held()).id

    resp = client.post(f"/api/orders/{oid}/production/complete", json={})

    assert resp.status_code == 409, resp.get_data(as_text=True)
    assert resp.get_json()["code"] == "HOLD_ACTIVE"
    assert _saved(oid).erp_stage_code == "PRODUCTION"
    assert _override_events(oid) == []


def test_hold_is_punched_by_admin_override(client):
    """ADMIN 이 admin_override 를 실으면 보류를 건너뛰고 제작을 완료한다(이력 1행)."""
    _login(client, _make_user("ov_hold_punch"))
    oid = _make_order("PRODUCTION", structured_data=_held()).id

    resp = client.post(f"/api/orders/{oid}/production/complete", json=_punch())

    assert resp.status_code == 200, resp.get_data(as_text=True)
    assert _saved(oid).erp_stage_code == "CONSTRUCTION"
    events = _override_events(oid)
    assert len(events) == 1
    payload = events[0].payload
    assert payload["gate"] == "HOLD_ACTIVE"
    assert payload["gates"] == ["HOLD_ACTIVE"]
    assert payload["reason"] == _REASON
    assert payload["axis"] == "MAIN"
    assert payload["from"] == "PRODUCTION" and payload["to"] == "CONSTRUCTION"
    assert payload["bulk"] is False


# --------------------------------------------------------------------------- #
# 2. 제작 완료 필수 승인(QUEST_INCOMPLETE)
# --------------------------------------------------------------------------- #
def test_production_quest_blocks_complete_without_override(client):
    """평소에는 관리자도 막힌다 — 미승인 생산 quest 는 409 QUEST_INCOMPLETE."""
    _login(client, _make_user("ov_quest_control"))
    oid = _make_order("PRODUCTION", structured_data={"quests": [_open_production_quest()]}).id

    resp = client.post(f"/api/orders/{oid}/production/complete", json={})

    assert resp.status_code == 409, resp.get_data(as_text=True)
    assert resp.get_json()["code"] == "QUEST_INCOMPLETE"
    assert _saved(oid).erp_stage_code == "PRODUCTION"


def test_production_quest_is_punched_by_admin_override(client):
    """ADMIN + admin_override 면 미승인 생산 quest 를 건너뛰고 완료한다."""
    _login(client, _make_user("ov_quest_punch"))
    oid = _make_order("PRODUCTION", structured_data={"quests": [_open_production_quest()]}).id

    resp = client.post(f"/api/orders/{oid}/production/complete", json=_punch())

    assert resp.status_code == 200, resp.get_data(as_text=True)
    assert _saved(oid).erp_stage_code == "CONSTRUCTION"
    assert _override_events(oid)[0].payload["gate"] == "QUEST_INCOMPLETE"


# --------------------------------------------------------------------------- #
# 3. 시공 시작 단계 전제(INVALID_STAGE)
# --------------------------------------------------------------------------- #
def test_construction_start_blocked_on_wrong_stage_without_override(client):
    """평소에는 관리자도 막힌다 — 시공 대기가 아니면 시공 시작은 409 INVALID_STAGE."""
    _login(client, _make_user("ov_cstart_control", team="CONSTRUCTION"))
    oid = _make_order("PRODUCTION").id

    resp = client.post(f"/api/orders/{oid}/construction/start", json={})

    assert resp.status_code == 409, resp.get_data(as_text=True)
    assert resp.get_json()["code"] == "INVALID_STAGE"
    assert db_session.query(OrderConstructionAttempt).filter_by(order_id=oid).count() == 0


def test_construction_start_stage_gate_is_punched_by_admin_override(client):
    """ADMIN + admin_override 면 단계 전제를 건너뛰고 시공 attempt 를 연다."""
    _login(client, _make_user("ov_cstart_punch", team="CONSTRUCTION"))
    oid = _make_order("PRODUCTION").id

    resp = client.post(f"/api/orders/{oid}/construction/start", json=_punch())

    assert resp.status_code == 200, resp.get_data(as_text=True)
    db_session.expire_all()
    assert db_session.query(OrderConstructionAttempt).filter_by(
        order_id=oid, is_current=True).count() == 1
    payload = _override_events(oid)[0].payload
    assert payload["gate"] == "INVALID_STAGE" and payload["axis"] == "CONSTRUCTION"


# --------------------------------------------------------------------------- #
# 4. 시공 증빙(EVIDENCE_MISSING)
# --------------------------------------------------------------------------- #
def test_construction_complete_blocked_without_evidence(client):
    """평소에는 관리자도 막힌다 — 증빙이 없으면 시공 완료는 400 '완료 요건 미충족'."""
    _login(client, _make_user("ov_evi_control", team="CONSTRUCTION"))
    oid = _make_order("CONSTRUCTION").id

    resp = client.post(f"/api/orders/{oid}/construction/complete", json={})

    assert resp.status_code == 400, resp.get_data(as_text=True)
    body = resp.get_json()
    assert body["error"] == "완료 요건 미충족"
    assert sorted(body["data"]["missing"]) == ["after", "signature"]
    assert _saved(oid).erp_stage_code == "CONSTRUCTION"


def test_construction_evidence_gate_is_punched_by_admin_override(client):
    """ADMIN + admin_override 면 증빙 없이도 시공을 완료해 CS 로 보낸다."""
    _login(client, _make_user("ov_evi_punch", team="CONSTRUCTION"))
    oid = _make_order("CONSTRUCTION").id

    resp = client.post(f"/api/orders/{oid}/construction/complete", json=_punch())

    assert resp.status_code == 200, resp.get_data(as_text=True)
    assert _saved(oid).erp_stage_code == "CS"
    payload = _override_events(oid)[0].payload
    assert payload["gate"] == "EVIDENCE_MISSING"
    assert payload["from"] == "CONSTRUCTION" and payload["to"] == "CS"


def test_construction_complete_with_evidence_needs_no_override(client):
    """대조군 — 증빙이 채워져 있으면 admin_override 없이 그냥 완료되고 이력도 안 남는다."""
    _login(client, _make_user("ov_evi_normal", team="CONSTRUCTION"))
    oid = _make_order("CONSTRUCTION").id
    _seed_construction_evidence(oid)

    resp = client.post(f"/api/orders/{oid}/construction/complete", json={})

    assert resp.status_code == 200, resp.get_data(as_text=True)
    assert _saved(oid).erp_stage_code == "CS"
    assert _override_events(oid) == []


# --------------------------------------------------------------------------- #
# 5. CS 완료 진행 중 AS(AS_ACTIVE)
# --------------------------------------------------------------------------- #
def test_cs_complete_blocked_by_active_as_without_override(client):
    """평소에는 관리자도 막힌다 — 진행 중 AS 가 있으면 CS 완료는 409 AS_ACTIVE."""
    _login(client, _make_user("ov_as_control", team="CS"))
    oid = _make_order("CS", structured_data=_active_as_cycle()).id

    resp = client.post(f"/api/orders/{oid}/cs/complete", json={})

    assert resp.status_code == 409, resp.get_data(as_text=True)
    assert resp.get_json()["code"] == "AS_ACTIVE"
    assert _saved(oid).structured_data["workflow"]["stage"] == "CS"


def test_cs_complete_active_as_is_punched_by_admin_override(client):
    """ADMIN + admin_override 면 진행 중 AS 를 건너뛰고 최종 완료한다."""
    _login(client, _make_user("ov_as_punch", team="CS"))
    oid = _make_order("CS", structured_data=_active_as_cycle()).id

    resp = client.post(f"/api/orders/{oid}/cs/complete", json=_punch())

    assert resp.status_code == 200, resp.get_data(as_text=True)
    # 본공정 축은 COMPLETED 다. ``order.status`` 는 AS overlay 가 덮어써 AS_RECEIVED 로 보인다
    # (AS 는 본공정 위에 얹히는 축이다) — 완료 판정은 본공정 축으로 한다.
    assert _saved(oid).structured_data["workflow"]["stage"] == "COMPLETED"
    payload = _override_events(oid)[0].payload
    assert payload["gate"] == "AS_ACTIVE"
    assert payload["route"] == "erp_orders_cs.api_cs_complete"
    assert payload["from"] == "CS" and payload["to"] == "COMPLETED"


# --------------------------------------------------------------------------- #
# 6. 부수효과 — 뚫고 완료해도 뒤가 비지 않는다
# --------------------------------------------------------------------------- #
def test_punched_completion_still_seals_construction_attempt(client):
    """admin_override 로 완료해도 시공 attempt 봉인·이력 행은 평소와 똑같이 일어난다."""
    _login(client, _make_user("ov_side_effect", team="CS"))
    oid = _make_order("CS", structured_data=_active_as_cycle()).id
    attempt = OrderConstructionAttempt(id="11111111-2222-3333-4444-555555555555", order_id=oid,
                                       status="IN_PROGRESS", is_current=True,
                                       evidence={"before": [], "after": []})
    db_session.add(attempt)
    db_session.commit()

    resp = client.post(f"/api/orders/{oid}/cs/complete", json=_punch())
    assert resp.status_code == 200, resp.get_data(as_text=True)

    db_session.expire_all()
    saved_attempt = db_session.get(OrderConstructionAttempt,
                                   "11111111-2222-3333-4444-555555555555")
    assert saved_attempt.status == "COMPLETED"
    assert saved_attempt.is_current is False
    saved = _saved(oid)
    assert saved.structured_data["workflow"]["stage"] == "COMPLETED"
    history = saved.structured_data["workflow"]["history"]
    assert history[-1]["note"] == "CS 완료 -> 최종 완료"


# --------------------------------------------------------------------------- #
# 7. 음성 — 중복 발급 계열은 관리자도 못 뚫는다(권한이 아니라 데이터 정합)
# --------------------------------------------------------------------------- #
def test_already_started_is_not_punchable(client):
    """이미 열린 시공 attempt 가 있으면 admin_override 로도 409 ALREADY_STARTED."""
    _login(client, _make_user("ov_already_c", team="CONSTRUCTION"))
    oid = _make_order("CONSTRUCTION").id
    first = client.post(f"/api/orders/{oid}/construction/start", json={})
    assert first.status_code == 200, first.get_data(as_text=True)

    resp = client.post(f"/api/orders/{oid}/construction/start", json=_punch())

    assert resp.status_code == 409, resp.get_data(as_text=True)
    assert resp.get_json()["code"] == "ALREADY_STARTED"
    db_session.expire_all()
    assert db_session.query(OrderConstructionAttempt).filter_by(order_id=oid).count() == 1
    assert _override_events(oid) == []


def test_already_in_production_is_not_punchable(client):
    """이미 제작중(current run 존재)이면 admin_override 로도 409 — 중복 run 을 만들지 않는다."""
    _login(client, _make_user("ov_already_p"))
    oid = _make_order("PRODUCTION").id
    _mint_run(oid)

    resp = client.post(f"/api/orders/{oid}/production/start", json=_punch())

    assert resp.status_code == 409, resp.get_data(as_text=True)
    assert resp.get_json()["message"] == "이미 제작중인 주문입니다."
    db_session.expire_all()
    assert db_session.query(ProductionRun).filter_by(order_id=oid).count() == 1
    assert _override_events(oid) == []


# --------------------------------------------------------------------------- #
# 8. 음성 — 비관리자는 뚫을 수 없다
# --------------------------------------------------------------------------- #
def test_manager_cannot_use_admin_override(client):
    """MANAGER 가 admin_override 를 실으면 게이트 코드가 아니라 403 ADMIN_ONLY 를 받는다."""
    _login(client, _make_user("ov_manager", role="MANAGER"))
    oid = _make_order("PRODUCTION", structured_data=_held()).id

    resp = client.post(f"/api/orders/{oid}/production/complete", json=_punch())

    assert resp.status_code == 403, resp.get_data(as_text=True)
    assert resp.get_json()["code"] == "ADMIN_ONLY"
    assert _saved(oid).erp_stage_code == "PRODUCTION"
    assert _override_events(oid) == []


def test_admin_override_without_reason_is_unprocessable(client):
    """ADMIN 이어도 사유가 공백이면 422 REASON_REQUIRED — 사유 없는 뚫기는 없다."""
    _login(client, _make_user("ov_no_reason"))
    oid = _make_order("PRODUCTION", structured_data=_held()).id

    resp = client.post(f"/api/orders/{oid}/production/complete",
                       json={"admin_override": True, "override_reason": "   "})

    assert resp.status_code == 422, resp.get_data(as_text=True)
    assert resp.get_json()["code"] == "REASON_REQUIRED"
    assert _saved(oid).erp_stage_code == "PRODUCTION"


# --------------------------------------------------------------------------- #
# 9. 음성(정합 축) — 잠금 아래 expected_from 재확인은 관리자도 못 뚫는다
# --------------------------------------------------------------------------- #
def test_stage_conflict_under_lock_survives_emergency_override(client):
    """다른 세션이 단계를 바꾼 상황: expected_from 불일치는 강제 진행으로도 뚫리지 않는다.

    CS 완료를 부르는 중에 주문이 CONSTRUCTION 으로 바뀐 상황을 흉내 낸다 — 라우트가 본
    ``expected_from`` 과 잠금 아래 실제 축 값이 다르면 :class:`StageConflictError` 다.
    관리자 강제 진행(``emergency_override=True`` + 사유)도 이 검사만은 통과하지 못한다.
    """
    _make_user("ov_conflict", team="CS")
    oid = _make_order("CONSTRUCTION").id

    with pytest.raises(StageConflictError):
        transition_order(
            db_session, command_id="CS_COMPLETE", order_id=oid, actor_user_id=1,
            expected_from="CS", target_value="COMPLETED",
            scope_hash=scope_hash("CS_COMPLETE", oid), request_hash=request_hash({}),
            emergency_override=True, reason=_REASON,
        )

    db_session.rollback()
    assert _saved(oid).erp_stage_code == "CONSTRUCTION"


# --------------------------------------------------------------------------- #
# 9. 도면 수령 확정 전제(DRAWING_STATUS)
# --------------------------------------------------------------------------- #
def test_drawing_receipt_requires_transferred_even_for_admin(client):
    """평소에는 관리자도 막힌다 — 전달된 도면이 아니면 400."""
    _login(client, _make_user("dr_plain", team="SALES"))
    order_id = _make_order("DRAWING").id

    resp = client.post(f"/api/orders/{order_id}/confirm-drawing-receipt", json={})

    assert resp.status_code == 400, resp.get_data(as_text=True)
    assert "전달된 도면" in resp.get_json()["message"]
    assert _override_events(order_id) == []


def test_drawing_receipt_gate_is_punched_by_admin_override(client):
    """ADMIN 뚫기 → 도면 상태 전제를 건너뛰고 수령 확정이 된다(이벤트 1행)."""
    _login(client, _make_user("dr_punch", team="SALES"))
    order_id = _make_order("DRAWING").id

    resp = client.post(
        f"/api/orders/{order_id}/confirm-drawing-receipt", json=_punch()
    )

    assert resp.status_code == 200, resp.get_data(as_text=True)
    events = _override_events(order_id)
    assert len(events) == 1
    assert events[0].payload["gates"] == ["DRAWING_STATUS"]
