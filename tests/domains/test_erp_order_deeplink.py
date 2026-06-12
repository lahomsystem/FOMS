"""Tests for stage-aware queue focus deep links."""

from db import db_session
from foms.services.erp_order_deeplink import build_order_queue_focus_href, resolve_order_stage_code
from models import Order


def test_queue_focus_href_received_stage_uses_home_queue(app) -> None:
    with app.app_context():
        order = Order(
            received_date="2026-05-30",
            customer_name="소마디자인",
            phone="010-3377-5193",
            address="Seoul",
            product="붙박이",
            status="RECEIVED",
            is_erp_order=True,
            structured_data={"workflow": {"stage": "RECEIVED"}},
        )
        db_session.add(order)
        db_session.commit()

        href = build_order_queue_focus_href(order, search_query="소마")
        assert href.startswith("/erp/dashboard?")
        assert "view=queue" in href
        assert f"focus_order={order.id}" in href
        assert "q=" in href
        assert resolve_order_stage_code(order) == "RECEIVED"


def test_queue_focus_href_drawing_stage_uses_workbench(app) -> None:
    with app.app_context():
        order = Order(
            received_date="2026-05-30",
            customer_name="도면고객",
            phone="010-1111-2222",
            address="Seoul",
            product="붙박이",
            status="DRAWING",
            erp_stage_code="DRAWING",
            is_erp_order=True,
            blueprint_image_url="https://example.com/plan.png",
            structured_data={
                "parties": {"customer": {"name": "도면고객"}},
                "workflow": {"stage": "DRAWING"},
            },
        )
        db_session.add(order)
        db_session.commit()

        href = build_order_queue_focus_href(order, search_query="도면고객")
        assert href.startswith("/erp/drawing-workbench?")
        assert f"focus_order={order.id}" in href
        assert "open=erp-order" not in href
