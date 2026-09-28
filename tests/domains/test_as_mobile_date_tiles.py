"""모바일 v2 AS 카드 A안 2단 날짜(2026-09-28) 계약.

좁은 폰에서 3칸 날짜 상자(접수·방문·완료)가 네이티브 date 입력 글자를 잘라 먹었다.
접수 = 한 줄 캡션, 방문·완료 = 2칸 타일(투명 진짜 date 입력이 타일을 덮음)로 바꿨다.
표기 SSOT = foms/services/as_dashboard_display.py build_as_mobile_date_view,
저장 직후 갱신 = static/js/cs/as-dashboard.js refreshAsCardDateTiles.
"""

from __future__ import annotations

import re
from pathlib import Path

from werkzeug.security import generate_password_hash

from db import db_session
from models import Order, User


def _login_as_admin(client):
    user = User(
        username="erp_as_date_tile_admin",
        password=generate_password_hash("admin"),
        role="ADMIN",
        team="CS",
        name="ERP AS Date Tile Admin",
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    with client.session_transaction() as sess:
        sess["user_id"] = user.id
        sess["username"] = user.username
        sess["role"] = user.role
    return user


# ── A안 2단 날짜(2026-09-28) ──────────────────────────────────────────────
# '오늘'은 언제나 KST(get_today_kst) 기준으로 상대 날짜를 만든다 — CI 는 UTC 라
# date.today() 로 만들면 한국 밤 시간대에 하루 어긋나 깨진다.


def _kst_today():
    from foms.services.datetime_kst import get_today_kst

    return get_today_kst()


def test_as_mobile_date_view_formats_weekday_year_today_and_overdue():
    import datetime

    from foms.services.as_dashboard_display import build_as_mobile_date_view

    today = datetime.date(2026, 9, 28)  # 월요일
    view = build_as_mobile_date_view(
        received="2026-09-22", visit="2026-10-08", completed=None, today=today
    )
    assert view["received_text"] == "9월 22일 (화)"
    assert view["visit_text"] == "10월 8일 (목)"  # 0 패딩 없음, 요일 한 글자
    assert view["visit_year_tag"] == ""
    assert view["visit_overdue_days"] == 0  # 앞으로 올 방문은 지남 아님
    assert view["completed_text"] == ""

    other_year = build_as_mobile_date_view(
        received="2025-12-03", visit="2025-12-10", completed="2025-12-11", today=today
    )
    assert other_year["received_text"] == "2025년 12월 3일 (수)"
    assert other_year["visit_text"] == "12월 10일 (수)"
    assert other_year["visit_year_tag"] == "2025년"
    assert other_year["completed_year_tag"] == "2025년"
    assert other_year["visit_overdue_days"] == 0  # 완료일이 있으면 지남 배지 없음

    today_rec = build_as_mobile_date_view(
        received="2026-09-28", visit="2026-09-28", completed="", today=today
    )
    assert today_rec["received_text"] == "9월 28일 (월) · 오늘"
    assert today_rec["visit_overdue_days"] == 0  # 오늘 방문은 아직 지남 아님

    overdue = build_as_mobile_date_view(
        received="2026-09-01", visit="2026-09-25", completed=None, today=today
    )
    assert overdue["visit_overdue_days"] == 3

    raw = build_as_mobile_date_view(received="미상", visit=None, completed=None, today=today)
    assert raw["received_text"] == "미상"  # 날짜로 못 읽으면 원문 그대로(지어내지 않음)
    assert raw["visit_text"] == "" and raw["visit_overdue_days"] == 0


def _card_html(body: str, order_id: int) -> str:
    start = body.index(f'id="as-card-{order_id}"')
    return body[start:body.index("</article>", start)]


def _create_dated_as_order(name, *, visit=None, received=None, completed=None, status="AS_RECEIVED"):
    today = _kst_today().isoformat()
    sd = {"shipment": {"as_content": "<div>n</div>"}}
    if visit:
        sd["schedule"] = {"as_visit": {"date": visit}}
    order = Order(
        received_date=today,
        customer_name=name,
        phone="010-0000-0000",
        address="Seoul",
        product="x",
        status=status,
        manager_name="M",
        as_received_date=received or today,
        as_completed_date=completed,
        is_erp_order=True,
        structured_data=sd,
    )
    db_session.add(order)
    db_session.commit()
    return order


def test_as_mobile_v2_card_renders_two_date_tiles_with_real_inputs(client, monkeypatch):
    """v2 카드 = 접수 캡션 + 방문·완료 2타일. 타일 안 진짜 date 입력은 저장 배선 계약
    (editable-date-as·data-field·aria-label)을 그대로 들고, 보이는 값은 aria-hidden 이다."""
    import datetime

    monkeypatch.setenv("ERP_MOBILE_V2_ENABLED", "true")
    user = _login_as_admin(client)
    monkeypatch.setenv("FOMS_V3_SHELL_COHORT", str(user.id))

    today = _kst_today()
    past_visit = today - datetime.timedelta(days=3)
    next_year_visit = datetime.date(today.year + 1, 1, 5)
    overdue_order = _create_dated_as_order("지남고객", visit=past_visit.isoformat())
    future_order = _create_dated_as_order("내년고객", visit=next_year_visit.isoformat())
    empty_order = _create_dated_as_order("미정고객")
    overdue_id, future_id, empty_id = overdue_order.id, future_order.id, empty_order.id

    resp = client.get("/erp/as?tab=incomplete")
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    # '오늘'은 서버 KST 값으로 JS 에 넘긴다(브라우저 시계 불신).
    assert f'data-as-today="{today.isoformat()}"' in body

    weekdays = "월화수목금토일"
    card = _card_html(body, overdue_id)
    assert card.count('class="erp-as-date-tile ') == 2
    assert "erp-as-mobile-card__date-grid" in card
    assert 'style="' not in card  # 인라인 스타일 금지
    for field, aria in (("as_visit_date", "AS 방문일"), ("as_completed_date", "AS 완료일")):
        assert re.search(
            r'<input type="date" class="erp-pro-input editable-date-as erp-as-date-tile__input"[^>]*'
            rf'data-field="{field}" aria-label="{aria}"',
            card,
        ), field
    assert card.count('class="erp-as-date-tile__value" aria-hidden="true"') == 2
    # 접수 캡션: 오늘 접수 → 'M월 D일 (요) · 오늘'
    received_caption = f"{today.month}월 {today.day}일 ({weekdays[today.weekday()]}) · 오늘"
    assert received_caption in card
    # 지난 방문 + 완료 없음 → 'N일 지남' 배지가 입력의 aria-describedby 로 묶인다.
    badge_id = f"as-visit-overdue-{overdue_id}"
    assert f'<span class="erp-as-date-tile__overdue" id="{badge_id}">3일 지남</span>' in card
    assert f'aria-describedby="{badge_id}"' in card
    assert f"{past_visit.month}월 {past_visit.day}일 ({weekdays[past_visit.weekday()]})" in card
    # 가능시간 칩은 타일 밖 자기 줄 — 기존 클래스·data-avail-* 유지.
    assert "erp-as-avail-chip erp-as-mobile-card__avail" in card
    assert 'data-avail-days=""' in card
    assert "방문 가능 시간 입력" in card
    # 칩은 두 타일(label)이 모두 닫힌 뒤에 온다 — 타일 안이면 투명 입력에 덮여 안 눌린다.
    assert card.rindex("</label>") < card.index('class="erp-as-avail-chip')

    future_card = _card_html(body, future_id)
    assert "erp-as-date-tile__overdue" not in future_card  # 앞으로 올 방문은 지남 아님
    assert "aria-describedby" not in future_card
    assert f'<span class="erp-as-date-tile__year">{next_year_visit.year}년</span>' in future_card
    assert "erp-as-date-tile erp-as-date-tile--visit is-set" in future_card

    empty_card = _card_html(body, empty_id)
    assert "erp-as-date-tile erp-as-date-tile--visit is-empty" in empty_card
    assert "날짜 선택" in empty_card
    assert "erp-as-date-tile__overdue" not in empty_card


def test_as_mobile_v2_completed_card_has_no_overdue_badge(client, monkeypatch):
    """완료일이 있으면 방문일이 지났어도 '지남' 배지를 내지 않는다."""
    import datetime

    monkeypatch.setenv("ERP_MOBILE_V2_ENABLED", "true")
    user = _login_as_admin(client)
    monkeypatch.setenv("FOMS_V3_SHELL_COHORT", str(user.id))
    today = _kst_today()
    order = _create_dated_as_order(
        "완료고객",
        visit=(today - datetime.timedelta(days=5)).isoformat(),
        completed=today.isoformat(),
        status="AS_COMPLETED",
    )
    order_id = order.id

    resp = client.get("/erp/as?tab=completed")
    assert resp.status_code == 200
    card = _card_html(resp.get_data(as_text=True), order_id)
    assert "erp-as-date-tile erp-as-date-tile--complete is-set" in card
    assert "erp-as-date-tile__overdue" not in card
    assert "aria-describedby" not in card


def test_as_date_tile_macro_readonly_has_no_input(app):
    """저장 게이트 밖 역할은 입력 없이 값 또는 '미정'만 본다(403 날 입력 자체를 안 준다)."""
    with app.test_request_context():
        macros = app.jinja_env.get_template("cs/partials/as_card_macros.html").module
        empty = str(macros.render_as_date_tile("visit", None, "", "", 0, 7, False))
        filled = str(macros.render_as_date_tile("complete", "2026-10-08", "10월 8일 (목)", "", 0, 7, False))
    assert "<input" not in empty and "<input" not in filled
    assert "is-readonly" in empty and "미정" in empty
    assert "10월 8일 (목)" in filled and "is-set" in filled
    assert empty.lstrip().startswith("<div") and 'style="' not in empty + filled


def test_as_dashboard_js_v2_tile_sync_contract():
    """저장 직후 v2 타일 갱신 경로 계약(첫 렌더 = 서버, 갱신 = JS 가 같은 규칙).

    - syncDateFieldVisuals 가 타일(.erp-as-date-tile)을 행(.erp-pro-order-card__row)과 따로 그린다.
    - 날짜는 손으로 쪼갠다(new Date(iso) 금지 — UTC 자정 해석으로 하루 밀림).
    - '오늘'은 #as-dashboard-config[data-as-today](서버 KST).
    - v2 카드의 미결 버튼은 타일 안이 아니라 footer 칩으로 넣고 뺀다.
    """
    root = Path(__file__).resolve().parents[2]
    js = (root / "static/js/cs/as-dashboard.js").read_text(encoding="utf-8").replace("\r\n", "\n")
    visuals = js.split("function syncDateFieldVisuals(")[1].split("\n    }\n")[0]
    assert "closest('.erp-as-date-tile')" in visuals
    assert "refreshAsCardDateTiles(card, field, value)" in visuals
    tile_helpers = js.split("function parseAsIsoDate(")[1].split("function syncDateFieldVisuals(")[0]
    assert "new Date(value" not in tile_helpers and "Date.UTC(" in tile_helpers
    assert "cfg.dataset.asToday" in js
    pending = js.split("function syncVisitPendingButtons(")[1].split("\n    }\n")[0]
    assert "erp-as-mobile-card--v2" in pending
    assert "syncV2FooterPendingButton(container, orderId, hasVisitDate)" in pending
    # 가능시간 칩 문구: v2 칩이 data-avail-label-* 로 긴 문구를 들고 온다.
    assert "chip.dataset.availLabelPrefix" in js and "chip.dataset.availLabelEmpty" in js
