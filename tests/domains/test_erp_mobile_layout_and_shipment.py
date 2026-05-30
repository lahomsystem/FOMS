import re
from datetime import date, timedelta
from pathlib import Path

from werkzeug.security import generate_password_hash

from db import db_session
from models import ChannelDeliveryLog, Order, OrderScheduleDate, User


def _login_erp_admin(client):
    user = User(
        username="erp_mobile_layout_admin",
        password=generate_password_hash("admin"),
        role="ADMIN",
        team="CS",
        name="ERP Mobile Layout Admin",
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()

    with client.session_transaction() as sess:
        sess["user_id"] = user.id
        sess["username"] = user.username
        sess["role"] = user.role

    return user


def test_erp_pages_mark_body_for_mobile_layout_shell(client, monkeypatch):
    monkeypatch.setenv("ERP_MOBILE_V2_ENABLED", "true")
    user = _login_erp_admin(client)
    monkeypatch.setenv("FOMS_V3_SHELL_COHORT", str(user.id))

    response = client.get("/erp/dashboard")

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert 'class="erp-mobile-v2-layout"' in body
    assert 'layout-global-nav--erp-v2-suppressed' in body
    assert 'data-erp-v2-global-nav="suppressed"' in body
    assert "erp-pro.css" in body


def test_erp_pages_without_cohort_keeps_unsuppressed_global_nav(client, monkeypatch):
    monkeypatch.setenv("ERP_MOBILE_V2_ENABLED", "true")
    _login_erp_admin(client)

    response = client.get("/erp/dashboard")

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert 'class="erp-mobile-v2-layout"' not in body
    assert 'layout-global-nav--erp-v2-suppressed' not in body
    assert 'class="layout-global-nav navbar' in body


def test_shipment_mobile_markup_includes_colgroup_reset_override(client, monkeypatch):
    monkeypatch.setenv("ERP_MOBILE_V2_ENABLED", "true")
    _login_erp_admin(client)

    today = date.today().strftime("%Y-%m-%d")
    order = Order(
        received_date=today,
        customer_name="모바일 출고",
        phone="010-5555-6666",
        address="Seoul",
        product="붙박이장",
        status="IN_CONSTRUCTION",
        manager_name="Alice",
        is_erp_order=True,
        structured_data={
            "items": [
                {
                    "product_name": "상부장",
                    "spec_width": "1200",
                    "spec_depth": "600",
                    "spec_height": "2300",
                    "quantity": 1,
                }
            ],
            "shipment": {
                "construction_time": "10:00",
                "drawing_managers": ["도면1", ""],
                "construction_workers": ["시공1", ""],
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
            source="beta_schedule",
        )
    )
    db_session.commit()

    response = client.get("/erp/shipment")

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert 'id="shipment-dashboard-table"' in body
    assert "shipment-dashboard-columns.css" in body
    assert "erp-shipment-mobile-summary__eyebrow" in body
    assert "Shipment Queue" in body
    assert "input-group input-group-sm flex-nowrap" in body
    assert body.count('value=""\n                            placeholder="도면담당자"') == 0
    assert body.count('value=""\n                            placeholder="시공자"') == 0


def test_shipment_text_edit_contract_adds_new_blank_rows_and_has_readable_widths() -> None:
    root = Path(__file__).resolve().parents[2]
    template = (root / "templates/shipment/partials/dashboard_main.html").read_text(encoding="utf-8")
    css = (root / "static/css/contexts/shipment/dashboard-table-extras.css").read_text(encoding="utf-8")
    columns = (root / "static/js/shipment/dashboard-columns.js").read_text(encoding="utf-8")

    assert "input-group input-group-sm flex-nowrap" in template
    assert "var reusable = Array.from(list.querySelectorAll('.shipment-text-row')).find" not in template
    assert "list.insertBefore(row, actionsRow || null);" in template
    assert "throw new Error((data && data.message) || ('HTTP ' + r.status));" in template
    assert "min-width: 8rem !important;" in css
    assert 'construction_time:    { defaultWidth: 150, minWidth: 140' in columns
    assert 'drawing_managers:     { defaultWidth: 170, minWidth: 150' in columns
    assert 'construction_workers: { defaultWidth: 170, minWidth: 150' in columns


def test_shipment_dashboard_template_includes_as_recommendation_prewarm_endpoint() -> None:
    root = Path(__file__).resolve().parents[2]
    template = (root / "templates/shipment/partials/dashboard_main.html").read_text(encoding="utf-8")
    assert "/api/erp/shipment/as-recommendations/prewarm" in template
    assert "scheduleShipmentAsRecPrewarm" in template or "shipment-asrec-prewarm:" in template


def test_shipment_dashboard_template_includes_as_recommend_entrypoint() -> None:
    """AS 일정 추천 버튼은 편집 가능한 출고 대시보드에만 노출되도록 템플릿에 포함된다."""
    root = Path(__file__).resolve().parents[2]
    template = (root / "templates/shipment/partials/dashboard_main.html").read_text(encoding="utf-8")
    assert 'id="shipment-as-recommend-btn"' in template
    assert "shipmentAsRecommendModal" in template
    assert "{% if can_edit_shipment %}" in template


def test_shipment_dashboard_as_rec_modal_has_rich_preview_hydration() -> None:
    root = Path(__file__).resolve().parents[2]
    template = (root / "templates/shipment/partials/dashboard_main.html").read_text(encoding="utf-8")
    assert "hydrateAsRecRichPreviews" in template
    assert "data-asrec-rich" in template
    assert "asrec-rich-preview" in template


def test_shipment_dashboard_hides_as_recommend_for_construction_team(client):
    """시공팀은 can_edit_shipment가 꺼져 AS 일정 추천 버튼이 렌더되지 않는다."""
    user = User(
        username="erp_shipment_construction_staff",
        password=generate_password_hash("admin"),
        role="STAFF",
        team="CONSTRUCTION",
        name="Construction Ship",
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()

    with client.session_transaction() as sess:
        sess["user_id"] = user.id
        sess["username"] = user.username
        sess["role"] = user.role

    today = date.today().strftime("%Y-%m-%d")
    order = Order(
        received_date=today,
        customer_name="시공팀 출고",
        phone="010-0000-0000",
        address="Seoul",
        product="붙박이장",
        status="IN_CONSTRUCTION",
        manager_name="Bob",
        is_erp_order=True,
        structured_data={
            "schedule": {"construction": {"date": today}},
            "shipment": {"construction_workers": ["시공1"]},
        },
    )
    db_session.add(order)
    db_session.flush()
    db_session.add(
        OrderScheduleDate(
            order_id=order.id,
            kind="construction",
            date=today,
            source="beta_schedule",
        )
    )
    db_session.commit()

    response = client.get("/erp/shipment")
    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert 'id="shipment-as-recommend-btn"' not in body


def test_shipment_dashboard_shows_as_recommend_for_cs_staff(client):
    """CS/STAFF는 출고 편집 가능 시 AS 일정 추천 버튼이 보인다."""
    _login_erp_admin(client)
    today = date.today().strftime("%Y-%m-%d")
    order = Order(
        received_date=today,
        customer_name="CS 출고",
        phone="010-1111-2222",
        address="Seoul",
        product="붙박이장",
        status="IN_CONSTRUCTION",
        manager_name="Alice",
        is_erp_order=True,
        structured_data={
            "schedule": {"construction": {"date": today}},
            "shipment": {"construction_workers": ["시공1"]},
        },
    )
    db_session.add(order)
    db_session.flush()
    db_session.add(
        OrderScheduleDate(
            order_id=order.id,
            kind="construction",
            date=today,
            source="beta_schedule",
        )
    )
    db_session.commit()

    response = client.get("/erp/shipment")
    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert 'id="shipment-as-recommend-btn"' in body


def test_shipment_dashboard_allows_past_date_search(client):
    _login_erp_admin(client)

    today = date.today()
    yesterday = (today - timedelta(days=1)).strftime("%Y-%m-%d")
    order = Order(
        received_date=today.strftime("%Y-%m-%d"),
        customer_name="과거 출고 검색",
        phone="010-7777-8888",
        address="Busan",
        product="수납장",
        status="IN_CONSTRUCTION",
        manager_name="Bob",
        is_erp_order=True,
        scheduled_date=yesterday,
        structured_data={
            "items": [
                {
                    "product_name": "하부장",
                    "spec_width": "900",
                    "spec_depth": "600",
                    "spec_height": "2300",
                    "quantity": 1,
                }
            ],
            "shipment": {},
        },
    )
    db_session.add(order)
    db_session.flush()
    db_session.add(
        OrderScheduleDate(
            order_id=order.id,
            kind="construction",
            date=yesterday,
            source="beta_schedule",
        )
    )
    db_session.commit()

    response = client.get(f"/erp/shipment?date={yesterday}")

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert 'id="shipment-dashboard-table"' in body
    assert "과거 출고 검색" in body


def test_shipment_update_noop_does_not_create_channel_delivery(client):
    _login_erp_admin(client)

    order = Order(
        received_date=date.today().strftime("%Y-%m-%d"),
        customer_name="출고 noop",
        phone="010-1111-2222",
        address="Seoul",
        product="붙박이장",
        status="IN_CONSTRUCTION",
        is_erp_order=True,
        structured_data={"shipment": {"construction_time": "10:00"}},
    )
    db_session.add(order)
    db_session.commit()
    order_id = order.id

    response = client.post(
        f"/api/erp/shipment/update/{order_id}",
        json={"construction_time": "10:00"},
        headers={"X-Requested-With": "XMLHttpRequest"},
    )

    assert response.status_code == 200
    assert response.get_json()["success"] is True
    assert (
        db_session.query(ChannelDeliveryLog)
        .filter(ChannelDeliveryLog.order_id == order_id)
        .count()
        == 0
    )


def test_shipment_construction_panel_count_excludes_as_orders(client, monkeypatch):
    """날짜별 시공 패널 badge-count는 AS 건을 제외한 순수 시공 건수만 집계한다."""
    from foms.web.shipment import dashboard as shipment_dashboard

    fake_today = date(2026, 5, 30)
    monkeypatch.setattr(shipment_dashboard, "get_today_kst", lambda: fake_today)
    _login_erp_admin(client)
    today = fake_today.strftime("%Y-%m-%d")

    construction_order = Order(
        received_date=today,
        customer_name="순수 시공",
        phone="010-2222-3333",
        address="Seoul",
        product="붙박이장",
        status="IN_CONSTRUCTION",
        manager_name="Alice",
        is_erp_order=True,
        structured_data={"schedule": {"construction": {"date": today}}},
    )
    as_order = Order(
        received_date=today,
        customer_name="AS 방문",
        phone="010-4444-5555",
        address="Busan",
        product="붙박이장",
        status="AS_RECEIVED",
        manager_name="Bob",
        is_erp_order=True,
        structured_data={
            "schedule": {
                "as_visit": {"date": today},
                "construction": {"date": today},
            }
        },
    )
    db_session.add(construction_order)
    db_session.add(as_order)
    db_session.flush()
    db_session.add_all(
        [
            OrderScheduleDate(
                order_id=construction_order.id,
                kind="construction",
                date=today,
                source="beta_schedule",
            ),
            OrderScheduleDate(
                order_id=as_order.id,
                kind="as_visit",
                date=today,
                source="beta_schedule",
            ),
            OrderScheduleDate(
                order_id=as_order.id,
                kind="construction",
                date=today,
                source="beta_schedule",
            ),
        ]
    )
    db_session.commit()

    response = client.get(f"/erp/shipment?date={today}")
    assert response.status_code == 200
    body = response.get_data(as_text=True)

    anchor = f'id="date-{today}"'
    anchor_idx = body.find(anchor)
    assert anchor_idx != -1, f"construction panel row for {today} missing"
    # measurement-panel-item <a> is multiline; [^>]* regex cannot span newlines.
    close_idx = body.find("</a>", anchor_idx)
    assert close_idx != -1, f"construction panel row for {today} not closed"
    snippet = body[anchor_idx: close_idx + len("</a>")]
    assert 'class="badge badge-count ms-auto">1</span>' in snippet
    assert 'class="badge badge-count ms-auto">2</span>' not in snippet
