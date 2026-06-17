import json

from db import db_session
from models import Order, OrderAttachment
from foms.services.erp_order_detail import (
    attach_order_detail_payloads,
    build_order_detail_payload_map,
)


def make_erp_order():
    return Order(
        received_date="2026-03-19",
        customer_name="테스트 고객",
        phone="010-1234-5678",
        address="서울시 강남구 테스트로 1",
        product="붙박이장",
        status="RECEIVED",
        is_erp_order=True,
        structured_data={
            "workflow": {"stage": "DRAWING"},
            "parties": {
                "customer": {"name": "테스트 고객", "phone": "010-1234-5678"},
                "orderer": {"name": "라홈"},
                "manager": {"name": "홍길동"},
            },
            "site": {
                "address_full": "서울시 강남구 테스트로 1",
            },
            "schedule": {
                "measurement": {"date": "2026-03-20"},
                "construction": {"date": "2026-03-25"},
            },
            "items": [
                {
                    "product_name": "붙박이장",
                    "spec_width": "3000",
                    "spec_depth": "600",
                    "spec_height": "2400",
                }
            ],
        },
    )


def test_build_order_detail_payload_map_slims_structured_data_without_attachments(app):
    order = make_erp_order()
    db_session.add(order)
    db_session.commit()

    attachment = OrderAttachment(
        order_id=order.id,
        filename="measure-photo.jpg",
        file_type="image",
        category="measurement",
        item_index=0,
        file_size=123,
        storage_key="orders/test/measure-photo.jpg",
        thumbnail_key="orders/test/thumb-measure-photo.jpg",
    )
    db_session.add(attachment)
    db_session.commit()

    payload_map = build_order_detail_payload_map(
        db_session,
        [{"id": order.id, "structured_data": order.structured_data}],
    )

    payload = payload_map[order.id]

    assert payload["success"] is True
    assert payload["structured_data"]["workflow"]["stage"] == "DRAWING"
    assert "attachments" not in payload  # Lazy loading in Phase M


def test_attach_order_detail_payloads_fallback_matches_lazy_load_shape() -> None:
    row = {"structured_data": {"workflow": {"stage": "MEASURE"}}}

    attach_order_detail_payloads(None, [row])

    assert row["detail_payload"]["success"] is True
    assert row["detail_payload"]["structured_data"]["workflow"]["stage"] == "MEASURE"
    assert "attachments" not in row["detail_payload"]


def test_erp_dashboard_includes_preloaded_order_detail_payload(login):
    order = make_erp_order()
    db_session.add(order)
    db_session.commit()

    attachment = OrderAttachment(
        order_id=order.id,
        filename="drawing.pdf",
        file_type="file",
        category="drawing",
        item_index=None,
        file_size=456,
        storage_key="orders/test/drawing.pdf",
        thumbnail_key=None,
    )
    db_session.add(attachment)
    db_session.commit()
    order_id = order.id

    response = login.get("/erp/dashboard")
    body = response.get_data(as_text=True)

    assert response.status_code == 200
    assert f'order-detail-preload-{order_id}' in body

    marker = f'<script type="application/json" id="order-detail-preload-{order_id}">'
    start = body.index(marker) + len(marker)
    end = body.index("</script>", start)
    payload = json.loads(body[start:end])

    assert payload["success"] is True
    assert payload["structured_data"]["workflow"]["stage"] == "DRAWING"
    assert "attachments" not in payload  # Lazy loading in Phase M
