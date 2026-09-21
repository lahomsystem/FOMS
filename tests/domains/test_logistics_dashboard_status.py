"""자가실측·지방 물류 보드 status dual-track (2026-07-23)."""

from __future__ import annotations

from werkzeug.security import generate_password_hash

from db import db_session
from models import Order, OrderConstructionAttempt, OrderEvent, User
from foms.services.orders.status_constants import (
    is_logistics_board_status,
    should_sync_workflow_stage_on_status,
)
from foms.services.orders.stage_override import OVERRIDE_BLOCK_MESSAGE


def _login(client, username: str, role: str = "STAFF") -> User:
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


def _make_erp(*, status: str, stage: str) -> Order:
    order = Order(
        received_date="2026-07-01",
        customer_name="logistics-고객",
        phone="010-2222-3333",
        address="Busan",
        product="붙박이장",
        status=status,
        manager_name="Mgr",
        is_erp_order=True,
        is_self_measurement=True,
        structured_data={"workflow": {"stage": stage}},
    )
    db_session.add(order)
    db_session.commit()
    return order


def test_logistics_helpers():
    assert is_logistics_board_status("SCHEDULED") is True
    assert is_logistics_board_status("COMPLETED") is True
    assert is_logistics_board_status("MEASURE") is False
    assert should_sync_workflow_stage_on_status("SCHEDULED") is False
    assert should_sync_workflow_stage_on_status("COMPLETED") is True


def test_field_update_rejects_completed_without_admin_override(client):
    """보드 우회로의 COMPLETED 쓰기는 409 USE_CS_COMPLETE 로 거부되고 상태는 그대로다.

    C-B2(2026-09-20): 메인 파이프라인 ERP 주문의 최종 완료는 cs/complete 한 길만 쓴다.
    옛 계약(단계가 시공이어도 보드에서 바로 COMPLETED 저장)은 quest·보류·AS 게이트를
    통째로 건너뛰었기 때문에 여기서 뒤집힌다.
    """
    _login(client, "log_comp_ok")
    order = _make_erp(status="SCHEDULED", stage="CONSTRUCTION")
    resp = client.post(
        "/api/update_order_field",
        json={"order_id": order.id, "field": "status", "value": "COMPLETED"},
    )
    assert resp.status_code == 409, resp.get_json()
    body = resp.get_json()
    assert body["success"] is False
    assert body["code"] == "USE_CS_COMPLETE"
    assert body["stage"] == "CONSTRUCTION"
    assert "시공" in body["message"]  # 막힌 이유를 사람 말로 준다
    saved = db_session.get(Order, order.id)
    assert saved is not None
    assert saved.status == "SCHEDULED"  # status 불변
    assert (saved.structured_data or {}).get("workflow", {}).get("stage") == "CONSTRUCTION"


def test_field_update_completed_untouched_for_non_erp_order(client):
    """대조군 — 비ERP 레거시 주문의 COMPLETED 저장은 기존 경로 그대로 200."""
    _login(client, "log_comp_legacy")
    order = Order(
        received_date="2026-07-01",
        customer_name="레거시-고객",
        phone="010-2222-4444",
        address="Busan",
        product="붙박이장",
        status="SCHEDULED",
        manager_name="Mgr",
        is_erp_order=False,
    )
    db_session.add(order)
    db_session.commit()
    resp = client.post(
        "/api/update_order_field",
        json={"order_id": order.id, "field": "status", "value": "COMPLETED"},
    )
    assert resp.status_code == 200, resp.get_json()
    assert db_session.get(Order, order.id).status == "COMPLETED"


def test_field_update_scheduled_preserves_workflow_stage(client):
    """설치예정 저장 시 workflow.stage 오염 금지."""
    _login(client, "log_sched_preserve")
    order = _make_erp(status="MEASURED", stage="CONSTRUCTION")
    resp = client.post(
        "/api/update_order_field",
        json={"order_id": order.id, "field": "status", "value": "SCHEDULED"},
    )
    assert resp.status_code == 200, resp.get_json()
    saved = db_session.get(Order, order.id)
    assert saved is not None
    assert saved.status == "SCHEDULED"
    assert (saved.structured_data or {}).get("workflow", {}).get("stage") == "CONSTRUCTION"


def test_field_update_blocks_main_pipeline_skip_without_admin_override(client):
    """음성 대조군 — 관리자라도 ``admin_override`` 없이 스킵하면 기존처럼 403."""
    _login(client, "log_skip_block", role="ADMIN")
    order = _make_erp(status="MEASURE", stage="MEASURE")
    resp = client.post(
        "/api/update_order_field",
        json={"order_id": order.id, "field": "status", "value": "CONFIRM"},
    )
    assert resp.status_code == 403
    assert OVERRIDE_BLOCK_MESSAGE in (resp.get_json() or {}).get("message", "")


def _admin_override_events(order_id: int) -> list:
    """주문에 남은 ``ADMIN_OVERRIDE_USED`` 이벤트 전부."""
    return (
        db_session.query(OrderEvent)
        .filter(
            OrderEvent.order_id == order_id,
            OrderEvent.event_type == "ADMIN_OVERRIDE_USED",
        )
        .all()
    )


def test_field_update_completed_passes_with_admin_override(client):
    """관리자가 사유를 적고 뚫으면 완료가 되고, 뒤(시공 attempt·이력)가 함께 닫힌다.

    뚫더라도 완료는 CS 완료 서비스 한 길만 탄다(C4) — "상태만 COMPLETED 이고 뒤가 빈"
    주문은 어느 경로로도 생기지 않아야 한다.
    """
    _login(client, "log_comp_override", role="ADMIN")
    # 물류 overlay 없는 순수 메인 파이프라인 주문 — status 가 메인 축을 그대로 투영한다.
    order = _make_erp(status="CONSTRUCTION", stage="CONSTRUCTION")
    order_id = int(order.id)
    attempt = OrderConstructionAttempt(
        order_id=order_id, status="READY", is_current=True,
        evidence={"before": [], "after": []},
    )
    db_session.add(attempt)
    db_session.commit()
    attempt_id = attempt.id  # uuid 문자열 — 요청 뒤 detach 회피용 primitive 캡처

    resp = client.post(
        "/api/update_order_field",
        json={
            "order_id": order_id,
            "field": "status",
            "value": "COMPLETED",
            "admin_override": True,
            "override_reason": "고객이 잔여 공정을 취소해 완료로 닫는다",
        },
    )
    assert resp.status_code == 200, resp.get_json()

    saved = db_session.get(Order, order_id)
    assert saved.status == "COMPLETED"
    assert db_session.get(OrderConstructionAttempt, attempt_id).is_current is False

    events = _admin_override_events(order_id)
    assert len(events) == 1
    payload = events[0].payload or {}
    assert "USE_CS_COMPLETE" in payload["gates"]
    assert payload["to"] == "COMPLETED"
    assert payload["reason"] == "고객이 잔여 공정을 취소해 완료로 닫는다"


def test_field_update_skip_passes_with_admin_override(client):
    """관리자가 사유를 적고 뚫으면 단계 건너뛰기가 통과하고 이벤트 1행이 남는다."""
    _login(client, "log_skip_override", role="ADMIN")
    order = _make_erp(status="MEASURE", stage="MEASURE")
    order_id = int(order.id)
    resp = client.post(
        "/api/update_order_field",
        json={
            "order_id": order_id,
            "field": "status",
            "value": "CONFIRM",
            "admin_override": True,
            "override_reason": "도면이 이미 승인돼 건너뛴다",
        },
    )
    assert resp.status_code == 200, resp.get_json()
    assert db_session.get(Order, order_id).status == "CONFIRM"

    events = _admin_override_events(order_id)
    assert len(events) == 1
    assert (events[0].payload or {})["gates"] == ["OVERRIDE_BLOCK"]
