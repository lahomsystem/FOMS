"""실측 대시보드 '동행 전달' 렌더 계약 (스펙 §6.2 / T5).

AS 영업/택배 전달 건이 실측 일정에 배정되면 실측 대시보드가:
  - 고객 셀에 `전달 N` 배지를 (전달이 있는 행에만) 낸다
  - 펼침 상세행에 전달 카드(고객·품목·주소·상태·배정자)를 낸다
  - 좌측 날짜 패널 카드에 그 날짜 전달 건수 합을 낸다
  - 상단 요약 스트립에 `실측 N건`·`동행 전달 N건` 을 낸다
  - 역방향 맵이 캡에 걸리면 그 사실을 공시한다

캐시 슬라이스 키(measurement_panel_assembly·main_rows)에는 전달 맵이 들어가지
않는다 — 배지는 렌더 시점 조인이라는 계약도 여기서 함께 못 박는다.
"""
import copy
import re
from datetime import date
from pathlib import Path

from sqlalchemy.orm.attributes import flag_modified
from werkzeug.security import generate_password_hash

from db import db_session
from foms.services.orders.sales_delivery_link import mark_delivered, write_link
from foms.web.measurement import dashboard as measurement_dashboard
from models import Order, OrderScheduleDate, User

_ROOT = Path(__file__).resolve().parents[2]
_CSS_ASSET = "css/contexts/measurement/measurement-sales-delivery.css"
_JS_ASSET = "js/measurement/measurement-sales-delivery.js"
_ASSET_PIN = "20260909a"


def _login_erp_admin(client, username="measurement_sd_admin"):
    """실측 대시보드를 볼 수 있는 ERP 관리자로 로그인한다."""
    user = User(
        username=username,
        password=generate_password_hash("admin"),
        role="ADMIN",
        team="CS",
        name="Measurement SD Admin",
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    with client.session_transaction() as sess:
        sess["user_id"] = user.id
        sess["username"] = user.username
        sess["role"] = user.role
    return user


def _create_measurement_order(*, customer_name, on_date, product="붙박이장"):
    """지정 날짜에 실측 일정이 잡힌 ERP 실측 주문을 만든다."""
    order = Order(
        received_date=on_date,
        customer_name=customer_name,
        phone="010-1111-2222",
        address="성남시 분당구 정자로 45",
        product=product,
        status="MEASURE",
        manager_name="이정민",
        measurement_date=on_date,
        is_erp_order=True,
        # 실측일은 컬럼·structured_data 양쪽에 둔다. before_flush 훅(sync_order_dates)이
        # 주문의 날짜 원본으로 schedule_dates 를 통째로 재생성하므로, 손으로 꽂은
        # OrderScheduleDate 는 렌더 중 첫 flush 에 사라진다.
        structured_data={
            "parties": {"manager": "이정민"},
            "schedule": {"measurement": {"date": on_date}},
        },
    )
    db_session.add(order)
    db_session.commit()
    assert (
        db_session.query(OrderScheduleDate)
        .filter_by(order_id=order.id, kind="measurement", date=on_date)
        .count()
        == 1
    )
    return order


def _create_delivery_order(*, customer_name, as_content="상판 마감캡 6EA", address="광주시 오포읍 능평로 87"):
    """`sales_delivery=true` 인 미완료 AS 주문(전달 건 후보)을 만든다."""
    today = date.today().strftime("%Y-%m-%d")
    order = Order(
        received_date=today,
        customer_name=customer_name,
        phone="010-3333-4444",
        address=address,
        product="붙박이장",
        status="AS_RECEIVED",
        manager_name="김보라",
        as_received_date=today,
        is_erp_order=True,
        structured_data={"shipment": {"sales_delivery": True, "as_content": as_content}},
    )
    db_session.add(order)
    db_session.commit()
    return order


def _assign(delivery_order, ref_order_id, *, ref_date, delivered=False, assigned_by="김보라"):
    """전달 건을 실측 주문에 배정한다(프로젝트 규약: deepcopy + flag_modified)."""
    sd = copy.deepcopy(delivery_order.structured_data or {})
    write_link(
        sd,
        ref_order_id=ref_order_id,
        ref_date=ref_date,
        ref_manager="이정민",
        actor_user_id=1,
        actor_name=assigned_by,
    )
    if delivered:
        mark_delivered(sd, by=assigned_by)
    delivery_order.structured_data = sd
    flag_modified(delivery_order, "structured_data")
    db_session.commit()


def _fetch_dashboard(client, on_date):
    """실측 대시보드 HTML 을 그 날짜로 연다."""
    response = client.get(f"/erp/measurement?date={on_date}")
    assert response.status_code == 200
    return response.get_data(as_text=True)


def test_delivery_badge_renders_only_on_rows_with_delivery(client):
    """전달 배지는 전달 건이 붙은 행에만 뜬다(음성 대조군: 전달 없는 실측 행)."""
    today = date.today().strftime("%Y-%m-%d")
    _login_erp_admin(client)
    with_delivery = _create_measurement_order(customer_name="오세영", on_date=today)
    _create_measurement_order(customer_name="신동혁", on_date=today)  # 대조군(전달 없음)
    _assign(_create_delivery_order(customer_name="한지훈"), with_delivery.id, ref_date=today)

    body = _fetch_dashboard(client, today)

    assert "오세영" in body and "신동혁" in body
    # 배지는 딱 1개(전달 있는 행) — 대조군 행에는 없다.
    assert body.count('data-meas-sd-count="1"') == 1
    assert "전달 1" in body


def test_detail_row_renders_delivery_card_with_deliver_hook(client):
    """상세행 전달 카드: 고객·품목·주소·배정자 + [전달 완료] 버튼 훅."""
    today = date.today().strftime("%Y-%m-%d")
    _login_erp_admin(client)
    ref = _create_measurement_order(customer_name="오세영", on_date=today)
    delivery = _create_delivery_order(
        customer_name="한지훈", as_content="<p>상판 마감캡 6EA</p>", address="광주시 오포읍 능평로 87 3층"
    )
    _assign(delivery, ref.id, ref_date=today, assigned_by="김보라")

    body = _fetch_dashboard(client, today)

    assert 'class="meas-sd-cards"' in body or "meas-sd-cards" in body
    assert f'data-meas-sd-order-id="{delivery.id}"' in body
    assert f"AS #{delivery.id} · 한지훈" in body
    assert "상판 마감캡 6EA" in body
    assert "광주시 오포읍 능평로 87 3층" in body
    assert "김보라 배정" in body
    assert "meas-sd-state--assigned" in body
    assert f'data-meas-sd-deliver="{delivery.id}"' in body
    assert "전달 완료" in body


def test_delivered_item_shows_done_marker_without_button(client):
    """이미 전달된 건은 버튼 대신 '전달 완료됨' 표시만 남는다."""
    today = date.today().strftime("%Y-%m-%d")
    _login_erp_admin(client)
    ref = _create_measurement_order(customer_name="오세영", on_date=today)
    delivery = _create_delivery_order(customer_name="윤아름")
    _assign(delivery, ref.id, ref_date=today, delivered=True)

    body = _fetch_dashboard(client, today)

    assert "meas-sd-state--delivered" in body
    assert "전달 완료됨" in body
    assert f'data-meas-sd-deliver="{delivery.id}"' not in body


def test_date_panel_card_shows_delivery_count_sum(client):
    """날짜 패널 배지 = 그 날짜에 실측이 잡힌 주문들의 전달 건수 **합**."""
    today = date.today().strftime("%Y-%m-%d")
    _login_erp_admin(client)
    ref = _create_measurement_order(customer_name="오세영", on_date=today)
    _assign(_create_delivery_order(customer_name="전달 A"), ref.id, ref_date=today)
    _assign(_create_delivery_order(customer_name="전달 B"), ref.id, ref_date=today)

    body = _fetch_dashboard(client, today)

    assert 'data-meas-sd-panel-count="2"' in body


def test_summary_strip_reports_measurement_and_delivery_counts(client):
    """요약 스트립: 선택 날짜 + `실측 N건` + `동행 전달 N건`."""
    today = date.today().strftime("%Y-%m-%d")
    _login_erp_admin(client)
    ref = _create_measurement_order(customer_name="오세영", on_date=today)
    _create_measurement_order(customer_name="신동혁", on_date=today)
    _assign(_create_delivery_order(customer_name="한지훈"), ref.id, ref_date=today)

    body = _fetch_dashboard(client, today)

    assert "data-meas-sd-summary" in body
    assert 'data-meas-sd-rows="2"' in body
    assert 'data-meas-sd-total="1"' in body
    assert "실측 2건" in body
    assert "동행 전달 1건" in body
    assert today in body


def test_truncated_map_is_disclosed_on_screen(client, monkeypatch):
    """역방향 맵이 캡에 걸리면 조용히 줄이지 않고 화면에 남긴다."""
    today = date.today().strftime("%Y-%m-%d")
    _login_erp_admin(client)
    _create_measurement_order(customer_name="오세영", on_date=today)
    monkeypatch.setattr(
        measurement_dashboard,
        "build_sales_delivery_by_ref",
        lambda db, cap=300: {"by_ref": {}, "total": 0, "truncated": True},
    )

    body = _fetch_dashboard(client, today)

    assert "data-meas-sd-truncated" in body
    assert "data-foms-no-autodismiss" in body
    assert str(measurement_dashboard.MEASUREMENT_SALES_DELIVERY_CAP) in body


def test_delivery_map_is_not_part_of_cache_slice_keys():
    """배지는 렌더 시점 조인이다 — 캐시 fingerprint 에 전달 맵이 섞이면 패널 캐시가 통째로 갈린다."""
    import inspect

    src = inspect.getsource(measurement_dashboard.erp_measurement_dashboard)
    panel_fp = src[src.index("_panel_fp = {"): src.index("_panel_key")]
    main_fp = src[src.index("_main_fp = {"): src.index("_main_key")]
    for fingerprint in (panel_fp, main_fp):
        assert "sales_delivery" not in fingerprint
    # 맵 호출은 라우트당 1회.
    assert src.count("build_sales_delivery_by_ref(") == 1


def test_deliver_button_posts_to_sales_delivery_endpoint():
    """[전달 완료] JS 훅: POST /api/orders/<id>/sales-delivery {"action":"deliver"}."""
    js = (_ROOT / "static" / _JS_ASSET).read_text(encoding="utf-8")

    assert "'/api/orders/' + encodeURIComponent(orderId) + '/sales-delivery'" in js
    assert "action: 'deliver'" in js
    assert "method: 'POST'" in js
    assert "try {" in js and "catch" in js
    assert "data.success !== true" in js
    # CSRF 는 전역 인터셉터 소관 — 수동 부착 금지.
    assert "X-CSRF-Token" not in js
    # 실패를 .alert 로만 알리지 않는다(자동 닫힘) — 버튼 옆 인라인 텍스트 병행.
    assert "data-meas-sd-msg" in js
    assert "전달 완료 실패" in js


def test_new_assets_have_no_inline_styles_and_define_classes():
    """목업의 색·배치는 전부 CSS 클래스로 옮긴다(인라인 스타일 금지)."""
    css = (_ROOT / "static" / _CSS_ASSET).read_text(encoding="utf-8")
    for klass in (
        ".meas-sd-badge",
        ".meas-sd-summary",
        ".meas-sd-card",
        ".meas-sd-state--delivered",
        ".meas-sd-done",
    ):
        assert klass in css, f"{klass} 정의 없음"

    template = (
        _ROOT / "templates" / "measurement" / "partials" / "dashboard_main.html"
    ).read_text(encoding="utf-8")
    for block in re.findall(r'<[^>]*meas-sd[^>]*>', template):
        assert "style=" not in block, f"인라인 스타일 발견: {block}"


def test_touched_asset_cache_pins_are_in_sync():
    """새 JS/CSS 의 `?v=` 핀이 저장소 전역에서 하나로 일치한다(서비스워커 stale 가드)."""
    # 핀이 박힐 수 있는 트리만 훑는다(문서 트리를 스캔하지 않으므로 CI-DOCSCOPE-01 무관).
    sources = [
        p
        for sub in ("templates", "static", "foms", "apps", "services", "tests")
        for ext in ("*.html", "*.js", "*.py")
        for p in (_ROOT / sub).glob(f"**/{ext}")
        if "node_modules" not in p.parts
    ]
    for asset in (_JS_ASSET, _CSS_ASSET):
        pattern = re.compile(re.escape(asset) + r"['\"\s\}\)]*\?v=([A-Za-z0-9._-]+)")
        pins = {
            pin
            for path in sources
            for pin in pattern.findall(path.read_text(encoding="utf-8", errors="ignore"))
        }
        assert pins == {_ASSET_PIN}, f"{asset}: 핀 불일치/부재 {sorted(pins)}"
