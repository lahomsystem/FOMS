"""Shipment dashboard mobile/tablet v2 queue surface."""

from __future__ import annotations

from pathlib import Path

from werkzeug.security import generate_password_hash

from db import db_session
from foms.services.erp_display import get_today_kst
from models import Order, OrderScheduleDate, User

ROOT = Path(__file__).resolve().parents[2]


def _login_admin(client) -> User:
    user = User(
        username="shipment_mobile_admin",
        password=generate_password_hash("admin"),
        role="ADMIN",
        team="CS",
        name="Shipment Mobile Admin",
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    with client.session_transaction() as sess:
        sess["user_id"] = user.id
        sess["username"] = user.username
        sess["role"] = user.role
    return user


def test_shipment_mobile_controls_template_contract() -> None:
    controls = (ROOT / "templates/shipment/partials/shipment_mobile_controls.html").read_text(
        encoding="utf-8"
    )
    main = (ROOT / "templates/shipment/partials/dashboard_main.html").read_text(encoding="utf-8")
    dash = (ROOT / "templates/shipment/dashboard.html").read_text(encoding="utf-8")

    assert "erp-shipment-mobile-controls" in controls
    assert 'id="erp-shipment-mobile-search"' in controls
    assert "erp-shipment-mobile-filter-drawer" in controls
    assert "erp-shipment-mobile-v2" in main
    assert "shipment_mobile_dates.html" in main
    assert "shipment_mobile_queue.html" in main
    assert "shipment_mobile_controls.html" in main
    assert "foms-shipment-mobile.css" in dash
    queue = (ROOT / "templates/shipment/partials/shipment_mobile_queue.html").read_text(
        encoding="utf-8"
    )
    pc = (ROOT / "templates/shipment/partials/dashboard_main.html").read_text(encoding="utf-8")
    assert "/api/erp/shipment/update/" in queue
    assert "data-shipment-mobile-edit-trigger" in queue
    assert "js-shipment-as-rec-cancel" in queue
    for field in ("site_extra", "construction_time", "drawing_managers", "construction_workers"):
        assert field in pc
        assert field in queue


def test_shipment_mobile_sections_do_not_expand_viewport() -> None:
    css = (ROOT / "static/css/components/foms-shipment-mobile.css").read_text(
        encoding="utf-8"
    )

    assert ".erp-shipment-mobile-v2 > *" in css
    assert "min-width: 0;" in css
    assert "max-width: 100%;" in css
    assert ".erp-shipment-mobile-dates__track" in css
    assert "overflow-x: auto;" in css
    assert "overflow-x: hidden;" in css


def test_shipment_dashboard_renders_mobile_v2_queue_surface(client, monkeypatch) -> None:
    monkeypatch.setenv("ERP_MOBILE_V2_ENABLED", "true")
    user = _login_admin(client)
    monkeypatch.setenv("FOMS_V3_SHELL_COHORT", str(user.id))

    response = client.get("/erp/shipment")

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert 'data-erp-mobile-v2="true"' in body
    assert "foms-mobile-v2-dashboard" in body
    assert "erp-shipment-mobile-dates" in body
    assert "erp-shipment-mobile-queue" in body
    assert "foms-mobile-empty" in body
    assert 'id="erp-shipment-mobile-search"' in body


def test_shipment_dashboard_renders_mobile_v2_queue_card(client, monkeypatch) -> None:
    monkeypatch.setenv("ERP_MOBILE_V2_ENABLED", "true")
    user = _login_admin(client)
    monkeypatch.setenv("FOMS_V3_SHELL_COHORT", str(user.id))

    today = get_today_kst().strftime("%Y-%m-%d")
    order = Order(
        received_date=today,
        customer_name="출고 모바일 고객",
        phone="010-1000-2000",
        address="서울시 출고구 모바일로 1",
        product="싱크대",
        status="IN_CONSTRUCTION",
        scheduled_date=today,
        manager_name="출고담당",
        is_erp_order=True,
        structured_data={
            "workflow": {"stage": "SHIPMENT"},
            "parties": {
                "customer": {"name": "출고 모바일 고객", "phone": "010-1000-2000"},
                "manager": {"name": "출고담당"},
            },
            "site": {"address_full": "서울시 출고구 모바일로 1"},
            "schedule": {"construction": {"date": today}},
            "items": [{"product_name": "싱크대", "spec_width": "1200"}],
            "shipment": {
                "construction_time": "오전 10:30",
                "drawing_managers": ["도면1"],
                "construction_workers": ["시공1"],
            },
        },
    )
    db_session.add(order)
    db_session.flush()
    db_session.add(
        OrderScheduleDate(
            order_id=order.id,
            kind="construction",
            date=today,
            source="shipment_mobile_test",
        )
    )
    db_session.commit()

    response = client.get("/erp/shipment")

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "foms-queue-card-v2" in body
    assert "erp-shipment-mobile-card--with-detail" in body
    assert "data-shipment-mobile-edit-trigger" in body
    assert "출고 정보 수정" in body
    assert "출고 모바일 고객" in body
    assert "오전 10:30" in body
    assert "도면1" in body
    assert "시공1" in body
