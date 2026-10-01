# -*- coding: utf-8 -*-
"""네이버 수집 워크벤치 폰 — 재감사(2026-09-29 · 스테이징 f325a418) 새 문제 R-02~R-13 · N-42 계약.

원장: docs/plans/2026-09-29-naver-mobile-ui-audit-ledger.md "## 재감사 (스테이징 f325a418 · 배포 7078e586)".
R-01(체크 칸 시작선)·R-12(메뉴 바탕 막 — 로컬 렌더에서는 이미 어둡다)·N-30(추가결제 상품 — 폐지된 상품)은 여기 없다.

음성 대조군: 각 시나리오 안에 둔다(네이버로 나가는 줄 · 누를 수 있는 줄 · 원본 창 닫기 · 데스크톱 등).
HEAD(P2, f325a4187) 코드로 돌리면 이 파일이 빨갛다.
"""

from __future__ import annotations

import re

from tests.services.integrations.test_naver_dock_width_live import _extract_function, _needs_node
from tests.services.integrations.test_naver_workbench import _collected
from tests.services.integrations.test_naver_workbench_mobile import TEMPLATE, TRIAGE_PATH, _empty_strips, _rule
from tests.services.integrations.test_naver_workbench_mobile_p0 import _run
from tests.services.integrations.test_naver_workbench_mobile_p1 import PANE, _css, _js, _node
from tests.services.integrations.test_naver_workbench_v3_contract import (  # noqa: F401
    _login,
    workbench_on,
)


def _fix() -> str:
    """폰 미디어 쿼리 안 '재감사 수정' 절."""
    phone, _ = _css()
    assert "══ 재감사 수정" in phone, "재감사 절이 폰 미디어 쿼리 안에 없다"
    return phone.split("══ 재감사 수정", 1)[1]


# --------------------------------------------------------------------------- #
# R-02 확인 시트 잠금 · R-04/R-05 더 할 일 시트 · R-10 그만두기
# --------------------------------------------------------------------------- #

@_needs_node
def test_ask_sheet_ignores_taps_for_a_full_second_but_other_sheets_keep_350ms():
    js = _js()
    assert "var ASK_ARM_MS = 1000;" in js and "var SHEET_ARM_MS = 350;" in js
    result = _run(("sheetArmed", "sheetTapTooSoon"), """
var t0 = Date.now();
function btnIn(id) { return {closest: function () { return {id: id}; }, matches: function () { return false; }}; }
sheetShownAt['wb-ask'] = t0; sheetShownAt['wb-more'] = t0;
Date.now = function () { return t0 + 600; };
var at600 = {ask: sheetTapTooSoon(btnIn('wb-ask')), more: sheetTapTooSoon(btnIn('wb-more'))};
Date.now = function () { return t0 + 1000; };
process.stdout.write(JSON.stringify({at600: at600, at1000: sheetTapTooSoon(btnIn('wb-ask')),
  armed: [sheetArmed(0 + 1, 999, 1000), sheetArmed(1, 1001, 1000), sheetArmed(1, 351)]}));""")
    # 0.6초 뒤 두 번째 누름: 확인 시트는 버리고(예전엔 90일 가져오기가 시작됐다), 더 할 일 시트는 받는다(대조군).
    assert result["at600"] == {"ask": True, "more": False}
    assert result["at1000"] is False
    assert result["armed"] == [False, True, True]


@_needs_node
def test_more_sheet_drops_the_repeated_first_clause_and_the_result_line_on_blocked_rows():
    result = _node(("buttonLabel", "moreItem", "moreWhy"), """
var NAVER_SEND_IDS = ['wb-confirm'];
var MORE_FX_SEND = 'S', MORE_FX_QUIET = 'Q';
function isDangerButton() { return false; }
function Node(tag) { this.tag = tag; this.children = []; this.attrs = {}; this.textContent = ''; this.className = '';
  this.classList = { add: function () {} }; }
Node.prototype.appendChild = function (c) { this.children.push(c); return c; };
Node.prototype.setAttribute = function (k, v) { this.attrs[k] = v; };
var document = { createElement: function (t) { return new Node(t); } };
function orig(id, why, disabled) {
  return { id: id, disabled: disabled, textContent: id,
           getAttribute: function (k) { return k === 'title' ? why : null; } };
}
var reread = moreItem(orig('wb-refresh', '네이버에 아무것도 보내지 않습니다(조회만) — 최신 상태를 다시 받아옵니다.', false), 0, {}).children[0];
var done = moreItem(orig('wb-review-done', '네이버에는 아무것도 보내지 않습니다 — 이 주문을 표시합니다.', false), 1, {}).children[0];
var send = moreItem(orig('wb-confirm', '네이버에는 아무것도 보내지 않습니다 — 거짓 문장', false), 2, {}).children[0];
var blocked = moreItem(orig('wb-confirm', '막힌 이유', true), 3, {}).children[0];
process.stdout.write(JSON.stringify({
  reread: reread.children.map(function (c) { return c.textContent; }),
  done: done.children[2].textContent, send: send.children[2].textContent,
  blocked: blocked.children.map(function (c) { return c.className; }), blockedDesc: blocked.attrs['aria-describedby']}));
""")
    assert result["reread"] == ["wb-refresh", "Q", "최신 상태를 다시 받아옵니다."]
    assert result["done"] == "이 주문을 표시합니다."
    # 대조군: 네이버로 나가는 줄은 이유를 자르지 않는다.
    assert result["send"] == "네이버에는 아무것도 보내지 않습니다 — 거짓 문장"
    # R-05: 막힌 줄에는 결과 줄(되돌릴 수 없음)이 없다 — 이름 + 이유만.
    assert result["blocked"] == ["wb-more__label", "wb-more__why"]
    assert result["blockedDesc"] == "wb-more-why-3"


def test_every_confirm_modal_and_ask_sheet_says_stop_the_same_way():
    pane = PANE.read_text(encoding="utf-8")
    page = TEMPLATE.read_text(encoding="utf-8")
    for markup in (pane, page):
        dismiss = re.findall(r'<button type="button" class="btn btn-outline-secondary" data-bs-dismiss="modal">([^<]+)</button>',
                             markup)
        assert dismiss and set(dismiss) == {"그만두기"}, dismiss
    for word in ("취소", "닫기", "그대로 두기"):
        assert f'data-bs-dismiss="modal">{word}</button>' not in pane, word
    assert "'그대로 두기'" not in _js() and "cancel: '그만두기'," in _extract_function(_js(), "askRunNow")
    # 대조군: 읽기 전용 원본 창은 보낼 것이 없어 `닫기` 그대로다.
    detail_modal = page.split('id="wb-modal-detail"')[1].split("</div>\n    </div>\n</div>")[0]
    assert 'data-bs-dismiss="modal">닫기</button>' in detail_modal


# --------------------------------------------------------------------------- #
# R-03 도면 쪽지 · R-07 원본 금액 · R-09 누름 자리 · R-11 시트 발바닥
# --------------------------------------------------------------------------- #

def test_drawing_notice_floats_above_the_bottom_bars_on_this_screen_only():
    fix = _fix()
    stack = _rule(fix, "    body:has(.naver-workbench) .foms-drawing-notices")
    assert "bottom: calc(88px + env(safe-area-inset-bottom, 0px));" in stack
    assert "left: 8px;" in stack and "max-width: none;" in stack
    assert "min-height: 44px;" in _rule(fix, "    body:has(.naver-workbench) .foms-drawing-notice__btn")
    _, everywhere = _css()
    assert "foms-drawing-notice" not in everywhere, "데스크톱·다른 화면의 쪽지 자리는 그대로(대조군)"


def test_history_original_amount_keeps_won_on_the_number_line():
    fix = _fix()
    cell = _rule(fix, "    #wb-detail-body .wb-cmp:has(thead .wb-cmp__num) tbody td:nth-child(4)")
    assert "display: flex;" in cell and "flex-wrap: wrap;" in cell and "justify-content: flex-end;" in cell
    assert "order: 1;" in _rule(fix, "    #wb-detail-body .wb-cmp:has(thead .wb-cmp__num) tbody td:nth-child(4)::after")
    lines = _rule(fix, "    #wb-detail-body .wb-cmp:has(thead .wb-cmp__num) tbody td:nth-child(4) > div")
    assert "order: 2;" in lines and "flex: 0 0 100%;" in lines


def test_small_targets_reach_44px_and_sheet_footer_shows_more_above():
    fix = _fix()
    ghost = _rule(fix, "    .wb-ghost__list td:first-child > a")
    assert "min-width: 44px;" in ghost and "min-height: 44px;" in ghost
    assert "min-width: 44px;" in _rule(fix, "    .wb-asheet .wb-ingest__edit")
    assert "min-height: 44px;" in _rule(fix, "    #wb-detail-body .wb-detail__links .btn")
    assert "min-height: 44px;" in _rule(fix, "    body:has(.naver-workbench) .navbar-toggler")
    assert "box-shadow: 0 -4px 12px -8px rgba(20, 23, 28, .3);" in _rule(fix, "    .wb-hsheet__foot")


# --------------------------------------------------------------------------- #
# R-08 이력 카드 셋째 줄 · R-13 이력 자리표시 · R-06/N-42 글꼴 · 핀
# --------------------------------------------------------------------------- #

def test_history_card_third_row_spans_the_card_and_drops_the_received_tail(client, workbench_on, monkeypatch):
    _empty_strips(monkeypatch)
    _login(client)
    _collected(order_no="N-RA-H1", product="이력 집", amount=100000, place_status="")
    body = client.get(TRIAGE_PATH, query_string={"tab": "all"}).get_data(as_text=True)
    assert re.search(r'<span class="wb-hist__when" aria-hidden="true">\d\d-\d\d \d\d:\d\d</span>', body)
    assert " 받음</span>" not in body
    assert '<span class="wb-dk">워크벤치</span><span class="wb-ph">처리 탭으로</span></a>' in body
    assert 'data-phone-placeholder="이름·주문번호·전화"' in body
    fix = _fix()
    row3 = _rule(fix, "    .wb-hist tbody tr[data-find] > td:nth-child(1),\n"
                      "    .wb-hist tbody tr[data-find] > td:nth-child(7),\n"
                      "    .wb-hist tbody tr[data-find] > td:nth-child(8)")
    assert "grid-column: 1 / -1;" in row3
    assert "margin-left: 10ch;" in _rule(fix, "    .wb-hist tbody tr[data-find] .wb-hist-open")
    # 대조군: 처리 탭 찾기 자리표시는 그대로.
    assert 'data-phone-placeholder="이름·주문번호·제품"' in TEMPLATE.read_text(encoding="utf-8")


def test_pretendard_is_loaded_for_phone_width_only_and_pins_moved():
    page = TEMPLATE.read_text(encoding="utf-8")
    styles = page.split("{% block styles %}")[1].split("{% endblock %}")[0]
    link = re.search(r'<link rel="stylesheet" media="([^"]+)" href="([^"]+pretendard[^"]+)"', styles)
    assert link, "폰 글꼴 시트가 없다"
    assert link.group(1) == "(max-width: 767.98px)"
    assert "pretendardvariable-dynamic-subset.min.css" in link.group(2)
    assert styles.index("pretendard") < styles.index("naver-workbench.css")
    assert page.count("?v=20261001b") == 2 and "?v=20260930c" not in page
