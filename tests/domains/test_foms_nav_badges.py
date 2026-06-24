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


def test_measurement_bucket_excludes_drawing():
    """실측 탭 배지는 MEASURE만 — DRAWING은 drawing_workbench 전담 (영업 통합 SSOT)."""
    from foms.services.dashboard_counts import NAV_STATUS_BUCKETS

    assert NAV_STATUS_BUCKETS["measurement"] == frozenset({"MEASURE"})
    assert "DRAWING" not in NAV_STATUS_BUCKETS["measurement"]
    assert NAV_STATUS_BUCKETS["drawing_workbench"] == frozenset({"DRAWING"})


def test_sales_drawing_cohort_primary_nav_promotes_drawing():
    """영업·도면 cohort는 bottom-nav primary에 도면(drawing_workbench)을 노출한다."""
    shell = _read("templates/partials/shared/erp_mobile_shell.html")
    assert "_sales_drawing_cohort" in shell
    assert "'SALES', 'DRAWING', 'MEASURE'" in shell
    assert "['dashboard', 'measurement', 'drawing_workbench', 'shipment']" in shell


def test_context_processor_registers_inject_foms_nav_badges():
    src = _read("foms/services/context_processors.py")
    assert "def inject_foms_nav_badges" in src
    assert "app.context_processor(inject_foms_nav_badges)" in src


def test_bottom_nav_template_renders_badge_from_foms_nav_badges():
    nav = _read("templates/partials/shared/erp_mobile_bottom_nav.html")
    assert "foms_nav_badges" in nav
    assert "erp-mobile-bottom-nav__badge" in nav


def test_foms_bottom_nav_css_imported():
    surfaces = _read("static/css/foundation/foms-mobile-surfaces.css")
    assert "foms-bottom-nav.css" in surfaces
    badge_css = _read("static/css/components/foms-bottom-nav.css")
    assert ".erp-mobile-bottom-nav__badge" in badge_css


def test_bottom_nav_tap_feedback_assets():
    """Tap ack + HTMX pending — compositor-only CSS, passive pointerdown JS."""
    css = _read("static/css/components/foms-bottom-nav.css")
    assert "-webkit-tap-highlight-color: transparent" in css
    assert "erp-nav-tap-ack" in css
    assert "prefers-reduced-motion" in css
    assert "transform: scale" in css
    js = _read("static/js/foms/bottom-nav-shell.js")
    assert "initBottomNavTapFeedback" in js
    assert "is-tap-ack" in js
    assert "is-nav-pending" in js
    assert "passive: true" in js
    assert "aria-busy" in js
    assert "12000" in js


def test_nav_badge_cache_ttl_constant():
    from foms.services.dashboard_counts import NAV_BADGE_CACHE_TTL_SEC

    assert NAV_BADGE_CACHE_TTL_SEC == 30


def test_compute_nav_badge_counts_empty_user():
    from foms.services.dashboard_counts import compute_nav_badge_counts, NAV_STATUS_BUCKETS

    counts = compute_nav_badge_counts(None)
    assert set(counts.keys()) == set(NAV_STATUS_BUCKETS.keys())
    assert all(v == 0 for v in counts.values())


def test_mine_only_teams_cover_sales_construction_not_drawing():
    """영업 통합·시공은 배지 mine-only, 도면은 전체 집계(assignee 누락 방지)."""
    from foms.services.dashboard_counts import MINE_ONLY_TEAMS

    assert {"CONSTRUCTION", "SALES", "MEASURE"} <= MINE_ONLY_TEAMS
    assert "DRAWING" not in MINE_ONLY_TEAMS


def test_sales_user_badge_counts_are_mine_only(app):
    """영업(SALES) 배지는 담당(manager_name) 주문만 집계 → '내 차례'. 타 영업 주문 제외."""
    from werkzeug.security import generate_password_hash

    from db import db_session
    from foms.services.dashboard_counts import compute_nav_badge_counts, _mine_only_for_user
    from models import Order, User

    with app.app_context():
        sales = User(
            username="sales_mine_only",
            password=generate_password_hash("x"),
            role="ADMIN",
            team="SALES",
            name="영업담당고유명",
        )
        db_session.add(sales)
        db_session.commit()
        assert _mine_only_for_user(sales) is True

        mine = Order(
            received_date="2026-05-30",
            customer_name="MyCust",
            phone="010-0000-0001",
            address="A",
            product="P",
            status="MEASURE",
            is_erp_order=True,
            manager_name="영업담당고유명",
            structured_data={},
        )
        other = Order(
            received_date="2026-05-30",
            customer_name="OtherCust",
            phone="010-0000-0002",
            address="B",
            product="P",
            status="MEASURE",
            is_erp_order=True,
            manager_name="다른영업사람",
            structured_data={},
        )
        db_session.add_all([mine, other])
        db_session.commit()

        counts = compute_nav_badge_counts(sales)
        # 두 건 모두 MEASURE지만 담당 매칭은 1건만 → "내 차례"
        assert counts["measurement"] == 1


def test_drawing_user_badges_follow_global_mine_selection(app):
    """도면 사용자가 전역 mine을 켜면 배지도 도면 배정 관계만 집계한다."""
    from werkzeug.security import generate_password_hash

    from db import db_session
    from foms.services.dashboard_counts import compute_nav_badge_counts
    from models import Order, User

    with app.app_context():
        drawing = User(
            username="drawing_badge_mine",
            password=generate_password_hash("x"),
            role="USER",
            team="DRAWING",
            name="도면배지담당",
        )
        db_session.add(drawing)
        db_session.commit()
        mine = Order(
            received_date="2026-05-30",
            customer_name="DrawingMine",
            phone="010-0000-0011",
            address="A",
            product="P",
            status="DRAWING",
            is_erp_order=True,
            manager_name="다른 영업",
            structured_data={
                "assignments": {"drawing_assignee_user_ids": [drawing.id]},
                "drawing_assignees": [{"id": drawing.id, "name": drawing.name}],
            },
        )
        manager_only = Order(
            received_date="2026-05-30",
            customer_name="ManagerOnly",
            phone="010-0000-0012",
            address="B",
            product="P",
            status="DRAWING",
            is_erp_order=True,
            manager_name=drawing.name,
            structured_data={
                "parties": {"manager": {"name": drawing.name}},
                "drawing_assignees": [{"name": "다른 도면"}],
            },
        )
        db_session.add_all([mine, manager_only])
        db_session.commit()

        counts = compute_nav_badge_counts(drawing, mine_only=True)

        assert counts["drawing_workbench"] == 1


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
