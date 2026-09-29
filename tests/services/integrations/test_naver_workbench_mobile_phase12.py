# -*- coding: utf-8 -*-
"""네이버 수집 워크벤치 폰 1·2단계(2026-09-29 목업) 계약.

폰(≤767.98px)에서만 바꾸고 **데스크톱 화면은 그대로**다. 여기서 무는 것:

* 1단계 — 전역 크롬(머리줄·메뉴 버튼 줄)을 **이 화면에서만** 접고, ☰ 가 **같은 전역 메뉴**
  (#navbarNav collapse)를 연다(메뉴가 펼쳐진 동안 알림·계정 줄이 돌아온다). 56px 한 줄,
  탭 2칸 세그먼트, `마지막 수집` 은 이미 실린 값만, 빈 처리 목록 문구 + 이력 보기.
* 2단계 — 이력 칩 8개 → `상태:` 버튼 + 아래 시트(칩과 **같은 주소·같은 켜짐**, 5 + 3 묶음),
  8칸 표 → 3줄 카드(같은 표 마크업을 CSS 로 편다 · 카드 전체 = 원본 보기), 찾기 16px.

폰 배치 1차(2026-09-28)의 계약·보조 함수는 ``test_naver_workbench_mobile.py`` 에 있다.
"""

from __future__ import annotations

import re

from flask import url_for

from foms.web.admin import naver_ingest
from tests.services.integrations.test_naver_workbench_mobile import (
    CSS,
    JS,
    PHONE_MEDIA,
    TEMPLATE,
    TRIAGE_PATH,
    _empty_strips,
    _media_block,
    _outside_media,
    _rule,
)
from tests.services.integrations.test_naver_workbench_v3_contract import (  # noqa: F401
    _login,
    workbench_on,
)


# --------------------------------------------------------------------------- #
# 폰 1단계(2026-09-29 목업) — 크롬 한 줄 · ☰ 전체 메뉴 · 탭 2칸 · 빈 처리 목록
# --------------------------------------------------------------------------- #

def _phone_css() -> tuple[str, str]:
    """(폰 미디어 블록, 미디어 쿼리 밖 규칙)."""
    css = CSS.read_text(encoding="utf-8").replace("\r\n", "\n")
    return _media_block(css, PHONE_MEDIA), _outside_media(css)


def _watermark(monkeypatch) -> None:
    """이력 탭 수집 상태 카드가 싣는 워터마크 — 마지막 실행 2026-09-29 08:26."""
    monkeypatch.setattr(naver_ingest, "_watermark_view", lambda db: {
        "last_success_to": "2026-09-29T08:25:57+09:00", "last_run_at": "2026-09-29T08:26:00+09:00",
        "last_success_to_text": "2026-09-29 08:25", "last_run_at_text": "2026-09-29 08:26",
        "last_error": None, "last_summary": {}})


def test_phone_folds_global_chrome_only_on_this_page():
    """폰에서만, 이 화면(`.naver-workbench` 가 있는 body)에서만 전역 머리줄·메뉴 줄을 접는다.
    ☰ 로 메뉴가 펼쳐진 동안(show·collapsing)은 두 줄을 그대로 돌려준다 — 알림·계정은 머리줄에만 있다."""
    phone, everywhere = _phone_css()

    assert "body:has(.naver-workbench) .layout-header { display: none !important; }" in phone
    assert "body:has(.naver-workbench) .layout-global-nav { display: none; }" in phone
    for state in ("show", "collapsing"):
        assert f"body:has(.naver-workbench):has(#navbarNav.{state}) .layout-header" in phone
        assert f"body:has(.naver-workbench):has(#navbarNav.{state}) .layout-global-nav" in phone
    assert "{ display: flex !important; }" in phone.split("#navbarNav.collapsing) .layout-header")[1][:60]
    # 데스크톱은 전역 크롬을 한 줄도 건드리지 않는다.
    assert ".layout-header" not in everywhere
    assert ".layout-global-nav" not in everywhere.split("/* ══ 폰 배치")[1]
    # 범위 없는 접기 금지 — 다른 화면의 메뉴를 삼킨다.
    for line in phone.splitlines():
        if ".layout-header {" in line or ".layout-global-nav {" in line:
            assert "body:has(.naver-workbench)" in line, line


def test_menu_button_opens_the_existing_global_menu(client, workbench_on, monkeypatch):
    """☰ 는 새 메뉴가 아니라 **이미 있는** 전역 collapse(#navbarNav)를 연다. 알림·계정 버튼은
    전역 머리줄에 그대로 있다(메뉴가 펼쳐지면 CSS 가 그 줄을 돌려준다)."""
    _empty_strips(monkeypatch)
    _login(client)

    body = client.get(TRIAGE_PATH, query_string={"tab": "work"}).get_data(as_text=True)

    head = body[body.index('class="wb-bar wb-bar--head"'):body.index('<nav class="wb-tabs"')]
    button = head[head.index('<button type="button" class="wb-menu"'):]
    button = button[:button.index(">")]
    assert 'data-bs-toggle="collapse"' in button and 'data-bs-target="#navbarNav"' in button
    assert 'aria-controls="navbarNav"' in button and 'aria-expanded="false"' in button
    assert 'aria-label="전체 메뉴"' in button
    assert body.count('id="navbarNav"') == 1, "메뉴를 두 벌 만들지 않는다"
    assert body.index('id="navbarNav"') < body.index('class="container-fluid naver-workbench"')
    for reach in ('id="global-notification-btn"', 'id="userDropdown"'):
        assert reach in body, f"{reach} — 폰에서 알림·계정에 닿을 길"
    _, everywhere = _phone_css()
    assert ".wb-menu { display: none; }" in everywhere


def test_phone_top_bar_is_one_56px_row_with_menu_last():
    """56px 한 줄: ‹ ERP(0) · 제목 상자(1) · 다시 읽기(2) · ☰(3) → 사실(5) → 탭(7).

    탭이 맨 아래 줄인 까닭(2026-09-30 P1 · N-06): 머리줄이 음수 top 으로 붙어 탭 줄만 화면에 남는다."""
    phone, everywhere = _phone_css()

    assert "min-height: 56px" in _rule(phone, "    .naver-workbench .wb-bar--head")
    assert "order: 1;" in _rule(phone, "    .wb-bar__titlebox")
    menu = _rule(phone, "    .wb-menu")
    assert "order: 3;" in menu and "width: 44px;" in menu and "height: 44px;" in menu
    assert "order: 7;" in phone.split("    .wb-tabs {")[-1].split("}")[0]
    # 데스크톱: 제목 상자는 없는 것과 같다(contents) — 제목이 예전처럼 머리줄의 한 칸.
    assert ".wb-bar__titlebox { display: contents; }" in everywhere
    assert ".wb-bar__sub { display: none; }" in everywhere


def test_last_ingest_time_rides_under_title_only_when_already_loaded(client, workbench_on,
                                                                   monkeypatch):
    """`마지막 수집` 은 서버가 이미 실은 값(이력 탭·ADMIN 의 ingest_status)만 쓴다 —
    처리 탭에서는 조회를 더하지 않으므로 줄이 없다. 날짜를 떼지 않는다(어제를 오늘로 읽는다)."""
    _empty_strips(monkeypatch)
    _watermark(monkeypatch)
    _login(client)

    hist = client.get(TRIAGE_PATH, query_string={"tab": "all"}).get_data(as_text=True)
    box = hist[hist.index('class="wb-bar__titlebox"'):hist.index('class="wb-menu"')]
    assert '<span class="wb-bar__sub">마지막 수집 09-29 08:26</span>' in box

    work = client.get(TRIAGE_PATH, query_string={"tab": "work"}).get_data(as_text=True)
    assert 'class="wb-bar__sub"' not in work


def test_tabs_are_two_segments(client, workbench_on, monkeypatch):
    """탭은 처리 · 이력 두 칸이다(대조 탭은 삭제됐다). 폰은 칸마다 44px 세그먼트."""
    _empty_strips(monkeypatch)
    _login(client)

    body = client.get(TRIAGE_PATH, query_string={"tab": "work"}).get_data(as_text=True)
    tabs = body[body.index('<nav class="wb-tabs"'):]
    tabs = tabs[:tabs.index("</nav>")]
    assert re.findall(r'data-tab="(\w+)"', tabs) == ["work", "all"]
    assert 'data-tab="gap"' not in body
    phone, _ = _phone_css()
    assert "min-height: 44px;" in phone.split("    .wb-tab {")[1].split("}")[0]
    selected = phone.split('    .wb-tab[aria-selected="true"] {')[-1].split("}")[0]
    assert "background: #ffffff;" in selected


def test_empty_work_list_says_nothing_to_do_and_points_to_history(client, workbench_on,
                                                                  monkeypatch):
    """빈 처리 목록(칩 '전체'): 목업 문구 + 이력 보기. 이력을 못 여는 사람에게는 길을 안 그린다.
    필터를 건 빈 목록의 문구는 그대로다."""
    _empty_strips(monkeypatch)
    _login(client)

    body = client.get(TRIAGE_PATH, query_string={"tab": "work"}).get_data(as_text=True)
    empty = body[body.index('class="wb-empty wb-empty--done"'):]
    empty = empty[:empty.index("</div>")]
    assert "지금 처리할 주문이 없어요" in empty
    with client.application.test_request_context():
        href = url_for("admin.naver_ingest_triage", tab="all")
    assert f'class="wb-empty__go" href="{href}">이력 보기</a>' in empty
    assert "확인할 주문이 없습니다" not in body
    assert 'style="' not in empty

    monkeypatch.setattr(naver_ingest, "_can_view_history", lambda: False)
    blind = client.get(TRIAGE_PATH, query_string={"tab": "work"}).get_data(as_text=True)
    assert "지금 처리할 주문이 없어요" in blind and "wb-empty__go" not in blind

    filtered = client.get(TRIAGE_PATH, query_string={"tab": "work", "f": "place"}).get_data(as_text=True)
    assert "이 필터에 해당하는 주문이 없습니다" in filtered


# --------------------------------------------------------------------------- #
# 폰 2단계(2026-09-29 목업) — 이력 상태 시트 · 3줄 카드 · 찾기 16px
# --------------------------------------------------------------------------- #

def _seed_history():
    """이력 행 셋 — 주문 없는 수집분 둘(하나는 발주확인 전) + 주문이 붙은 하나."""
    from db import db_session
    from models import Order
    from tests.services.integrations.test_naver_workbench import _collected

    first = _collected(order_no="N-MOB-H1", product="모바일 이력 붙박이장", amount=1284000)
    _collected(order_no="N-MOB-H2", product="모바일 이력 서랍장", amount=342000,
               place_status="", address="서울 마포구 2", tel="010-5555-0002")
    linked = _collected(order_no="N-MOB-H3", product="모바일 이력 선반", amount=171000,
                        address="서울 종로구 3", tel="010-5555-0003")
    order = Order(received_date="2026-09-01", customer_name="이수취", phone="010-5555-0003",
                  address="서울 종로구 3 101호", product="선반", status="RECEIVED")
    db_session.add(order)
    db_session.commit()
    linked.order_id = order.id
    linked.sync_status = "LINKED"
    db_session.commit()
    return first, linked, order


def _chip_links(body: str) -> list[tuple[str, str]]:
    """이력 칩 8개의 (href, aria-pressed)."""
    block = body.split('class="wb-filters"', 1)[1].split('<form class="wb-find"', 1)[0]
    return [(href, pressed) for pressed, href in
            re.findall(r'<a class="wb-chip" aria-pressed="(\w+)"\s+href="([^"]+)"', block)]


def _sheet(body: str) -> str:
    start = body.index('<dialog class="wb-hsheet"')
    return body[start:body.index("</dialog>", start)]


def test_history_sheet_uses_the_same_links_as_the_chips(client, workbench_on, monkeypatch):
    """시트 줄 8개 = 칩 8개와 **같은 주소·같은 켜짐**(한 목록에서 그린다). 묶음은 5 + 3."""
    _empty_strips(monkeypatch)
    _seed_history()
    _login(client)

    for query in ({"tab": "all"},
                  {"tab": "all", "status": "COLLECTED", "place": "PENDING"},
                  {"tab": "all", "rel": "ADDON_REPAY", "q": "이수취"}):
        body = client.get(TRIAGE_PATH, query_string=query).get_data(as_text=True)
        chips = _chip_links(body)
        sheet = _sheet(body)
        opts = re.findall(r'<a class="wb-hsheet__opt" href="([^"]+)"( aria-current="true")?>', sheet)
        assert len(chips) == 8 and len(opts) == 8, (query, chips, opts)
        assert [href for href, _ in opts] == [href for href, _ in chips], query
        assert [bool(cur) for _, cur in opts] == [p == "true" for _, p in chips], query
        groups = sheet.split('class="wb-hsheet__group"')[1:]
        assert [g.count('class="wb-hsheet__opt"') for g in groups] == [5, 3]
        assert "받은 뒤 단계" in groups[0] and "네이버에 남은 일" in groups[1]


def test_history_sheet_button_says_current_filter_and_count(client, workbench_on, monkeypatch):
    """버튼 = `상태: <켜진 것> <지금 목록 총계>` · 시트 여는 버튼의 aria 셋. 찾기 중에는 숫자를 비운다."""
    _empty_strips(monkeypatch)
    _seed_history()
    _login(client)

    def button(query):
        body = client.get(TRIAGE_PATH, query_string=query).get_data(as_text=True)
        tag = body[body.index('<button type="button" class="wb-hsheet-open"'):]
        return body, tag[:tag.index("</button>")]

    body, tag = button({"tab": "all"})
    for attr in ('id="wb-hsheet-open"', 'aria-haspopup="dialog"', 'aria-expanded="false"',
                 'aria-controls="wb-hsheet"'):
        assert attr in tag, attr
    assert '<span class="wb-hsheet-open__v">전체</span>' in tag
    assert '<b class="wb-hsheet-open__n">3</b>' in tag
    assert body.index('id="wb-hsheet-open"') < body.index('class="wb-filters"'), "칩 줄 앞(자리 계약)"
    dialog = _sheet(body)
    assert 'id="wb-hsheet"' in dialog and 'aria-labelledby="wb-hsheet-title"' in dialog
    assert 'aria-modal="true"' in dialog and 'id="wb-hsheet-title" tabindex="-1"' in dialog
    assert 'id="wb-hsheet-close" aria-label="닫기"' in dialog
    # 0 도 고를 수 있다 — 숫자가 0 인 줄도 링크로 남는다.
    assert re.search(r'확인 필요</span>\s*<span class="wb-hsheet__n">0</span>', dialog)

    _, tag = button({"tab": "all", "status": "COLLECTED", "place": "PENDING"})
    assert "받아옴 · 주문 전 + 발주확인 남음 · 취소 포함" in tag
    assert '<b class="wb-hsheet-open__n">1</b>' in tag

    _, tag = button({"tab": "all", "q": "이수취"})
    assert "wb-hsheet-open__n" not in tag, "찾기 중 총계를 '전체 N' 이라 말하면 거짓말"


def test_history_rows_carry_phone_card_parts(client, workbench_on, monkeypatch):
    """카드 셋째 줄 부품: 짧은 시각(`MM-DD HH:MM 받음`, 읽기 프로그램에서 숨김) ·
    주문이 없으면 `FOMS 주문 없음`. 카드를 누르면 여는 것은 그 행의 `원본 보기` 링크다."""
    _empty_strips(monkeypatch)
    _, _linked, order = _seed_history()
    _login(client)

    body = client.get(TRIAGE_PATH, query_string={"tab": "all"}).get_data(as_text=True)
    tbody = body.split('class="wb-cmp wb-hist"')[1].split("<tbody>")[1].split("</tbody>")[0]
    rows = ["<tr" + chunk for chunk in tbody.split("<tr")[1:] if "data-find=" in chunk.split(">")[0]]
    assert len(rows) == 3
    for row in rows:
        assert re.search(r'<span class="wb-hist__when" aria-hidden="true">\d\d-\d\d \d\d:\d\d 받음</span>',
                         row)
        assert 'class="wb-hist-detail"' in row
        assert 'style="' not in row
    with_order = [row for row in rows if f">#{order.id}</a>" in row]
    assert len(with_order) == 1 and "wb-hist__nofoms" not in with_order[0]
    assert sum("FOMS 주문 없음" in row for row in rows) == 2


def test_phone_css_turns_history_table_into_cards_and_keeps_desktop():
    """폰: 칩 → 버튼, 표 머리 숨김, 행 = 격자 카드, 카드 전체 = 원본 보기, 찾기 16px.
    데스크톱: 칩은 그대로, 폰 부품(버튼·짧은 시각·빈 꼴)은 숨는다."""
    phone, everywhere = _phone_css()

    assert ".wb-filters > .wb-chip { display: none; }" in phone
    assert "display: flex;" in _rule(phone, "    .wb-hsheet-open")
    assert "min-height: 44px;" in _rule(phone, "    .wb-hsheet-open")
    assert ".wb-hist thead { display: none; }" in phone
    card = _rule(phone, "    .wb-hist tbody tr[data-find]")
    assert "display: grid;" in card and "position: relative;" in card
    assert ".naver-workbench .wb-hist { display: block; min-width: 0; }" in phone, "표 최소 폭 720px 해제"
    overlay = _rule(phone, "    .wb-hist tbody tr[data-find] .wb-hist-detail::after")
    assert "position: absolute;" in overlay and "inset: 0;" in overlay
    assert "z-index: 1;" in _rule(phone, "    .wb-hist tbody tr[data-find] > td:nth-child(7) > a")
    assert "text-overflow: ellipsis;" in _rule(phone, "    .wb-hist tbody tr[data-find] > td:nth-child(3)")
    sheet = _rule(phone, "    .wb-hsheet")
    assert "max-height: 85vh;" in sheet and "border-radius: 16px 16px 0 0;" in sheet
    assert ".wb-hsheet::backdrop" in phone
    assert "min-height: 52px;" in _rule(phone, "    .wb-hsheet__opt")
    # 찾기 16px(아이폰 포커스 확대 방지) · 폭 전체.
    assert "font-size: calc(16px * var(--wb-fs, 1));" in phone.split("    .wb-find__input {")[1].split("}")[0]
    assert ".wb-filters .wb-find { flex: 1 1 100%; margin-left: 0; }" in phone
    # 데스크톱.
    assert ".wb-hsheet-open { display: none; }" in everywhere
    assert ".wb-hist__when,\n.wb-hist__nofoms { display: none; }" in everywhere
    assert ".wb-filters > .wb-chip" not in everywhere
    assert ".wb-hist { min-width: calc(720px * var(--wb-fs, 1)); }" in everywhere


def test_phone_js_opens_sheet_as_modal_and_returns_focus():
    """시트는 네이티브 모달 dialog — Esc 는 브라우저가, 바탕 누르기·닫기·포커스 돌려주기는 JS 가."""
    js = JS.read_text(encoding="utf-8").replace("\r\n", "\n")

    assert "'wb-hsheet-open': openHistSheet," in js
    assert "'wb-hsheet-close': closeHistSheet" in js
    opener = js.split("function openHistSheet(", 1)[1].split("\n    }\n", 1)[0]
    assert "sheet.showModal();" in opener and "button.setAttribute('aria-expanded', 'true');" in opener
    assert "document.addEventListener('close', onHistSheetClose, true);" in js
    closer = js.split("function onHistSheetClose(", 1)[1].split("\n    }\n", 1)[0]
    assert "setAttribute('aria-expanded', 'false')" in closer and "opener.focus(" in closer
    click = js.split("function onClick(", 1)[1][:600]
    assert "target.id === 'wb-hsheet'" in click, "바탕 누르기 = 닫기"


def test_phase12_markup_adds_no_inline_style():
    """폰 1·2단계로 더한 마크업(제목 상자·☰·시트·빈 목록·카드 부품)에 인라인 스타일이 없다."""
    markup = TEMPLATE.read_text(encoding="utf-8")
    regions = [
        markup[markup.index('<span class="wb-bar__titlebox">'):markup.index('<nav class="wb-tabs"')],
        markup[markup.index('<button type="button" class="wb-hsheet-open"'):
               markup.index('<div class="wb-filters">')],
        markup[markup.index('<div class="wb-empty wb-empty--done">'):
               markup.index('{% endfor %}', markup.index('wb-empty--done'))],
    ]
    for region in regions:
        assert 'style="' not in region, region[:80]
    assert 'class="wb-hist__when" aria-hidden="true"' in markup
