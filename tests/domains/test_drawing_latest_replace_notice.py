"""영업 확정 전 재전달 = 최신 도면으로 교체 — 전달 화면 안내 계약.

2026-09-30 주문 5331: 확정 전 3회 전달이 도면 칸에 3장으로 남았다. 서버는 이제 mode 없는
재전달을 REPLACE_ALL 로 처리하므로(``perform_drawing_transfer``), 도면팀이 보내기 전에 "이전
도면은 빠지고 이번 도면이 최신 도면으로 교체"됨을 화면에서 알 수 있어야 한다.
"""
from __future__ import annotations

from pathlib import Path

from foms.web.drawing.tablet_sheet import _sheet_transfer_replaced_count

ROOT = Path(__file__).resolve().parents[2]
WORKBENCH = ROOT / "templates/drawing/partials/workbench_detail_body.html"
SHEET = ROOT / "templates/drawing/partials/tablet_sheet_body.html"


def test_sheet_replaced_count_only_before_sales_confirm():
    files = [{"key": "a"}, {"key": "b"}]
    assert _sheet_transfer_replaced_count({"drawing_status": "TRANSFERRED", "drawing_current_files": files}) == 2
    assert _sheet_transfer_replaced_count({"drawing": {"status": "transferred"}, "drawing_current_files": files}) == 2
    for status in ("PENDING", "RETURNED", "CONFIRMED"):
        assert _sheet_transfer_replaced_count({"drawing_status": status, "drawing_current_files": files}) == 0
    assert _sheet_transfer_replaced_count({"drawing_status": "TRANSFERRED"}) == 0


def test_sheet_template_shows_latest_notice_when_replacing():
    body = SHEET.read_text(encoding="utf-8")
    assert "transfer_replaced_count" in body
    assert "data-foms-drawing-latest-notice" in body
    assert "최신 도면으로 교체" in body


def test_workbench_transfer_modal_shows_latest_notice_before_confirm():
    body = WORKBENCH.read_text(encoding="utf-8")
    assert "{% if drawing_status == 'TRANSFERRED' and drawing_files %}" in body
    assert "dw-transfer-latest-notice" in body
    assert "이번 도면이 최신 도면으로 교체" in body
    assert "최신 도면으로 교체됩니다. 진행할까요?" in body


def _render_sheet(app, client, status: str) -> str:
    from werkzeug.security import generate_password_hash

    from db import db_session
    from models import Order, User

    user = User(username=f"dws_notice_{status.lower()}", password=generate_password_hash("pw"),
                name="도면 담당", role="ADMIN", team="DRAWING", is_active=True)
    db_session.add(user)
    db_session.commit()
    order = Order(
        received_date="2026-09-30", customer_name="안내 고객", phone="010-0000-0000",
        address="Seoul", product="붙박이장", status="DRAWING", manager_name="담당",
        is_erp_order=True, erp_stage_code="DRAWING",
        structured_data={
            "workflow": {"stage": "DRAWING"},
            "drawing_status": status,
            "drawing_current_files": [{"key": "orders/x/a.png"}, {"key": "orders/x/b.png"}],
            "assignments": {"drawing_assignee_user_ids": [user.id]},
        },
    )
    db_session.add(order)
    db_session.commit()
    with client.session_transaction() as sess:
        sess["user_id"] = user.id
        sess["username"] = user.username
        sess["role"] = user.role
    res = client.get(f"/erp/drawing-workbench/tablet-sheet/{order.id}")
    assert res.status_code == 200
    return res.get_data(as_text=True)


def test_sheet_route_renders_notice_only_when_transferred(app, client):
    html = _render_sheet(app, client, "TRANSFERRED")
    assert "이전 도면 2장은 빠지고 이번 도면이 최신 도면으로 교체됩니다." in html
    html = _render_sheet(app, client, "PENDING")
    assert "data-foms-drawing-latest-notice" not in html
