"""Shipment dashboard mobile/tablet v2 queue surface."""

from __future__ import annotations

import re
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
    shipment_display = (ROOT / "foms/services/shipment_dashboard_display.py").read_text(
        encoding="utf-8"
    )
    assert "drawing_preview_only=True" in shipment_display
    queue = (ROOT / "templates/shipment/partials/shipment_mobile_queue.html").read_text(
        encoding="utf-8"
    )
    card_v2 = (ROOT / "templates/partials/shared/erp_mobile_queue_card_v2.html").read_text(
        encoding="utf-8"
    )
    pc = (ROOT / "templates/shipment/partials/dashboard_main.html").read_text(encoding="utf-8")
    assert "/api/erp/shipment/update/" in queue
    assert "data-shipment-mobile-edit-trigger" in queue
    assert "data-shipment-mobile-detail-field" in queue
    assert "syncShipmentMobileDetail" in queue
    assert "js-shipment-as-rec-cancel" in queue
    # 출고 큐: 스케줄·역할 메타 억제 + 발주사·제품 defer + 담당3 SSOT.
    assert "suppress_drawing_role_meta=true" in queue
    assert "suppress_schedule_meta=true" in queue
    assert "suppress_role_meta=true" in queue
    assert "show_orderer=true" in queue
    assert "defer_product=true" in queue
    assert "defer_attachments=true" in queue
    assert "suppress_drawing_role_meta=false" in card_v2
    assert "suppress_schedule_meta=false" in card_v2
    assert "suppress_role_meta=false" in card_v2
    assert "and not suppress_drawing_role_meta" in card_v2
    assert "and not suppress_schedule_meta" in card_v2
    assert "if not suppress_role_meta" in card_v2
    assert 'data-shipment-mobile-detail-field="sales_manager"' in queue
    assert "<dt>영업</dt>" in queue
    assert "<dt>도면</dt>" in queue
    assert "<dt>시공</dt>" in queue
    assert "PEOPLE_FIELDS" in queue
    assert "foms-queue-card-v2__orderer-logo" in card_v2
    assert 'width="39"' in card_v2
    assert 'width="67"' in card_v2
    assert 'height="18"' in card_v2
    assert ".foms-queue-card-v2__orderer-logo {" in (
        ROOT / "static/css/components/foms-queue-card-v2.css"
    ).read_text(encoding="utf-8")
    assert "max-height: 18px" in (
        ROOT / "static/css/components/foms-queue-card-v2.css"
    ).read_text(encoding="utf-8")
    for field in ("site_extra", "construction_time", "construction_date", "drawing_managers", "construction_workers", "vehicle", "trip"):
        assert field in queue
    assert "시공일" in queue
    for field in ("site_extra", "construction_time", "drawing_managers", "construction_workers", "vehicle", "trip"):
        assert field in pc


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
                "site_extra": [{"text": "엘리베이터 사용"}],
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
    assert 'data-shipment-mobile-detail-field="construction_date"' in body
    assert today in body
    assert "도면1" in body
    assert "시공1" in body
    assert "엘리베이터 사용" in body
    assert 'data-shipment-mobile-detail-field="site_extra"' in body


def test_shipment_mobile_drawing_stage_does_not_duplicate_drawing_assignee(
    client, monkeypatch
) -> None:
    """DRAWING stage여도 출고 큐는 담당3 SSOT만 — 메타 도면 담당·실측일 금지."""
    monkeypatch.setenv("ERP_MOBILE_V2_ENABLED", "true")
    user = _login_admin(client)
    monkeypatch.setenv("FOMS_V3_SHELL_COHORT", str(user.id))

    today = get_today_kst().strftime("%Y-%m-%d")
    order = Order(
        received_date=today,
        customer_name="도면중복방지 고객",
        phone="010-3000-4000",
        address="서울시 출고구 중복로 2",
        product="붙박이장",
        status="DRAWING",
        scheduled_date=today,
        manager_name="영업담당",
        is_erp_order=True,
        structured_data={
            "workflow": {"stage": "DRAWING"},
            "parties": {
                "customer": {"name": "도면중복방지 고객", "phone": "010-3000-4000"},
                "manager": {"name": "영업담당"},
                "orderer": {"name": "라홈"},
            },
            "site": {"address_full": "서울시 출고구 중복로 2"},
            "schedule": {
                "measurement": {"date": today},
                "construction": {"date": today},
            },
            "items": [{"product_name": "붙박이장", "spec_width": "900"}],
            "drawing_assignees": [{"name": "김한비"}],
            "shipment": {
                "drawing_managers": ["김한비"],
                "construction_workers": ["시공갑"],
                "construction_time": "오후 2:00",
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
            source="shipment_mobile_drawing_dup_test",
        )
    )
    db_session.commit()

    response = client.get("/erp/shipment")
    assert response.status_code == 200
    body = response.get_data(as_text=True)

    assert "도면중복방지 고객" in body
    assert 'data-queue-card-field="address"' in body
    assert 'data-queue-card-field="phone"' in body
    assert 'data-queue-card-field="product"' in body
    assert "붙박이장" in body
    assert "lahom-logo.png" in body
    assert 'width="39"' in body
    assert 'height="18"' in body
    assert 'data-shipment-mobile-detail-field="sales_manager"' in body
    assert 'data-shipment-mobile-detail-field="drawing_managers"' in body
    assert 'data-shipment-mobile-detail-field="construction_workers"' in body
    assert "영업담당" in body
    assert "김한비" in body
    assert "시공갑" in body
    assert 'data-queue-card-field="drawing-assignee"' not in body
    assert "도면 담당" not in body
    assert 'data-queue-card-field="manager"' not in body
    # 공용 메타 스케줄(실측) 억제 — 네비 '실측' 링크와 구분하려면 dt만 검사.
    assert "<dt>실측</dt>" not in body
    assert "<dt>실측 담당</dt>" not in body


def test_shipment_mobile_gate_follows_shell_matrix() -> None:
    """셸 매트릭스 통합(2026-07-12): 출고 모바일 UI 게이트는 폭 단독(max-width:
    1365.98px)이 아니라 폰(<992) + 태블릿 세로(≥992 coarse portrait) 열거식이어야
    한다. 구 단독 폭 arm이 되살아나면 iPad 가로(1180)에서 출고만 폰 UI가 떠
    태블릿 모드(PC 표면+레일)가 깨진다(회귀). 태블릿 가로·992–1365 fine/none 창은
    PC 표면을 유지한다.

    foms-shell.css/foms-split-view.css의 매트릭스 열거와 동일한 tablet-portrait
    조건을 공유한다(shell 파일은 별도 계약 테스트가 잠근다)."""
    css = (ROOT / "static/css/components/foms-shipment-mobile.css").read_text(
        encoding="utf-8"
    )
    norm = re.sub(r"\s+", " ", css)

    # 구 폭 단독 게이트 부재 — 폰·태블릿 전부를 폰 UI로 강제하던 회귀 원인.
    assert "@media (max-width: 1365.98px) {" not in norm
    assert "@media (min-width: 992px) and (max-width: 1365.98px) {" not in norm

    # 신규 모바일 UI 표시 arm = 폰 + 태블릿 세로 열거.
    assert (
        "@media (max-width: 991.98px), "
        "((min-width: 992px) and (pointer: coarse) and (orientation: portrait)) {"
        in norm
    )
    # 신규 밴드 정제 arm(720px 중앙 + 4열 디테일) = 태블릿 세로 전용.
    assert (
        "@media ((min-width: 992px) and (pointer: coarse) and (orientation: portrait)) {"
        in norm
    )
