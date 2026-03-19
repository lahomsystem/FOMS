"""Regression tests for AS shipment dashboard behavior."""

from db import db_session
from models import Order
from services.order_date_sync import collect_order_schedule_date_specs, sync_order_dates
import apps.erp_shipment_page as shipment_page
import services.as_content_safety as as_content_safety


def make_order(**overrides):
    data = {
        "received_date": "2026-03-19",
        "customer_name": "테스터",
        "phone": "010-0000-0000",
        "address": "서울시 강남구 테스트로 1",
        "product": "테스트 제품",
        "status": "RECEIVED",
        "is_erp_beta": False,
        "structured_data": {},
    }
    data.update(overrides)
    return Order(**data)


def persist_orders(*orders):
    db_session.add_all(list(orders))
    db_session.commit()
    for order in orders:
        sync_order_dates(order, db_session)
    db_session.commit()


def test_collect_order_schedule_date_specs_includes_as_visit_for_non_beta_order():
    order = make_order(
        status="AS_RECEIVED",
        structured_data={"schedule": {"as_visit": {"date": "2026-03-21"}}},
    )

    specs = collect_order_schedule_date_specs(order)
    pairs = {(spec["kind"], spec["date"]) for spec in specs}

    assert ("as_visit", "2026-03-21") in pairs


def test_extract_dashboard_target_dates_uses_as_visit_for_as_orders():
    order = make_order(
        status="AS",
        scheduled_date="2026-03-25",
        structured_data={
            "schedule": {
                "construction": {"date": "2026-03-25"},
                "as_visit": {"date": "2026-03-21"},
            }
        },
    )

    assert hasattr(shipment_page, "extract_dashboard_target_dates")
    assert shipment_page.extract_dashboard_target_dates(order) == {"2026-03-21"}


def test_as_content_html_to_text_strips_tags():
    html = "<div><b>경첩</b> 교체</div><div><font color='red'>긴급</font></div>"

    assert hasattr(as_content_safety, "as_content_html_to_text")
    text = as_content_safety.as_content_html_to_text(html)

    assert "경첩 교체" in text
    assert "긴급" in text
    assert "<div>" not in text
    assert "<font" not in text
    assert "경첩\n교체" not in text


def test_shipment_route_uses_as_visit_for_as_orders(login):
    as_order = make_order(
        status="AS",
        customer_name="AS고객",
        structured_data={
            "schedule": {"as_visit": {"date": "2026-03-21"}},
            "shipment": {"as_content": "<div>경첩 교체</div>"},
        },
    )
    normal_order = make_order(
        status="CONFIRM",
        is_erp_beta=True,
        customer_name="일반고객",
        structured_data={"schedule": {"construction": {"date": "2026-03-25"}}},
    )

    persist_orders(as_order, normal_order)

    response = login.get("/erp/shipment?date=2026-03-21")
    body = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "AS고객" in body
    assert "일반고객" not in body


def test_shipment_route_range_uses_as_visit_for_as_orders(login):
    as_order = make_order(
        status="AS_RECEIVED",
        customer_name="AS범위고객",
        structured_data={
            "schedule": {"as_visit": {"date": "2026-03-21"}},
            "shipment": {"as_content": "<div>AS 방문</div>"},
        },
    )
    normal_order = make_order(
        status="CONFIRM",
        is_erp_beta=True,
        customer_name="범위밖고객",
        structured_data={"schedule": {"construction": {"date": "2026-03-25"}}},
    )

    persist_orders(as_order, normal_order)

    response = login.get("/erp/shipment?date_from=2026-03-20&date_to=2026-03-22")
    body = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "AS범위고객" in body
    assert "범위밖고객" not in body


def test_shipment_route_keeps_null_status_construction_order(login):
    legacy_order = make_order(
        status=None,
        customer_name="NULL상태고객",
        scheduled_date="2026-03-21",
        structured_data={"schedule": {"construction": {"date": "2026-03-21"}}},
    )

    persist_orders(legacy_order)

    response = login.get("/erp/shipment?date=2026-03-21")
    body = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "NULL상태고객" in body
