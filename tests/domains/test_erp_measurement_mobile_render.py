from datetime import date
from pathlib import Path

from foms.web.measurement import dashboard as erp_measurement_dashboard
from werkzeug.security import generate_password_hash

from db import db_session
from models import Order, OrderAttachment, OrderScheduleDate, User

ROOT = Path(__file__).resolve().parents[2]


def _login_erp_admin(client):
    user = User(
        username="measurement_mobile_admin",
        password=generate_password_hash("admin"),
        role="ADMIN",
        team="CS",
        name="Measurement Mobile Admin",
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()

    with client.session_transaction() as sess:
        sess["user_id"] = user.id
        sess["username"] = user.username
        sess["role"] = user.role

    return user


def test_measurement_mobile_page_renders_queue_card_attachments(client, monkeypatch):
    monkeypatch.setenv("ERP_MOBILE_V2_ENABLED", "true")
    fake_today = date(2026, 4, 8)
    monkeypatch.setattr(erp_measurement_dashboard, "get_today_kst", lambda: fake_today)
    user = _login_erp_admin(client)
    monkeypatch.setenv("FOMS_V3_SHELL_COHORT", str(user.id))

    today = fake_today.strftime("%Y-%m-%d")
    order = Order(
        received_date=today,
        customer_name="모바일 실측",
        phone="010-2222-3333",
        address="Seoul",
        product="붙박이장",
        status="MEASURE",
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
            ]
        },
    )
    db_session.add(order)
    db_session.flush()
    order_id = order.id

    db_session.add(
        OrderScheduleDate(
            order_id=order_id,
            kind="measurement",
            date=today,
            source="beta_schedule",
        )
    )
    db_session.add(
        OrderAttachment(
            order_id=order_id,
            filename="measurement-1.jpg",
            file_type="image/jpeg",
            storage_key="tests/measurement-1.jpg",
            category="measurement",
            item_index=0,
        )
    )
    db_session.commit()

    response = client.get("/erp/measurement")

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "모바일 실측" in body
    assert "foms-queue-card-v2__attachments" in body
    assert "data-foms-erp-attachment-preview-gallery" in body
    assert "data-foms-erp-attachment-view-url" in body
    assert "erp-attachment-preview-open.js" in body


def test_measurement_mobile_page_uses_normalized_manager_name(client, monkeypatch):
    monkeypatch.setenv("ERP_MOBILE_V2_ENABLED", "true")
    fake_today = date(2026, 4, 8)
    monkeypatch.setattr(erp_measurement_dashboard, "get_today_kst", lambda: fake_today)
    user = _login_erp_admin(client)
    monkeypatch.setenv("FOMS_V3_SHELL_COHORT", str(user.id))
    manager_user = User(
        username="measurement_mobile_manager",
        password=generate_password_hash("manager"),
        role="STAFF",
        team="CS",
        name="Resolved Manager",
        is_active=True,
    )
    db_session.add(manager_user)
    db_session.commit()
    manager_user_id = manager_user.id

    today = fake_today.strftime("%Y-%m-%d")
    order = Order(
        received_date=today,
        customer_name="Mobile Manager Restore",
        phone="010-1234-5678",
        address="Seoul",
        product="Cabinet",
        status="MEASURE",
        manager_name="Alice",
        is_erp_order=True,
        structured_data={
            "parties": {
                "manager": {
                    "name": manager_user.id,
                }
            },
            "items": [
                {
                    "product_name": "Upper Cabinet",
                }
            ],
        },
    )
    db_session.add(order)
    db_session.flush()
    order_id = order.id
    db_session.add(
        OrderScheduleDate(
            order_id=order_id,
            kind="measurement",
            date=today,
            source="beta_schedule",
        )
    )
    db_session.commit()

    response = client.get("/erp/measurement")

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "Mobile Manager Restore" in body
    # 담당은 user id가 아니라 표시명(Resolved Manager)으로 정규화되어 카드에 노출
    assert "Resolved Manager" in body
    assert f"담당 {manager_user_id}" not in body


def test_measurement_focus_order_lands_outside_date_window(client, monkeypatch):
    """검색 카드 딥링크(?q=&focus_order=)는 실측 날짜가 오늘이 아니어도 큐에 착지해야 한다."""
    monkeypatch.setenv("ERP_MOBILE_V2_ENABLED", "true")
    fake_today = date(2026, 6, 24)
    monkeypatch.setattr(erp_measurement_dashboard, "get_today_kst", lambda: fake_today)
    user = _login_erp_admin(client)
    monkeypatch.setenv("FOMS_V3_SHELL_COHORT", str(user.id))

    # 실측 예정일이 '어제'인 주문 — 기본(오늘) 날짜창에는 잡히지 않는다.
    yesterday = "2026-06-23"
    order = Order(
        received_date=yesterday,
        customer_name="남궁명주",
        phone="010-2282-3114",
        address="인천 부평구 수변로 333",
        product="붙박이장",
        status="MEASURE",
        is_erp_order=True,
        structured_data={"items": [{"product_name": "상부장"}]},
    )
    db_session.add(order)
    db_session.flush()
    order_id = order.id
    db_session.add(
        OrderScheduleDate(
            order_id=order_id,
            kind="measurement",
            date=yesterday,
            source="beta_schedule",
        )
    )
    db_session.commit()

    # 컨트롤: focus_order 없이 검색만 하면 오늘 날짜창 밖이라 목록에 없다.
    search_only = client.get("/erp/measurement?q=%EB%82%A8%EA%B6%81")
    assert search_only.status_code == 200
    assert "남궁명주" not in search_only.get_data(as_text=True)

    # 검색 카드 딥링크: focus_order로 단건 강제 착지.
    focused = client.get(f"/erp/measurement?q=%EB%82%A8%EA%B6%81&focus_order={order_id}")
    assert focused.status_code == 200
    body = focused.get_data(as_text=True)
    assert "남궁명주" in body
    assert f'data-measurement-mobile-order-id="{order_id}"' in body


def test_measurement_dashboard_mine_filter_fallback_path(client, monkeypatch):
    """회귀 가드: mine=1(mine_filter_active) + raw-match fallback 경로가
    build_measurement_main_rows에서 build_mine_sql_filter를 정상 호출해야 한다.
    (read-model 추출 시 해당 lazy import 누락 시 NameError→500 발생했던 잠복버그 방지.)"""
    fake_today = date(2026, 6, 24)
    monkeypatch.setattr(erp_measurement_dashboard, "get_today_kst", lambda: fake_today)
    _login_erp_admin(client)

    today_str = "2026-06-24"
    order = Order(
        received_date=today_str,
        customer_name="민필터고객",
        phone="010-0000-1234",
        address="서울 강남구",
        product="붙박이장",
        status="MEASURE",
        is_erp_order=True,
        structured_data={"items": [{"product_name": "상부장"}]},
    )
    db_session.add(order)
    db_session.flush()
    db_session.add(
        OrderScheduleDate(
            order_id=order.id,
            kind="measurement",
            date=today_str,
            source="beta_schedule",
        )
    )
    db_session.commit()

    # mine=1 → mine_filter_active=True → fallback 블록에서 build_mine_sql_filter 호출 경로 실행.
    resp = client.get("/erp/measurement?mine=1")
    assert resp.status_code == 200


def test_measurement_dashboard_excludes_stale_legacy_schedule_date(client, monkeypatch):
    monkeypatch.setenv("ERP_MOBILE_V2_ENABLED", "true")
    fake_today = date(2026, 5, 4)
    monkeypatch.setattr(erp_measurement_dashboard, "get_today_kst", lambda: fake_today)
    user = _login_erp_admin(client)
    monkeypatch.setenv("FOMS_V3_SHELL_COHORT", str(user.id))

    order = Order(
        received_date="2026-05-01",
        customer_name="Stale Legacy Measurement",
        phone="010-9999-0000",
        address="Seoul",
        product="Cabinet",
        status="MEASURE",
        measurement_date="2026-05-04",
        is_erp_order=True,
        erp_measurement_date="2026-05-06",
        structured_data={
            "schedule": {"measurement": {"date": "2026-05-06"}},
            "items": [{"product_name": "Cabinet"}],
        },
    )
    db_session.add(order)
    db_session.flush()
    db_session.add_all(
        [
            OrderScheduleDate(
                order_id=order.id,
                kind="measurement",
                date="2026-05-04",
                source="legacy_column",
            ),
            OrderScheduleDate(
                order_id=order.id,
                kind="measurement",
                date="2026-05-06",
                source="beta_schedule",
            ),
        ]
    )
    db_session.commit()

    stale_response = client.get("/erp/measurement?date=2026-05-04")
    fresh_response = client.get("/erp/measurement?date=2026-05-06")

    assert stale_response.status_code == 200
    assert fresh_response.status_code == 200
    assert "Stale Legacy Measurement" not in stale_response.get_data(as_text=True)
    assert "Stale Legacy Measurement" in fresh_response.get_data(as_text=True)


def test_measurement_dashboard_includes_regional_order(client, monkeypatch):
    """지방주문(is_regional)도 실측 대시보드 큐에 표시되어야 한다."""
    monkeypatch.setenv("ERP_MOBILE_V2_ENABLED", "true")
    fake_today = date(2026, 7, 2)
    monkeypatch.setattr(erp_measurement_dashboard, "get_today_kst", lambda: fake_today)
    _login_erp_admin(client)

    today = fake_today.strftime("%Y-%m-%d")
    order = Order(
        received_date=today,
        customer_name="지방 실측 고객",
        phone="010-1111-2222",
        address="Busan",
        product="붙박이장",
        status="MEASURE",
        manager_name="Bob",
        is_erp_order=True,
        is_regional=True,
        is_self_measurement=False,
        construction_type="하우드 시공",
        structured_data={
            "items": [{"product_name": "붙박이장"}],
            "flags": {"factory2": True},
        },
    )
    db_session.add(order)
    db_session.flush()
    db_session.add(
        OrderScheduleDate(
            order_id=order.id,
            kind="measurement",
            date=today,
            source="beta_schedule",
        )
    )
    db_session.commit()

    resp = client.get(f"/erp/measurement?date={today}")
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert "지방 실측 고객" in body
    customer_idx = body.index("지방 실측 고객")
    customer_cell_start = body.rfind('<td data-label="고객"', 0, customer_idx)
    customer_cell = body[customer_cell_start: body.find("</td>", customer_idx)]
    assert "지방주문" not in customer_cell

    orderer_cell_start = body.find('data-label="발주사"', customer_idx)
    orderer_cell = body[orderer_cell_start: body.find("</td>", orderer_cell_start)]
    assert 'class="d-flex flex-column align-items-start gap-1 mt-1"' in orderer_cell
    assert "라홈시스템" in orderer_cell
    assert 'class="badge bg-success text-white" title="지방주문"' in orderer_cell


def test_measurement_dashboard_panel_segmented_count_badges(client, monkeypatch):
    """날짜별 패널 뱃지는 전체·지방·수도권 건수를 색상별로 표시한다."""
    fake_today = date(2026, 7, 6)
    monkeypatch.setattr(erp_measurement_dashboard, "get_today_kst", lambda: fake_today)
    _login_erp_admin(client)
    target = fake_today.strftime("%Y-%m-%d")

    regional = Order(
        received_date=target,
        customer_name="지방 패널",
        phone="010-3333-4444",
        address="Busan",
        product="장",
        status="MEASURE",
        is_erp_order=True,
        is_regional=True,
        construction_type="하우드 시공",
        structured_data={"schedule": {"measurement": {"date": target}}},
    )
    metro = Order(
        received_date=target,
        customer_name="수도권 패널",
        phone="010-5555-6666",
        address="Seoul",
        product="장",
        status="MEASURE",
        is_erp_order=True,
        is_regional=False,
        structured_data={"schedule": {"measurement": {"date": target}}},
    )
    db_session.add_all([regional, metro])
    db_session.flush()
    db_session.add_all(
        [
            OrderScheduleDate(order_id=regional.id, kind="measurement", date=target, source="beta_schedule"),
            OrderScheduleDate(order_id=metro.id, kind="measurement", date=target, source="beta_schedule"),
        ]
    )
    db_session.commit()

    body = client.get(f"/erp/measurement?date={target}").get_data(as_text=True)
    anchor = f'id="date-{target}"'
    idx = body.find(anchor)
    assert idx != -1
    snippet = body[idx: body.find("</a>", idx)]
    assert 'erp-scheduler-count--total" title="전체">2</span>' in snippet
    assert 'erp-scheduler-count--regional" title="지방">1</span>' in snippet
    assert 'erp-scheduler-count--metro" title="수도권">1</span>' in snippet


def test_measurement_dashboard_scheduler_badge_css_excludes_erp_scheduler_count(client):
    """실측 대시보드 legacy .badge-count blue rule must not paint scheduler segmented badges."""
    body = (ROOT / "templates/measurement/partials/dashboard_main.html").read_text(encoding="utf-8")
    assert ".badge-count:not(.erp-scheduler-count)" in body
    assert "erp-scheduler-count--regional" in body


def test_measurement_shell_fragment_includes_page_local_css(client, monkeypatch):
    """FOUC 가드: 셸 fragment(head 없음)에도 page-local CSS link가 실려야 한다.

    X1 preloadFragmentStylesheets는 fragment HTML의 <link rel=stylesheet>만
    swap 전 head에 선로드한다. 실측 heroes/route-strip가 dashboard.html styles
    블록에만 있으면 하단탭 첫 진입에서 미스타일로 뜬다(AS/출고와 동일 계약).
    ?v= 는 dashboard.html styles 블록과 fragment가 동기여야 캐시 드리프트 없다.
    """
    monkeypatch.setenv("ERP_MOBILE_V2_ENABLED", "true")
    user = _login_erp_admin(client)
    monkeypatch.setenv("FOMS_V3_SHELL_COHORT", str(user.id))

    dash = (ROOT / "templates/measurement/dashboard.html").read_text(encoding="utf-8")
    frag_src = (
        ROOT / "templates/measurement/partials/dashboard_fragment.html"
    ).read_text(encoding="utf-8")
    for token in (
        "foms-v2-domain-heroes.css') }}?v=20260712a",
        "foms-route-strip.css') }}?v=20260805a",
    ):
        assert token in dash
        assert token in frag_src

    full = client.get("/erp/measurement").get_data(as_text=True)
    assert "foms-v2-domain-heroes.css" in full
    assert "foms-route-strip.css" in full
    assert "v=20260712a" in full
    assert "v=20260805a" in full

    frag_resp = client.get(
        "/erp/measurement?view=fragment",
        headers={"X-FOMS-ERP-SHELL": "1"},
    )
    assert frag_resp.status_code == 200
    frag = frag_resp.get_data(as_text=True)
    assert "foms-v2-domain-heroes.css" in frag
    assert "foms-route-strip.css" in frag
    assert "v=20260712a" in frag
    assert "v=20260805a" in frag
    assert "<html" not in frag.lower()
