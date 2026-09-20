"""자가실측·지방 물류 보드 status dual-track (2026-07-23)."""

from __future__ import annotations

from werkzeug.security import generate_password_hash

from db import db_session
from models import Order, User
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


def test_field_update_rejects_completed_with_use_cs_complete(client):
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


def test_field_update_still_blocks_main_pipeline_skip(client):
    """메인 파이프라인끼리 스킵은 기존처럼 403."""
    _login(client, "log_skip_block", role="ADMIN")
    order = _make_erp(status="MEASURE", stage="MEASURE")
    resp = client.post(
        "/api/update_order_field",
        json={"order_id": order.id, "field": "status", "value": "CONFIRM"},
    )
    assert resp.status_code == 403
    assert OVERRIDE_BLOCK_MESSAGE in (resp.get_json() or {}).get("message", "")
