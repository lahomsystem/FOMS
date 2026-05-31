"""P1-01: ERP mobile bottom-nav badge counts and template wiring."""

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def _read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def test_nav_status_buckets_cover_primary_tabs():
    from foms.services.dashboard_counts import NAV_STATUS_BUCKETS

    for nav_id in ("dashboard", "measurement", "construction", "shipment", "completion"):
        assert nav_id in NAV_STATUS_BUCKETS


def test_context_processor_registers_inject_foms_nav_badges():
    src = _read("foms/services/context_processors.py")
    assert "def inject_foms_nav_badges" in src
    assert "app.context_processor(inject_foms_nav_badges)" in src


def test_bottom_nav_template_renders_badge_from_foms_nav_badges():
    nav = _read("templates/partials/shared/erp_mobile_bottom_nav.html")
    assert "foms_nav_badges" in nav
    assert "erp-mobile-bottom-nav__badge" in nav


def test_foms_bottom_nav_css_imported():
    erp_pro = _read("static/css/foundation/erp-pro.css")
    assert "foms-bottom-nav.css" in erp_pro
    badge_css = _read("static/css/components/foms-bottom-nav.css")
    assert ".erp-mobile-bottom-nav__badge" in badge_css


def test_nav_badge_cache_ttl_constant():
    from foms.services.dashboard_counts import NAV_BADGE_CACHE_TTL_SEC

    assert NAV_BADGE_CACHE_TTL_SEC == 30


def test_compute_nav_badge_counts_empty_user():
    from foms.services.dashboard_counts import compute_nav_badge_counts, NAV_STATUS_BUCKETS

    counts = compute_nav_badge_counts(None)
    assert set(counts.keys()) == set(NAV_STATUS_BUCKETS.keys())
    assert all(v == 0 for v in counts.values())


def test_compute_nav_badge_counts_aggregates_erp_orders(app, monkeypatch):
    """Stage bucket sums appear on dashboard tab after ERP order insert."""
    from werkzeug.security import generate_password_hash

    from db import db_session
    from foms.services.dashboard_counts import compute_nav_badge_counts
    from models import Order, User

    monkeypatch.setenv("ERP_MOBILE_V2_ENABLED", "true")

    with app.app_context():
        user = User(
            username="nav_badge_admin",
            password=generate_password_hash("admin"),
            role="ADMIN",
            team="CS",
            name="Nav Badge Admin",
        )
        db_session.add(user)
        db_session.commit()
        monkeypatch.setenv("FOMS_V3_SHELL_COHORT", str(user.id))

        order = Order(
            received_date="2026-05-30",
            customer_name="Badge Test",
            phone="010-1111-2222",
            address="Seoul",
            product="Kitchen",
            status="RECEIVED",
            is_erp_order=True,
            structured_data={},
        )
        db_session.add(order)
        db_session.commit()

        counts = compute_nav_badge_counts(user)
        assert counts["dashboard"] >= 1
        assert counts["measurement"] == 0
