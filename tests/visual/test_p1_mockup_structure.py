"""P1 mockup visual structure contracts — DOM/CSS vs docs/design/mockups."""

from __future__ import annotations

from pathlib import Path

import pytest
from werkzeug.security import generate_password_hash

from db import db_session
from models import User

ROOT = Path(__file__).resolve().parents[2]


def _login_admin(client) -> User:
    user = User(
        username="p1_mockup_admin",
        password=generate_password_hash("admin"),
        role="ADMIN",
        team="CS",
        name="P1 Mockup Admin",
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    with client.session_transaction() as sess:
        sess["user_id"] = user.id
        sess["username"] = user.username
        sess["role"] = user.role
    return user


def test_p1_mockup_css_bundle_imports() -> None:
    """Mobile surfaces bundle must import P1 mockup-derived CSS."""
    bundle = (ROOT / "static/css/foundation/foms-mobile-surfaces.css").read_text(
        encoding="utf-8"
    )
    for fragment in (
        "foms-shell.css",
        "foms-buttons.css",
        "foms-chip-strip.css",
        "foms-queue-card-v2.css",
        "foms-detail-hero.css",
        "foms-detail-extras.css",
    ):
        assert fragment in bundle


def test_p1_dashboard_mobile_v2_body_mockup_selectors() -> None:
    """Dashboard mobile v2 partial uses mockup class names."""
    body = (ROOT / "templates/orders/partials/dashboard_mobile_v2_body.html").read_text(
        encoding="utf-8"
    )
    card = (ROOT / "templates/partials/shared/erp_mobile_queue_card_v2.html").read_text(
        encoding="utf-8"
    )
    for selector in (
        "chip-strip",
        "foms-chip-strip",
        "foms-shell-fab",
        "foms-mobile-queue-list",
        "foms-section-header",
        "foms-chip-strip--sort",
        "sort=latest",
        "sort=schedule",
        "sort=amount",
        "today=1",
        "담당:",
        "data-foms-mobile-queue-scroll",
        "data-foms-mobile-queue-sentinel",
        "data-foms-mobile-queue-chunk",
        "긴급 · 오늘 처리 필요",
    ):
        assert selector in body
    for selector in ("queue-card", "foms-queue-card-v2", "foms-queue-card-v2__attachments", "data-foms-lightbox-src"):
        assert selector in card


def test_p1_foms_app_shell_includes_queue_scroll_script() -> None:
    """C01 app shell loads mobile queue infinite scroll script."""
    shell = (ROOT / "templates/partials/shared/foms_app_shell.html").read_text(encoding="utf-8")
    assert "foms-app-shell" in shell
    assert "mobile-queue-scroll.js" in shell
    alias = (ROOT / "templates/partials/shared/erp_mobile_shell.html").read_text(encoding="utf-8")
    assert "foms_app_shell.html" in alias

def test_p1_order_detail_mobile_v2_mockup_selectors() -> None:
    """Mobile order detail partial matches mockup hero/quick-action structure."""
    body = (ROOT / "templates/orders/partials/order_detail_mobile_v2.html").read_text(
        encoding="utf-8"
    )
    products = (
        ROOT / "templates/orders/partials/order_detail_mobile_products.html"
    ).read_text(encoding="utf-8")
    combined = body + products
    for selector in (
        "foms-detail-hero",
        "foms-quick-actions",
        "foms-detail-section",
        "foms-detail-sticky-cta",
        "foms-attach-grid",
        "foms-timeline",
        "data-copy-value",
        "foms-detail-customer-title",
        "foms-detail-schedule-title",
        "foms-detail-amount-title",
        "data-foms-lightbox-gallery",
        "data-foms-mobile-product",
    ):
        assert selector in combined


def test_p1_shell_hides_desktop_chrome_on_mobile_v2() -> None:
    """foms-shell.css must hide legacy ERP header/nav under mobile v2."""
    shell = (ROOT / "static/css/foundation/foms-shell.css").read_text(encoding="utf-8")
    assert "foms-shell-desktop-only" in shell
    assert ".erp-pro-header" in shell
    assert ".erp-pro-nav" in shell
    assert "display: none !important" in shell


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("/erp/dashboard", "chip-strip"),
        ("/erp/dashboard", "foms-mobile-v2-dashboard"),
    ],
)
def test_p1_dashboard_renders_mockup_structure(
    client,
    monkeypatch: pytest.MonkeyPatch,
    path: str,
    expected: str,
) -> None:
    """Cohort ERP dashboard HTML includes P1 mockup DOM hooks."""
    user = _login_admin(client)
    monkeypatch.setenv("ERP_MOBILE_V2_ENABLED", "true")
    monkeypatch.setenv("FOMS_V3_SHELL_COHORT", str(user.id))

    resp = client.get(path)
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert 'class="erp-mobile-v2-layout"' in html
    assert expected in html


def test_p1_mobile_order_detail_route(
    client,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Mobile order detail route renders mockup hero section."""
    user = _login_admin(client)
    monkeypatch.setenv("ERP_MOBILE_V2_ENABLED", "true")
    monkeypatch.setenv("FOMS_V3_SHELL_COHORT", str(user.id))

    from models import Order, OrderEvent

    import datetime

    order = Order(
        received_date=datetime.date.today().isoformat(),
        customer_name="P1 Mockup Customer",
        phone="010-1234-5678",
        address="서울시 테스트",
        product="테스트 제품",
        is_erp_order=True,
        structured_data={
            "parties": {"customer": {"name": "P1 Mockup Customer", "phone": "010-1234-5678"}},
            "site": {"address_full": "서울시 테스트"},
            "workflow": {"stage": "RECEIVED"},
        },
    )
    db_session.add(order)
    db_session.flush()
    db_session.add(
        OrderEvent(
            order_id=order.id,
            event_type="STAGE_CHANGED",
            payload={"from": "RECEIVED", "to": "HAPPYCALL"},
            created_by_user_id=user.id,
        )
    )
    db_session.commit()

    resp = client.get(f"/erp/orders/{order.id}/mobile")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert "foms-detail-hero" in html
    assert "P1 Mockup Customer" in html
    assert "data-copy-value" in html
    assert "foms-timeline" in html


def test_p1_dashboard_mobile_chunk_fragment(
    client,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """mobile_chunk=1 returns queue chunk partial only."""
    user = _login_admin(client)
    monkeypatch.setenv("ERP_MOBILE_V2_ENABLED", "true")
    monkeypatch.setenv("FOMS_V3_SHELL_COHORT", str(user.id))

    resp = client.get("/erp/dashboard?mobile_chunk=1&page=1")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert "data-foms-mobile-queue-chunk" in html
    assert "foms-mobile-v2-dashboard" not in html


def test_p1_measurement_mobile_v2_home_ia_parity() -> None:
    """탭1 실측: 모바일 v2 분기가 홈 IA 표준 셸/칩/큐/FAB 셀렉터를 사용한다."""
    main = (ROOT / "templates/measurement/partials/dashboard_main.html").read_text(
        encoding="utf-8"
    )
    filters = (ROOT / "templates/measurement/partials/mobile_filters.html").read_text(
        encoding="utf-8"
    )
    listing = (ROOT / "templates/measurement/partials/mobile_list.html").read_text(
        encoding="utf-8"
    )
    # 셸 래퍼 + FAB (홈 dashboard_mobile_v2_body 동형)
    for selector in ("foms-shell-body", "foms-mobile-v2-dashboard", "foms-shell-fab"):
        assert selector in main, selector
    # 표준 칩 스트립 (bespoke quick-actions 대체)
    for selector in ("chip-strip", "foms-chip-strip"):
        assert selector in filters, selector
    # 큐 리스트 컨테이너 + 섹션 헤더
    for selector in ("foms-mobile-queue-list", "foms-section-header"):
        assert selector in listing, selector


def test_p1_measurement_dashboard_renders_home_ia(
    client,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Cohort 실측 대시보드 HTML이 홈 IA 셸/칩/FAB DOM 훅을 렌더한다."""
    user = _login_admin(client)
    monkeypatch.setenv("ERP_MOBILE_V2_ENABLED", "true")
    monkeypatch.setenv("FOMS_V3_SHELL_COHORT", str(user.id))

    resp = client.get("/erp/measurement")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert 'class="erp-mobile-v2-layout"' in html
    for selector in (
        "foms-shell-body",
        "foms-mobile-v2-dashboard",
        "chip-strip",
        "foms-chip-strip",
        "foms-section-header",
        "foms-shell-fab",
    ):
        assert selector in html, selector
