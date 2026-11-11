"""태블릿 가로 출고 탭 — 위 줄 [협력사 희망 N] 단추로 내려오는 협력사 희망 판 (설계서 2026-11-09-tablet-production-ui §14.8 P14-6).

고정하는 것:

* 위 줄 단추 ``협력사 희망 N`` + 가장 빠른 날이 내일이면 ``내일 n``. 판이 그려질 때만(``count or history``), 켜진 프리랜서는 없음.
* 판은 한 벌(``data-prb`` 1개) · 뒤 막 1개 · [닫기 ▴] 1개 — 서랍용으로 판을 또 그리지 않는다.
* 여러 협력사일 때 회사 이름은 따로 감싼 칸(PC 글은 ``이름 (회사)`` 그대로).
* CSS: 태블릿 코호트에서 판 평소 숨김 → 뿌리 ``.is-prb-drop-open`` 일 때 고정 서랍 · 막 · 7칸 · 13px 이상 · 칠 없음.
  PC 판 모양(14칸 · 주말 칠)은 그대로.
* JS: 여닫기는 새 작은 파일(entry CHAIN 핀), 판 JS 는 창이 열린 채 칸을 누르면 날짜를 바꾼다 · 300줄 안.

모든 이름은 지어낸 값이다.
"""
from __future__ import annotations

import datetime
import re
from pathlib import Path

from flask import render_template

from db import db_session
from foms.services.datetime_kst import get_today_kst
from models import PartnerOrg, User
from tests.security.partner_fixtures import (  # noqa: F401 — pytest fixture 재노출
    _PAYLOAD,
    _client,
    _create,
    world,
)

ROOT = Path(__file__).resolve().parents[2]
BOARD_CSS = "static/css/contexts/shipment/partner-request-board.css"
COLUMNS_CSS = "static/css/contexts/shipment/shipment-dashboard-columns.css"
BOARD_JS = "static/js/shipment/partner-request-board.js"
DROP_JS = "static/js/shipment/tablet-prb-drop.js"
ENTRY_JS = "static/js/shipment/shipment-entry.js"
DASHBOARD_MAIN = "templates/shipment/partials/dashboard_main.html"
CORE_MQ = "@media (min-width: 992px) and (orientation: landscape) and (pointer: coarse) {"


def _read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def _day(n: int) -> str:
    return (get_today_kst() + datetime.timedelta(days=n)).isoformat()


def _order(app, partner_id, *, hope, name, time=""):
    resp = _create(app, partner_id, {**_PAYLOAD, "customer_name": name,
                                     "requested_construction_date": hope, "requested_construction_time": time})
    assert resp.status_code == 200, resp.get_json()
    return resp.get_json()["data"]["order_id"]


def _page(app, user_id) -> str:
    return _client(app, db_session.get(User, user_id)).get("/erp/shipment").get_data(as_text=True)


def _button(html: str) -> str:
    m = re.search(r"<button [^>]*data-prb-drop-toggle[^>]*>.*?</button>", html, re.S)
    return m.group(0) if m else ""


# --- (1) 실제 출고 화면 렌더 -------------------------------------------------------


def test_shipment_page_top_bar_button_and_single_board(app, world):
    _order(app, world["partner_a"], hope=_day(1), name="내일고객")
    _order(app, world["partner_a"], hope=_day(4), name="나흘고객")
    _order(app, world["partner_a"], hope="", name="날짜없음고객", time="오후")   # 날짜 없이 시간만 = 판 밖 줄
    page = _page(app, world["staff"])
    btn = _button(page)
    assert btn, "위 줄 단추가 없다"
    assert "협력사 희망 3" in btn and "내일 1" in btn
    assert 'aria-expanded="false"' in btn and 'aria-controls="foms-prb-drop"' in btn and "style=" not in btn
    # 단추는 위 줄(pcbar) 안 · 판보다 앞
    assert page.index('class="foms-ship-pcbar"') < page.index("data-prb-drop-toggle") < page.index("data-partner-pending-requests")
    # 판은 한 벌, 막 · [닫기]도 하나씩
    assert len(re.findall(r"\sdata-prb[\s>]", page)) == 1
    assert page.count('id="foms-prb-drop"') == 1
    assert page.count("data-prb-drop-scrim") == 1 and page.count("data-prb-drop-close") == 1
    assert "닫기 ▴" in page


def test_no_tomorrow_text_when_earliest_is_later(app, world):
    _order(app, world["partner_a"], hope=_day(3), name="사흘고객")
    btn = _button(_page(app, world["staff"]))
    assert "협력사 희망 1" in btn and "내일" not in btn


def test_no_button_when_no_board(app, world):
    """판이 안 그려지면(확정 대기 0 · 기록 0) 단추 · 막도 없다 — 대조군."""
    page = _page(app, world["staff"])
    assert "data-prb-drop-toggle" not in page and "data-prb-drop-scrim" not in page


def test_multi_partner_company_name_wrapped_separately(app, world):
    _order(app, world["partner_a"], hope=_day(2), name="가나고객")
    _order(app, world["partner_b"], hope=_day(2), name="다라고객")
    page = _page(app, world["staff"])
    org = db_session.get(PartnerOrg, world["org_b"]).name
    assert ('<span class="prb-chip__name">다라고객</span><span class="prb-chip__co"><span class="prb-chip__paren"> (</span>'
            f'{org}<span class="prb-chip__paren">)</span></span>') in page
    # PC 에 보이는 글은 예전과 같다: '이름 (회사)'
    text = re.sub(r"<[^>]+>", "", page)
    assert f"다라고객 ({org})" in text


# --- (2) 단추 파샬 직접 렌더(프리랜서 · 판 없음 · 기록만) ------------------------------


def _render_button(app, board, freelancer=False) -> str:
    with app.test_request_context("/erp/shipment"):
        return render_template("shipment/partials/partner_request_drop_button.html",
                               partner_request_board=board, shipment_freelancer_view=freelancer)


def test_button_partial_conditions(app):
    full = {"count": 5, "history": [], "earliest": {"is_tomorrow": True, "items": [{}, {}]}}
    html = _render_button(app, full)
    assert "협력사 희망 5" in html and "내일 2" in html
    assert "data-prb-drop-toggle" not in _render_button(app, full, freelancer=True)
    assert "data-prb-drop-toggle" not in _render_button(app, None)
    assert "data-prb-drop-toggle" not in _render_button(app, {"count": 0, "history": [], "earliest": None})
    history_only = _render_button(app, {"count": 0, "history": [{"order_id": 1}], "earliest": None})
    assert "협력사 희망 0" in history_only and "내일" not in history_only
    later = _render_button(app, {"count": 2, "history": [], "earliest": {"is_tomorrow": False, "items": [{}]}})
    assert "협력사 희망 2" in later and "내일" not in later


def test_dashboard_main_includes_button_after_unassigned_pill() -> None:
    html = _read(DASHBOARD_MAIN)
    miss = html.index('class="foms-ship-pcbar__miss"')
    inc = html.index("partner_request_drop_button.html")
    assert miss < inc < html.index('<form class="foms-ship-pcbar__filter"')


# --- (3) CSS ---------------------------------------------------------------------


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"/\*.*?\*/", "", text, flags=re.S))


def test_board_css_hidden_in_cohort_and_drawer_only_when_open() -> None:
    css = _norm(_read(BOARD_CSS))
    pc, _, tablet = css.partition(CORE_MQ)
    assert tablet, "태블릿 코호트 블록이 없다"
    assert ".prb-drop-close, .prb-drop-scrim { display: none; }" in pc
    # PC 판 모양 그대로: 14칸 · 주말 칠
    assert "grid-template-columns: repeat(14, minmax(0, 1fr));" in pc and ".prb-cell.is-off { background: #fffaf0; }" in pc
    assert "body.erp-mobile-v2-layout .erp-dashboard-shipment .prb { display: none; }" in tablet
    m = re.search(r"body\.erp-mobile-v2-layout \.erp-dashboard-shipment\.is-prb-drop-open \.prb \{([^}]*)\}", tablet)
    assert m and "position: fixed;" in m.group(1) and "var(--prb-drop-top" in m.group(1)
    assert "100dvh / var(--foms-ui-zoom, 1)" in m.group(1)
    scrim = re.search(r"\.is-prb-drop-open \.prb-drop-scrim \{([^}]*)\}", tablet)
    assert scrim and "position: fixed;" in scrim.group(1)
    z_drop = int(re.search(r"z-index: (\d+)", m.group(1)).group(1))
    z_scrim = int(re.search(r"z-index: (\d+)", scrim.group(1)).group(1))
    z_pop = int(re.search(r"\.prb-pop \{[^}]*z-index: (\d+)", pc).group(1))
    assert z_scrim < z_drop < z_pop, "막 < 서랍 < 정하기 창"
    # 서랍 안 머리 접기 끔 · 늘 펼침
    assert ".prb.is-folded .prb-body { display: block; }" in tablet and ".prb-head { pointer-events: none;" in tablet


def test_board_css_finger_sizes_no_fill() -> None:
    css = _norm(_read(BOARD_CSS))
    tablet = css.partition(CORE_MQ)[2]
    assert "grid-template-columns: repeat(7, minmax(0, 1fr));" in tablet
    chip = re.search(r"\.erp-dashboard-shipment \.prb-chip \{([^}]*)\}", tablet).group(1)
    assert int(re.search(r"min-height: (\d+)px", chip).group(1)) >= 44
    assert "background: var(--foms-surface-base, #fff);" in chip
    assert ".prb-cell.is-off { background: var(--foms-surface-base, #fff); }" in tablet
    assert ".prb-chip__paren { display: none; }" in tablet
    sizes = re.findall(r"font-size: ([^;]+);", tablet)
    assert sizes
    for value in sizes:
        mm = re.fullmatch(r"calc\((\d+)px \* var\(--foms-fs, 1\)\)( !important)?", value.strip())
        assert mm, f"글자 손잡이를 안 따르는 font-size: {value}"
        assert int(mm.group(1)) >= 13, f"13px 보다 작은 글자: {value}"
    for sel in re.findall(r"(?:^|[{}])\s*([^{}@]+?)\s*\{", tablet):
        for part in sel.split(","):
            assert part.strip().startswith("body.erp-mobile-v2-layout"), f"문지기 밖 선택자: {part.strip()}"


def test_top_bar_button_css_in_cohort() -> None:
    css = _norm(_read(COLUMNS_CSS))
    assert "body.erp-mobile-v2-layout .foms-ship-pcbar__prb {" in css
    assert 'body.erp-mobile-v2-layout .foms-ship-pcbar__prb[aria-expanded="true"] {' in css
    assert ".foms-ship-pcbar__prb-soon { font-size: calc(13px * var(--foms-fs, 1));" in css


# --- (4) JS ----------------------------------------------------------------------


def test_drop_js_contract_and_pins() -> None:
    js = _read(DROP_JS)
    assert len(js.splitlines()) <= 80
    assert "jQuery" not in js and "$(" not in js
    assert "__FOMS_PRB_DROP_BOUND" in js and "is-prb-drop-open" in js and "aria-expanded" in js
    for hook in ("[data-prb-drop-toggle]", "[data-prb-drop-scrim]", "[data-prb-drop-close]", "'Escape'"):
        assert hook in js
    assert "fomsUiZoom" in js and "--prb-drop-top" in js
    assert "localStorage" not in js, "열림을 기억하지 않는다(늘 닫힌 채 시작)"
    entry = _read(ENTRY_JS)
    assert re.search(r"'/static/js/shipment/tablet-prb-drop\.js\?v=\d{8}[a-z]'", entry)
    assert entry.index("partner-request-board.js") < entry.index("tablet-prb-drop.js")


def test_board_js_cell_tap_changes_open_pop_date() -> None:
    js = _read(BOARD_JS)
    assert len(js.splitlines()) < 300
    i_cell = js.index("document.querySelector('#prb-pop [data-prb-pop-date]')")
    i_close = js.index("if (!t.closest('#prb-pop')) closePop();")
    assert i_cell < i_close, "칸 누름이 창 닫기보다 먼저 와야 날짜가 바뀐다"
    block = js[i_cell:i_close]
    assert "t.closest('[data-prb-cell]')" in block and "getAttribute('data-prb-cell')" in block
    assert "dispatchEvent(new Event('change'))" in block and "return;" in block
