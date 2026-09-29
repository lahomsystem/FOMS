# -*- coding: utf-8 -*-
"""네이버 수집 워크벤치 폰 P2 나머지 — 처리 탭·상세 쪽(2026-09-30 · 감사 원장 N-03·N-11·N-12·N-15~N-23·
N-27~N-29·N-31~N-34·N-37·N-41~N-43) 계약. 이력 탭 쪽은 `_p2b`.

* 말 두 벌: 데스크톱 글자는 `wb-dk`, 폰 글자는 `wb-ph` 두 span 이다. 데스크톱은 `wb-ph` 만 숨긴다.
* 폰 규칙은 폰 미디어 쿼리 끝 'P2 나머지' 절에서 앞 단계 규칙을 **뒤에서 덮는다**(앞 단계 계약 글자는 그대로).

음성 대조군: 각 시나리오 안에 둔다(기본 정렬 · FOMS 주문이 붙은 집 · 데스크톱 · 폰이 아닐 때 등).
HEAD(P1, 00568f34c) 코드로 돌리면 이 파일이 빨갛다.
"""

from __future__ import annotations

import re

from foms.web.admin import naver_ingest
from tests.services.integrations.test_naver_dock_width_live import _extract_function, _needs_node
from tests.services.integrations.test_naver_workbench import _collected
from tests.services.integrations.test_naver_workbench_mobile import TEMPLATE, TRIAGE_PATH, _empty_strips, _rule
from tests.services.integrations.test_naver_workbench_mobile_p1 import _css, _js, _node
from tests.services.integrations.test_naver_workbench_mobile_phase34 import _seed_rows
from tests.services.integrations.test_naver_workbench_v3_contract import (  # noqa: F401
    _login,
    workbench_on,
)


def _p2() -> str:
    """폰 미디어 쿼리 안 'P2 나머지' 절."""
    phone, _ = _css()
    assert "══ P2 나머지" in phone, "P2 절이 폰 미디어 쿼리 안에 없다"
    return phone.split("══ P2 나머지", 1)[1]


def _work(client, monkeypatch, **qs) -> str:
    return client.get(TRIAGE_PATH, query_string={"tab": "work", **qs}).get_data(as_text=True)


# --------------------------------------------------------------------------- #
# 말 두 벌 · 토큰 · 글꼴 · 줄바꿈 (N-16 · N-19 · N-20 · N-27 · N-42)
# --------------------------------------------------------------------------- #

def test_phone_words_swap_by_class_and_desktop_hides_only_the_phone_words():
    _, everywhere = _css()
    p2 = _p2()
    assert ".wb-ph,\n.wb-reread,\n.wb-find__clear,\n.wb-cmp__nofoms { display: none; }" in everywhere
    assert ".wb-dk" not in everywhere, "데스크톱 글자는 데스크톱에서 늘 보인다"
    assert "    .naver-workbench .wb-dk { display: none; }" in p2
    assert "    .naver-workbench .wb-ph { display: revert; }" in p2


def test_phone_root_uses_one_accent_token_font_order_and_keep_all():
    root = _rule(_p2(), "    .naver-workbench")
    for decl in ("--wb-accent: #4a55b8;", "--wb-accent-soft: #f3f4ff;", "--wb-muted: #4b525d;",
                 "--bs-link-color: #4a55b8;", "word-break: keep-all;", "overflow-wrap: break-word;"):
        assert decl in root, decl
    assert re.search(r'font-family: "Pretendard Variable", Pretendard, -apple-system', root), "Pretendard 가 먼저"
    p2 = re.sub(r"/\*.*?\*/", "", _p2(), flags=re.S)   # 주석(옛 색 이름) 은 빼고 규칙만
    assert "#2563eb" not in p2 and "#0d6efd" not in p2
    sizes = {int(n) for n in re.findall(r"font-size: (?:max\(12px, )?calc\((\d+)px", p2)}
    assert sizes and min(sizes) >= 12, sizes
    radii = set(re.findall(r"border-radius: (\d+)px", p2))
    assert radii <= {"8", "12"}, radii
    assert "--wb-accent: #2563eb;" in _css()[1], "데스크톱 강조색은 그대로(대조군)"


# --------------------------------------------------------------------------- #
# N-03 다시 읽기 · N-15/N-17 머리 · N-18 정렬 · N-12/N-34 머리 숫자 · N-37 일괄 막대
# --------------------------------------------------------------------------- #

def test_phone_reread_is_a_worded_button_at_the_list_end(client, workbench_on, monkeypatch):
    _empty_strips(monkeypatch)
    monkeypatch.setattr(naver_ingest, "_refresh_all_view",
                        lambda db: {"count": 85, "skipped_done": 0, "skipped_recent": 0, "eta": "약 2분"})
    monkeypatch.setattr(naver_ingest, "_refresh_running_view", lambda db: {"running": False})
    _login(client)
    _collected(order_no="N-P2-RR", product="다시 읽을 집", amount=100000, place_status="")
    body = _work(client, monkeypatch)

    reread = body.split('<div class="wb-reread">')[1].split("</div>")[0]
    assert 'id="wb-refresh-all-phone"' in reread and "네이버에서 목록 전체 다시 읽기 · 85주문" in reread
    assert "약 2분 걸려요" in reread and "네이버에는 아무것도 보내지 않아요" in reread
    assert body.index('id="wb-queue"') < body.index('class="wb-reread"'), "목록 끝"
    assert 'id="wb-refresh-all"' in body, "원래 버튼(확인창·진행 한 벌)은 그대로"
    js = _js()
    assert "'wb-refresh-all-phone': function () { clickOriginal('wb-refresh-all'); }" in js
    assert "orig.click();" in _extract_function(js, "clickOriginal")
    assert "    .naver-workbench #wb-refresh-all:not(:disabled) { display: none; }" in _p2()
    # 음성 대조군: 원래 버튼이 없으면(0주문) 폰 줄도 없다.
    monkeypatch.setattr(naver_ingest, "_refresh_all_view",
                        lambda db: {"count": 0, "skipped_done": 0, "skipped_recent": 0, "eta": ""})
    assert 'class="wb-reread"' not in _work(client, monkeypatch)


def test_head_line_speaks_field_words_and_drops_the_fourth_number(client, workbench_on, monkeypatch):
    _empty_strips(monkeypatch)
    _login(client)
    _collected(order_no="N-P2-L", product="잠긴 집", amount=100000, place_status="", claim_status="CANCEL_DONE")
    body = _work(client, monkeypatch)
    locked = body.split('class="wb-bar__locked"')[1][:400]
    assert '<span class="wb-dk">처리 수에는 없고 목록에는 있음</span><span class="wb-ph">판매자센터에서 처리</span>' in locked
    assert "    .wb-bar--head .wb-bar__fact:not(.wb-bar__fact--quiet) { display: none; }" in _p2()
    # N-18: 폰 정렬 이름은 짧게(기한순) — 데스크톱 글자는 그대로.
    assert '<span class="wb-dk">발송기한 임박순</span><span class="wb-ph">기한순</span>' in body
    assert body.count(">접수순</a>") == 1


def test_list_head_count_and_pick_all_name_follow_the_visible_rows(client, workbench_on, monkeypatch):
    _empty_strips(monkeypatch)
    _login(client)
    _collected(order_no="N-P2-A", product="고를 집 가", amount=100000, place_status="")
    _collected(order_no="N-P2-B", product="고를 집 나", amount=100000, place_status="")
    _collected(order_no="N-P2-C", product="끝난 집", amount=100000, place_status="OK")
    body = _work(client, monkeypatch)
    assert '<span id="wb-visible">보이는 3줄</span>' in body
    label = body.split('wb-pickall')[1].split("</label>")[0]
    assert '<span class="wb-dk">전부 선택</span><span class="wb-ph"><span id="wb-pick-all-n">2</span>주문 모두 고르기</span>' in label
    assert "wb-pickall--none" not in label


@_needs_node
def test_sync_bulk_recounts_head_and_pick_all_from_visible_rows():
    """찾기로 숨긴 줄은 머리 수·`모두 고르기` 수에서 빠진다. 모두 고르기는 보이는 줄만 고른다(절대 규칙 5)."""
    result = _node(("visiblePickBoxes", "pickBoxes", "togglePickAll", "syncBulk", "setText"), """
var els = {};
function El() { this.textContent = ''; this.classList = { toggle: function () {} }; this.dataset = {}; }
['wb-bulk', 'wb-visible', 'wb-pick-all-n', 'wb-pick-all', 'wb-bulk-note', 'wb-bulk-submit'].forEach(function (id) { els[id] = new El(); });
var shown = [{checked: false, dataset: {count: '1'}}, {checked: false, dataset: {count: '2'}}];
var hidden = [{checked: false, dataset: {count: '9'}}];
var document = {
  getElementById: function (id) { return els[id] || null; },
  querySelectorAll: function (sel) {
    if (sel === '#wb-queue .wb-rowbox:not([hidden]) input.wb-pick:not([disabled])') { return shown; }
    if (sel === '#wb-queue input.wb-pick:not([disabled])') { return shown.concat(hidden); }
    if (sel === '#wb-queue a.wb-row:not([hidden])') { return [1, 2, 3]; }
    return [];
  }
};
togglePickAll(true);
process.stdout.write(JSON.stringify({visible: els['wb-visible'].textContent, n: els['wb-pick-all-n'].textContent,
  picked: shown.concat(hidden).map(function (b) { return b.checked; }), all: els['wb-pick-all'].checked}));
""")
    assert result == {"visible": "보이는 3줄", "n": "2", "picked": [True, True, False], "all": True}, result


def test_phone_bulk_bar_is_one_line_with_a_close_mark(client, workbench_on, monkeypatch):
    _empty_strips(monkeypatch)
    _login(client)
    _collected(order_no="N-P2-BK", product="고를 집", amount=100000, place_status="")
    bar = _work(client, monkeypatch).split('id="wb-bulk"')[1].split('<div class="wb-split">')[0]
    assert '<b id="wb-bulk-n">0</b>주문<span class="wb-dk"> 선택됨</span>' in bar
    assert 'aria-label="고른 것 모두 풀기"><span class="wb-dk">선택 해제</span><span class="wb-ph" aria-hidden="true">×</span>' in bar
    p2 = _p2()
    assert "    #wb-bulk.on { flex-wrap: nowrap; align-items: center; gap: 8px; }" in p2
    submit = _rule(p2, "    .naver-workbench #wb-bulk #wb-bulk-submit")
    assert "font-size: calc(16px" in submit and "min-height: 48px;" in submit


# --------------------------------------------------------------------------- #
# N-11 정렬·찾기 낱말을 상세 주소에
# --------------------------------------------------------------------------- #

def test_row_links_keep_the_sort_and_the_layer_says_it(client, workbench_on, monkeypatch):
    _empty_strips(monkeypatch)
    _login(client)
    link = _collected(order_no="N-P2-S", product="기한 집", amount=100000, place_status="")
    due = _work(client, monkeypatch, s="due")
    assert f"tab=work&amp;f=all&amp;s=due&amp;link_id={link.id}" in due
    assert '<span class="wb-layer__sort"> · 기한순</span>' in due
    # 음성 대조군: 기본 정렬(접수순)은 주소를 예전 그대로 둔다.
    new = _work(client, monkeypatch)
    assert f"tab=work&amp;f=all&amp;link_id={link.id}" in new and "wb-layer__sort" not in new


@_needs_node
def test_find_word_rides_on_the_detail_url_and_comes_back():
    result = _node(("findParamHref",), """
process.stdout.write(JSON.stringify([
  findParamHref('/admin/naver-ingest/triage?tab=work&f=all&s=due&link_id=3', ' 박 '),
  findParamHref('/admin/naver-ingest/triage?tab=work&q=%EB%B0%95&link_id=3', ''),
  findParamHref('http://h.test/a?tab=work', '김')]));
""")
    assert result == ["/admin/naver-ingest/triage?tab=work&f=all&s=due&link_id=3&q=%EB%B0%95",
                      "/admin/naver-ingest/triage?tab=work&link_id=3", "http://h.test/a?tab=work&q=%EA%B9%80"]
    js = _js()
    assert "var href = withFindParam(row.href);" in _extract_function(js, "onRowClick")
    assert "var href = withFindParam(row.href);" in _extract_function(js, "stepLayer")
    assert "isHistoryTab()" in _extract_function(js, "withFindParam"), "이력 탭(서버 찾기)은 건드리지 않는다"
    assert "restoreFindFromUrl();" in _extract_function(js, "init")


# --------------------------------------------------------------------------- #
# 상세: N-21 주문 단위 · N-22 막힌 이유 · N-41 이전/다음 · N-43 번호 · N-16 시트 이름
# --------------------------------------------------------------------------- #

def test_household_rows_without_foms_value_show_only_the_naver_value(client, workbench_on, monkeypatch):
    _empty_strips(monkeypatch)
    first, linked = _seed_rows()
    _login(client)
    new = _work(client, monkeypatch, link_id=first.id)
    table = new.split('data-cmp-section="household"')[1].split("</table>")[0]
    assert table.count('<tr class="wb-cmp__row--nofoms">') == 3
    assert "FOMS 주문이 아직 없어 네이버 값만 보여요." in table
    assert table.index("wb-cmp__nofoms") < table.index("<table"), "안내는 제목 안 — 표가 제목 바로 뒤여야 한다"
    # 음성 대조군: FOMS 주문이 붙은 집은 두 줄 비교 그대로.
    old = _work(client, monkeypatch, link_id=linked.id).split('data-cmp-section="household"')[1].split("</table>")[0]
    assert "wb-cmp__row--nofoms" not in old and "FOMS 주문이 아직 없어" not in old
    p2 = _p2()
    assert 'content: "네이버 값";' in p2 and 'content: "FOMS 값";' in p2
    assert "    #wb-pane .wb-seek--locked { display: none; }" in p2
    assert ('    #wb-pane [data-cmp-section="household"] + .wb-cmp tr.wb-cmp__row--nofoms td:nth-child(2)::before'
            in p2)


def test_locked_detail_folds_the_attach_box_and_numbers_move_down(client, workbench_on, monkeypatch):
    _empty_strips(monkeypatch)
    _login(client)
    lock = _collected(order_no="N-P2-LK", product="잠긴 집", amount=100000, place_status="",
                      claim_status="CANCEL_DONE")
    body = _work(client, monkeypatch, link_id=lock.id)
    assert '<div class="wb-seek wb-seek--locked">' in body
    assert '<span class="small text-muted wb-detail__no">상품주문 ' in body
    assert 'data-phone-label="확인 완료 — 할 일에서 빼기"' in body and "확인 완료 — 큐에서 빼기" in body
    assert 'data-phone-placeholder="이름·주문번호" enterkeyhint="search"' in body
    p2 = _p2()
    assert "    #wb-pane .wb-detail__no { order: 99; flex-basis: 100%; }" in p2
    assert "    .wb-layer__step { width: 52px; min-height: 52px; }" in p2
    assert "    .wb-layer__step-t { font-size: calc(12px * var(--wb-fs, 1)); }" in p2
    assert "background: #fef2f2;" in _rule(p2, "    #wb-pane .wb-acts__why--locked,\n"
                                               "    #wb-pane .wb-acts__why--locked ~ .wb-acts__why:not([hidden])")


@_needs_node
def test_more_sheet_says_a_blocked_reason_once_and_uses_the_phone_name():
    result = _node(("buttonLabel", "moreItem", "moreWhy"), """
var NAVER_SEND_IDS = ['wb-confirm', 'wb-dispatch'];
var MORE_FX_SEND = 'S', MORE_FX_QUIET = 'Q';
function isDangerButton() { return false; }
function Node(tag) { this.tag = tag; this.children = []; this.attrs = {}; this.textContent = ''; this.className = '';
  this.classList = { add: function () {} }; }
Node.prototype.appendChild = function (c) { this.children.push(c); return c; };
Node.prototype.setAttribute = function (k, v) { this.attrs[k] = v; };
var document = { createElement: function (t) { return new Node(t); } };
function orig(id, why, disabled, phone) {
  return { id: id, disabled: disabled, textContent: id + ' 글자',
           getAttribute: function (k) { return k === 'title' ? why : (k === 'data-phone-label' ? phone : null); } };
}
var seen = {};
var a = moreItem(orig('wb-confirm', '같은 이유', true, null), 0, seen).children[0];
var b = moreItem(orig('wb-dispatch', '같은 이유', true, null), 1, seen).children[0];
var c = moreItem(orig('wb-review-done', '안내', false, '확인 완료 — 할 일에서 빼기'), 2, seen).children[0];
process.stdout.write(JSON.stringify({a: a.children.length, b: b.children.length, bDesc: b.attrs['aria-describedby'],
  c: c.children[0].textContent}));
""")
    # 재감사 R-05(2026-09-29): 누를 수 없는 줄에는 결과 줄(fx)을 달지 않는다 — a 는 이름+이유, b 는 이름뿐.
    assert result == {"a": 2, "b": 1, "bDesc": "wb-more-why-0", "c": "확인 완료 — 할 일에서 빼기"}, result


# --------------------------------------------------------------------------- #
# N-23 메뉴 층 · N-28/N-29 누름 영역·모달 발바닥 · N-31 자리표시 · N-32 칩 끝 · N-33 색 막대
# --------------------------------------------------------------------------- #

def test_menu_opens_as_an_overlay_and_a_backdrop_tap_closes_it():
    p2 = _p2()
    head = _rule(p2, "    body:has(.naver-workbench):has(#navbarNav.show) .layout-header,\n"
                     "    body:has(.naver-workbench):has(#navbarNav.collapsing) .layout-header")
    nav = _rule(p2, "    body:has(.naver-workbench):has(#navbarNav.show) .layout-global-nav,\n"
                    "    body:has(.naver-workbench):has(#navbarNav.collapsing) .layout-global-nav")
    assert "position: fixed !important;" in head and "position: fixed !important;" in nav
    assert "top: var(--wb-menu-top, 60px);" in nav and "overflow-y: auto;" in nav
    assert "background: rgba(20, 23, 28, .55);" in _rule(p2, "    body:has(.naver-workbench):has(#navbarNav.show)::after")
    js = _js()
    assert "if (closeMenuFromBackdrop(target)) {" in _extract_function(js, "onClick")
    closer = _extract_function(js, "closeMenuFromBackdrop")
    assert "!isPhone()" in closer and "'.layout-header, .layout-global-nav, .dropdown-menu'" in closer
    assert "document.addEventListener('shown.bs.collapse', syncMenuTop);" in js


def test_targets_are_44px_and_long_modals_keep_their_footer():
    p2 = _p2()
    close = _rule(p2, "    .naver-workbench .modal .btn-close")
    assert "width: 16px;" in close and "padding: 14px;" in close, "16 + 14×2 = 44"
    assert "min-width: 72px; min-height: 48px;" in p2.split("#wb-pane #wb-seek-run {")[1].split("}")[0]
    assert "    body:has(.naver-workbench) #userDropdown { min-height: 44px; }" in p2
    foot = _rule(p2, "    .naver-workbench .modal-footer")
    assert "position: sticky;" in foot and "bottom: 0;" in foot and "background: #ffffff;" in foot


@_needs_node
def test_phone_placeholders_are_short_only_on_phone():
    scenario = """
var inputs = [{ p: '긴 자리표시', d: '이름·주문번호', getAttribute: function (k) { return k === 'data-phone-placeholder' ? this.d : this.p; },
                setAttribute: function (k, v) { this.p = v; } }];
var scope = { querySelectorAll: function () { return inputs; } };
function isPhone() { return %s; }
applyPhonePlaceholders(scope);
process.stdout.write(JSON.stringify(inputs[0].p));
"""
    assert _node(("applyPhonePlaceholders",), scenario % "true") == "이름·주문번호"
    assert _node(("applyPhonePlaceholders",), scenario % "false") == "긴 자리표시", "데스크톱은 그대로"
    markup = TEMPLATE.read_text(encoding="utf-8")
    assert 'data-phone-placeholder="이름·주문번호·제품"' in markup


@_needs_node
def test_chip_row_fades_until_scrolled_to_the_end():
    result = _node(("chipsAtEnd",), "process.stdout.write(JSON.stringify("
                                    "[chipsAtEnd(0, 366, 528), chipsAtEnd(161, 366, 528), chipsAtEnd(0, 366, 300)]));")
    assert result == [False, True, True]
    p2 = _p2()
    assert "mask-image: linear-gradient(to right, #000 calc(100% - 40px), transparent);" in _rule(
        p2, "    .wb-chips:not(.wb-chips--end)")
    assert "    .wb-row__bar { visibility: hidden; }" in p2, "N-33 색만으로 뜻을 전하지 않는다"
