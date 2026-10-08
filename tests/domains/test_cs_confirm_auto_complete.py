"""CS 확인 최종 승인 = 최종 완료 (CS-AUTO-COMPLETE-01, 2026-10-08).

운영 #5450 모양: CS quest 승인이 끝나 "CS 확인 완료" 배지가 붙었는데 단계가 CS 에 남아
ERP 대시보드에서는 완료로 보낼 버튼이 없었다. 승인 라우트가 완료 정본 서비스
(``complete_order_as_cs``)를 같은 tx 로 부르는지, 보류·AS 일 때 승인만 남기는지,
이미 막힌 주문을 같은 버튼으로 재전이하는지 본다. 대조군은 생산 단계 승인(이동 없음)이다.
"""
from __future__ import annotations

from werkzeug.security import generate_password_hash

from db import db_session
from models import Order, OrderEvent, User


def _make_user(username: str, *, role: str = "STAFF", team: str | None = "CS") -> User:
    user = User(
        username=username,
        password=generate_password_hash("pw"),
        role=role,
        team=team,
        name=f"{username} 이름",
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    return user


def _login(client, user: User) -> None:
    with client.session_transaction() as sess:
        sess["user_id"] = user.id
        sess["username"] = user.username
        sess["role"] = user.role


def _cs_quest(status: str = "OPEN") -> dict:
    quest = {
        "stage": "CS", "title": "CS", "status": status, "approval_mode": "team",
        "required_approvals": ["CS"], "team_approvals": {},
    }
    if status == "COMPLETED":
        quest["team_approvals"] = {"CS": {
            "approved": True, "approved_by": 58, "approved_by_name": "claude_master",
            "approved_at": "2026-10-07T10:00:00",
        }}
        quest["completed_at"] = "2026-10-07T10:00:00"
    return quest


def _create_order(*, stage: str = "CS", quests: list, hold: bool = False) -> Order:
    workflow: dict = {"stage": stage}
    if hold:
        workflow["hold"] = {"active": True}
    order = Order(
        received_date="2026-10-01",
        customer_name="이영아",
        phone="010-1234-5678",
        address="서울 테헤란로 123",
        product="붙박이장",
        status=stage,
        is_erp_order=True,
        structured_data={"workflow": workflow, "quests": quests},
        erp_stage_code=stage,
    )
    db_session.add(order)
    db_session.commit()
    return order


def _saved(order_id: int) -> Order:
    db_session.expire_all()
    return db_session.get(Order, order_id)


def _completed_events(order_id: int) -> list[OrderEvent]:
    return (
        db_session.query(OrderEvent)
        .filter(OrderEvent.order_id == order_id, OrderEvent.event_type == "CS_COMPLETED")
        .all()
    )


def test_cs_final_approve_moves_order_to_completed(client):
    _login(client, _make_user("cs_auto_ok"))
    order_id = _create_order(quests=[_cs_quest()]).id

    resp = client.post(f"/api/orders/{order_id}/quest/approve", json={"team": "CS"})
    assert resp.status_code == 200, resp.get_json()
    body = resp.get_json()
    assert body["all_approved"] is True
    assert body["auto_transitioned"] is True
    assert body["completion_blocked"] is None
    assert body["next_stage"] == "완료"

    saved = _saved(order_id)
    assert saved.erp_stage_code == "COMPLETED"
    assert saved.structured_data["workflow"]["stage"] == "COMPLETED"
    assert saved.structured_data["quests"][0]["status"] == "COMPLETED"
    history = saved.structured_data["workflow"].get("history") or []
    assert any(h.get("note") == "CS 완료 -> 최종 완료" for h in history)
    assert len(_completed_events(order_id)) == 1


def test_cs_approve_on_hold_records_approval_but_stays_in_cs(client):
    _login(client, _make_user("cs_auto_hold"))
    order_id = _create_order(quests=[_cs_quest()], hold=True).id

    resp = client.post(f"/api/orders/{order_id}/quest/approve", json={"team": "CS"})
    assert resp.status_code == 200, resp.get_json()
    body = resp.get_json()
    assert body["all_approved"] is True
    assert body["auto_transitioned"] is False
    assert body["completion_blocked"]["code"] == "HOLD_ACTIVE"

    saved = _saved(order_id)
    assert saved.structured_data["workflow"]["stage"] == "CS"
    assert saved.structured_data["quests"][0]["status"] == "COMPLETED", "승인 기록은 남아야 한다"
    assert _completed_events(order_id) == []


def test_completed_cs_quest_stuck_in_cs_is_retransitioned_to_completed(client):
    """#5450 모양 — 승인 기록은 그대로 두고 완료로만 보낸다."""
    _login(client, _make_user("cs_auto_retrans"))
    order_id = _create_order(quests=[_cs_quest("COMPLETED")]).id

    resp = client.post(f"/api/orders/{order_id}/quest/approve", json={})
    assert resp.status_code == 200, resp.get_json()
    body = resp.get_json()
    assert body["retransitioned"] is True
    assert body["auto_transitioned"] is True
    assert body["next_stage"] == "완료"

    saved = _saved(order_id)
    assert saved.structured_data["workflow"]["stage"] == "COMPLETED"
    approval = saved.structured_data["quests"][0]["team_approvals"]["CS"]
    assert approval["approved_by"] == 58, "승인 기록이 actor 로 덮이면 안 된다"
    assert len(_completed_events(order_id)) == 1


def test_production_approve_control_does_not_move_stage(client):
    """대조군 — 생산 승인은 여전히 기록만 남는다."""
    _login(client, _make_user("cs_auto_prod", role="ADMIN", team="SALES"))
    quest = {
        "stage": "PRODUCTION", "title": "생산", "status": "OPEN", "approval_mode": "team",
        "required_approvals": ["SALES"], "team_approvals": {},
    }
    order_id = _create_order(stage="PRODUCTION", quests=[quest]).id

    resp = client.post(f"/api/orders/{order_id}/quest/approve", json={"team": "SALES"})
    assert resp.status_code == 200, resp.get_json()
    assert resp.get_json()["auto_transitioned"] is False
    assert _saved(order_id).structured_data["workflow"]["stage"] == "PRODUCTION"
