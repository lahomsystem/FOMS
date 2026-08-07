"""Regional dashboard bucket rules — 섹션=상태 개편(2026-08-07) 계약.

섹션 구성: 상차 예정 알림 / 진행 중인 주문 / AS 접수 / 설치 예정 / 완료된 주문.
상차완료·보류 섹션은 폐지됐다(상차일 경과분은 설치 예정으로 흡수, ON_HOLD 는 진행 중).
행에는 status 드롭다운이 없고 읽기 전용 뱃지만 있다. 표기 SSOT 는 섹션 분류이며,
저장된 status 기록은 읽기 경로가 아니라 상차일 변경 시점에 보드 JS 가 canonical
경로로 수행한다(read 경로 직접 쓰기는 test_state_guard 가 차단).
"""

import re
from datetime import timedelta
from pathlib import Path

from werkzeug.security import generate_password_hash

from db import db_session
from foms.services.erp_display import get_today_kst
from models import Order, User


ROOT = Path(__file__).resolve().parents[2]


def _login_as_admin(client, username: str) -> User:
    """Create an admin user and attach it to the test client session."""
    user = User(
        username=username,
        password=generate_password_hash("admin"),
        role="ADMIN",
        team="CS",
        name="Regional Dashboard Admin",
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()

    with client.session_transaction() as sess:
        sess["user_id"] = user.id
        sess["username"] = user.username
        sess["role"] = user.role

    return user


def _create_regional_order(**overrides) -> Order:
    """Create a minimal regional order for dashboard bucket tests."""
    payload = {
        "received_date": "2026-06-01",
        "customer_name": "Regional Bucket Tester",
        "phone": "010-2222-3333",
        "address": "Busan",
        "product": "Kitchen",
        "status": "MEASURE",
        "is_regional": True,
        "measurement_completed": True,
        "structured_data": {},
    }
    payload.update(overrides)
    order = Order(**payload)
    db_session.add(order)
    db_session.commit()
    return order


def _order_ids_in_section(html: str, section_title: str) -> set[str]:
    """Return order ids rendered under a regional dashboard section header."""
    return set(_order_row_ids_in_section(html, section_title))


def _section_chunk(html: str, section_title: str) -> str:
    """Return HTML chunk for a regional dashboard section header.

    섹션 경계는 점프바 앵커(``class="row ... regional-section"``)가 SSOT다.
    (구 구현은 ``<div class="row mb-4">`` 리터럴에 묶여 클래스가 늘면 경계를 잃었다.)
    """
    marker = f">{section_title}"
    start = html.find(marker)
    assert start != -1, f"missing section: {section_title}"
    rest_at = start + len(marker)
    next_card = re.search(r'<div class="row[^"]*\bregional-section\b"', html[rest_at:])
    return html[start:rest_at + next_card.start()] if next_card else html[start:]


def _order_row_ids_in_section(html: str, section_title: str) -> list[str]:
    """Return rendered order row ids under a regional dashboard section header."""
    chunk = _section_chunk(html, section_title)
    return re.findall(r'<tr[^>]+data-order-id="(\d+)"', chunk)


def _order_ids_in_card_class(html: str, card_class: str) -> set[str]:
    """Return order ids inside a rendered dashboard card by CSS class."""
    match = re.search(rf'<div class="card shadow {re.escape(card_class)}".*?</div>\s*</div>\s*</div>', html, re.S)
    if not match:
        return set()
    return set(re.findall(r'data-order-id="(\d+)"', match.group(0)))


def test_shipping_completed_and_hold_sections_are_retired(client) -> None:
    """상차완료·보류 섹션은 폐지 — 렌더 결과에 두 헤더가 없어야 한다."""
    _login_as_admin(client, "regional-retired-sections-admin")
    past_shipping_date = (get_today_kst() - timedelta(days=3)).strftime("%Y-%m-%d")
    _create_regional_order(status="PRODUCTION", shipping_scheduled_date=past_shipping_date)
    _create_regional_order(status="ON_HOLD", shipping_scheduled_date="")

    response = client.get("/regional_dashboard")
    assert response.status_code == 200
    body = response.get_data(as_text=True)

    assert "상차완료 (" not in body
    assert "보류 상태 주문 (" not in body


def test_past_shipping_date_absorbed_into_scheduled_and_status_synced(client) -> None:
    """상차일 경과분은 설치 예정 섹션으로 흡수된다(읽기 경로는 status 무변경)."""
    _login_as_admin(client, "regional-bucket-scheduled-admin")
    past_shipping_date = (get_today_kst() - timedelta(days=3)).strftime("%Y-%m-%d")

    order = _create_regional_order(
        status="PRODUCTION",
        shipping_scheduled_date=past_shipping_date,
    )
    order_id = order.id

    response = client.get("/regional_dashboard", query_string={"search_query": str(order_id)})
    assert response.status_code == 200
    body = response.get_data(as_text=True)

    assert _order_ids_in_section(body, "설치 예정 (1건)") == {str(order_id)}
    # 표기 SSOT 는 섹션 분류다 — 저장된 status 가 뒤처져 있어도 뱃지는 설치예정.
    chunk = _section_chunk(body, "설치 예정 (1건)")
    assert "foms-board-status-badge--scheduled" in chunk
    # 읽기 경로는 상태를 쓰지 않는다(canonical 전이 엔진 우회 금지 — test_state_guard).
    db_session.expire_all()
    assert db_session.get(Order, order_id).status == "PRODUCTION"


def test_hold_order_renders_in_progress_section(client) -> None:
    """보류 섹션 폐지 후 ON_HOLD 주문은 진행 중 섹션에 남는다(상태값은 보존)."""
    _login_as_admin(client, "regional-hold-into-progress-admin")

    order = _create_regional_order(status="ON_HOLD", shipping_scheduled_date="")
    order_id = order.id

    response = client.get("/regional_dashboard", query_string={"search_query": str(order_id)})
    assert response.status_code == 200
    body = response.get_data(as_text=True)

    assert str(order_id) in _order_ids_in_section(body, "진행 중인 주문 (1건)")
    db_session.expire_all()
    assert db_session.get(Order, order_id).status == "ON_HOLD"


def test_future_shipping_alert_renders_shipped_badge(client) -> None:
    """상차 예정 알림 행은 상차예정 뱃지를 단다(상태 기록은 상차일 변경 시 JS 담당)."""
    _login_as_admin(client, "regional-alert-status-sync-admin")
    future_shipping_date = (get_today_kst() + timedelta(days=3)).strftime("%Y-%m-%d")

    order = _create_regional_order(
        status="PRODUCTION",
        shipping_scheduled_date=future_shipping_date,
        measurement_completed=True,
    )
    order_id = order.id

    response = client.get("/regional_dashboard", query_string={"search_query": str(order_id)})
    assert response.status_code == 200
    body = response.get_data(as_text=True)

    assert _order_ids_in_card_class(body, "shipping-alert-card") == {str(order_id)}
    assert "foms-board-status-badge--shipped" in body
    db_session.expire_all()
    assert db_session.get(Order, order_id).status == "PRODUCTION"


def test_as_received_order_has_own_section_and_keeps_status(client) -> None:
    """AS접수는 전용 섹션 + AS완료 버튼, 상태는 AS_RECEIVED 로 보존(동기화 제외)."""
    _login_as_admin(client, "regional-as-section-admin")
    future_shipping_date = (get_today_kst() + timedelta(days=2)).strftime("%Y-%m-%d")

    order = _create_regional_order(
        status="AS_RECEIVED",
        shipping_scheduled_date=future_shipping_date,
        as_received_date=get_today_kst().strftime("%Y-%m-%d"),
        measurement_completed=False,
    )
    order_id = order.id

    response = client.get("/regional_dashboard", query_string={"search_query": str(order_id)})
    assert response.status_code == 200
    body = response.get_data(as_text=True)

    assert _order_ids_in_section(body, "AS 접수 (1건)") == {str(order_id)}
    # 사용자 결정: 재상차 일정이 잡히면 상차 예정 알림에도 병행 표시.
    assert str(order_id) in _order_ids_in_card_class(body, "shipping-alert-card")

    chunk = _section_chunk(body, "AS 접수 (1건)")
    assert 'data-field="as_completed_date"' in chunk, "AS완료 버튼이 canonical 필드를 쓰지 않음"
    assert "AS완료" in chunk

    db_session.expire_all()
    assert db_session.get(Order, order_id).status == "AS_RECEIVED"


def test_board_rows_have_no_status_dropdown(client) -> None:
    """섹션=상태 개편: 행에서 임의 상태 전이(드롭다운)를 제공하지 않는다."""
    _login_as_admin(client, "regional-no-dropdown-admin")
    _create_regional_order(status="SCHEDULED")
    _create_regional_order(status="AS_RECEIVED", as_received_date="2026-08-01")

    response = client.get("/regional_dashboard")
    assert response.status_code == 200
    body = response.get_data(as_text=True)

    # 완료 버튼은 data-field="status" 를 정당하게 쓰므로 <select> 한정으로 판정한다.
    selects = re.findall(r"<select\b[^>]*>", body)
    offenders = [s for s in selects if 'data-field="status"' in s]
    assert offenders == [], f"status 드롭다운 잔존: {offenders}"
    assert "foms-board-status-badge" in body, "상태 뱃지 미렌더"


def test_scheduled_regional_order_excluded_from_shipping_alerts(client) -> None:
    """SCHEDULED orders must not appear in 상차 예정 알림."""
    _login_as_admin(client, "regional-bucket-alert-admin")
    future_shipping_date = (get_today_kst() + timedelta(days=2)).strftime("%Y-%m-%d")

    order = _create_regional_order(
        status="SCHEDULED",
        shipping_scheduled_date=future_shipping_date,
    )

    response = client.get("/regional_dashboard", query_string={"search_query": str(order.id)})
    assert response.status_code == 200
    body = response.get_data(as_text=True)

    assert _order_ids_in_section(body, "설치 예정 (1건)") == {str(order.id)}
    assert _order_ids_in_card_class(body, "shipping-alert-card") == set()


def test_as_received_rework_shipping_joins_alerts_sorted_and_badged(client) -> None:
    """AS_RECEIVED rework orders with a new shipping date join the regular alert sort."""
    _login_as_admin(client, "regional-bucket-as-rework-admin")
    today = get_today_kst()
    as_shipping_date = (today + timedelta(days=2)).strftime("%Y-%m-%d")
    normal_shipping_date = (today + timedelta(days=5)).strftime("%Y-%m-%d")

    normal_order = _create_regional_order(
        customer_name="AS Shipping Sort Normal",
        status="PRODUCTION",
        shipping_scheduled_date=normal_shipping_date,
        measurement_completed=True,
    )
    as_order = _create_regional_order(
        customer_name="AS Shipping Sort Rework",
        status="AS_RECEIVED",
        shipping_scheduled_date=as_shipping_date,
        measurement_completed=False,
        as_received_date=today.strftime("%Y-%m-%d"),
    )

    response = client.get(
        "/regional_dashboard",
        query_string={"search_query": "AS Shipping Sort"},
    )
    assert response.status_code == 200
    body = response.get_data(as_text=True)

    alert_ids = _order_row_ids_in_section(body, "상차 예정 알림 (2건)")
    assert alert_ids == [str(as_order.id), str(normal_order.id)]

    as_row = re.search(rf'<tr[^>]+data-order-id="{as_order.id}".*?</tr>', body, re.S)
    assert as_row is not None
    as_row_html = as_row.group(0)
    assert 'data-as-shipping-schedule="true"' in as_row_html
    assert "regional-as-schedule-badge" in as_row_html
    assert "AS 재상차 일정" in as_row_html


def test_shipping_alerts_sort_by_install_date_within_same_ship_and_region(client) -> None:
    """같은 상차일·같은 지역에서 설치일 오름차순, 빈 설치일은 그룹 맨 뒤."""
    _login_as_admin(client, "regional-bucket-install-sort-admin")
    today = get_today_kst()
    ship_date = (today + timedelta(days=2)).strftime("%Y-%m-%d")
    install_late = (today + timedelta(days=10)).strftime("%Y-%m-%d")
    install_early = (today + timedelta(days=3)).strftime("%Y-%m-%d")

    # 동일 상차일·동일 지역(부산) — 설치일만 다르게. 빈 설치일 1건 포함.
    late_order = _create_regional_order(
        customer_name="Regional Install Sort Late",
        address="부산광역시 해운대구",
        status="PRODUCTION",
        shipping_scheduled_date=ship_date,
        scheduled_date=install_late,
    )
    early_order = _create_regional_order(
        customer_name="Regional Install Sort Early",
        address="부산광역시 해운대구",
        status="PRODUCTION",
        shipping_scheduled_date=ship_date,
        scheduled_date=install_early,
    )
    empty_order = _create_regional_order(
        customer_name="Regional Install Sort Empty",
        address="부산광역시 해운대구",
        status="PRODUCTION",
        shipping_scheduled_date=ship_date,
        scheduled_date="",
    )

    response = client.get(
        "/regional_dashboard",
        query_string={"search_query": "Regional Install Sort"},
    )
    assert response.status_code == 200
    body = response.get_data(as_text=True)

    alert_ids = _order_row_ids_in_section(body, "상차 예정 알림 (3건)")
    assert alert_ids == [
        str(early_order.id),
        str(late_order.id),
        str(empty_order.id),
    ]


def test_regional_shipping_export_cells_never_bleed_into_neighbors() -> None:
    """Fixed-width export cells must clip and self-check (badge overflow regression).

    2026-08-07: AS + 라홈시스템 배지가 200px 고객 셀을 넘겨 주소 칸 위에 그려졌다.
    원인은 nowrap + overflow visible. 두 방어선이 코드에 남아 있는지 고정한다.
    """
    js = (ROOT / "static/js/measurement/regional-shipping-export.js").read_text(
        encoding="utf-8"
    )

    # 1) 모든 본문 셀은 클립(옆 셀 침범 차단)
    assert "td.style.overflow = 'hidden'" in js
    # 2) 고객 컬럼은 줄바꿈 허용 컬럼
    assert "wrap: true" in js
    assert "col.align === 'left' || col.wrap" in js
    # 3) 캡처 직전 오버플로 자기검사 게이트
    assert "function relaxOverflowingCells(" in js
    assert "cell.scrollWidth > cell.clientWidth" in js
    assert "relaxOverflowingCells(table);" in js


def test_regional_shipping_export_preserves_as_schedule_badge_contract() -> None:
    """PNG export must carry the AS schedule marker from the rendered row."""
    js = (ROOT / "static/js/measurement/regional-shipping-export.js").read_text(
        encoding="utf-8"
    )

    assert "data-as-shipping-schedule" in js
    assert "is_as_schedule" in js
    assert "querySelector('.regional-as-schedule-badge')" in js
    assert "badge.textContent = 'AS'" in js


def _install_date_input_html(row_html: str) -> str:
    """Extract 설치일 date input from a regional dashboard order row."""
    match = re.search(
        r'<input[^>]*type="date"[^>]*data-field="(?:scheduled_date|completion_date)"[^>]*>',
        row_html,
    )
    assert match is not None, "missing 설치일 date input in row"
    return match.group(0)


def test_shipping_date_change_records_status_via_board_js() -> None:
    """상태 기록은 상차일 변경 시점(canonical 보드 경로)에서 일어난다.

    읽기 경로 직접 쓰기(EXTERNAL state-writer)를 금지한 대신, 상차일 저장 성공 후
    같은 field_update status 경로로 섹션에 맞는 상태를 기록한다. AS 접수 행은 제외.
    """
    src = (ROOT / "templates/measurement/regional_dashboard.html").read_text(
        encoding="utf-8"
    )
    assert "function syncStatusToShippingDate(" in src
    assert "syncStatusToShippingDate(orderId, value, e.target)" in src
    assert "'SCHEDULED' : 'SHIPPED_PENDING'" in src
    assert "as-order-row" in src, "AS 행 제외 마커 누락"


def test_regional_dashboard_read_path_has_no_direct_status_write() -> None:
    """지방 대시보드 라우트는 렌더 중 order.status 를 직접 쓰지 않는다."""
    src = (ROOT / "foms/web/measurement/dashboard.py").read_text(encoding="utf-8")
    start = src.index("def regional_dashboard()")
    end = src.index("def metropolitan_dashboard()")
    body = src[start:end]
    # 대입만 잡는다 — 비교(``order.status == "SCHEDULED"``)는 정상 분류 로직이다.
    writes = re.findall(r"^\s*\w+\.status\s*=(?!=)", body, re.M)
    assert writes == [], f"read 경로 status 직접 쓰기: {writes}"
