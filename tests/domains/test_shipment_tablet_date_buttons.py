"""태블릿 가로 출고 탭 위 줄 날짜 버튼 계약 (설계서 2026-11-09-tablet-production-ui §14.10 P14-8 · 시안 안 28, sqlite domains lane).

위 줄(.foms-ship-pcbar) 왼쪽 = [◀] + 날짜 버튼 14개(라우트가 이미 넘기는 construction_panel_dates 앞 14일) + [▶].
버튼 = ``<a href="?date=…&q=…">`` (셸이 조각만 바꿔 연다). 고른 날 = is-selected + aria-current, 오늘 = is-today,
고른 날이 14일 밖이면 띠 앞에 그 날 버튼 하나(건수 없이). 제목 ``M/D(요일) 출고`` · ``N건`` 은 위 줄에서 뺐다.
오른쪽 = [돋보기](검색칸 펼침) · [AS 넣기](권한 그대로) · [더보기 ▾] 안 네 가지(다른 날짜 · 남은 자수 · 줄 높이 · 이미지 저장).
PC 머리(erp-pro-header) · PC 필터 카드는 그대로. 모든 이름은 지어낸 값이다.
"""
from __future__ import annotations

import datetime
import re
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest
from werkzeug.security import generate_password_hash

from db import db_session
from foms.services.erp_display import get_today_kst
from models import Order, OrderScheduleDate, User

ROOT = Path(__file__).resolve().parents[2]
DATEBAR_JS = "static/js/shipment/tablet-ship-datebar.js"
COLUMNS_CSS = "static/css/contexts/shipment/shipment-dashboard-columns.css"
DASHBOARD_MAIN = "templates/shipment/partials/dashboard_main.html"
DAY_RE = re.compile(r'<a class="foms-ship-day[ "][^>]*>.*?</a>', re.S)


def _read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def _login(client, team: str = "SHIPMENT") -> None:
    user = User(username=f"ship-datebar-{team}".lower(), password=generate_password_hash("secret"),
                role="STAFF", team=team, name="날짜단추시험", is_active=True)
    db_session.add(user)
    db_session.commit()
    with client.session_transaction() as sess:
        sess["user_id"] = user.id
        sess["username"] = user.username
        sess["role"] = user.role


def _order(day: str) -> None:
    sd = {"parties": {"customer": {"name": "가짜고객"}, "orderer": {"name": "가짜대리점"}},
          "items": [{"product_name": "가짜붙박이장", "spec_width": "2400", "quantity": 1}],
          "schedule": {"construction": {"date": day}}}
    order = Order(received_date=day, customer_name="가짜고객", phone="010-0000-0000", address="가짜시 가짜로 1",
                  product="가짜붙박이장", status="IN_CONSTRUCTION", is_erp_order=True, structured_data=sd)
    db_session.add(order)
    db_session.flush()
    db_session.add(OrderScheduleDate(order_id=order.id, kind="construction", date=day, source="beta_schedule"))
    db_session.commit()


def _bar(html: str) -> str:
    start = html.index('class="foms-ship-pcbar')
    return html[start:html.index('class="erp-pro-card erp-shipment-desktop-shell"', start)]


def _get(client, query: str) -> str:
    resp = client.get(f"/erp/shipment{query}")
    assert resp.status_code == 200, resp.status_code
    return resp.get_data(as_text=True)


def _href(tag: str) -> dict:
    href = re.search(r'href="([^"]+)"', tag).group(1).replace("&amp;", "&")
    return parse_qs(urlparse(href).query, keep_blank_values=True)


def test_fourteen_day_buttons_selected_today_and_url(client) -> None:
    today = get_today_kst()
    pick = (today + datetime.timedelta(days=2)).isoformat()
    _login(client)
    _order(today.isoformat())
    bar = _bar(_get(client, f"?date={pick}&q=%EA%B0%80%EC%A7%9C"))
    days = DAY_RE.findall(bar)
    assert len(days) == 14
    assert [re.search(r'data-ship-day="([^"]+)"', d).group(1) for d in days][0] == today.isoformat()
    sel = [d for d in days if "is-selected" in d]
    assert len(sel) == 1 and f'data-ship-day="{pick}"' in sel[0] and 'aria-current="date"' in sel[0]
    tod = [d for d in days if "is-today" in d]
    assert len(tod) == 1 and f'data-ship-day="{today.isoformat()}"' in tod[0]
    assert "<em>1건</em>" in tod[0]  # 그날 건수 = construction_panel_dates.count
    wd = "월화수목금토일"[today.weekday()]
    assert f"<b>{today.day} {wd}</b>" in tod[0]
    # 주소 = 지금 날짜 입력칸과 같은 ?date= (검색어 유지)
    assert _href(sel[0]) == {"date": [pick], "q": ["가짜"]}
    # 제목 · N건 은 위 줄에서 뺐다(고른 날 버튼이 대신)
    assert "foms-ship-pcbar__title" not in bar and " 출고</h2>" not in bar
    assert "foms-ship-pcbar__sub" not in bar
    # ◀ ▶
    assert 'data-ship-days-nav="-1"' in bar and 'data-ship-days-nav="1"' in bar
    assert bar.index('data-ship-days-nav="-1"') < bar.index("data-ship-days-track") < bar.index('data-ship-days-nav="1"')


def test_weekend_buttons_are_grey_class_only(client) -> None:
    _login(client)
    bar = _bar(_get(client, f"?date={get_today_kst().isoformat()}"))
    days = DAY_RE.findall(bar)
    weekend = [d for d in days if re.search(r"<b>\d+ [토일]</b>", d)]
    assert weekend and all("is-off" in d for d in weekend)


def test_selected_outside_range_adds_lead_button_without_count(client) -> None:
    far = (get_today_kst() + datetime.timedelta(days=30)).isoformat()
    _login(client)
    bar = _bar(_get(client, f"?date={far}"))
    days = DAY_RE.findall(bar)
    assert len(days) == 15
    first = days[0]
    assert "is-outside" in first and "is-selected" in first and f'data-ship-day="{far}"' in first
    assert "건</em>" not in first and f"<b>{int(far[5:7])}/{int(far[8:10])}</b>" in first
    assert sum("is-selected" in d for d in days) == 1
    assert _href(first)["date"] == [far]


def test_search_toggle_and_more_menu_four_items(client) -> None:
    _login(client)
    bar = _bar(_get(client, f"?date={get_today_kst().isoformat()}"))
    # 돋보기 → 검색칸(같은 GET 폼). 검색어가 없으면 접힌 채 시작.
    assert bar.startswith('class="foms-ship-pcbar"')
    assert "data-ship-search-toggle" in bar and 'aria-controls="foms-ship-pcbar-filter"' in bar
    assert "foms-ship-find__q" not in bar  # 검색어 없으면 돋보기만
    form = bar[bar.index('<form class="foms-ship-pcbar__filter"'):bar.index("</form>")]
    assert 'method="get"' in form and 'name="q"' in form
    # AS 넣기(출고팀 = 편집 가능)
    assert "<span>AS 넣기</span>" in bar
    menu = bar[bar.index('class="foms-ship-more__menu"'):]
    # 1) 다른 날짜(달력) — 같은 폼에 form= 으로 묶인 date 칸 + 열기
    assert re.search(r'<input type="date"[^>]*name="date"[^>]*form="foms-ship-pcbar-filter"', menu)
    assert re.search(r'<button type="submit"[^>]*form="foms-ship-pcbar-filter"', menu)
    # 2) 날짜별 남은 자수(띠 여닫기 그대로)
    assert 'data-ship-cap-toggle aria-expanded="false" aria-controls="foms-ship-cap-strip"' in menu
    # 3) 줄 높이 40 48 56
    assert 'class="foms-density-toggle"' in menu
    assert all(f'data-density="{n}"' in menu for n in (40, 48, 56))
    # 4) 이미지 저장(숨은 PC 단추를 누르는 방아쇠)
    assert "js-shipment-export-trigger" in menu and "<span>이미지 저장</span>" in menu
    # 더보기 단추가 메뉴를 가리킨다
    assert 'data-ship-more-toggle aria-expanded="false" aria-controls="foms-ship-more-menu"' in bar
    assert "style=" not in bar


def test_search_query_shown_beside_lens(client) -> None:
    """검색 중이면 돋보기 옆에 검색어(작은 창은 닫힌 채 시작 — 위 줄은 늘 한 줄)."""
    _login(client)
    bar = _bar(_get(client, f"?date={get_today_kst().isoformat()}&q=zz"))
    lens = re.search(r"<button [^>]*data-ship-search-toggle[^>]*>.*?</button>", bar, re.S).group(0)
    assert "is-active" in lens and '<span class="foms-ship-find__q">zz</span>' in lens
    assert 'aria-expanded="false"' in lens
    assert 'value="zz"' in bar


def test_sales_has_no_as_insert_but_keeps_more(client) -> None:
    _login(client, "SALES")
    bar = _bar(_get(client, f"?date={get_today_kst().isoformat()}"))
    assert "data-shipment-as-recommend-open" not in bar
    assert "data-ship-more-toggle" in bar and "js-shipment-export-trigger" in bar


def test_pc_header_and_filter_card_unchanged(client) -> None:
    _login(client)
    html = _get(client, f"?date={get_today_kst().isoformat()}")
    start = html.index('<header class="erp-pro-header">')
    head = html[start:html.index("</header>", start)]
    assert "<span>출고 대시보드</span>" in head and 'id="btn-export-image"' in head
    card = html[html.index('<form class="erp-pro-filter-form'):]
    card = card[:card.index("</form>")]
    assert 'name="q"' in card and 'name="date"' in card and "<span>조회</span>" in card


def test_js_css_contract() -> None:
    js = _read(DATEBAR_JS)
    assert len(js.splitlines()) <= 150
    assert "__FOMS_SHIP_DATEBAR_BOUND" in js and "foms:erp-shell-fragment-swapped" in js
    assert "jQuery" not in js and "$(" not in js
    assert "'Escape'" in js
    entry = _read("static/js/shipment/shipment-entry.js")
    assert re.search(r"'/static/js/shipment/tablet-ship-datebar\.js\?v=\d{8}[a-z]'", entry)
    css = re.sub(r"\s+", " ", _read(COLUMNS_CSS))
    sel = css[css.index("body.erp-mobile-v2-layout .foms-ship-day.is-selected {"):]
    sel = sel[:sel.index("}")]
    assert "solid" in sel and "background" not in sel  # 칠 없음(D29) — 테두리만
    assert ".foms-ship-day.is-today { border: 1.5px dashed" in css
    assert "scroll-snap-type: x mandatory;" in css
    assert "body.erp-mobile-v2-layout .foms-ship-more.is-open .foms-ship-more__menu { display: flex; }" in css
    assert ".foms-ship-find.is-open .foms-ship-pcbar__filter { display: flex;" in css
    # 새 글자 크기는 손잡이 배율을 탄다
    block = css[css.index(".foms-ship-days {"):css.index(".foms-ship-pcbar__btn {")]
    assert not re.search(r"font-size: \d+px", block)


@pytest.mark.parametrize("rel", [DASHBOARD_MAIN])
def test_template_has_no_inline_style_in_bar(rel) -> None:
    html = _read(rel)
    seg = html[html.index('<div class="foms-ship-pcbar'):html.index('<div class="erp-pro-card erp-shipment-desktop-shell">')]
    assert "style=" not in seg
