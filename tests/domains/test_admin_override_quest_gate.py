"""ADMIN-OVERRIDE-01 — 퀘스트 승인 라우트의 COMMAND_REQUIRED 게이트 두 갈래.

평소 막힘(음성 대조군)은 ``test_auth_quest_approve.py`` 가 그대로 지키고, 여기서는 관리자가
사유를 적고 뚫었을 때와, 뚫어도 하류 전이 계층은 그대로라는 것, 그리고 ``emergency_override``
(권한 소유 축)로는 이 업무 게이트가 안 뚫린다는 것을 못박는다.
"""

from __future__ import annotations

from werkzeug.security import generate_password_hash

from db import db_session
from models import Order, OrderEvent, User


def _make_user(*, role: str, team: str, username: str) -> User:
    user = User(username=username, password=generate_password_hash("pw"), role=role,
                team=team, name=username, is_active=True)
    db_session.add(user)
    db_session.commit()
    return user


def _login(client, user: User) -> None:
    with client.session_transaction() as sess:
        sess["user_id"] = user.id
        sess["username"] = user.username
        sess["role"] = user.role


def _team_quest(stage_code: str, teams: list[str]) -> dict:
    return {
        "stage": stage_code,
        "title": f"{stage_code} quest",
        "description": "",
        "owner_team": teams[0] if teams else "",
        "owner_person": "",
        "status": "OPEN",
        "required_approvals": list(teams),
        "team_approvals": {
            t: {"approved": False, "approved_by": None, "approved_at": None} for t in teams
        },
        "approval_mode": "team",
        "assignee_approval": None,
        "created_at": "2026-07-24T00:00:00",
        "updated_at": "2026-07-24T00:00:00",
    }


def _assignee_quest(stage_code: str) -> dict:
    return {
        "stage": stage_code,
        "title": f"{stage_code} quest",
        "description": "",
        "owner_team": "SALES",
        "owner_person": "",
        "status": "OPEN",
        "required_approvals": ["SALES"],
        "team_approvals": {},
        "approval_mode": "assignee",
        "assignee_approval": {
            "approved": False, "approved_by": None,
            "approved_by_name": None, "approved_at": None,
        },
        "created_at": "2026-07-24T00:00:00",
        "updated_at": "2026-07-24T00:00:00",
    }


def _create_order(*, stage: str, quests: list[dict]) -> Order:
    order = Order(
        received_date="2026-09-21",
        customer_name="홍길동",
        phone="010-1234-5678",
        address="서울 테헤란로 123",
        product="붙박이장",
        status=stage,
        is_erp_order=True,
        structured_data={"workflow": {"stage": stage}, "quests": quests},
    )
    db_session.add(order)
    db_session.commit()
    return order


def test_drawing_standalone_approval_passes_with_admin_override(client):
    """ADMIN 이 사유를 적고 admin_override 를 켜면 COMMAND_REQUIRED 를 건너뛴다(200 + 이벤트 1행).

    필수 팀이 둘 남은 DRAWING quest 라 한 팀 승인으로는 quest 가 끝나지 않는다 — 단계 전이를
    부르지 않으므로 라우트 게이트를 뚫은 결과가 그대로 200 이다.
    """
    user = _make_user(role="ADMIN", team="DRAWING", username="draw-admin-punch")
    _login(client, user)
    order_id = _create_order(
        stage="DRAWING", quests=[_team_quest("DRAWING", ["DRAWING", "SALES"])]
    ).id

    resp = client.post(
        f"/api/orders/{order_id}/quest/approve",
        json={
            "team": "DRAWING",
            "admin_override": True,
            "override_reason": "도면 담당자 부재로 관리자가 대신 승인",
        },
    )

    assert resp.status_code == 200, resp.get_json()
    events = (
        db_session.query(OrderEvent)
        .filter(
            OrderEvent.order_id == order_id,
            OrderEvent.event_type == "ADMIN_OVERRIDE_USED",
        )
        .all()
    )
    assert len(events) == 1
    payload = events[0].payload
    assert payload["gate"] == "COMMAND_REQUIRED"
    assert payload["gates"] == ["COMMAND_REQUIRED"]
    assert payload["reason"] == "도면 담당자 부재로 관리자가 대신 승인"
    assert payload["route"] == "quest.api_order_quest_approve"


def test_admin_override_does_not_reach_downstream_transition_layer(client):
    """뚫어도 하류 전이 계층은 그대로다 — DRAWING quest 가 끝나면 409 를 그대로 돌려준다.

    ``admin_override`` 는 라우트의 업무 게이트만 건너뛴다. 단계 전이 서비스에는 그 값을
    넘기지 않으므로 전용 command 규칙이 살아 있고, 실패했으니 이벤트도 남지 않는다.
    """
    user = _make_user(role="ADMIN", team="DRAWING", username="draw-admin-downstream")
    _login(client, user)
    order_id = _create_order(stage="DRAWING", quests=[_assignee_quest("DRAWING")]).id

    resp = client.post(
        f"/api/orders/{order_id}/quest/approve",
        json={"admin_override": True, "override_reason": "관리자 직접 진행"},
    )

    assert resp.status_code == 409, resp.get_json()
    assert resp.get_json().get("code") == "STAGE_COMMAND_REQUIRED"
    assert (
        db_session.query(OrderEvent)
        .filter(
            OrderEvent.order_id == order_id,
            OrderEvent.event_type == "ADMIN_OVERRIDE_USED",
        )
        .count()
        == 0
    )


def test_emergency_override_alone_does_not_punch_command_required(client):
    """축 분리 음성 대조군 — emergency_override 는 권한 소유 축이라 COMMAND_REQUIRED 를 못 뚫는다."""
    user = _make_user(role="ADMIN", team="DRAWING", username="draw-admin-emg")
    _login(client, user)
    order_id = _create_order(stage="DRAWING", quests=[_assignee_quest("DRAWING")]).id

    resp = client.post(
        f"/api/orders/{order_id}/quest/approve",
        json={"emergency_override": True, "override_reason": "긴급"},
    )

    assert resp.status_code == 409, resp.get_json()
    assert resp.get_json().get("code") == "COMMAND_REQUIRED"
    assert (
        db_session.query(OrderEvent)
        .filter(
            OrderEvent.order_id == order_id,
            OrderEvent.event_type == "ADMIN_OVERRIDE_USED",
        )
        .count()
        == 0
    )
