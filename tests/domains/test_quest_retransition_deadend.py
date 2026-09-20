"""실측 완료 뒤 도면으로 못 넘어가는 막다른 길 — 승인 라우트의 재전이(C1, 2026-09-20).

스테이징 #4382 모양: 강제 단계 변경(regress)으로 MEASURE 로 돌아왔는데 MEASURE quest 는 COMPLETED
그대로다. 승인 라우트가 이 quest 를 만나면 승인 기록을 다시 쓰지 않고 전이만 다시 건다
(``retransitioned: True``). 대조군은 권한 없는 팀·이미 넘어간 단계·정상 OPEN 승인이다.
"""
from __future__ import annotations

from werkzeug.security import generate_password_hash

from db import db_session
from models import Order, OrderEvent, User


def _make_user(username: str, *, role: str = "ADMIN", team: str | None = "SALES") -> User:
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


def _create_order(*, stage: str, sd: dict) -> Order:
    order = Order(
        received_date="2026-09-14",
        customer_name="이영아",
        phone="010-1234-5678",
        address="서울 테헤란로 123",
        product="붙박이장",
        status=stage,
        is_erp_order=True,
        structured_data=sd,
        erp_stage_code=stage,
    )
    db_session.add(order)
    db_session.commit()
    return order


def _events(order_id: int, event_type: str) -> list[OrderEvent]:
    return (
        db_session.query(OrderEvent)
        .filter(OrderEvent.order_id == order_id, OrderEvent.event_type == event_type)
        .all()
    )


def _staging_4382_sd(stage: str = "MEASURE") -> dict:
    """스테이징 #4382 원문 모양 — regress 표식 + COMPLETED MEASURE quest(승인자 58)."""
    return {
        "workflow": {
            "stage": stage,
            "stage_override": {"at": "2026-09-14T05:39:50", "stage": "MEASURE", "measurement_date": ""},
        },
        "quests": [{
            "stage": "MEASURE", "title": "실측", "status": "COMPLETED", "approval_mode": "assignee",
            "required_approvals": ["CS", "SALES"], "team_approvals": {},
            "assignee_approval": {
                "approved": True, "approved_by": 58, "approved_by_name": "claude_master",
                "approved_at": "2026-09-14T05:39:39",
            },
            "completed_at": "2026-09-14T05:39:39",
        }],
    }


def _saved(order_id: int) -> Order:
    db_session.expire_all()
    return db_session.get(Order, order_id)


# --------------------------------------------------------------------------- #
# 1. SALES STAFF 가 완료 quest 에 {} 를 보내면 기록은 그대로, 전이만 다시 건다
# --------------------------------------------------------------------------- #
def test_sales_staff_retransitions_completed_measure_quest_without_rewriting_approval(client):
    _login(client, _make_user("dead_sales", role="STAFF", team="SALES"))
    order_id = _create_order(stage="MEASURE", sd=_staging_4382_sd()).id

    resp = client.post(f"/api/orders/{order_id}/quest/approve", json={})
    assert resp.status_code == 200, resp.get_json()
    body = resp.get_json()
    assert body["retransitioned"] is True
    assert body["auto_transitioned"] is True
    assert body["next_stage"] == "도면"
    assert body["all_approved"] is True and body["missing_teams"] == []

    saved = _saved(order_id)
    assert saved.structured_data["workflow"]["stage"] == "DRAWING"
    assert saved.erp_stage_code == "DRAWING"
    quest = saved.structured_data["quests"][0]
    assert quest["assignee_approval"]["approved_by"] == 58, "승인 기록이 actor 로 덮이면 안 된다"
    assert quest["completed_at"] == "2026-09-14T05:39:39"
    assert _events(order_id, "QUEST_APPROVAL_CHANGED") == [], "가짜 승인 이벤트가 또 남으면 안 된다"
    done = _events(order_id, "MEASUREMENT_COMPLETED")
    assert len(done) == 1
    assert "재전이" in str(done[0].payload.get("reason") or "")


# --------------------------------------------------------------------------- #
# 2. 대조군 — 권한 없는 팀(DRAWING) 은 403, 아무것도 안 움직인다
# --------------------------------------------------------------------------- #
def test_drawing_team_staff_is_denied_and_nothing_moves(client):
    _login(client, _make_user("dead_drawing", role="STAFF", team="DRAWING"))
    order_id = _create_order(stage="MEASURE", sd=_staging_4382_sd()).id

    resp = client.post(f"/api/orders/{order_id}/quest/approve", json={})
    assert resp.status_code == 403, resp.get_json()

    saved = _saved(order_id)
    assert saved.structured_data["workflow"]["stage"] == "MEASURE"
    assert db_session.query(OrderEvent).filter(OrderEvent.order_id == order_id).count() == 0


# --------------------------------------------------------------------------- #
# 3. 대조군 — 이미 다음 단계로 간 주문은 재전이 대상이 아니다
# --------------------------------------------------------------------------- #
def test_order_already_in_drawing_is_rejected_by_existing_axis(client):
    """stage DRAWING + COMPLETED MEASURE quest: DRAWING 은 command 전용이라 409 로 막히고 stage 불변."""
    _login(client, _make_user("dead_drawing_stage", role="STAFF", team="SALES"))
    order_id = _create_order(stage="DRAWING", sd=_staging_4382_sd(stage="DRAWING")).id

    resp = client.post(f"/api/orders/{order_id}/quest/approve", json={})
    assert resp.status_code == 409, resp.get_json()
    assert resp.get_json()["code"] == "COMMAND_REQUIRED"
    assert _saved(order_id).structured_data["workflow"]["stage"] == "DRAWING"
    assert _events(order_id, "MEASUREMENT_COMPLETED") == []


def test_order_already_in_production_after_confirm_is_already_transitioned(client):
    """stage PRODUCTION + COMPLETED CONFIRM quest 는 기존 ALREADY_TRANSITIONED 축 그대로다."""
    _login(client, _make_user("dead_prod_stage", role="STAFF", team="SALES"))
    sd = _lee_daeun_sd()
    sd["workflow"]["stage"] = "PRODUCTION"
    order_id = _create_order(stage="PRODUCTION", sd=sd).id

    resp = client.post(f"/api/orders/{order_id}/quest/approve", json={})
    assert resp.status_code == 409, resp.get_json()
    assert resp.get_json()["code"] == "ALREADY_TRANSITIONED"
    assert _events(order_id, "CUSTOMER_CONFIRMED") == []


# --------------------------------------------------------------------------- #
# 4. 팀 모드 RECEIVED COMPLETED 도 같은 규칙 — 팀 슬롯을 다시 쓰지 않는다, ADMIN 은 팀 없이도 200
# --------------------------------------------------------------------------- #
def _received_team_completed_sd() -> dict:
    return {
        "workflow": {"stage": "RECEIVED"},
        "quests": [{
            "stage": "RECEIVED", "title": "접수 확인", "status": "COMPLETED", "approval_mode": "team",
            "required_approvals": ["CS"],
            "team_approvals": {"CS": {"approved": True, "approved_by": 9, "approved_at": "2026-09-10T00:00:00"}},
            "completed_at": "2026-09-10T00:00:00",
        }],
    }


def test_team_mode_received_completed_retransitions_and_keeps_team_slot(client):
    _login(client, _make_user("dead_cs", role="STAFF", team="CS"))
    order_id = _create_order(stage="RECEIVED", sd=_received_team_completed_sd()).id

    resp = client.post(f"/api/orders/{order_id}/quest/approve", json={})
    assert resp.status_code == 200, resp.get_json()
    assert resp.get_json()["retransitioned"] is True
    assert resp.get_json()["next_stage"] == "실측"

    saved = _saved(order_id)
    assert saved.structured_data["workflow"]["stage"] == "MEASURE"
    quests = saved.structured_data["quests"]
    received = [q for q in quests if q["stage"] == "RECEIVED"][0]
    assert received["team_approvals"]["CS"]["approved_by"] == 9
    measure_open = [q for q in quests if q["stage"] == "MEASURE" and q["status"] == "OPEN"]
    assert len(measure_open) == 1, "RECEIVED→MEASURE 전이는 새 MEASURE quest 를 하나 만든다"
    assert _events(order_id, "QUEST_APPROVAL_CHANGED") == []


def test_admin_without_team_retransitions_team_mode_quest(client):
    """예전엔 팀 없는 ADMIN 이 400 '팀이 지정되지 않았습니다' 였다 — 재전이는 팀이 필요 없다."""
    _login(client, _make_user("dead_admin_noteam", role="ADMIN", team=None))
    order_id = _create_order(stage="RECEIVED", sd=_received_team_completed_sd()).id

    resp = client.post(f"/api/orders/{order_id}/quest/approve", json={})
    assert resp.status_code == 200, resp.get_json()
    assert resp.get_json()["retransitioned"] is True
    assert _saved(order_id).structured_data["workflow"]["stage"] == "MEASURE"


# --------------------------------------------------------------------------- #
# 5. 한글 저장형 '고객컨펌' COMPLETED 도 재전이 — PRODUCTION quest 미생성, blueprint 불변
# --------------------------------------------------------------------------- #
def _lee_daeun_sd() -> dict:
    """test_confirm_to_production_flow._lee_daeun_sd 와 같은 모양(복사)."""
    return {
        "workflow": {"stage": "CONFIRM", "history": [{"stage": "CONFIRM", "note": "도면 수령 확정"}]},
        "quests": [{
            "stage": "고객컨펌", "title": "고객 컨펌", "status": "COMPLETED", "approval_mode": "assignee",
            "required_approvals": ["CS", "SALES"], "team_approvals": {},
            "assignee_approval": {
                "approved": True, "approved_by": 12, "approved_by_name": "이다은담당",
                "approved_at": "2026-09-16T10:00:00",
            },
            "completed_at": "2026-09-16T10:00:00", "updated_at": "2026-09-16T10:00:00",
        }],
        "blueprint": {
            "customer_confirmed": True, "confirmed_at": "2026-09-16T10:00:00", "confirmed_by": "이다은담당",
        },
    }


def test_korean_stored_confirm_completed_retransitions_to_production(client):
    _login(client, _make_user("dead_confirm_sales", role="STAFF", team="SALES"))
    order_id = _create_order(stage="CONFIRM", sd=_lee_daeun_sd()).id

    resp = client.post(f"/api/orders/{order_id}/quest/approve", json={})
    assert resp.status_code == 200, resp.get_json()
    assert resp.get_json()["retransitioned"] is True
    assert resp.get_json()["next_stage"] == "생산"

    saved = _saved(order_id)
    sd = saved.structured_data
    assert sd["workflow"]["stage"] == "PRODUCTION"
    assert [q["stage"] for q in sd["quests"]] == ["고객컨펌"], "PRODUCTION quest 를 만들면 안 된다"
    assert sd["blueprint"]["confirmed_by"] == "이다은담당"
    assert sd["quests"][0]["assignee_approval"]["approved_by"] == 12
    assert len(_events(order_id, "CUSTOMER_CONFIRMED")) == 1


# --------------------------------------------------------------------------- #
# 6. 정상 OPEN 승인 응답에도 retransitioned 키가 False 로 항상 있다
# --------------------------------------------------------------------------- #
def test_normal_open_approval_response_carries_retransitioned_false(client):
    _login(client, _make_user("dead_normal", role="STAFF", team="SALES"))
    sd = _staging_4382_sd()
    sd["quests"][0].update(
        status="OPEN",
        assignee_approval={"approved": False, "approved_by": None, "approved_by_name": None, "approved_at": None},
    )
    sd["quests"][0].pop("completed_at")
    order_id = _create_order(stage="MEASURE", sd=sd).id

    resp = client.post(f"/api/orders/{order_id}/quest/approve", json={})
    assert resp.status_code == 200, resp.get_json()
    body = resp.get_json()
    assert "retransitioned" in body and body["retransitioned"] is False
    assert body["auto_transitioned"] is True
    assert len(_events(order_id, "QUEST_APPROVAL_CHANGED")) == 1


# --------------------------------------------------------------------------- #
# 7. 같은 Idempotency-Key 재전이 2회 → 두 번째는 409, 전이 이벤트 1건
# --------------------------------------------------------------------------- #
def test_same_idempotency_key_retransitions_once(client):
    _login(client, _make_user("dead_idem", role="STAFF", team="SALES"))
    order_id = _create_order(stage="CONFIRM", sd=_lee_daeun_sd()).id
    headers = {"Idempotency-Key": "retransition-idem-1"}

    first = client.post(f"/api/orders/{order_id}/quest/approve", json={}, headers=headers)
    second = client.post(f"/api/orders/{order_id}/quest/approve", json={}, headers=headers)

    assert first.status_code == 200, first.get_json()
    assert first.get_json()["retransitioned"] is True
    assert second.status_code == 409, second.get_json()
    assert second.get_json()["code"] == "ALREADY_TRANSITIONED"
    assert len(_events(order_id, "CUSTOMER_CONFIRMED")) == 1
    assert _saved(order_id).erp_stage_code == "PRODUCTION"


# --------------------------------------------------------------------------- #
# 8. 대조군 — 같은 단계에 COMPLETED 옆 OPEN quest 가 있으면 재전이가 아니라 정상 승인이다
# --------------------------------------------------------------------------- #
def test_duplicate_stage_quest_prefers_open_quest_over_retransition(client):
    """COMPLETED MEASURE 옆에 새 OPEN MEASURE 가 있으면 화면이 버튼을 그린 OPEN quest 를 승인한다.

    옛 quest 의 승인 기록은 그대로, OPEN 이던 quest 가 actor 승인으로 COMPLETED 가 되고 전이는
    정상 경로(QUEST_APPROVAL_CHANGED 1건, retransitioned False)로 간다. 화면 SSOT 도 같은 답이다.
    """
    from foms.services.erp_quest_display import build_current_quest_payload

    actor = _make_user("dead_dup_sales", role="STAFF", team="SALES")
    actor_id = actor.id
    _login(client, actor)
    sd = _staging_4382_sd()
    sd["quests"].append({
        "stage": "MEASURE", "title": "실측", "status": "OPEN", "approval_mode": "assignee",
        "required_approvals": ["CS", "SALES"], "team_approvals": {},
        "assignee_approval": {"approved": False, "approved_by": None, "approved_by_name": None, "approved_at": None},
        "created_at": "2026-09-20T10:00:00",
    })
    order = _create_order(stage="MEASURE", sd=sd)
    order_id = order.id

    screen = build_current_quest_payload(
        sd=sd, stage="실측", stage_code="MEASURE", order=order, current_user=actor, user_map={}
    )
    assert screen is not None
    assert screen["is_done"] is False
    assert screen["can_retransition"] is False
    assert screen["can_assignee_approve"] is True

    resp = client.post(f"/api/orders/{order_id}/quest/approve", json={})
    assert resp.status_code == 200, resp.get_json()
    body = resp.get_json()
    assert body["retransitioned"] is False
    assert body["auto_transitioned"] is True
    assert body["next_stage"] == "도면"

    saved = _saved(order_id)
    quests = saved.structured_data["quests"]
    old, fresh = quests[0], quests[1]
    assert old["assignee_approval"]["approved_by"] == 58
    assert old["completed_at"] == "2026-09-14T05:39:39"
    assert fresh["status"] == "COMPLETED"
    assert fresh["assignee_approval"]["approved_by"] == actor_id
    assert len(_events(order_id, "QUEST_APPROVAL_CHANGED")) == 1
    assert len(_events(order_id, "MEASUREMENT_COMPLETED")) == 1


def test_duplicate_team_quest_prefers_open_quest_over_retransition(client):
    """팀 모드 변형 — RECEIVED [COMPLETED, OPEN] 에 CS STAFF 가 {} 로 오면 OPEN quest 의 CS 슬롯을 쓴다."""
    actor = _make_user("dead_dup_cs", role="STAFF", team="CS")
    actor_id = actor.id
    _login(client, actor)
    sd = _received_team_completed_sd()
    sd["quests"].append({
        "stage": "RECEIVED", "title": "접수 확인", "status": "OPEN", "approval_mode": "team",
        "required_approvals": ["CS"], "team_approvals": {}, "created_at": "2026-09-20T10:00:00",
    })
    order_id = _create_order(stage="RECEIVED", sd=sd).id

    resp = client.post(f"/api/orders/{order_id}/quest/approve", json={})
    assert resp.status_code == 200, resp.get_json()
    assert resp.get_json()["retransitioned"] is False

    quests = _saved(order_id).structured_data["quests"]
    received = [q for q in quests if q["stage"] == "RECEIVED"]
    assert received[0]["team_approvals"]["CS"]["approved_by"] == 9, "옛 완료 quest 의 팀 슬롯은 그대로"
    assert received[1]["team_approvals"]["CS"]["approved_by"] == actor_id
    assert len(_events(order_id, "QUEST_APPROVAL_CHANGED")) == 1
