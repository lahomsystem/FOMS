"""관리자 강제 진행(admin_override) 공통 판정 + 강제 단계 변경 확장 목표 계약.

두 축을 절대 섞지 않는다는 것을 고정한다.

* 권한 축(admin_override): ADMIN 이 사유를 적고 업무 게이트를 건너뛴다.
* 정합 축: If-Match·동일 상태·모델에 길 없음(AS_NO_PATH)·삭제된 주문은 관리자도 못 뚫는다.

기존 "관리자도 막힌다" 테스트는 지우지 않고 음성 대조군으로 남겨 두었다
(``test_workflow_stage_override.py``·``test_state_form.py``).
"""

from __future__ import annotations

import pytest
from werkzeug.security import generate_password_hash

from db import db_session
from foms.services.orders.admin_override import (
    AdminOverride,
    admin_override_error,
    resolve_admin_override,
)
from models import Order, OrderConstructionAttempt, OrderEvent, User


def _make_user(username: str, role: str = "ADMIN") -> User:
    """테스트 사용자 1명을 만든다."""
    user = User(
        username=username,
        password=generate_password_hash("pw"),
        role=role,
        team="CS",
        name=f"{username}-이름",
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    return user


def _login(client, username: str, role: str = "ADMIN") -> User:
    """사용자를 만들고 세션에 로그인시킨다."""
    user = _make_user(username, role)
    with client.session_transaction() as sess:
        sess["user_id"] = user.id
        sess["username"] = user.username
        sess["role"] = user.role
    return user


def _make_order(*, status: str = "DRAWING", structured: dict | None = None) -> Order:
    """ERP 주문 1건(기본 도면 단계)."""
    sd = {"workflow": {"stage": status}}
    if structured:
        sd.update(structured)
    order = Order(
        received_date="2026-09-01",
        customer_name="강제-고객",
        phone="010-5555-6666",
        address="Seoul",
        product="붙박이장",
        status=status,
        manager_name="Mgr",
        is_erp_order=True,
        structured_data=sd,
    )
    db_session.add(order)
    db_session.commit()
    return order


def _event_types(order_id: int) -> list[str]:
    """주문에 쌓인 이벤트 종류 목록."""
    return [
        e.event_type
        for e in db_session.query(OrderEvent).filter(OrderEvent.order_id == order_id).all()
    ]


def _override_body(to_stage: str, reason: str = "관리자 판단으로 강제 진행") -> dict:
    """강제 단계 변경 + 관리자 강제 진행 요청 본문."""
    return {
        "to_stage": to_stage,
        "reason": reason,
        "confirm": True,
        "admin_override": True,
        "override_reason": reason,
    }


# --- 1) 판정 헬퍼 단위 -------------------------------------------------------
def test_resolve_admin_override_only_for_admin_with_reason(client, app):
    """ADMIN + 사유면 객체, MANAGER·STAFF 는 403, 사유 공백은 422, dict 모양은 400.

    거부 응답은 ``jsonify`` 라 app context 안에서 만들어진다(라우트와 같은 조건).
    """
    admin = _make_user("ovc_admin", role="ADMIN")
    manager = _make_user("ovc_manager", role="MANAGER")
    staff = _make_user("ovc_staff", role="STAFF")
    admin_id, admin_name = admin.id, admin.name  # 요청 뒤 detach 회피용 primitive 캡처
    body = {"admin_override": True, "override_reason": "  사유 있음  "}

    got = resolve_admin_override(admin, body)
    assert isinstance(got, AdminOverride)
    assert got.reason == "사유 있음" and got.actor_role == "ADMIN"
    assert got.actor_id == admin_id and got.actor_name == admin_name
    assert resolve_admin_override(manager, body) is None

    blank = {"admin_override": True, "override_reason": "   "}
    assert resolve_admin_override(admin, blank) is None
    shaped = {"admin_override": {"12": True}, "override_reason": "주문별 모양"}

    # 거부 응답은 jsonify 를 쓰므로 앱 컨텍스트 안에서 본다.
    with client.application.app_context():
        assert admin_override_error(admin, body) is None
        assert admin_override_error(manager, body)[1] == 403
        assert admin_override_error(manager, body)[0].get_json()["code"] == "ADMIN_ONLY"
        assert admin_override_error(staff, body)[1] == 403
        assert admin_override_error(admin, blank)[1] == 422
        assert admin_override_error(admin, blank)[0].get_json()["code"] == "REASON_REQUIRED"
        assert admin_override_error(admin, shaped)[1] == 400
        assert admin_override_error(admin, shaped)[0].get_json()["code"] == "ADMIN_OVERRIDE_SHAPE"


def test_resolve_reads_reason_field_and_ignores_other_axis(client):
    """사유는 override_reason → 없으면 reason 을 읽고, emergency_override 는 다른 축이다."""
    admin = _make_user("ovc_axis", role="ADMIN")
    assert resolve_admin_override(admin, {"admin_override": True, "reason": "본문 사유"}).reason == (
        "본문 사유"
    )
    # 키가 없거나 다른 축만 실린 요청은 뚫기가 아니다(축 분리).
    assert resolve_admin_override(admin, {"reason": "그냥 사유"}) is None
    assert resolve_admin_override(admin, {"emergency_override": True, "reason": "소유 축"}) is None
    with client.application.app_context():
        assert admin_override_error(admin, {"emergency_override": True}) is None


# --- 2) AS 3종 목표 ----------------------------------------------------------
def test_denied_attempt_leaves_only_a_security_log(client):
    """거부된 뚫기 시도는 감사 원장에만 남고 주문 이력에는 남지 않는다(일어나지 않은 일)."""
    from models import SecurityLog

    _login(client, "ovc_denied", role="MANAGER")
    order_id = _make_order(status="MEASURE").id
    resp = client.post(
        f"/api/orders/{order_id}/workflow/stage-override", json=_override_body("AS_RECEIVED")
    )
    assert resp.status_code == 403 and resp.get_json()["code"] == "ADMIN_ONLY"

    db_session.expire_all()
    assert _event_types(order_id) == []
    logs = (
        db_session.query(SecurityLog)
        .filter(SecurityLog.action == "ADMIN_OVERRIDE_DENIED", SecurityLog.target_id == order_id)
        .all()
    )
    assert len(logs) == 1
    assert logs[0].detail["gate"] == "ADMIN_ONLY"
    assert logs[0].detail["route"] == "orders.stage_override"


def test_admin_override_opens_as_cycle_and_keeps_main_stage(client):
    """ADMIN + admin_override 면 AS 접수로 강제 변경되고 본공정 단계는 그대로다."""
    _login(client, "ovc_as_open", role="ADMIN")
    order = _make_order(status="MEASURE")
    order_id = order.id

    resp = client.post(
        f"/api/orders/{order_id}/workflow/stage-override", json=_override_body("AS_RECEIVED")
    )
    assert resp.status_code == 200, resp.get_json()
    data = resp.get_json()["data"]
    assert data["to"] == "AS_RECEIVED" and data["mode"] == "admin_override"

    db_session.expire_all()
    saved = db_session.get(Order, order_id)
    lifecycle = saved.structured_data["as_lifecycle"]
    assert lifecycle["cycles"] and lifecycle["current_cycle_id"]
    # 본공정 stage 는 AS 문자열로 오염되지 않는다(두 축 분리).
    assert saved.structured_data["workflow"]["stage"] == "MEASURE"
    types = _event_types(order_id)
    assert types.count("AS_REGISTERED") == 1
    assert types.count("ADMIN_OVERRIDE_USED") == 1


def test_admin_override_event_payload_keys(client):
    """ADMIN_OVERRIDE_USED payload 키 9종이 계약 그대로다."""
    user = _login(client, "ovc_payload", role="ADMIN")
    user_id, user_name = user.id, user.name  # 요청 뒤 detach 회피용 primitive 캡처
    order_id = _make_order(status="MEASURE").id
    resp = client.post(
        f"/api/orders/{order_id}/workflow/stage-override",
        json=_override_body("AS_RECEIVED", "AS 접수를 강제로 연다"),
    )
    assert resp.status_code == 200, resp.get_json()

    event = (
        db_session.query(OrderEvent)
        .filter(OrderEvent.order_id == order_id, OrderEvent.event_type == "ADMIN_OVERRIDE_USED")
        .one()
    )
    payload = event.payload
    assert set(payload) == {
        "gate", "gates", "route", "axis", "from", "to", "reason", "actor", "bulk",
    }
    assert payload["gate"] == "OVERRIDE_TARGET" and payload["gates"] == ["OVERRIDE_TARGET"]
    assert payload["axis"] == "AS" and payload["to"] == "AS_RECEIVED"
    assert payload["reason"] == "AS 접수를 강제로 연다" and payload["bulk"] is False
    assert payload["actor"] == {"id": user_id, "name": user_name, "role": "ADMIN"}
    assert event.created_by_user_id == user_id


def test_admin_override_cannot_rewind_running_as(client):
    """진행 중 AS 를 접수로 되돌리는 길은 모델에 없다 — admin_override 로도 409."""
    _login(client, "ovc_as_rewind", role="ADMIN")
    order_id = _make_order(status="MEASURE").id
    assert client.post(
        f"/api/orders/{order_id}/workflow/stage-override", json=_override_body("AS")
    ).status_code == 200

    resp = client.post(
        f"/api/orders/{order_id}/workflow/stage-override", json=_override_body("AS_RECEIVED")
    )
    assert resp.status_code == 409
    assert resp.get_json()["code"] == "AS_NO_PATH"


def test_admin_override_same_as_state_rejected(client):
    """같은 AS 상태로의 강제 변경은 관리자도 400(못 뚫는 정합 축)."""
    _login(client, "ovc_as_same", role="ADMIN")
    order_id = _make_order(status="MEASURE").id
    assert client.post(
        f"/api/orders/{order_id}/workflow/stage-override", json=_override_body("AS_RECEIVED")
    ).status_code == 200
    resp = client.post(
        f"/api/orders/{order_id}/workflow/stage-override", json=_override_body("AS_RECEIVED")
    )
    assert resp.status_code == 400


def test_as_target_keeps_if_match(client):
    """AS 목표도 If-Match(mutation_version)를 지킨다 — 정합 축은 관리자도 못 뚫는다.

    낡은 version 이면 아무것도 바꾸지 않고 409, 맞는 version 이면 200 이다.
    (AS cycle 명령 4종에 ``expected_version`` 을 가산 노출해 얻었다.)
    """
    _login(client, "ovc_ifmatch", role="ADMIN")
    order = _make_order(status="MEASURE")
    order_id = order.id
    current_version = int(order.mutation_version or 0)

    stale = client.post(
        f"/api/orders/{order_id}/workflow/stage-override",
        json=_override_body("AS_RECEIVED"),
        headers={"If-Match": str(current_version + 5)},
    )
    assert stale.status_code == 409, stale.get_json()
    db_session.expire_all()
    assert "as_lifecycle" not in (db_session.get(Order, order_id).structured_data or {})

    fresh = client.post(
        f"/api/orders/{order_id}/workflow/stage-override",
        json=_override_body("AS_RECEIVED"),
        headers={"If-Match": str(current_version)},
    )
    assert fresh.status_code == 200, fresh.get_json()
    db_session.expire_all()
    assert db_session.get(Order, order_id).structured_data["as_lifecycle"]["current_cycle_id"]


# --- 3) DELETED 목표 ---------------------------------------------------------
def test_admin_override_soft_deletes_with_trash_mirror(client):
    """DELETED 목표는 휴지통 미러까지 함께 남긴다(복구 가능)."""
    _login(client, "ovc_delete", role="ADMIN")
    order_id = _make_order(status="DRAWING").id

    resp = client.post(
        f"/api/orders/{order_id}/workflow/stage-override",
        json=_override_body("DELETED", "중복 접수라 휴지통으로"),
    )
    assert resp.status_code == 200, resp.get_json()

    db_session.expire_all()
    saved = db_session.get(Order, order_id)
    assert saved.deleted_at is not None
    assert saved.status == "DELETED" and saved.original_status == "DRAWING"
    types = _event_types(order_id)
    assert "ORDER_SOFT_DELETED" in types
    assert types.count("ADMIN_OVERRIDE_USED") == 1


def test_admin_override_delete_twice_is_not_found(client):
    """이미 삭제된 주문은 관리자도 다시 삭제하지 않는다(404, 뚫지 않는 축)."""
    _login(client, "ovc_delete2", role="ADMIN")
    order_id = _make_order(status="DRAWING").id
    assert client.post(
        f"/api/orders/{order_id}/workflow/stage-override", json=_override_body("DELETED")
    ).status_code == 200
    resp = client.post(
        f"/api/orders/{order_id}/workflow/stage-override", json=_override_body("DELETED")
    )
    assert resp.status_code == 404


def test_admin_override_delete_can_be_restored_to_original_stage(client):
    """강제 변경으로 삭제한 주문은 휴지통에서 복구하면 원래 단계로 돌아온다.

    삭제는 ``soft_delete_order`` + 휴지통 미러가 한 계약이므로, 복구까지 왕복해야
    미러(``original_status``)가 제 역할을 했다고 말할 수 있다.
    """
    _login(client, "ovc_restore", role="ADMIN")
    order_id = _make_order(status="CONFIRM").id
    assert client.post(
        f"/api/orders/{order_id}/workflow/stage-override",
        json=_override_body("DELETED", "오접수라 휴지통으로"),
    ).status_code == 200

    restored = client.post(
        "/restore_orders", data={"selected_order": [str(order_id)]}, follow_redirects=False
    )
    assert restored.status_code in (200, 302), restored.status_code

    db_session.expire_all()
    saved = db_session.get(Order, order_id)
    assert saved.deleted_at is None
    assert saved.status == "CONFIRM"
    assert saved.original_status is None
    assert saved.structured_data["workflow"]["stage"] == "CONFIRM"


def test_bulk_as_target_opens_cycle_for_each_order(client):
    """일괄 AS 목표: ADMIN + admin_override 면 주문마다 cycle 과 기록이 1벌씩 생긴다."""
    _login(client, "ovc_bulk_admin", role="ADMIN")
    first_id = _make_order(status="MEASURE").id
    second_id = _make_order(status="DRAWING").id

    resp = client.post(
        "/api/orders/workflow/stage-override/bulk",
        json={
            "order_ids": [first_id, second_id], "to_stage": "AS_RECEIVED",
            "reason": "현장 재방문 건 일괄 AS 접수", "confirm": True,
            "admin_override": True,
        },
    )
    assert resp.status_code == 200, resp.get_json()
    data = resp.get_json()["data"]
    assert data["updated"] == 2 and data["to"] == "AS_RECEIVED"

    db_session.expire_all()
    for oid, stage in ((first_id, "MEASURE"), (second_id, "DRAWING")):
        saved = db_session.get(Order, oid)
        assert saved.structured_data["as_lifecycle"]["current_cycle_id"]
        assert saved.structured_data["workflow"]["stage"] == stage
        types = _event_types(oid)
        assert types.count("AS_REGISTERED") == 1
        assert types.count("ADMIN_OVERRIDE_USED") == 1


def test_deleted_order_cannot_be_revived_by_stage_override(client):
    """삭제된 주문은 강제 단계 변경으로 되살아나지 않는다(단건 404·일괄 not_found).

    되살아나면 ``deleted_at`` 이 남은 채 단계만 바뀌어 휴지통에서도 목록에서도 사라진다.
    """
    _login(client, "ovc_revive", role="ADMIN")
    order_id = _make_order(status="DRAWING").id
    assert client.post(
        f"/api/orders/{order_id}/workflow/stage-override", json=_override_body("DELETED")
    ).status_code == 200

    single = client.post(
        f"/api/orders/{order_id}/workflow/stage-override",
        json=_override_body("MEASURE", "삭제된 건을 되살리려는 시도"),
    )
    assert single.status_code == 404

    bulk = client.post(
        "/api/orders/workflow/stage-override/bulk",
        json={
            "order_ids": [order_id], "to_stage": "MEASURE",
            "reason": "삭제된 건을 되살리려는 일괄 시도", "confirm": True,
            "admin_override": True,
        },
    )
    assert bulk.status_code == 404

    db_session.expire_all()
    saved = db_session.get(Order, order_id)
    assert saved.deleted_at is not None and saved.status == "DELETED"


# --- 4) COMPLETED 목표은 CS 완료 한 길로만 --------------------------------------
def test_completed_target_goes_through_cs_complete(client):
    """완료 목표는 CS 게이트를 타고, 뚫은 뒤엔 시공 attempt 가 봉인된다."""
    _login(client, "ovc_complete", role="ADMIN")
    order = _make_order(
        status="CONSTRUCTION",
        structured={"quests": [{"stage": "CS", "status": "OPEN", "required_teams": ["CS"]}]},
    )
    order_id = order.id
    attempt = OrderConstructionAttempt(
        order_id=order_id, status="READY", is_current=True,
        evidence={"before": [], "after": []},
    )
    db_session.add(attempt)
    db_session.commit()
    attempt_id = attempt.id

    blocked = client.post(
        f"/api/orders/{order_id}/workflow/stage-override",
        json={"to_stage": "COMPLETED", "reason": "그냥 완료", "confirm": True},
    )
    assert blocked.status_code == 409
    assert "관리자 권한" in blocked.get_json()["message"]

    resp = client.post(
        f"/api/orders/{order_id}/workflow/stage-override",
        json=_override_body("COMPLETED", "고객 요청으로 완료 처리"),
    )
    assert resp.status_code == 200, resp.get_json()

    db_session.expire_all()
    saved = db_session.get(Order, order_id)
    assert saved.status == "COMPLETED"
    assert db_session.get(OrderConstructionAttempt, attempt_id).is_current is False
    types = _event_types(order_id)
    assert "CS_COMPLETED" in types
    assert types.count("ADMIN_OVERRIDE_USED") == 1


# --- 5) 일괄 -----------------------------------------------------------------
def test_bulk_as_target_requires_admin_override(client):
    """일괄 AS 목표도 ADMIN + admin_override 가 없으면 400."""
    _login(client, "ovc_bulk_mgr", role="MANAGER")
    order_id = _make_order(status="MEASURE").id
    resp = client.post(
        "/api/orders/workflow/stage-override/bulk",
        json={
            "order_ids": [order_id], "to_stage": "AS_RECEIVED",
            "reason": "일괄 AS 접수", "confirm": True,
        },
    )
    assert resp.status_code == 400
    db_session.expire_all()
    assert "as_lifecycle" not in (db_session.get(Order, order_id).structured_data or {})
def test_as_target_never_drops_if_match_silently(client):
    """AS 목표에 If-Match 가 오면 조용히 버리지 않는다.

    ``as_cycle_service`` 가 ``expected_version`` 을 받기 전에는 409
    ``IF_MATCH_UNSUPPORTED_TARGET`` 으로 **명시 거부**하고, 가산 수정이 들어오면 그대로
    지켜 200 이 된다. 어느 쪽이든 "무시하고 통과" 는 없다.
    """
    from foms.api.orders.stage_override_targets import _as_commands_accept_expected_version

    _login(client, "ovc_ifmatch", role="ADMIN")
    order = _make_order(status="MEASURE")
    order_id = order.id
    version = int(getattr(order, "mutation_version", 0) or 0)

    resp = client.post(
        f"/api/orders/{order_id}/workflow/stage-override",
        json=_override_body("AS_RECEIVED", "If-Match 를 지키는지 본다"),
        headers={"If-Match": str(version)},
    )
    if _as_commands_accept_expected_version():
        assert resp.status_code == 200, resp.get_json()
    else:
        assert resp.status_code == 409
        assert resp.get_json()["code"] == "IF_MATCH_UNSUPPORTED_TARGET"
        db_session.expire_all()
        assert "as_lifecycle" not in (db_session.get(Order, order_id).structured_data or {})
