"""Shipment dashboard mobile v2 sticky search/filter (optional P0 gap)."""

from __future__ import annotations

from pathlib import Path

from werkzeug.security import generate_password_hash

from db import db_session
from models import User

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
    assert "erp-shipment-mobile-list__sticky" in main
    assert "shipment_mobile_controls.html" in main
    assert "foms-shipment-mobile.css" in dash


def test_shipment_dashboard_renders_mobile_v2_controls(client, monkeypatch) -> None:
    monkeypatch.setenv("ERP_MOBILE_V2_ENABLED", "true")
    user = _login_admin(client)
    monkeypatch.setenv("FOMS_V3_SHELL_COHORT", str(user.id))

    response = client.get("/erp/shipment")

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert 'data-erp-mobile-v2="true"' in body
    assert "erp-shipment-mobile-list__sticky" in body
    assert 'id="erp-shipment-mobile-search"' in body
