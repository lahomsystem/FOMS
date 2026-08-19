"""AUTH-QUEST-01 — quest approve 권한 게이트.

quest approve route 는 승인 **권한만** 판정하고 order 상태를 직접 전이시키지 않는다
(전이는 STATE-QUEST-01 하류). 정본 규칙(§5.2):

* actor team = 현 단계 필수 승인 팀(불일치 403).
* DRAWING/CONFIRM 단독 승인은 전용 command 로만 → command-required 409.
* 시공 승인은 ASSIGNMENT-00 ``order_assignments`` user-ID row 기반(팀 자격만으로는 불가).
* 관리자 override 승인은 사유(override_reason) 필수(감사) — STAFF 는 override 불가.
* approve 는 stage 를 **직접** 쓰지 않는다. 최종 승인 시 전이는 STATE-QUEST-01
  (quest_transition_service → order_transition_service) 정본 경로로만 일어난다.
"""

from __future__ import annotations

from werkzeug.security import generate_password_hash

from db import db_session
from foms.services.datetime_kst import now_utc_naive
from models import Order, OrderAssignment, OrderEvent, User


def _make_user(*, role: str, team: str, username: str) -> User:
    user = User(
        username=username,
        password=generate_password_hash("pw"),
        role=role,
        team=team,
        name=username,
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
            "approved": False,
            "approved_by": None,
            "approved_by_name": None,
            "approved_at": None,
        },
        "created_at": "2026-07-24T00:00:00",
        "updated_at": "2026-07-24T00:00:00",
    }


def _create_order(*, stage: str, quests: list[dict], status: str | None = None) -> Order:
    order = Order(
        received_date="2026-07-24",
        customer_name="홍길동",
        phone="010-1234-5678",
        address="서울 테헤란로 123",
        product="붙박이장",
        status=status or stage,
        is_erp_order=True,
        structured_data={"workflow": {"stage": stage}, "quests": quests},
    )
    db_session.add(order)
    db_session.commit()
    return order


# --------------------------------------------------------------------------- #
# actor team = 현 단계 필수 승인 팀
# --------------------------------------------------------------------------- #
def test_actor_team_matches_required_team_approves(client):
    """PRODUCTION 단계 quest 는 PRODUCTION 팀원이 승인할 수 있다(200)."""
    user = _make_user(role="STAFF", team="PRODUCTION", username="prod-staff")
    _login(client, user)
    order = _create_order(stage="PRODUCTION", quests=[_team_quest("PRODUCTION", ["PRODUCTION"])])

    resp = client.post(f"/api/orders/{order.id}/quest/approve", json={"team": "PRODUCTION"})

    assert resp.status_code == 200, resp.get_json()
    assert resp.get_json()["success"] is True


def test_actor_team_mismatch_forbidden(client):
    """PRODUCTION 단계 quest 를 SALES 팀원이 승인하면 403(팀 불일치)."""
    user = _make_user(role="STAFF", team="SALES", username="sales-staff")
    _login(client, user)
    order = _create_order(stage="PRODUCTION", quests=[_team_quest("PRODUCTION", ["PRODUCTION"])])

    resp = client.post(f"/api/orders/{order.id}/quest/approve", json={"team": "PRODUCTION"})

    assert resp.status_code == 403, resp.get_json()


# --------------------------------------------------------------------------- #
# DRAWING/CONFIRM 단독 승인 → command-required 409
# --------------------------------------------------------------------------- #
def test_drawing_standalone_approval_is_command_required(client):
    """DRAWING 단독 quest 승인은 409(전용 command 로만) — 관리자도 예외 없음."""
    user = _make_user(role="ADMIN", team="DRAWING", username="draw-admin")
    _login(client, user)
    order = _create_order(stage="DRAWING", quests=[_assignee_quest("DRAWING")])

    resp = client.post(f"/api/orders/{order.id}/quest/approve", json={})

    assert resp.status_code == 409, resp.get_json()
    assert resp.get_json().get("code") == "COMMAND_REQUIRED"


def test_confirm_standalone_approval_is_command_required(client):
    """CONFIRM 단독 quest 승인은 409(전용 command 로만) — 관리자도 예외 없음."""
    user = _make_user(role="ADMIN", team="SALES", username="confirm-admin")
    _login(client, user)
    order = _create_order(stage="CONFIRM", quests=[_assignee_quest("CONFIRM")])

    resp = client.post(f"/api/orders/{order.id}/quest/approve", json={})

    assert resp.status_code == 409, resp.get_json()
    assert resp.get_json().get("code") == "COMMAND_REQUIRED"


# --------------------------------------------------------------------------- #
# 시공 = ASSIGNMENT-00 배정 ID 기반
# --------------------------------------------------------------------------- #
def test_construction_assignment_based_approval(client):
    """시공은 팀 자격이 없어도(팀=CONSTRUCTION) 배정된 담당자면 승인 가능(200)."""
    user = _make_user(role="STAFF", team="CONSTRUCTION", username="con-worker")
    _login(client, user)
    order = _create_order(stage="CONSTRUCTION", quests=[_team_quest("CONSTRUCTION", ["CONSTRUCTION"])])
    db_session.add(
        OrderAssignment(
            order_id=order.id, domain="CONSTRUCTION", user_id=user.id, source="TEAM_REPLACE",
            active=True, assigned_at=now_utc_naive(), assigned_by_user_id=user.id,
        )
    )
    db_session.commit()

    resp = client.post(f"/api/orders/{order.id}/quest/approve", json={"team": "CONSTRUCTION"})

    assert resp.status_code == 200, resp.get_json()
    assert resp.get_json()["success"] is True


def test_construction_team_alone_insufficient_when_assignments_exist(client):
    """시공에 active 배정이 있으면 배정 ID 만 승인 — CS 팀 자격만으로는 403(ID > 팀)."""
    assigned = _make_user(role="STAFF", team="CONSTRUCTION", username="con-assigned")
    order = _create_order(stage="CONSTRUCTION", quests=[_team_quest("CONSTRUCTION", ["CONSTRUCTION"])])
    db_session.add(
        OrderAssignment(
            order_id=order.id, domain="CONSTRUCTION", user_id=assigned.id, source="TEAM_REPLACE",
            active=True, assigned_at=now_utc_naive(), assigned_by_user_id=assigned.id,
        )
    )
    db_session.commit()

    other = _make_user(role="STAFF", team="CS", username="cs-not-assigned")
    _login(client, other)

    resp = client.post(f"/api/orders/{order.id}/quest/approve", json={"team": "CONSTRUCTION"})

    assert resp.status_code == 403, resp.get_json()


# --------------------------------------------------------------------------- #
# 관리자 override 승인은 사유 필수(감사); STAFF override 불가
# --------------------------------------------------------------------------- #
def test_override_requires_reason(client):
    """팀 불일치를 override 로 뚫으려면 사유가 필수 — 없으면 422."""
    user = _make_user(role="MANAGER", team="SALES", username="mgr-sales")
    _login(client, user)
    order = _create_order(stage="RECEIVED", quests=[_team_quest("RECEIVED", ["CS"])])

    resp = client.post(
        f"/api/orders/{order.id}/quest/approve",
        json={"team": "CS", "emergency_override": True},
    )

    assert resp.status_code == 422, resp.get_json()


def test_override_with_reason_records_audit(client):
    """override 사유가 있으면 승인(200)되고 감사 이벤트에 사유가 기록된다."""
    user = _make_user(role="MANAGER", team="SALES", username="mgr-sales2")
    _login(client, user)
    order = _create_order(stage="RECEIVED", quests=[_team_quest("RECEIVED", ["CS"])])
    order_id = order.id

    resp = client.post(
        f"/api/orders/{order_id}/quest/approve",
        json={"team": "CS", "emergency_override": True, "override_reason": "긴급 처리"},
    )

    assert resp.status_code == 200, resp.get_json()
    db_session.expire_all()
    events = (
        db_session.query(OrderEvent)
        .filter(
            OrderEvent.order_id == order_id,
            OrderEvent.event_type == "QUEST_APPROVAL_CHANGED",
        )
        .all()
    )
    assert events, "감사 이벤트가 기록되어야 한다."
    assert any(
        (e.payload or {}).get("is_override") and (e.payload or {}).get("override_reason") == "긴급 처리"
        for e in events
    ), [e.payload for e in events]


def test_staff_cannot_override(client):
    """STAFF 는 override 승인 불가 — 사유가 있어도 403(관리자 전용)."""
    user = _make_user(role="STAFF", team="SALES", username="staff-noover")
    _login(client, user)
    order = _create_order(stage="RECEIVED", quests=[_team_quest("RECEIVED", ["CS"])])

    resp = client.post(
        f"/api/orders/{order.id}/quest/approve",
        json={"team": "CS", "emergency_override": True, "override_reason": "x"},
    )

    assert resp.status_code == 403, resp.get_json()


# --------------------------------------------------------------------------- #
# 최종 승인 → 전이는 정본 경로(STATE-QUEST-01)로만
# --------------------------------------------------------------------------- #
def test_final_approval_advances_stage_via_canonical_engine(client):
    """RECEIVED 최종 승인은 정본 엔진 경유로 MEASURE 전이 + fresh MEASURE quest 를 만든다."""
    user = _make_user(role="STAFF", team="CS", username="cs-staff")
    _login(client, user)
    order = _create_order(stage="RECEIVED", quests=[_team_quest("RECEIVED", ["CS"])], status="RECEIVED")
    order_id = order.id

    resp = client.post(f"/api/orders/{order_id}/quest/approve", json={"team": "CS"})

    assert resp.status_code == 200, resp.get_json()
    data = resp.get_json()
    assert data["all_approved"] is True
    assert data["auto_transitioned"] is True

    db_session.expire_all()
    saved = db_session.get(Order, order_id)
    assert saved is not None
    assert (saved.structured_data or {}).get("workflow", {}).get("stage") == "MEASURE"
    assert saved.erp_stage_code == "MEASURE"
    # 승인 기록과 전이가 같은 commit 에 남는다(한쪽만 남지 않는다).
    receiv_quest = [
        q for q in (saved.structured_data.get("quests") or []) if q.get("stage") == "RECEIVED"
    ][0]
    assert receiv_quest["team_approvals"]["CS"]["approved"] is True
    assert receiv_quest["status"] == "COMPLETED"
    # 다음 단계(MEASURE) quest 가 생성된다.
    assert any(q.get("stage") == "MEASURE" for q in saved.structured_data.get("quests") or [])
    # 전이는 정본 엔진 이벤트로 기록된다(라우트의 legacy 직접-쓰기 마커는 사용하지 않는다).
    assert (
        db_session.query(OrderEvent)
        .filter(
            OrderEvent.order_id == order_id,
            OrderEvent.event_type == "MEASUREMENT_REQUESTED",
        )
        .count()
        == 1
    )
    assert (
        db_session.query(OrderEvent)
        .filter(
            OrderEvent.order_id == order_id,
            OrderEvent.event_type == "STAGE_AUTO_TRANSITIONED",
        )
        .count()
        == 0
    )


def test_measure_assignee_approval_advances_to_drawing(client):
    """실측 담당자 승인('실측 완료 → 도면 전달')은 MEASURE→DRAWING 전이를 일으킨다."""
    user = _make_user(role="STAFF", team="SALES", username="sales-measure")
    _login(client, user)
    order = _create_order(stage="MEASURE", quests=[_assignee_quest("MEASURE")], status="MEASURE")
    order_id = order.id

    resp = client.post(f"/api/orders/{order_id}/quest/approve", json={})

    assert resp.status_code == 200, resp.get_json()
    data = resp.get_json()
    assert data["all_approved"] is True
    assert data["auto_transitioned"] is True
    assert data["next_stage"] in ("도면", "DRAWING")

    db_session.expire_all()
    saved = db_session.get(Order, order_id)
    assert (saved.structured_data or {}).get("workflow", {}).get("stage") == "DRAWING"
    assert saved.erp_stage_code == "DRAWING"
    measure_quest = [
        q for q in (saved.structured_data.get("quests") or []) if q.get("stage") == "MEASURE"
    ][0]
    assert measure_quest["assignee_approval"]["approved"] is True
    # DRAWING quest 는 만들지 않는다(도면은 전용 command 소관).
    assert not any(q.get("stage") == "DRAWING" for q in saved.structured_data.get("quests") or [])
    assert (
        db_session.query(OrderEvent)
        .filter(
            OrderEvent.order_id == order_id,
            OrderEvent.event_type == "MEASUREMENT_COMPLETED",
        )
        .count()
        == 1
    )


def test_partial_team_approval_does_not_transition(client):
    """필수 팀이 둘인데 하나만 승인하면 전이하지 않는다(stage 불변)."""
    user = _make_user(role="STAFF", team="CS", username="cs-partial")
    _login(client, user)
    order = _create_order(
        stage="RECEIVED", quests=[_team_quest("RECEIVED", ["CS", "SALES"])], status="RECEIVED"
    )
    order_id = order.id

    resp = client.post(f"/api/orders/{order_id}/quest/approve", json={"team": "CS"})

    assert resp.status_code == 200, resp.get_json()
    data = resp.get_json()
    assert data["all_approved"] is False
    assert data["auto_transitioned"] is False

    db_session.expire_all()
    saved = db_session.get(Order, order_id)
    assert (saved.structured_data or {}).get("workflow", {}).get("stage") == "RECEIVED"
    assert saved.erp_stage_code in (None, "RECEIVED")


def test_prerequisite_only_stage_approval_does_not_transition(client):
    """PRODUCTION 등 prerequisite-only 단계는 승인해도 stage 를 쓰지 않는다."""
    user = _make_user(role="STAFF", team="PRODUCTION", username="prod-noadvance")
    _login(client, user)
    order = _create_order(
        stage="PRODUCTION", quests=[_team_quest("PRODUCTION", ["PRODUCTION"])], status="PRODUCTION"
    )
    order_id = order.id

    resp = client.post(f"/api/orders/{order_id}/quest/approve", json={"team": "PRODUCTION"})

    assert resp.status_code == 200, resp.get_json()
    assert resp.get_json()["auto_transitioned"] is False

    db_session.expire_all()
    saved = db_session.get(Order, order_id)
    assert (saved.structured_data or {}).get("workflow", {}).get("stage") == "PRODUCTION"


def test_double_submit_after_transition_is_rejected_without_second_transition(client):
    """전이 후 같은 버튼 재요청은 전용-command 가드(409)에 막혀 두 번 전이하지 않는다.

    stage 가 이미 DRAWING 이라 라우트 선행 가드가 먼저 걸린다(전이 진입 자체가 없음).
    이중 클릭 방어의 실질 계약이며, 전이 이벤트는 1건으로 유지된다.
    """
    user = _make_user(role="STAFF", team="SALES", username="sales-idem")
    _login(client, user)
    order = _create_order(stage="MEASURE", quests=[_assignee_quest("MEASURE")], status="MEASURE")
    order_id = order.id
    headers = {"Idempotency-Key": "quest-approve-idem-1"}

    first = client.post(f"/api/orders/{order_id}/quest/approve", json={}, headers=headers)
    second = client.post(f"/api/orders/{order_id}/quest/approve", json={}, headers=headers)

    assert first.status_code == 200, first.get_json()
    assert second.status_code == 409, second.get_json()
    assert second.get_json()["code"] == "COMMAND_REQUIRED"

    db_session.expire_all()
    assert (
        db_session.query(OrderEvent)
        .filter(
            OrderEvent.order_id == order_id,
            OrderEvent.event_type == "MEASUREMENT_COMPLETED",
        )
        .count()
        == 1
    )
