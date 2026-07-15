"""워크플로 단계 강제 변경(역행·건너뛰기) — Spec 2026-07-15."""

from __future__ import annotations

from werkzeug.security import generate_password_hash

from db import db_session
from models import Order, OrderEvent, User
from foms.services.orders.stage_override import (
    OVERRIDE_BLOCK_MESSAGE,
    classify_stage_move,
    requires_privileged_override,
)


def _login(client, username: str, role: str = "ADMIN") -> User:
    user = User(
        username=username,
        password=generate_password_hash("pw"),
        role=role,
        team="CS",
        name=f"{username}",
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    with client.session_transaction() as sess:
        sess["user_id"] = user.id
        sess["username"] = user.username
        sess["role"] = user.role
    return user


def _make_erp_order(*, status: str = "DRAWING", hist: list | None = None) -> Order:
    hist = hist if hist is not None else [
        {"action": "ERP_ORDER_CHANGED", "note": "치수", "at": "2026-07-15 10:00:00"}
    ]
    order = Order(
        received_date="2026-07-01",
        customer_name="override-고객",
        phone="010-1111-2222",
        address="Seoul",
        product="붙박이장",
        status=status,
        manager_name="Mgr",
        is_erp_order=True,
        structured_data={
            "workflow": {"stage": status},
            "drawing_transfer_history": hist,
            "drawing": {"status": "IN_PROGRESS"},
        },
    )
    db_session.add(order)
    db_session.commit()
    return order


def test_classify_and_requires_override_unit():
    assert classify_stage_move("DRAWING", "MEASURE") == "regress"
    assert classify_stage_move("MEASURE", "CONFIRM") == "skip"
    assert classify_stage_move("MEASURE", "DRAWING") == "advance"
    assert classify_stage_move("DRAWING", "DRAWING") == "same"
    assert requires_privileged_override("DRAWING", "MEASURE") is True
    assert requires_privileged_override("MEASURE", "CONFIRM") is True
    assert requires_privileged_override("MEASURE", "DRAWING") is False
    assert requires_privileged_override("DRAWING", "AS_RECEIVED") is False


def test_override_api_manager_regress_preserves_history(client):
    user = _login(client, "ov_mgr", role="MANAGER")
    user_id = user.id
    order = _make_erp_order(status="DRAWING")
    order_id = order.id
    hist_len = len(order.structured_data["drawing_transfer_history"])

    resp = client.post(
        f"/api/orders/{order_id}/workflow/stage-override",
        json={
            "to_stage": "MEASURE",
            "reason": "실측 재방문 — 치수 오류 확인",
            "confirm": True,
        },
    )
    assert resp.status_code == 200, resp.get_json()
    data = resp.get_json()
    assert data["success"] is True
    assert data["data"]["mode"] == "regress"
    assert data["data"]["to"] == "MEASURE"

    db_session.expire_all()
    saved = db_session.get(Order, order_id)
    assert saved.status == "MEASURE"
    assert saved.structured_data["workflow"]["stage"] == "MEASURE"
    assert len(saved.structured_data["drawing_transfer_history"]) == hist_len
    assert saved.structured_data["drawing"]["status"] == "IN_PROGRESS"

    ev = (
        db_session.query(OrderEvent)
        .filter(OrderEvent.order_id == order_id, OrderEvent.event_type == "STAGE_OVERRIDE")
        .all()
    )
    assert len(ev) == 1
    assert ev[0].payload["reason"].startswith("실측 재방문")
    assert ev[0].created_by_user_id == user_id


def test_override_api_staff_forbidden(client):
    _login(client, "ov_staff", role="STAFF")
    order_id = _make_erp_order(status="DRAWING").id
    resp = client.post(
        f"/api/orders/{order_id}/workflow/stage-override",
        json={
            "to_stage": "MEASURE",
            "reason": "실측 재방문 — 치수 오류 확인",
            "confirm": True,
        },
    )
    assert resp.status_code == 403


def test_override_api_requires_confirm_and_reason(client):
    _login(client, "ov_admin", role="ADMIN")
    order_id = _make_erp_order(status="DRAWING").id

    r1 = client.post(
        f"/api/orders/{order_id}/workflow/stage-override",
        json={"to_stage": "MEASURE", "reason": "충분한 사유입니다", "confirm": False},
    )
    assert r1.status_code == 400

    r2 = client.post(
        f"/api/orders/{order_id}/workflow/stage-override",
        json={"to_stage": "MEASURE", "reason": "짧음", "confirm": True},
    )
    assert r2.status_code == 400

    r3 = client.post(
        f"/api/orders/{order_id}/workflow/stage-override",
        json={"to_stage": "DRAWING", "reason": "충분한 사유입니다", "confirm": True},
    )
    assert r3.status_code == 400  # same stage


def test_override_api_skip_forward(client):
    _login(client, "ov_skip", role="ADMIN")
    order_id = _make_erp_order(status="MEASURE").id
    resp = client.post(
        f"/api/orders/{order_id}/workflow/stage-override",
        json={
            "to_stage": "CONFIRM",
            "reason": "실측 생략 — 고객 셀프 치수 확정",
            "confirm": True,
        },
    )
    assert resp.status_code == 200
    assert resp.get_json()["data"]["mode"] == "skip"


def test_update_order_status_blocks_regress(client):
    _login(client, "ov_block", role="ADMIN")
    order_id = _make_erp_order(status="DRAWING").id
    resp = client.post(
        "/api/update_order_status",
        json={"order_id": order_id, "status": "MEASURE"},
    )
    assert resp.status_code == 403
    assert OVERRIDE_BLOCK_MESSAGE in (resp.get_json() or {}).get("message", "")


def test_update_order_status_allows_adjacent_advance(client):
    _login(client, "ov_adv", role="STAFF")
    order_id = _make_erp_order(status="MEASURE").id
    resp = client.post(
        "/api/update_order_status",
        json={"order_id": order_id, "status": "DRAWING"},
    )
    assert resp.status_code == 200
    assert resp.get_json()["success"] is True


def test_bulk_blocks_only_override_required(client):
    _login(client, "ov_bulk2", role="MANAGER")
    regress_id = _make_erp_order(status="DRAWING").id
    advance_id = _make_erp_order(status="MEASURE").id
    resp = client.post(
        "/api/bulk_update_order_status",
        json={"order_ids": [regress_id, advance_id], "status": "MEASURE"},
    )
    # regress: DRAWING→MEASURE blocked; same MEASURE→MEASURE updated
    data = resp.get_json()
    assert regress_id in data.get("blocked_override_required", [])
    assert data["updated"] >= 1


def test_update_order_field_status_blocks_skip(client):
    _login(client, "ov_field", role="STAFF")
    order_id = _make_erp_order(status="MEASURE").id
    resp = client.post(
        "/api/update_order_field",
        json={"order_id": order_id, "field": "status", "value": "CONFIRM"},
    )
    assert resp.status_code == 403


def test_js_contract_defer_and_api_path():
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    js = (root / "static/js/orders/erp-stage-override.js").read_text(encoding="utf-8")
    assert "__FOMS_STAGE_OVERRIDE_BOUND" in js
    assert "/workflow/stage-override" in js
    assert "needsOverride" in js

    erp_js = (root / "templates/orders/partials/erp_order_js.html").read_text(encoding="utf-8")
    assert "erp-stage-override.js" in erp_js
    assert "defer" in erp_js
    assert "erp_stage_override_modal.html" in erp_js
