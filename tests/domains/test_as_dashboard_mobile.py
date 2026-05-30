"""P0-03: ERP AS dashboard mobile card audit (v1.1 badge, sticky controls, thumbnails)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from werkzeug.security import generate_password_hash

from db import db_session
from foms.services.as_dashboard_display import (
    as_stage_badge_modifier,
    as_thumb_enabled,
    batch_resolve_as_thumbnail_urls,
)
from models import Order, OrderAttachment, User


def _login_as_admin(client):
    user = User(
        username="erp_as_mobile_admin",
        password=generate_password_hash("admin"),
        role="ADMIN",
        team="CS",
        name="ERP AS Mobile Admin",
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()

    with client.session_transaction() as sess:
        sess["user_id"] = user.id
        sess["username"] = user.username
        sess["role"] = user.role

    return user


def _create_as_order(**kwargs):
    from datetime import date

    today = date.today().strftime("%Y-%m-%d")
    shipment = {"as_content": "<div>내용</div>"}
    shipment_extra = kwargs.pop("shipment_extra", None)
    if shipment_extra:
        shipment.update(shipment_extra)
    order = Order(
        received_date=today,
        customer_name=kwargs.get("customer_name", "AS 모바일 고객"),
        phone="010-1111-2222",
        address="Seoul",
        product="붙박이장",
        status=kwargs.get("status", "AS_RECEIVED"),
        manager_name="Alice",
        as_received_date=today,
        is_erp_order=True,
        structured_data={"shipment": shipment},
    )
    db_session.add(order)
    db_session.commit()
    return order


def test_as_stage_badge_modifier_completed():
    assert as_stage_badge_modifier(status="AS_COMPLETED", as_pending=False) == "--completed"


def test_as_stage_badge_modifier_cs_pending():
    assert as_stage_badge_modifier(status="AS_RECEIVED", as_pending=True) == "--cs"


def test_as_thumb_enabled_respects_env(monkeypatch):
    monkeypatch.delenv("FOMS_V3_AS_THUMB_ENABLED", raising=False)
    assert as_thumb_enabled() is False
    monkeypatch.setenv("FOMS_V3_AS_THUMB_ENABLED", "true")
    assert as_thumb_enabled() is True


def test_batch_resolve_as_thumbnail_urls_skips_when_disabled(monkeypatch):
    monkeypatch.setenv("FOMS_V3_AS_THUMB_ENABLED", "false")
    assert batch_resolve_as_thumbnail_urls([1, 2], db_session) == {}


@patch("foms.services.as_dashboard_display.build_file_view_url", return_value="/files/as-thumb")
def test_batch_resolve_as_thumbnail_urls_first_as_image(mock_url, monkeypatch, app):
    monkeypatch.setenv("FOMS_V3_AS_THUMB_ENABLED", "true")
    order = _create_as_order()
    db_session.add(
        OrderAttachment(
            order_id=order.id,
            filename="note.pdf",
            file_type="document",
            category="as",
            file_size=1,
            storage_key="as/doc.pdf",
        )
    )
    db_session.add(
        OrderAttachment(
            order_id=order.id,
            filename="photo.jpg",
            file_type="image",
            category="as",
            file_size=2,
            storage_key="as/photo.jpg",
        )
    )
    db_session.commit()

    urls = batch_resolve_as_thumbnail_urls([order.id], db_session)

    assert urls == {order.id: "/files/as-thumb"}
    mock_url.assert_called_once_with("as/photo.jpg")


def test_as_dashboard_mobile_v2_wiring_contract():
    body_src = (
        Path(__file__).resolve().parents[2] / "templates/cs/partials/as_dashboard_body.html"
    ).read_text(encoding="utf-8")
    dash_src = (Path(__file__).resolve().parents[2] / "templates/cs/as_dashboard.html").read_text(
        encoding="utf-8"
    )

    assert "foms-as-mobile-card.css" in dash_src
    assert "erp-as-mobile-list__sticky" in body_src
    assert "foms-stage-badge{{ r.stage_badge_modifier }}" in body_src
    assert "erp-as-mobile-card__thumb" in body_src
    assert body_src.count("as_mobile_controls.html") == 1


def test_as_dashboard_renders_mobile_v2_markup(client, monkeypatch):
    monkeypatch.setenv("ERP_MOBILE_V2_ENABLED", "true")
    monkeypatch.setenv("FOMS_V3_AS_THUMB_ENABLED", "true")
    user = _login_as_admin(client)
    monkeypatch.setenv("FOMS_V3_SHELL_COHORT", str(user.id))

    order = _create_as_order(customer_name="모바일 v2 AS")
    db_session.add(
        OrderAttachment(
            order_id=order.id,
            filename="as.jpg",
            file_type="image",
            category="as",
            file_size=100,
            storage_key="as/as.jpg",
        )
    )
    db_session.commit()

    with patch(
        "foms.services.as_dashboard_display.build_file_view_url",
        return_value="/files/as-view",
    ):
        response = client.get("/erp/as?tab=incomplete")

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert 'data-erp-mobile-v2="true"' in body
    assert "erp-as-mobile-list__sticky" in body
    assert "erp-as-mobile-controls" in body
    assert "foms-stage-badge foms-stage-badge--cs" in body
    assert "erp-as-mobile-card__thumb" in body
    assert "/files/as-view" in body


def test_as_dashboard_hides_thumb_when_flag_off(client, monkeypatch):
    monkeypatch.setenv("ERP_MOBILE_V2_ENABLED", "true")
    monkeypatch.setenv("FOMS_V3_AS_THUMB_ENABLED", "false")
    user = _login_as_admin(client)
    monkeypatch.setenv("FOMS_V3_SHELL_COHORT", str(user.id))

    _create_as_order(customer_name="썸네일 off")

    response = client.get("/erp/as?tab=incomplete")

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "erp-as-mobile-list__sticky" in body
    assert "erp-as-mobile-card__thumb" not in body
