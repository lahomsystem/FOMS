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
        "foms-mobile-filter-bar.css",
        "foms-queue-card-v2.css",
        "foms-detail-hero.css",
        "foms-detail-extras.css",
        "foms-drawing-mobile-card.css",
        "dashboard-control-tower.css",
    ):
        assert fragment in bundle
    filter_bar = (ROOT / "static/css/components/foms-mobile-filter-bar.css").read_text(
        encoding="utf-8"
    )
    for token in ("100vw", "calc(50% - 50vw)", "overflow: visible"):
        assert token in filter_bar


def test_p1_dashboard_tower_has_no_fragment_stylesheet_link() -> None:
    """Tower CSS must live in mobile-surfaces bundle — fragment <link> causes shell-swap FOUC."""
    tower = (ROOT / "templates/orders/partials/dashboard_mobile_tower.html").read_text(
        encoding="utf-8"
    )
    assert 'rel="stylesheet"' not in tower
    assert "<link " not in tower


def test_p1_dashboard_tower_mobile_width_contract() -> None:
    """Tower home must shrink inside foms-shell-body like other mobile-v2 tabs."""
    tower_css = (
        ROOT / "static/css/contexts/orders/dashboard-control-tower.css"
    ).read_text(encoding="utf-8")
    tower_tpl = (
        ROOT / "templates/orders/partials/dashboard_mobile_tower.html"
    ).read_text(encoding="utf-8")
    tower_field_list = (
        ROOT / "templates/orders/partials/dashboard_mobile_tower_field_list.html"
    ).read_text(encoding="utf-8")
    for token in (
        "foms-shell-body.foms-tower",
        "min-width: 0",
        "max-width: 100%",
        "foms-tower__field-body",
        "foms-tower__risk",
        "foms-tower__risk-count",
        "flex-shrink: 0",
        "overflow: clip",
        "erp-dashboard-mobile-v2",
    ):
        assert token in tower_css or token in tower_tpl
    for token in (
        "foms-tower__day-count--measure",
        "foms-tower__day-count--as",
        "grid-template-rows: auto auto auto",
        "grid-template-columns: repeat(4, minmax(0, 1fr))",
        "justify-content: center",
        "min-width: 34px",
        "foms-tower__pipeline-toggle::after",
        "content: '펼치기'",
        "content: '접기'",
        "align-content: start",
        "is-empty",
        "📐",
        "🔧",
    ):
        assert token in tower_css or token in tower_tpl
    assert 'class="foms-tower__pipeline-toggle" aria-hidden="true"></span>' in tower_tpl
    assert 'class="foms-tower__pipeline-toggle">접기</span>' not in tower_tpl
    assert "row.type_code == 'as'" in tower_field_list
    assert "foms-stage-badge--{{ 'construction' if row.type_code == 'construction' else ('cs' if row.type_code == 'as' else 'measure') }}" in tower_field_list


def test_p1_dashboard_mobile_v2_body_mockup_selectors() -> None:
    """Dashboard mobile v2 partial keeps app-like queue chrome without filter chip rows."""
    body = (ROOT / "templates/orders/partials/dashboard_mobile_v2_body.html").read_text(
        encoding="utf-8"
    )
    sections = (
        ROOT / "templates/orders/partials/dashboard_mobile_queue_sections.html"
    ).read_text(encoding="utf-8")
    filters = (
        ROOT / "templates/orders/partials/dashboard_mobile_filter_sheet.html"
    ).read_text(encoding="utf-8")
    card = (ROOT / "templates/partials/shared/erp_mobile_queue_card_v2.html").read_text(
        encoding="utf-8"
    )
    for selector in (
        "foms-shell-fab",
        "foms-mobile-queue-list",
        "data-foms-mobile-queue-scroll",
        "data-foms-mobile-queue-sentinel",
        "data-foms-mobile-queue-chunk",
        "dashboard_mobile_queue_sections.html",
    ):
        assert selector in body
    for selector in (
        "foms-section-header",
        "foms-section-header--stage",
        "긴급 · 오늘 처리 필요",
    ):
        assert selector in sections
    assert "dashboard_mobile_filter_sheet.html" in body
    for selector in (
        "foms-mobile-queue-toolbar",
        "data-foms-mobile-filter-open",
        "foms-mobile-filter-sheet",
        "erp-dashboard-mobile-filter-drawer",
        'name="sort"',
        "foms-mobile-filter-bar",
        "foms-mobile-filter-bar--dashboard-queue",
        'aria-label="작업 큐 단계 필터"',
        'name="view"',
        "foms-chip--filter",
        "foms-chip__count",
        "fa-hammer",
        "fa-layer-group",
    ):
        assert selector in filters
    assert "{{ total_orders }}건" not in filters
    for removed_selector in (
        "foms-chip-strip--sort",
        "sort=latest",
        "sort=schedule",
        'aria-label="필터"',
        'aria-label="정렬"',
    ):
        assert removed_selector not in body
    for selector in (
        "queue-card",
        "foms-queue-card-v2",
        "foms-queue-card-v2__attachments",
        "data-foms-erp-attachment-view-url",
        "data-workflow-stage",
        "has_manager_phone",
        "tel:{{ safe_manager_phone }}",
        'aria-label="{{ edit_label }}"',
        "{{ edit_label }}",
    ):
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
        "data-foms-attachment-preview-gallery",
        "data-foms-attachment-preview",
        "data-foms-product-item",
        "data-foms-product-toggle",
    ):
        assert selector in combined


def test_p1_shell_hides_desktop_chrome_on_mobile_v2() -> None:
    """foms-shell.css must hide legacy ERP header/nav under mobile v2."""
    shell = (ROOT / "static/css/foundation/foms-shell.css").read_text(encoding="utf-8")
    head = (ROOT / "templates/partials/shared/layout_head.html").read_text(
        encoding="utf-8"
    )
    assert "foms-shell-desktop-only" in shell
    assert ".erp-pro-header" in shell
    assert ".erp-pro-nav" in shell
    assert "display: none !important" in shell
    assert "foms-mobile-v2-critical-css" in head
    assert ".layout-header" in head
    assert ".layout-global-nav--erp-v2-suppressed" in head
    assert 'erp-dashboard\\00002d layout' in head
    assert "foms-mobile-surfaces.css') }}?v=20260723g" in head
    assert head.index("foms-mobile-v2-critical-css") < head.index("foms-mobile-surfaces.css")


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        # 홈(드릴 없음) = 오퍼레이션 컨트롤 타워.
        ("/erp/dashboard", "foms-mobile-v2-dashboard"),
        ("/erp/dashboard", "foms-tower"),
        ("/erp/dashboard", "data-foms-tower"),
        # 드릴(view=queue) = 기존 작업 큐. 빈 DB면 큐 빈 상태(foms-mobile-empty).
        ("/erp/dashboard?view=queue", "foms-mobile-v2-dashboard"),
        ("/erp/dashboard?view=queue", "foms-mobile-empty"),
        ("/erp/dashboard?mine=1&view=queue", "foms-mobile-filter-bar--dashboard-queue"),
        ("/erp/dashboard?mine=1&view=queue", 'aria-label="작업 큐 단계 필터"'),
    ],
)
def test_p1_dashboard_renders_mockup_structure(
    client,
    monkeypatch: pytest.MonkeyPatch,
    path: str,
    expected: str,
) -> None:
    """Cohort ERP dashboard: 홈은 컨트롤 타워, 드릴은 작업 큐 DOM hook을 노출한다."""
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
    dates = (ROOT / "templates/measurement/partials/mobile_dates.html").read_text(
        encoding="utf-8"
    )
    listing = (ROOT / "templates/measurement/partials/mobile_list.html").read_text(
        encoding="utf-8"
    )
    # 셸 래퍼 + FAB (홈 dashboard_mobile_v2_body 동형)
    for selector in ("foms-shell-body", "foms-mobile-v2-dashboard", "foms-shell-fab"):
        assert selector in main, selector
    # 표준 필터 바 + 칩 스트립 (bespoke quick-actions 대체)
    for selector in ("foms-mobile-filter-bar", "chip-strip", "foms-chip-strip"):
        assert selector in filters, selector
    for selector in (
        "erp-measurement-mobile-date-chip",
        "erp-measurement-mobile-date-chip__meta",
    ):
        assert selector in dates, selector
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


def test_p1_drawing_mobile_v2_home_ia_parity() -> None:
    """탭2 도면: 모바일 v2가 홈 IA 셸/칩/큐/FAB 셀렉터를 사용하고 process-map은 모바일 hide."""
    body = (ROOT / "templates/drawing/partials/workbench_dashboard_body.html").read_text(
        encoding="utf-8"
    )
    queue = (ROOT / "templates/drawing/partials/workbench_mobile_queue.html").read_text(
        encoding="utf-8"
    )
    combined = body + queue
    controls = (
        ROOT / "templates/drawing/partials/drawing_mobile_controls.html"
    ).read_text(encoding="utf-8")
    gallery = (
        ROOT / "templates/drawing/partials/drawing_mobile_v2_gallery.html"
    ).read_text(encoding="utf-8")
    # 큐 리스트 + 섹션 헤더 + FAB. v2는 legacy erp-pro-card 밖 foms-shell-body 표면에서 렌더한다.
    for selector in ("foms-drawing-mobile-dashboard", "foms-mobile-queue-list", "foms-section-header", "foms-shell-fab"):
        assert selector in combined, selector
    assert "drawing_mobile_v2_gallery.html" not in body
    # 레거시 process-map은 모바일 v2에서 hide (chip-strip로 대체)
    assert 'dw-process-map{% if erp_mobile_v2_enabled %} d-none d-lg-block' in body
    # 표준 필터 바 + 칩 스트립 (상태 필터)
    for selector in ("foms-mobile-filter-bar", "foms-mobile-filter-bar--drawing", "chip-strip", "foms-chip-strip"):
        assert selector in controls, selector
    # 갤러리는 foms-shell-body
    assert "foms-shell-body" in gallery


def test_p1_drawing_queue_card_action_bar_css_contract() -> None:
    """도면 큐 카드 액션 footer는 queue-card-v2처럼 grid full-span·border-top·foms-btn flex."""
    css = (ROOT / "static/css/components/foms-drawing-mobile-card.css").read_text(encoding="utf-8")
    queue = (ROOT / "templates/drawing/partials/workbench_mobile_queue_card.html").read_text(encoding="utf-8")
    assert "grid-column: 1 / -1;" in css
    assert "flex: 1 1 auto;" in css
    assert "foms-drawing-queue-card__action-label" in css
    assert "foms-drawing-queue-card__action-label" in queue
    assert "flex: 1 1 0" not in css


def test_p1_drawing_handoff_mobile_v2_mockup_selectors() -> None:
    """도면 핸드오프 목업 A/B/C가 모바일 v2 partial/CSS/JS hook으로 연결된다."""
    body = (ROOT / "templates/drawing/partials/workbench_mobile_handoff.html").read_text(
        encoding="utf-8"
    )
    queue = (ROOT / "templates/drawing/partials/workbench_mobile_queue_card.html").read_text(
        encoding="utf-8"
    )
    css = (ROOT / "static/css/components/foms-drawing-mobile.css").read_text(
        encoding="utf-8"
    )
    js = (ROOT / "static/js/foms/drawing-handoff.js").read_text(encoding="utf-8")
    for selector in (
        "foms-drawing-handoff",
        "foms-drawing-sheet-list",
        "foms-drawing-handoff-detail",
        "foms-drawing-viewer",
        "foms-drawing-viewer__download",
        "foms-drawing-viewer__stage",
        "foms-drawing-thread",
        "foms-drawing-action-bar",
    ):
        assert selector in body, selector
        assert selector in css, selector
    for selector in ("foms-drawing-queue-card__turn", "primary_action_label", "foms-drawing-queue-card__erp-edit", "open='erp-order'"):
        assert selector in queue, selector
    for selector in ("data-drawing-handoff-open", "data-drawing-handoff-action"):
        assert selector in body, selector
    assert "padding: 0.5rem 0.75rem 5.25rem;" in css
    assert "body.erp-mobile-v2-layout .foms-drawing-action-bar__btn span" in css
    assert "white-space: nowrap;" in css
    assert "GlobalImageViewer.open" in js
    assert "btn-confirm-receipt" in js


def test_p1_fragment_scripts_are_redeclaration_safe() -> None:
    """ERP shell fragment scripts may run more than once; top-level labels/state must not use lexical declarations."""
    for rel in (
        "templates/production/partials/scripts.html",
        "templates/construction/partials/scripts.html",
    ):
        src = (ROOT / rel).read_text(encoding="utf-8")
        for forbidden in (
            "const TEAM_LABELS",
            "const STAGE_LABELS",
            "let __selectedOrderId",
            "let __attachmentsCache",
            "const ATTACHMENT_CATEGORY_META",
            "let notificationPanelOpen",
        ):
            assert forbidden not in src, f"{rel}: {forbidden}"
        assert "var TEAM_LABELS" in src


def test_p1_global_image_viewer_touch_pan_after_pinch() -> None:
    """첨부 뷰어는 핀치 줌 후 남은 한 손가락 이동을 pan으로 이어받는다."""
    src = (ROOT / "static/js/runtime/layout-scripts-core.js").read_text(
        encoding="utf-8"
    )
    layout = (ROOT / "templates/partials/shared/layout_scripts.html").read_text(
        encoding="utf-8"
    )
    assert "function beginTouchPan" in src
    assert "remaining === 1" in src
    assert "beginTouchPan(e.touches[0])" in src
    assert "layout-scripts-core.js" not in layout
    assert "window.FOMSNotificationBadge" in layout or "GlobalImageViewer" in src
    assert "touch-action: none;" in layout


def test_p1_drawing_dashboard_renders_home_ia(
    client,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Cohort 도면 작업실 HTML이 홈 IA 셸/칩/FAB DOM 훅을 렌더한다."""
    user = _login_admin(client)
    monkeypatch.setenv("ERP_MOBILE_V2_ENABLED", "true")
    monkeypatch.setenv("FOMS_V3_SHELL_COHORT", str(user.id))

    resp = client.get("/erp/drawing-workbench")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert 'class="erp-mobile-v2-layout"' in html
    for selector in (
        "foms-shell-body",
        "chip-strip",
        "foms-chip-strip",
        "foms-section-header",
        "foms-shell-fab",
    ):
        assert selector in html, selector


def test_p1_production_mobile_v2_home_ia_parity() -> None:
    """탭3 생산: 모바일 v2가 홈 IA 셸/칩/큐/FAB 셀렉터를 사용한다."""
    body = (ROOT / "templates/production/partials/dashboard_body.html").read_text(
        encoding="utf-8"
    )
    filters = (ROOT / "templates/production/partials/mobile_filters.html").read_text(
        encoding="utf-8"
    )
    queue = (ROOT / "templates/production/partials/mobile_queue.html").read_text(
        encoding="utf-8"
    )
    for selector in ("foms-shell-body", "foms-mobile-v2-dashboard", "foms-shell-fab"):
        assert selector in body, selector
    for selector in ("foms-mobile-filter-bar", "chip-strip", "foms-chip-strip"):
        assert selector in filters, selector
    for selector in ("foms-mobile-queue-list", "foms-section-header"):
        assert selector in queue, selector


def test_queue_card_v2_supports_pc_workflow_action_parity() -> None:
    """Mobile v2 cards must keep workflow actions and ERP edit as separate affordances."""
    card = (ROOT / "templates/partials/shared/erp_mobile_queue_card_v2.html").read_text(
        encoding="utf-8"
    )
    css = (ROOT / "static/css/components/foms-queue-card-v2.css").read_text(
        encoding="utf-8"
    )

    assert "task_actions=None" in card
    assert "queue_card_schedule" in card
    assert "action_list" in card
    assert "for action in action_list" in card
    assert "open='erp-order'" in card
    assert "edit_return_to" in card
    assert "flex-wrap: wrap;" in css
    assert "min-height: var(--foms-touch-target-min);" in css
    # 액션 없는 카드(메인/실측/출고 등)는 stage 워크플로우 액션을 1순위로 노출하고
    # ERP 편집은 secondary로 강등한다.
    # - 미승인 퀘스트: 상세 승인 섹션으로 deep-link(맥락/권한 재검증)
    # - 도면 단계(메인 enrichment에서 퀘스트 미생성): 도면 창구로 직접 진입
    assert "quest_actionable" in card
    assert "퀘스트 승인" in card
    assert "#foms-detail-quest" in card
    assert "can_assignee_approve" in card
    assert "drawing_actionable" in card
    assert "도면 창구" in card
    assert "erp_drawing_workbench.erp_drawing_workbench_detail" in card
    assert "action_list or workflow_actionable" in card


def test_p1_production_dashboard_renders_home_ia(
    client,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Cohort 생산 대시보드 HTML이 홈 IA 셸/칩/FAB DOM 훅을 렌더한다."""
    user = _login_admin(client)
    monkeypatch.setenv("ERP_MOBILE_V2_ENABLED", "true")
    monkeypatch.setenv("FOMS_V3_SHELL_COHORT", str(user.id))

    resp = client.get("/erp/production/dashboard")
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


def test_p1_shipment_mobile_v2_home_ia_parity() -> None:
    """탭4 출고: 모바일 v2가 실측형 셸/칩/날짜/queue-card-v2/FAB 셀렉터를 사용한다."""
    body = (ROOT / "templates/shipment/partials/dashboard_main.html").read_text(
        encoding="utf-8"
    )
    controls = (
        ROOT / "templates/shipment/partials/shipment_mobile_controls.html"
    ).read_text(encoding="utf-8")
    dates = (
        ROOT / "templates/shipment/partials/shipment_mobile_dates.html"
    ).read_text(encoding="utf-8")
    queue = (
        ROOT / "templates/shipment/partials/shipment_mobile_queue.html"
    ).read_text(encoding="utf-8")
    for selector in ("foms-shell-body", "foms-mobile-v2-dashboard", "foms-shell-fab"):
        assert selector in body, selector
    for selector in ("foms-mobile-filter-bar", "chip-strip", "foms-chip-strip"):
        assert selector in controls, selector
    for selector in (
        "erp-shipment-mobile-date-chip",
        "erp-shipment-mobile-date-chip__meta",
    ):
        assert selector in dates, selector
    for selector in ("foms-mobile-queue-list", "foms-section-header", "render_queue_card_v2"):
        assert selector in queue, selector


def test_p1_shipment_dashboard_renders_home_ia(
    client,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Cohort 출고 대시보드 HTML이 홈 IA 셸/칩/FAB DOM 훅을 렌더한다."""
    user = _login_admin(client)
    monkeypatch.setenv("ERP_MOBILE_V2_ENABLED", "true")
    monkeypatch.setenv("FOMS_V3_SHELL_COHORT", str(user.id))

    resp = client.get("/erp/shipment")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert 'class="erp-mobile-v2-layout"' in html
    for selector in (
        "foms-shell-body",
        "foms-mobile-v2-dashboard",
        "chip-strip",
        "foms-chip-strip",
        "foms-section-header",
        "erp-shipment-mobile-queue",
        "foms-shell-fab",
    ):
        assert selector in html, selector


def test_p1_as_mobile_v2_home_ia_parity() -> None:
    """탭5 AS: 모바일 v2가 홈 IA 셸/칩/큐/FAB + AS 카메라 바 셀렉터를 사용한다."""
    body = (ROOT / "templates/cs/partials/as_dashboard_body.html").read_text(
        encoding="utf-8"
    )
    controls = (ROOT / "templates/cs/partials/as_mobile_controls.html").read_text(
        encoding="utf-8"
    )
    summary = (ROOT / "templates/cs/partials/as_mobile_summary.html").read_text(
        encoding="utf-8"
    )
    camera = (ROOT / "templates/cs/partials/as_mobile_v2_camera_bar.html").read_text(
        encoding="utf-8"
    )
    for selector in ("foms-shell-body", "foms-mobile-queue-list", "foms-shell-fab"):
        assert selector in body, selector
    # 슬림 sticky 요약 바(section-header + 건수)는 as_mobile_summary.html로 분리
    assert "as_mobile_summary.html" in body
    assert "foms-section-header" in summary
    assert "erp-as-mobile-controls__count" in summary
    assert "erp-as-mobile-controls__mine-toggle" not in summary
    # 스크롤로 흘려보내는 보조 컨트롤(필터 바·칩 스트립)은 controls에 유지
    for selector in ("foms-mobile-filter-bar", "chip-strip", "foms-chip-strip"):
        assert selector in controls, selector
    assert "foms-as-camera-bar" in camera


def test_p1_as_dashboard_renders_home_ia(
    client,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Cohort AS 대시보드 HTML이 홈 IA 셸/칩/FAB + 카메라 바 DOM 훅을 렌더한다."""
    user = _login_admin(client)
    monkeypatch.setenv("ERP_MOBILE_V2_ENABLED", "true")
    monkeypatch.setenv("FOMS_V3_SHELL_COHORT", str(user.id))

    resp = client.get("/erp/as")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert 'class="erp-mobile-v2-layout"' in html
    for selector in (
        "foms-shell-body",
        "chip-strip",
        "foms-chip-strip",
        "foms-section-header",
        "foms-shell-fab",
        "foms-as-camera-bar",
    ):
        assert selector in html, selector


def test_p1_construction_mobile_v2_home_ia_parity() -> None:
    """탭6 시공: 모바일 v2가 홈 IA 셸/칩/큐/FAB 셀렉터를 사용한다."""
    body = (ROOT / "templates/construction/partials/dashboard_body.html").read_text(
        encoding="utf-8"
    )
    filters = (
        ROOT / "templates/construction/partials/mobile_filters.html"
    ).read_text(encoding="utf-8")
    queue = (ROOT / "templates/construction/partials/mobile_queue.html").read_text(
        encoding="utf-8"
    )
    for selector in ("foms-shell-body", "foms-mobile-v2-dashboard", "foms-shell-fab"):
        assert selector in body, selector
    for selector in ("foms-mobile-filter-bar", "chip-strip", "foms-chip-strip"):
        assert selector in filters, selector
    for selector in ("foms-mobile-queue-list", "foms-section-header"):
        assert selector in queue, selector


def test_mobile_pager_single_line_css_contract() -> None:
    """모바일 번호 페이저는 nowrap + 가로 스크롤 폴백으로 1줄 유지 (화살표 줄바꿈 방지)."""
    css = (
        ROOT / "static/css/foundation/erp-pro/11-queue-family-mobile.css"
    ).read_text(encoding="utf-8")
    pager_block = css.split(".foms-mobile-pager {", 1)[1].split(".foms-mobile-pager__num", 1)[0]
    assert "flex-wrap: nowrap" in pager_block
    assert "overflow-x: auto" in pager_block
    assert "flex-wrap: wrap" not in pager_block


def test_mobile_pager_shared_partial_unification() -> None:
    """모바일 큐 페이저는 shared macro 단일 SSOT (도면 relative 포함)."""
    pager = (ROOT / "templates/partials/shared/mobile_queue_pager.html").read_text(
        encoding="utf-8"
    )
    for macro in (
        "render_mobile_pager",
        "render_mobile_pager_relative",
        "foms-mobile-pager",
    ):
        assert macro in pager
    construction = (
        ROOT / "templates/construction/partials/mobile_queue.html"
    ).read_text(encoding="utf-8")
    drawing = (
        ROOT / "templates/drawing/partials/workbench_mobile_queue.html"
    ).read_text(encoding="utf-8")
    assert "render_mobile_pager(" in construction
    assert "render_mobile_pager_relative(" in drawing
    assert '<nav class="foms-mobile-pager"' not in drawing


def test_p1_construction_dashboard_renders_home_ia(
    client,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Cohort 시공 대시보드 HTML이 홈 IA 셸/칩/FAB DOM 훅을 렌더한다."""
    user = _login_admin(client)
    monkeypatch.setenv("ERP_MOBILE_V2_ENABLED", "true")
    monkeypatch.setenv("FOMS_V3_SHELL_COHORT", str(user.id))

    resp = client.get("/erp/construction/dashboard")
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


def test_p1_completion_mobile_v2_home_ia_parity() -> None:
    """탭7 시공완료: 모바일 v2가 홈 IA 셸/큐/섹션/FAB 셀렉터를 사용한다 (JS 리뷰 리스트, 필터 없음)."""
    body = (ROOT / "templates/cs/partials/completion_dashboard_body.html").read_text(
        encoding="utf-8"
    )
    for selector in (
        "foms-shell-body",
        "foms-mobile-queue-list",
        "foms-section-header",
        "foms-shell-fab",
    ):
        assert selector in body, selector


def test_p1_completion_dashboard_renders_home_ia(
    client,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Cohort 시공완료 대시보드 HTML이 홈 IA 셸/큐/섹션/FAB DOM 훅을 렌더한다."""
    user = _login_admin(client)
    monkeypatch.setenv("ERP_MOBILE_V2_ENABLED", "true")
    monkeypatch.setenv("FOMS_V3_SHELL_COHORT", str(user.id))

    resp = client.get("/erp/completion")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert 'class="erp-mobile-v2-layout"' in html
    for selector in (
        "foms-shell-body",
        "foms-mobile-queue-list",
        "foms-section-header",
        "foms-shell-fab",
    ):
        assert selector in html, selector


def test_p1_history_mobile_v2_home_ia_parity() -> None:
    """탭8 과거이력: 모바일 v2가 홈 IA 셸/칩/큐/섹션/FAB 셀렉터를 사용한다."""
    body = (ROOT / "templates/orders/partials/history_dashboard_body.html").read_text(
        encoding="utf-8"
    )
    for selector in (
        "foms-shell-body",
        "history_mobile_filters.html",
        "foms-mobile-queue-list",
        "foms-shell-fab",
    ):
        assert selector in body, selector
    filters = (ROOT / "templates/orders/partials/history_mobile_filters.html").read_text(encoding="utf-8")
    for selector in ("chip-strip", "foms-chip-strip"):
        assert selector in filters, selector


def test_p1_history_dashboard_renders_home_ia(
    client,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Cohort 과거이력 대시보드(필터 적용)가 홈 IA 셸/칩/큐/FAB DOM 훅을 렌더한다."""
    import datetime

    from models import Order

    user = _login_admin(client)
    monkeypatch.setenv("ERP_MOBILE_V2_ENABLED", "true")
    monkeypatch.setenv("FOMS_V3_SHELL_COHORT", str(user.id))

    order = Order(
        received_date=datetime.date.today().isoformat(),
        customer_name="P1 History Customer",
        phone="010-1234-5678",
        address="안양시 동안구 학의로 1",
        product="맞춤 가구",
        status="COMPLETED",
        is_erp_order=True,
        erp_stage_code="COMPLETED",
        structured_data={"parties": {"customer": {"name": "P1 History Customer"}}},
    )
    db_session.add(order)
    db_session.commit()

    resp = client.get("/erp/history/?stage=COMPLETED")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert 'class="erp-mobile-v2-layout"' in html
    for selector in (
        "foms-shell-body",
        "erp-history-mobile-filters",
        "chip-strip",
        "foms-chip-strip",
        "foms-mobile-queue-list",
        "foms-shell-fab",
    ):
        assert selector in html, selector


def test_p1_workflow_tabs_use_clean_queue_card_v2() -> None:
    """홈 외 워크플로 탭(실측/생산/시공)도 홈과 동일한 깔끔한 queue-card-v2를 쓴다.

    레거시 v1 카드(erp_mobile_queue_card.html — 스와이프 액션 peek)는 쓰지 않는다.
    """
    for rel in (
        "templates/measurement/partials/mobile_list.html",
        "templates/production/partials/mobile_queue.html",
        "templates/construction/partials/mobile_queue.html",
        "templates/shipment/partials/shipment_mobile_queue.html",
    ):
        src = (ROOT / rel).read_text(encoding="utf-8")
        assert "shared/erp_mobile_queue_card_v2.html" in src, rel
        assert "render_queue_card_v2" in src, rel
        assert "shared/erp_mobile_queue_card.html" not in src, rel


def test_p1_mobile_v2_only_surfaces_hidden_on_desktop() -> None:
    """모바일 v2 전용 표면(도면 갤러리·AS 카메라 바·FAB)이 데스크톱에서 숨겨진다."""
    shell = (ROOT / "static/css/foundation/foms-shell.css").read_text(encoding="utf-8")
    assert "foms-drawing-mobile-v2" in shell
    assert "foms-shell-fab" in shell
    assert "foms-as-camera-bar" in shell
    # 워크플로 탭 본문에서 '레거시 모바일' 안내 notice 제거됨
    for rel in (
        "templates/measurement/partials/dashboard_main.html",
        "templates/production/partials/dashboard_body.html",
        "templates/construction/partials/dashboard_body.html",
        "templates/orders/partials/history_dashboard_body.html",
    ):
        body = (ROOT / rel).read_text(encoding="utf-8")
        assert "erp_mobile_v2_tab_notice.html" not in body, rel
