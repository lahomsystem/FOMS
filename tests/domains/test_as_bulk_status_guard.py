"""AS overlay 보호 + 상태 이전값 감사 — 2026-08-14 일괄 완료처리 사고 회귀 가드.

사고: 「단계 강제 변경」·주문 일괄 상태변경이 AS 접수/완료 주문의 ``status`` 를
``COMPLETED`` 로 덮어써 AS 대시보드에서 55건이 사라졌다(기록은 남고 목록 술어만 status).
게다가 ``STAGE_OVERRIDE`` payload 의 ``from`` 은 workflow.stage 라 status 이전값이 남지
않아 복구 근거가 부족했다.

가드 3종:
1. 일괄 경로는 AS overlay 주문을 기본 제외하고 경고를 돌려준다.
2. ``include_as: true`` 명시 opt-in 이면 통과한다(사람이 알고 누른 경우).
3. 단계 강제 변경은 status 이전값을 payload + security_logs 로 남긴다.
"""

from __future__ import annotations

from werkzeug.security import generate_password_hash

from db import db_session
from models import Order, OrderEvent, SecurityLog, User
from foms.services.orders.stage_override import AS_OVERLAY_STATUSES, as_overlay_status


def _login(client, username: str, role: str = "ADMIN") -> User:
    """테스트 사용자 생성 + 세션 로그인."""
    user = User(
        username=username,
        password=generate_password_hash("pw"),
        role=role,
        team="CS",
        name=username,
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    with client.session_transaction() as sess:
        sess["user_id"] = user.id
        sess["username"] = user.username
        sess["role"] = user.role
    return user


def _make_order(*, status: str, stage: str = "MEASURE") -> Order:
    """AS overlay status + 메인 stage 를 동시에 가진 ERP 주문(사고 재현 형태)."""
    order = Order(
        received_date="2026-08-01",
        customer_name="AS-고객",
        phone="010-3333-4444",
        address="Seoul",
        product="붙박이장",
        status=status,
        manager_name="Mgr",
        is_erp_order=True,
        as_received_date="2026-08-14" if status in AS_OVERLAY_STATUSES else None,
        structured_data={"workflow": {"stage": stage}},
    )
    db_session.add(order)
    db_session.commit()
    return order


def test_as_overlay_status_unit(client):
    """status 기준 판정 — workflow.stage 가 메인 코드여도 AS 를 놓치지 않는다."""
    assert as_overlay_status(_make_order(status="AS_RECEIVED")) == "AS_RECEIVED"
    assert as_overlay_status(_make_order(status="AS_COMPLETED")) == "AS_COMPLETED"
    assert as_overlay_status(_make_order(status="DRAWING", stage="DRAWING")) == ""


def test_bulk_stage_override_excludes_as_orders(client):
    """일괄 단계 강제 변경: AS 주문은 제외되고 경고가 온다."""
    _login(client, "as_guard_mgr", role="MANAGER")
    as_order = _make_order(status="AS_RECEIVED")
    plain = _make_order(status="DRAWING", stage="DRAWING")
    as_id, plain_id = as_order.id, plain.id

    resp = client.post(
        "/api/orders/workflow/stage-override/bulk",
        json={
            "order_ids": [as_id, plain_id],
            "to_stage": "COMPLETED",
            "reason": "완료 정리",
            "confirm": True,
        },
    )
    assert resp.status_code == 200, resp.get_json()
    data = resp.get_json()["data"]
    assert data["updated"] == 1
    assert [item["order_id"] for item in data["skipped_as"]] == [as_id]
    assert "AS" in data["warning"]

    db_session.expire_all()
    assert db_session.get(Order, as_id).status == "AS_RECEIVED"  # 사고 재현 차단
    assert db_session.get(Order, plain_id).status == "COMPLETED"


def test_bulk_stage_override_all_as_returns_400(client):
    """대상이 전부 AS 면 아무것도 바꾸지 않고 400 으로 알린다."""
    _login(client, "as_guard_mgr2", role="MANAGER")
    as_id = _make_order(status="AS_COMPLETED").id
    resp = client.post(
        "/api/orders/workflow/stage-override/bulk",
        json={"order_ids": [as_id], "to_stage": "COMPLETED", "reason": "완료", "confirm": True},
    )
    assert resp.status_code == 400
    assert "AS" in resp.get_json()["error"]
    db_session.expire_all()
    assert db_session.get(Order, as_id).status == "AS_COMPLETED"


def test_bulk_stage_override_include_as_opt_in(client):
    """include_as: true 는 명시 opt-in — 그때만 AS 주문도 바뀐다."""
    _login(client, "as_guard_mgr3", role="MANAGER")
    as_id = _make_order(status="AS_RECEIVED").id
    resp = client.post(
        "/api/orders/workflow/stage-override/bulk",
        json={
            "order_ids": [as_id], "to_stage": "COMPLETED", "reason": "정말 완료",
            "confirm": True, "include_as": True,
        },
    )
    assert resp.status_code == 200, resp.get_json()
    assert resp.get_json()["data"]["updated"] == 1
    db_session.expire_all()
    assert db_session.get(Order, as_id).status == "COMPLETED"


def test_stage_override_records_previous_status(client):
    """단건 강제 변경이 status 이전값을 이벤트 payload + 감사행에 남긴다."""
    _login(client, "as_guard_mgr4", role="MANAGER")
    as_id = _make_order(status="AS_RECEIVED").id

    resp = client.post(
        f"/api/orders/{as_id}/workflow/stage-override",
        json={"to_stage": "COMPLETED", "reason": "AS 종결 후 완료", "confirm": True},
    )
    assert resp.status_code == 200, resp.get_json()

    ev = (
        db_session.query(OrderEvent)
        .filter(OrderEvent.order_id == as_id, OrderEvent.event_type == "STAGE_OVERRIDE")
        .one()
    )
    assert ev.payload["from_status"] == "AS_RECEIVED"
    assert ev.payload["as_overlay_cleared"] == "AS_RECEIVED"

    log = (
        db_session.query(SecurityLog)
        .filter(SecurityLog.target_id == as_id, SecurityLog.action == "ORDER_STATUS_CHANGED")
        .one()
    )
    assert log.detail["before"] == "AS_RECEIVED"
    assert log.detail["after"] == "COMPLETED"
    assert log.detail["stage_override"] is True


def test_bulk_status_api_excludes_as_orders(client):
    """주문 일괄 상태변경(status API)도 AS 주문을 제외하고 사유를 알려준다."""
    _login(client, "as_guard_admin", role="ADMIN")
    as_id = _make_order(status="AS_RECEIVED").id
    plain_id = _make_order(status="CS", stage="CS").id  # CS → COMPLETED = advance(차단 대상 아님)

    resp = client.post(
        "/api/bulk_update_order_status",
        json={"order_ids": [as_id, plain_id], "status": "COMPLETED"},
    )
    assert resp.status_code == 200, resp.get_json()
    payload = resp.get_json()
    assert [item["order_id"] for item in payload["blocked_as_orders"]] == [as_id]
    assert "AS" in payload["message"]

    db_session.expire_all()
    assert db_session.get(Order, as_id).status == "AS_RECEIVED"


def test_bulk_status_api_allows_as_target(client):
    """AS 상태로 바꾸는 일괄 작업은 막지 않는다(AS 대시보드 안에서의 이동)."""
    _login(client, "as_guard_admin2", role="ADMIN")
    as_id = _make_order(status="AS_RECEIVED").id
    resp = client.post(
        "/api/bulk_update_order_status",
        json={"order_ids": [as_id], "status": "AS_COMPLETED"},
    )
    assert resp.status_code == 200, resp.get_json()
    assert resp.get_json()["updated"] == 1
    db_session.expire_all()
    assert db_session.get(Order, as_id).status == "AS_COMPLETED"
