"""수동 quest 저장·권한(C6 F4, 2026-09-20) — PUT /quest/status 와 POST /quest.

예전엔 (1) PUT 이 stage 정확 일치만 봐서 한글 저장형('고객컨펌') quest 를 stage CONFIRM 에서 못 찾았고
(2) 예전 in-place 수정 경로(로드된 dict 제자리 수정 뒤 같은 객체 재대입)에선 200 을 주고도 저장이 안 됐으며 (3) STAFF 도 COMPLETED 로 만들 수 있었다.
이제 수동 COMPLETED 는 ADMIN/MANAGER 만 + 사유 필수, OPEN/IN_PROGRESS 는 STAFF 도 가능하고 실제로 저장된다.
"""
from __future__ import annotations

from werkzeug.security import generate_password_hash

from db import db_session
from models import Order, SecurityLog, User


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
        received_date="2026-09-16",
        customer_name="수동 고객",
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


def _open_quest(stage: str) -> dict:
    return {
        "stage": stage, "title": "고객 컨펌", "status": "OPEN", "approval_mode": "assignee",
        "required_approvals": ["CS", "SALES"], "team_approvals": {},
        "assignee_approval": {"approved": False, "approved_by": None, "approved_by_name": None, "approved_at": None},
        "created_at": "2026-09-16T00:00:00", "updated_at": "2026-09-16T00:00:00",
    }


def _measure_order(*, quests: list[dict] | None = None) -> Order:
    return _create_order(
        stage="MEASURE",
        sd={"workflow": {"stage": "MEASURE"}, "quests": quests if quests is not None else [_open_quest("MEASURE")]},
    )


def _saved_quest(order_id: int, index: int = 0) -> dict:
    db_session.expire_all()
    return db_session.get(Order, order_id).structured_data["quests"][index]


def _put_status(client, order_id: int, body: dict):
    return client.put(f"/api/orders/{order_id}/quest/status", json=body)


def _logs(action: str, order_id: int) -> list[SecurityLog]:
    """tests/domains/test_audit_action_coverage.py::_logs 와 같은 조회."""
    db_session.expire_all()
    return (
        db_session.query(SecurityLog)
        .filter(SecurityLog.action == action, SecurityLog.target_id == order_id)
        .order_by(SecurityLog.id.asc())
        .all()
    )


# --------------------------------------------------------------------------- #
# 1. STAFF 는 수동 COMPLETED 를 못 한다 — 403, 저장은 OPEN 그대로
# --------------------------------------------------------------------------- #
def test_staff_cannot_manually_complete_quest(client):
    _login(client, _make_user("man_staff", role="STAFF"))
    order_id = _measure_order().id

    resp = _put_status(client, order_id, {"status": "COMPLETED", "reason": "그냥"})
    assert resp.status_code == 403, resp.get_json()
    assert resp.get_json()["code"] == "ROLE_REQUIRED"
    assert _saved_quest(order_id)["status"] == "OPEN"


# --------------------------------------------------------------------------- #
# 2. MANAGER 라도 사유 없으면 400
# --------------------------------------------------------------------------- #
def test_manager_needs_reason_to_manually_complete(client):
    _login(client, _make_user("man_mgr_noreason", role="MANAGER"))
    order_id = _measure_order().id

    resp = _put_status(client, order_id, {"status": "COMPLETED", "reason": "   "})
    assert resp.status_code == 400, resp.get_json()
    assert resp.get_json()["code"] == "REASON_REQUIRED"
    assert _saved_quest(order_id)["status"] == "OPEN"


# --------------------------------------------------------------------------- #
# 3. MANAGER + 사유 → 200, 재조회에 COMPLETED·manual_status·completed_at 이 실제로 저장돼 있다
# --------------------------------------------------------------------------- #
def test_manager_with_reason_completes_and_it_is_persisted(client):
    manager = _make_user("man_mgr", role="MANAGER")
    manager_id = manager.id
    _login(client, manager)
    order_id = _measure_order().id

    resp = _put_status(client, order_id, {"status": "COMPLETED", "reason": "고객이 전화로 실측 완료 확인"})
    assert resp.status_code == 200, resp.get_json()

    quest = _saved_quest(order_id)
    assert quest["status"] == "COMPLETED", "예전 in-place 수정 경로(로드된 dict 제자리 수정 뒤 같은 객체 재대입)에선 200 을 주고도 저장되지 않았다"
    assert quest["completed_at"]
    assert quest["manual_status"]["reason"] == "고객이 전화로 실측 완료 확인"
    assert quest["manual_status"]["by"] == manager_id
    assert quest["manual_status"]["status"] == "COMPLETED"


# --------------------------------------------------------------------------- #
# 4. 한글 저장형 '고객컨펌' quest 를 stage CONFIRM 에서 찾는다(예전 404)
# --------------------------------------------------------------------------- #
def test_korean_stored_quest_is_found_by_stage_alias(client):
    _login(client, _make_user("man_admin_kr", role="ADMIN"))
    order_id = _create_order(
        stage="CONFIRM",
        sd={"workflow": {"stage": "CONFIRM"}, "quests": [_open_quest("고객컨펌")]},
    ).id

    resp = _put_status(client, order_id, {"status": "IN_PROGRESS"})
    assert resp.status_code == 200, resp.get_json()
    quest = _saved_quest(order_id)
    assert quest["stage"] == "고객컨펌" and quest["status"] == "IN_PROGRESS"


# --------------------------------------------------------------------------- #
# 5. STAFF 의 IN_PROGRESS 는 200 이고 저장된다(사유 선택)
# --------------------------------------------------------------------------- #
def test_staff_can_set_in_progress_and_it_is_persisted(client):
    _login(client, _make_user("man_staff_prog", role="STAFF"))
    order_id = _measure_order().id

    resp = _put_status(client, order_id, {"status": "IN_PROGRESS", "owner_person": "담당 김"})
    assert resp.status_code == 200, resp.get_json()
    quest = _saved_quest(order_id)
    assert quest["status"] == "IN_PROGRESS"
    assert quest["owner_person"] == "담당 김"
    assert "manual_status" not in quest


# --------------------------------------------------------------------------- #
# 6. POST /quest — 한글 저장형이 있으면 400, 없으면 만들고 실제로 저장된다
# --------------------------------------------------------------------------- #
def test_post_quest_rejects_duplicate_when_korean_stored_quest_exists(client):
    _login(client, _make_user("man_post_dup", role="ADMIN"))
    order_id = _create_order(
        stage="CONFIRM",
        sd={"workflow": {"stage": "CONFIRM"}, "quests": [_open_quest("고객컨펌")]},
    ).id

    resp = client.post(f"/api/orders/{order_id}/quest", json={"stage": "CONFIRM"})
    assert resp.status_code == 400, resp.get_json()
    assert "이미" in resp.get_json()["message"]
    db_session.expire_all()
    assert len(db_session.get(Order, order_id).structured_data["quests"]) == 1


def test_post_quest_creates_and_persists_when_missing(client):
    _login(client, _make_user("man_post_new", role="ADMIN"))
    order_id = _create_order(stage="MEASURE", sd={"workflow": {"stage": "MEASURE"}, "quests": []}).id

    resp = client.post(f"/api/orders/{order_id}/quest", json={"stage": "MEASURE"})
    assert resp.status_code in (200, 201), resp.get_json()
    assert resp.get_json()["success"] is True
    db_session.expire_all()
    quests = db_session.get(Order, order_id).structured_data["quests"]
    assert len(quests) == 1, "예전 in-place 수정 경로(로드된 dict 제자리 수정 뒤 같은 객체 재대입)에선 200 을 주고도 quest 가 저장되지 않았다"
    assert quests[0]["stage"] in ("MEASURE", "실측")


# --------------------------------------------------------------------------- #
# 7. 감사 원장 QUEST_STATUS_CHANGED.detail.reason 이 요청 사유와 같다
# --------------------------------------------------------------------------- #
def test_audit_log_carries_manual_reason(client):
    _login(client, _make_user("man_audit", role="MANAGER"))
    order_id = _measure_order().id

    resp = _put_status(client, order_id, {"status": "COMPLETED", "reason": "현장 사진으로 확인"})
    assert resp.status_code == 200, resp.get_json()

    rows = _logs("QUEST_STATUS_CHANGED", order_id)
    assert len(rows) == 1
    assert rows[0].detail["reason"] == "현장 사진으로 확인"
    assert rows[0].detail["status"] == "COMPLETED"
