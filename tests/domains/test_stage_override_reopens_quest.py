"""강제 단계 변경(regress)이 되돌아간 단계의 완료 quest 를 다시 OPEN 으로 돌린다(C2, 2026-09-20).

스테이징 #4382: DRAWING→MEASURE regress 뒤 MEASURE quest 가 COMPLETED 그대로라 완료 배지만 남고
승인 버튼이 사라져 막다른 길이 됐다. 이제 regress 는 그 단계 COMPLETED quest 1건(가장 최근)을
OPEN 으로 되돌리고 ``reopened_by_override`` 흔적과 STAGE_OVERRIDE payload ``quest_reopened`` 를 남긴다.
advance 는 손대지 않고, 나중 단계 quest(CONFIRM 등)는 그대로 둔다.
"""
from __future__ import annotations

from werkzeug.security import generate_password_hash

from db import db_session
from foms.services.orders.stage_override import apply_stage_override
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


def _completed_quest(stage: str, *, completed_at: str = "2026-09-14T05:39:39") -> dict:
    return {
        "stage": stage, "title": "실측", "status": "COMPLETED", "approval_mode": "assignee",
        "required_approvals": ["CS", "SALES"], "team_approvals": {},
        "assignee_approval": {
            "approved": True, "approved_by": 58, "approved_by_name": "claude_master",
            "approved_at": completed_at,
        },
        "completed_at": completed_at, "updated_at": completed_at,
    }


def _override(client, order_id: int, to_stage: str, reason: str = "검증 뒤 원상 복구"):
    return client.post(
        f"/api/orders/{order_id}/workflow/stage-override",
        json={"to_stage": to_stage, "reason": reason, "confirm": True},
    )


def _override_events(order_id: int) -> list[OrderEvent]:
    return (
        db_session.query(OrderEvent)
        .filter(OrderEvent.order_id == order_id, OrderEvent.event_type == "STAGE_OVERRIDE")
        .order_by(OrderEvent.id.asc())
        .all()
    )


def _saved(order_id: int) -> Order:
    db_session.expire_all()
    return db_session.get(Order, order_id)


# --------------------------------------------------------------------------- #
# 1. DRAWING→MEASURE regress 는 MEASURE COMPLETED quest 를 OPEN 으로 돌린다
# --------------------------------------------------------------------------- #
def test_regress_reopens_completed_quest_of_target_stage(client):
    _login(client, _make_user("ovr_admin"))
    sd = {"workflow": {"stage": "DRAWING"}, "quests": [_completed_quest("MEASURE")]}
    order_id = _create_order(stage="DRAWING", sd=sd).id

    resp = _override(client, order_id, "MEASURE", reason="도면 전달 검증 뒤 복구")
    assert resp.status_code == 200, resp.get_json()

    saved = _saved(order_id)
    assert saved.structured_data["workflow"]["stage"] == "MEASURE"
    quest = saved.structured_data["quests"][0]
    assert quest["status"] == "OPEN"
    assert "completed_at" not in quest
    assert not (quest.get("assignee_approval") or {}).get("approved")
    assert quest["reopened_by_override"]["from_stage"] == "DRAWING"
    assert quest["reopened_by_override"]["reason"] == "도면 전달 검증 뒤 복구"

    events = _override_events(order_id)
    assert len(events) == 1
    assert events[0].payload["quest_reopened"] == "MEASURE"


# --------------------------------------------------------------------------- #
# 2. 한글 저장형 '실측' 도 같은 단계로 본다
# --------------------------------------------------------------------------- #
def test_regress_reopens_korean_stored_quest(client):
    _login(client, _make_user("ovr_admin_kr"))
    sd = {"workflow": {"stage": "DRAWING"}, "quests": [_completed_quest("실측")]}
    order_id = _create_order(stage="DRAWING", sd=sd).id

    resp = _override(client, order_id, "MEASURE")
    assert resp.status_code == 200, resp.get_json()
    quest = _saved(order_id).structured_data["quests"][0]
    assert quest["stage"] == "실측" and quest["status"] == "OPEN"
    assert _override_events(order_id)[0].payload["quest_reopened"] == "MEASURE"


# --------------------------------------------------------------------------- #
# 3. 대조군 — advance 는 quest 를 건드리지 않는다
# --------------------------------------------------------------------------- #
def test_advance_leaves_completed_quest_untouched(client):
    _login(client, _make_user("ovr_admin_adv"))
    sd = {"workflow": {"stage": "RECEIVED"}, "quests": [_completed_quest("MEASURE")]}
    order_id = _create_order(stage="RECEIVED", sd=sd).id

    resp = _override(client, order_id, "MEASURE")
    assert resp.status_code == 200, resp.get_json()
    assert resp.get_json()["data"]["mode"] == "advance"
    quest = _saved(order_id).structured_data["quests"][0]
    assert quest["status"] == "COMPLETED" and quest["completed_at"] == "2026-09-14T05:39:39"
    assert "reopened_by_override" not in quest
    assert "quest_reopened" not in _override_events(order_id)[0].payload


# --------------------------------------------------------------------------- #
# 4. 대조군 — 나중 단계 quest(CONFIRM) 는 삭제도 변경도 하지 않는다
# --------------------------------------------------------------------------- #
def test_regress_keeps_later_stage_quest_completed(client):
    _login(client, _make_user("ovr_admin_later"))
    confirm = {**_completed_quest("CONFIRM", completed_at="2026-09-16T10:00:00"), "title": "고객 컨펌"}
    sd = {"workflow": {"stage": "PRODUCTION"}, "quests": [_completed_quest("MEASURE"), confirm]}
    order_id = _create_order(stage="PRODUCTION", sd=sd).id

    resp = _override(client, order_id, "MEASURE")
    assert resp.status_code == 200, resp.get_json()
    quests = _saved(order_id).structured_data["quests"]
    assert [q["stage"] for q in quests] == ["MEASURE", "CONFIRM"]
    assert quests[0]["status"] == "OPEN"
    assert quests[1]["status"] == "COMPLETED" and quests[1]["completed_at"] == "2026-09-16T10:00:00"


# --------------------------------------------------------------------------- #
# 5. 같은 단계 COMPLETED 2건이면 completed_at 최신 1건만 되돌린다
# --------------------------------------------------------------------------- #
def test_regress_reopens_only_the_latest_of_duplicate_completed_quests(client):
    _login(client, _make_user("ovr_admin_dup"))
    older = _completed_quest("MEASURE", completed_at="2026-09-01T00:00:00")
    newer = _completed_quest("MEASURE", completed_at="2026-09-14T05:39:39")
    sd = {"workflow": {"stage": "DRAWING"}, "quests": [newer, older]}
    order_id = _create_order(stage="DRAWING", sd=sd).id

    resp = _override(client, order_id, "MEASURE")
    assert resp.status_code == 200, resp.get_json()
    quests = _saved(order_id).structured_data["quests"]
    assert quests[0]["status"] == "OPEN" and "completed_at" not in quests[0]
    assert quests[1]["status"] == "COMPLETED" and quests[1]["completed_at"] == "2026-09-01T00:00:00"


# --------------------------------------------------------------------------- #
# 6. 원본 참조 무변경 — 셸 복사된 sd 의 quests 리스트·dict 를 제자리에서 바꾸지 않는다
# --------------------------------------------------------------------------- #
def test_apply_stage_override_does_not_mutate_original_quest_list_in_place(app):
    user = _make_user("ovr_unit")
    sd = {"workflow": {"stage": "DRAWING"}, "quests": [_completed_quest("MEASURE")]}
    order = _create_order(stage="DRAWING", sd=sd)
    orig_quests = order.structured_data["quests"]
    orig_first = orig_quests[0]

    payload = apply_stage_override(
        order=order, to_stage="MEASURE", reason="단위 검증", user_id=user.id, db=db_session,
    )

    assert payload["mode"] == "regress" and payload["quest_reopened"] == "MEASURE"
    assert orig_first["status"] == "COMPLETED", "원본 quest dict 가 제자리에서 바뀌면 안 된다"
    assert orig_quests[0] is orig_first, "원본 리스트가 제자리에서 바뀌면 안 된다"
    assert order.structured_data["quests"] is not orig_quests
    assert order.structured_data["quests"][0]["status"] == "OPEN"
    db_session.rollback()


# --------------------------------------------------------------------------- #
# 7. 되돌린 뒤 SALES STAFF 승인 → 정상 경로(retransitioned False)로 DRAWING 까지 간다
# --------------------------------------------------------------------------- #
def test_reopened_quest_can_be_approved_normally_to_drawing(client):
    _login(client, _make_user("ovr_admin_e2e"))
    sd = {"workflow": {"stage": "DRAWING"}, "quests": [_completed_quest("MEASURE")]}
    order_id = _create_order(stage="DRAWING", sd=sd).id
    assert _override(client, order_id, "MEASURE").status_code == 200

    staff = _make_user("ovr_sales_staff", role="STAFF", team="SALES")
    staff_id = staff.id
    _login(client, staff)
    resp = client.post(f"/api/orders/{order_id}/quest/approve", json={})
    assert resp.status_code == 200, resp.get_json()
    body = resp.get_json()
    assert body["retransitioned"] is False
    assert body["auto_transitioned"] is True and body["next_stage"] == "도면"

    saved = _saved(order_id)
    assert saved.structured_data["workflow"]["stage"] == "DRAWING"
    quest = saved.structured_data["quests"][0]
    assert quest["status"] == "COMPLETED"
    assert quest["assignee_approval"]["approved_by"] == staff_id
    assert quest["reopened_by_override"]["from_stage"] == "DRAWING"
