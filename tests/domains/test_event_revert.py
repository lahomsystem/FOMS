"""EVENT-REVERT-01 계약 테스트 — generic JSON-path revert 제거·typed compensation.

`foms/api/events.py` 의 generic revert route(임의 target 을 JSON-path 로 되돌리던 위험
엔드포인트) 는 제거됐다. 되돌리기는 event_type 화이트리스트에 등록된 **typed
compensation** 만 허용하며, 각 compensation 은 만지는 key·효과가 코드로 고정이다.

고정 계약:
* 구 generic revert route ``.../revert`` direct POST → 404(엔드포인트 제거).
* 미등록 event_type(임의 target/JSON-path) → 400, structured_data 변화 0(arbitrary target 0).
* 등록된 typed compensation(DRAWING_ASSIGNEE_SET) → 200, 고정 target 만 복원·보상 event 기록.
* 후속 변경으로 현재 값이 event 의 after 예상과 다르면 409, 변화 0.

기본 lane 은 root conftest 의 SQLite in-memory ``client``/``app`` 픽스처(외부 의존 0).
"""
from __future__ import annotations

from werkzeug.security import generate_password_hash

from db import db_session
from models import Order, OrderEvent, User


def _make_user(*, username: str, role: str = "STAFF", team: str = "DRAWING") -> int:
    user = User(
        username=username,
        password=generate_password_hash("pw"),
        role=role,
        team=team,
        name=f"{username}-name",
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    return user.id


def _login(client, uid: int, *, username: str, role: str) -> None:
    with client.session_transaction() as sess:
        sess["user_id"] = uid
        sess["username"] = username
        sess["role"] = role


def _create_order(structured_data: dict) -> int:
    order = Order(
        received_date="2026-04-07",
        customer_name="되돌리기 대상",
        phone="010-0000-0000",
        address="Seoul",
        product="Wardrobe",
        status="DRAWING",
        manager_name="Alice",
        is_erp_order=True,
        structured_data=structured_data,
    )
    db_session.add(order)
    db_session.commit()
    return order.id


def _create_event(*, order_id: int, event_type: str, payload: dict, creator_id: int) -> int:
    event = OrderEvent(
        order_id=order_id,
        event_type=event_type,
        payload=payload,
        created_by_user_id=creator_id,
    )
    db_session.add(event)
    db_session.commit()
    return event.id


def _fresh_order(oid: int) -> Order:
    db_session.remove()
    return db_session.query(Order).filter_by(id=oid).first()


# ── 1) 구 generic revert route 제거(direct POST → 404) ────────────────────────


def test_generic_revert_route_removed_returns_404(client, app):
    """구 ``.../revert`` route 는 제거됐다 — direct POST 는 404(엔드포인트 부재)."""
    admin_id = _make_user(username="admin-revert", role="ADMIN")
    _login(client, admin_id, username="admin-revert", role="ADMIN")
    oid = _create_order({"workflow": {"stage": "DRAWING"}})
    eid = _create_event(
        order_id=oid,
        event_type="DRAWING_ASSIGNEE_SET",
        payload={"target": "assignments.drawing_assignee_user_ids", "before_ids": [], "after_ids": []},
        creator_id=admin_id,
    )

    resp = client.post(
        f"/api/orders/{oid}/change-events/{eid}/revert",
        json={"reason": "구 route 시도"},
    )
    assert resp.status_code == 404


# ── 2) 임의 target(JSON-path) 되돌리기 불가(arbitrary target 0) ────────────────


def test_arbitrary_json_path_target_not_revertable(client, app):
    """미등록 event_type(임의 target/JSON-path) → 400, structured_data 변화 0."""
    admin_id = _make_user(username="admin-arb", role="ADMIN")
    _login(client, admin_id, username="admin-arb", role="ADMIN")
    oid = _create_order({"workflow": {"stage": "DRAWING"}, "secret": {"flag": "keep"}})
    # 구 generic revert 라면 이 payload 로 workflow.stage / secret.flag 를 임의 write 했을 것.
    eid = _create_event(
        order_id=oid,
        event_type="STAGE_CHANGED",  # registry 미등록
        payload={"target": "workflow.stage", "before": "RECEIVED", "after": "DRAWING"},
        creator_id=admin_id,
    )

    resp = client.post(
        f"/api/orders/{oid}/change-events/{eid}/compensate",
        json={"reason": "임의 경로 되돌리기 시도"},
    )
    assert resp.status_code == 400
    assert resp.get_json()["success"] is False

    order = _fresh_order(oid)
    # 임의 JSON-path 는 전혀 바뀌지 않는다.
    assert order.structured_data["workflow"]["stage"] == "DRAWING"
    assert order.structured_data["secret"]["flag"] == "keep"
    # 보상 event 도 기록되지 않는다.
    reverts = db_session.query(OrderEvent).filter_by(order_id=oid, event_type="CHANGE_REVERTED").count()
    assert reverts == 0


# ── 3) 등록된 typed compensation 만 동작(DRAWING_ASSIGNEE_SET → 200) ───────────


def test_registered_typed_compensation_reverts_drawing_assignee(client, app):
    """등록된 DRAWING_ASSIGNEE_SET compensation → 200, 고정 target 만 복원·보상 event 기록."""
    admin_id = _make_user(username="admin-typed", role="ADMIN")
    prev_id = _make_user(username="prev-assignee")
    now_id = _make_user(username="now-assignee")
    _login(client, admin_id, username="admin-typed", role="ADMIN")

    # 현재(after) 상태: now_id 가 담당. before: prev_id.
    oid = _create_order(
        {
            "assignments": {"drawing_assignee_user_ids": [now_id]},
            "drawing_assignees": [{"id": now_id, "name": "now-assignee-name", "team": "DRAWING"}],
            "shipment": {"drawing_managers": ["now-assignee-name"]},
            "workflow": {"stage": "DRAWING"},
        }
    )
    eid = _create_event(
        order_id=oid,
        event_type="DRAWING_ASSIGNEE_SET",
        payload={
            "domain": "DRAWING_DOMAIN",
            "target": "assignments.drawing_assignee_user_ids",
            "before": "prev-assignee-name",
            "after": "now-assignee-name",
            "before_ids": [prev_id],
            "after_ids": [now_id],
        },
        creator_id=admin_id,
    )

    resp = client.post(
        f"/api/orders/{oid}/change-events/{eid}/compensate",
        json={"reason": "잘못 지정하여 원복"},
    )
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["success"] is True
    assert body["reverted_target"] == "assignments.drawing_assignee_user_ids"

    order = _fresh_order(oid)
    # 고정 target + 파생 projection 이 before 상태로 복원.
    assert order.structured_data["assignments"]["drawing_assignee_user_ids"] == [prev_id]
    assert [a["id"] for a in order.structured_data["drawing_assignees"]] == [prev_id]
    assert order.structured_data["shipment"]["drawing_managers"] == ["prev-assignee-name"]
    # workflow 같은 무관 key 는 불변.
    assert order.structured_data["workflow"]["stage"] == "DRAWING"
    # append-only 보상 event 1건.
    reverts = db_session.query(OrderEvent).filter_by(order_id=oid, event_type="CHANGE_REVERTED").all()
    assert len(reverts) == 1
    assert reverts[0].payload["original_event_type"] == "DRAWING_ASSIGNEE_SET"


# ── 4) 미등록 event_type 거부(typed 만 허용) ─────────────────────────────────


def test_unregistered_event_type_rejected(client, app):
    """registry 에 없는 event_type → 400, 되돌리기 미수행."""
    admin_id = _make_user(username="admin-unreg", role="ADMIN")
    _login(client, admin_id, username="admin-unreg", role="ADMIN")
    oid = _create_order({"assignments": {"drawing_assignee_user_ids": [admin_id]}})
    eid = _create_event(
        order_id=oid,
        event_type="MEMO_UPDATED",  # registry 미등록
        payload={"target": "memo", "before": "old", "after": "new"},
        creator_id=admin_id,
    )

    resp = client.post(
        f"/api/orders/{oid}/change-events/{eid}/compensate",
        json={"reason": "미등록 유형 되돌리기"},
    )
    assert resp.status_code == 400
    reverts = db_session.query(OrderEvent).filter_by(order_id=oid, event_type="CHANGE_REVERTED").count()
    assert reverts == 0


# ── 5) 후속 변경 발생 시 409(compensation 불변) ──────────────────────────────


def test_compensation_conflict_when_state_moved(client, app):
    """현재 값이 event 의 after 예상과 다르면 409, structured_data 변화 0."""
    admin_id = _make_user(username="admin-conf", role="ADMIN")
    prev_id = _make_user(username="conf-prev")
    now_id = _make_user(username="conf-now")
    other_id = _make_user(username="conf-other")
    _login(client, admin_id, username="admin-conf", role="ADMIN")

    # 현재 상태는 other_id(후속 변경) — event 의 after_ids=[now_id] 와 다르다.
    oid = _create_order({"assignments": {"drawing_assignee_user_ids": [other_id]}})
    eid = _create_event(
        order_id=oid,
        event_type="DRAWING_ASSIGNEE_SET",
        payload={
            "target": "assignments.drawing_assignee_user_ids",
            "before_ids": [prev_id],
            "after_ids": [now_id],
        },
        creator_id=admin_id,
    )

    resp = client.post(
        f"/api/orders/{oid}/change-events/{eid}/compensate",
        json={"reason": "충돌 상황"},
    )
    assert resp.status_code == 409

    order = _fresh_order(oid)
    assert order.structured_data["assignments"]["drawing_assignee_user_ids"] == [other_id]


# ── 6) 권한 고정: 비-ADMIN·비-생성자 403 ─────────────────────────────────────


def test_non_creator_non_admin_forbidden(client, app):
    """ADMIN 도 생성자도 아니면 403(권한 typed compensation 내부 고정)."""
    creator_id = _make_user(username="rev-creator", role="STAFF")
    other_id = _make_user(username="rev-other", role="STAFF")
    _login(client, other_id, username="rev-other", role="STAFF")
    oid = _create_order({"assignments": {"drawing_assignee_user_ids": [creator_id]}})
    eid = _create_event(
        order_id=oid,
        event_type="DRAWING_ASSIGNEE_SET",
        payload={"target": "assignments.drawing_assignee_user_ids", "before_ids": [], "after_ids": [creator_id]},
        creator_id=creator_id,
    )

    resp = client.post(
        f"/api/orders/{oid}/change-events/{eid}/compensate",
        json={"reason": "타인이 되돌리기 시도"},
    )
    assert resp.status_code == 403


# ── 7) 정책 가드 활성화 시 STAFF 생성자 통과·비-생성자 handler 403 ────────────


def test_policy_guard_allows_staff_creator_blocks_other(client, app):
    """AUTH_POLICY_ENABLED 활성 하에서도 STAFF_MUTATION 가드가 도면 STAFF 생성자를 통과시켜
    compensate 200(before_request 가 조기 403 하지 않음). 무관한 STAFF 비-생성자는 가드는
    통과하나 handler 의 creator 검사로 403.
    """
    creator_id = _make_user(username="guard-creator", role="STAFF", team="DRAWING")
    prev_id = _make_user(username="guard-prev", role="STAFF", team="DRAWING")
    other_id = _make_user(username="guard-other", role="STAFF", team="CS")
    oid = _create_order({"assignments": {"drawing_assignee_user_ids": [creator_id]}})
    eid = _create_event(
        order_id=oid,
        event_type="DRAWING_ASSIGNEE_SET",
        payload={
            "target": "assignments.drawing_assignee_user_ids",
            "before_ids": [prev_id],
            "after_ids": [creator_id],
        },
        creator_id=creator_id,
    )

    app.config["AUTH_POLICY_ENABLED"] = True
    try:
        _login(client, creator_id, username="guard-creator", role="STAFF")
        resp_ok = client.post(
            f"/api/orders/{oid}/change-events/{eid}/compensate",
            json={"reason": "생성자 원복"},
        )
        _login(client, other_id, username="guard-other", role="STAFF")
        resp_forbidden = client.post(
            f"/api/orders/{oid}/change-events/{eid}/compensate",
            json={"reason": "타 STAFF 시도"},
        )
    finally:
        app.config.pop("AUTH_POLICY_ENABLED", None)

    assert resp_ok.status_code == 200, resp_ok.get_json()
    assert resp_forbidden.status_code == 403
