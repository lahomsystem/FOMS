# -*- coding: utf-8 -*-
"""네이버 수집 워크벤치 폰 P0 안전(2026-09-30 · 감사 원장 N-01·N-02·N-13·N-44) 계약.

* N-01 — 더보기를 두 번 누르면 둘째 누름이 시트에 막 뜬 `확인 완료` 를 눌렀다(확인 없이 /review POST).
  시트 줄 순서(위 = 네이버에 안 보내는 일 → 아래 = 위험), 맨 아래 엄지 자리 = `닫기`, 시트가 열린 뒤
  350ms 조작 누름 무시, `확인 완료`·`다시 읽기` 는 주문 이름을 단 확인 시트를 거친다. 줄마다 결과 한 줄
  (네이버에 보냄/안 보냄). 되돌리기 토스트는 **만들지 않았다** — 확인 완료를 무르는 라우트가 없다.
* N-02 — `다음` 직후 `더보기` 는 이전 주문 시트였다. pane 을 불러오는 동안 주 버튼·더보기 aria-disabled,
  열린 시트는 닫고, 확인 시트는 그 주문이 그대로일 때만 누른다.
* N-13 — 폰 관리 시트의 `지금 수집`·`과거 긁어오기` 는 확인 시트를 거친다(데스크톱 카드는 그대로).
* N-44 — 시트 손잡이 줄을 누르면 바탕 누름으로 닫혔다(손잡이 margin 겹침 + `dialog` = 바탕 판정).

JS 는 IIFE 라 통째로 못 돌린다 — 함수를 뜯어 가짜 DOM 과 함께 Node 로 실제 실행한다(3·4단계와 같은 방식).
음성 대조군은 각 시나리오 안에 둔다(데스크톱 길 · 같은 주문 · 관리 확인 시트 · 350ms 경계 등).
"""

from __future__ import annotations

import json
import pathlib
import shutil
import subprocess
import tempfile

from tests.services.integrations.test_naver_dock_width_live import _extract_function, _needs_node
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
from tests.services.integrations.test_naver_workbench_mobile_phase34 import _patch_ingest, _seed_rows
from tests.services.integrations.test_naver_workbench_v3_contract import (  # noqa: F401
    _login,
    workbench_on,
)

NAVER_DIR = pathlib.Path(__file__).resolve().parents[3] / "foms" / "services" / "integrations" / "naver_commerce"


def _js() -> str:
    return JS.read_text(encoding="utf-8").replace("\r\n", "\n")


def _phone_css() -> str:
    return _media_block(CSS.read_text(encoding="utf-8").replace("\r\n", "\n"), PHONE_MEDIA)


def _run(names: tuple[str, ...], scenario: str) -> dict:
    """선언부(SHEETS … ASK_COPY) + 뜯어낸 함수 + 시나리오를 Node 로 돌려 stdout JSON 을 읽는다."""
    js = _js()
    head = js[js.index("    var SHEETS = {"):js.index("    document.addEventListener('click', onClick);")]
    script = "\n".join([head] + [_extract_function(js, name) for name in names] + [scenario])
    with tempfile.TemporaryDirectory(prefix="naver-wb-p0-") as tmp:
        path = pathlib.Path(tmp) / "p0.js"
        path.write_text(script, encoding="utf-8")
        proc = subprocess.run([shutil.which("node"), str(path)], capture_output=True, text=True,
                              encoding="utf-8", timeout=60)
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


#: 가짜 DOM 조각 — 속성·열림·close 만 흉내 낸다.
FAKE_DOM = """
var closed = [];
function El(id) { this.id = id; this.attrs = {}; this.open = false; this.textContent = ''; }
El.prototype.setAttribute = function (k, v) { this.attrs[k] = String(v); };
El.prototype.removeAttribute = function (k) { delete this.attrs[k]; };
El.prototype.getAttribute = function (k) { return this.attrs.hasOwnProperty(k) ? this.attrs[k] : null; };
El.prototype.hasAttribute = function (k) { return this.attrs.hasOwnProperty(k); };
El.prototype.close = function () { this.open = false; closed.push(this.id); };
var els = {};
['wb-layer', 'wb-layer-primary', 'wb-more-open', 'wb-more', 'wb-ask', 'wb-asheet',
 'wb-backfill-from', 'wb-backfill-to'].forEach(function (id) { els[id] = new El(id); });
var document = { getElementById: function (id) { return els[id] || null; } };
function out(value) { process.stdout.write(JSON.stringify(value)); }
"""


# --------------------------------------------------------------------------- #
# 마크업 — 닫기 줄 · 확인 시트
# --------------------------------------------------------------------------- #

def test_more_sheet_ends_with_close_row_and_ask_sheet_exists_once(client, workbench_on, monkeypatch):
    """더 할 일 시트의 맨 아래(목록 뒤)는 `닫기` 줄. 확인 시트는 문서에 한 벌, 버튼 글자는 JS 가 채운다."""
    _empty_strips(monkeypatch)
    _, linked = _seed_rows()
    _login(client)
    body = client.get(TRIAGE_PATH, query_string={"tab": "work", "link_id": linked.id}).get_data(as_text=True)

    sheet = body[body.index('<dialog class="wb-hsheet wb-more"'):]
    sheet = sheet[:sheet.index("</dialog>")]
    assert sheet.index('id="wb-more-list"') < sheet.index('class="wb-hsheet__foot"')
    assert '<button type="button" class="wb-hsheet__dismiss" id="wb-more-dismiss">닫기</button>' in sheet
    assert body.count('id="wb-ask"') == 1
    ask = body[body.index('<dialog class="wb-hsheet wb-ask"'):]
    ask = ask[:ask.index("</dialog>")]
    for mark in ('aria-labelledby="wb-ask-title"', 'aria-modal="true"', 'id="wb-ask-title" tabindex="-1"',
                 'id="wb-ask-who"', 'id="wb-ask-facts"', 'id="wb-ask-go"', 'id="wb-ask-cancel"'):
        assert mark in ask, mark
    # 엄지 자리(맨 아래)는 그만두기 — 확인 버튼은 그 위.
    assert ask.index('id="wb-ask-go"') < ask.index('id="wb-ask-cancel"')
    assert 'style="' not in sheet and 'style="' not in ask


def test_history_admin_sheet_also_gets_close_row_and_ask_sheet(client, workbench_on, monkeypatch):
    _empty_strips(monkeypatch)
    _patch_ingest(monkeypatch)
    _login(client)
    body = client.get(TRIAGE_PATH, query_string={"tab": "all"}).get_data(as_text=True)

    admin = body[body.index('<dialog class="wb-hsheet wb-asheet"'):]
    admin = admin[:admin.index("</dialog>")]
    assert admin.index('id="wb-asheet-slot"') < admin.index('id="wb-asheet-dismiss"')
    assert body.count('id="wb-ask"') == 1, "관리 시트도 같은 확인 시트를 쓴다"
    assert 'id="wb-run-now"' in body and 'id="wb-backfill-run"' in body, "데스크톱 카드 id 는 그대로"


# --------------------------------------------------------------------------- #
# N-01 — 순서 · 350ms · 확인 시트
# --------------------------------------------------------------------------- #

def test_js_wires_close_rows_ask_and_the_tap_guard():
    js = _js()
    for entry in ("'wb-more-dismiss': function () { closeSheet('wb-more'); }", "'wb-ask-go': runAsk",
                  "'wb-ask-cancel': function () { closeSheet('wb-ask'); }", "'wb-run-now': askRunNow",
                  "'wb-backfill-run': askBackfill", "var SHEET_ARM_MS = 350;"):
        assert entry in js, entry
    assert "sheetShownAt[id] = Date.now();" in _extract_function(js, "showSheet")
    click = _extract_function(js, "onClick")
    # 350ms 가드는 대리 버튼·ACTIONS 보다 먼저다(늦으면 이미 눌렸다).
    assert click.index("if (sheetTapTooSoon(btn)) {") < click.index("if (btn.hasAttribute('data-proxy-for')) {")
    assert click.index("if (sheetTapTooSoon(btn)) {") < click.index("ACTIONS[btn.id](btn);")
    # 확인 완료·다시 읽기의 처리 함수는 그대로 한 벌 — 확인 시트는 원래 버튼을 누를 뿐이다.
    assert "'wb-review-done': submitReviewDone," in js and "'wb-refresh': submitRefresh," in js
    assert "/undo" not in js and "unreview" not in js, "없는 라우트를 부르지 않는다(되돌리기 토스트 없음)"
    # 층이 걸어 두는 inert 에서 확인 시트는 뺀다(안 빼면 시트가 떠도 누를 수 없다).
    assert ".toast-container, .wb-ask')" in _extract_function(js, "setBackgroundInert")


@_needs_node
def test_more_sheet_order_puts_quiet_on_top_and_danger_last():
    """pane 순서(주문 만들기 … 다시 읽기 · 확인 완료)가 그대로면 `확인 완료` 가 엄지 바로 위였다(음성 대조군 = 입력 순서)."""
    result = _run(("moreOrder",), """
function it(id, disabled, danger) { return {id: id, disabled: !!disabled, danger: !!danger}; }
var pane = [it('wb-create'), it('wb-dispatch', true), it('wb-cancel', false, true), it('wb-refresh'),
            it('wb-review-done')];
process.stdout.write(JSON.stringify({
  order: moreOrder(pane),
  input: pane.map(function (x) { return x.id; }),
  sends: moreOrder([it('wb-review-done'), it('wb-confirm'), it('wb-return-reject', false, true)]),
  empty: moreOrder([])
}));""")
    assert result["input"][-1] == "wb-review-done", "대조군: 옛 순서는 확인 완료가 맨 아래"
    assert result["order"] == ["wb-create", "wb-refresh", "wb-review-done", "wb-dispatch", "wb-cancel"]
    assert result["sends"] == ["wb-review-done", "wb-confirm", "wb-return-reject"]
    assert result["empty"] == []


@_needs_node
def test_sheet_taps_are_ignored_for_350ms_but_close_always_works():
    result = _run(("sheetArmed", "sheetTapTooSoon"), """
var realNow = Date.now;
function btnIn(sheetId, isClose) {
  return {closest: function () { return sheetId ? {id: sheetId} : null; },
          matches: function () { return !!isClose; }};
}
var t0 = realNow();
sheetShownAt['wb-more'] = t0;
Date.now = function () { return t0 + 120; };
var early = {item: sheetTapTooSoon(btnIn('wb-more')), close: sheetTapTooSoon(btnIn('wb-more', true)),
             outside: sheetTapTooSoon(btnIn(null)), foreign: sheetTapTooSoon(btnIn('wb-hsheet'))};
Date.now = function () { return t0 + 350; };
var late = sheetTapTooSoon(btnIn('wb-more'));
process.stdout.write(JSON.stringify({early: early, late: late,
  b349: sheetArmed(1000, 1349), b350: sheetArmed(1000, 1350), never: sheetArmed(undefined, 5)}));""")
    assert result["early"] == {"item": True, "close": False, "outside": False, "foreign": False}
    assert result["late"] is False
    assert (result["b349"], result["b350"], result["never"]) == (False, True, True)


@_needs_node
def test_review_done_and_refresh_from_the_sheet_ask_first_other_items_do_not():
    """시트에서 누른 확인 완료·다시 읽기는 원래 버튼을 바로 누르지 않는다. 취소처리(모달 있음)는 예전 길(대조군)."""
    result = _run(("proxyClick", "askForPaneAction"), FAKE_DOM + """
var asked = [], clicks = [];
function openAsk(spec) { asked.push(spec); return true; }
function closeSheet(id) { closed.push(id); }
function syncLayer() {}
function paneLeadId() { return '42'; }
els['wb-layer-name'] = new El('wb-layer-name'); els['wb-layer-name'].textContent = '홍길동';
els['wb-layer-state'] = new El('wb-layer-state'); els['wb-layer-state'].textContent = '발주확인 할 차례';
var targets = {};
function target(id, toggle) {
  targets[id] = {id: id, disabled: false, getAttribute: function (k) { return k === 'data-bs-toggle' ? toggle : null; },
                 click: function () { clicks.push(id); }};
}
target('wb-review-done', null); target('wb-refresh', null); target('wb-cancel', 'modal');
function paneActionButton(id) { return targets[id] || null; }
function proxy(id, inSheet) {
  return {getAttribute: function (k) { return k === 'data-proxy-for' ? id : null; },
          closest: function () { return inSheet ? {} : null; }};
}
proxyClick(proxy('wb-review-done', true));
proxyClick(proxy('wb-refresh', true));
proxyClick(proxy('wb-cancel', true));
var direct = clicks.slice();
asked[0].run();
out({direct: direct, afterRun: clicks, who: asked[0].who, title: asked[0].title, link: asked[0].linkId,
     facts: asked[0].facts, back: asked[0].back && asked[0].back.id, n: asked.length, closed: closed,
     refresh: asked[1].facts});""")
    assert result["direct"] == ["wb-cancel"], "확인 완료·다시 읽기는 확인 시트를 먼저 연다"
    assert result["afterRun"] == ["wb-cancel", "wb-review-done"], "확인을 누르면 그때 원래 버튼을 누른다"
    assert result["n"] == 2 and result["closed"] == ["wb-more"] * 3
    assert result["who"] == "홍길동 주문 · 발주확인 할 차례" and result["link"] == "42"
    assert result["title"] == "확인 완료로 표시할까요?" and result["back"] == "wb-more-open"
    assert result["facts"][0] == "네이버에는 아무것도 보내지 않아요."
    assert "되돌릴 수 없어요" in result["facts"][-1], "무르는 라우트가 없다는 사실을 말한다"
    assert any("알림" in line for line in result["refresh"]), "다시 읽기는 알림이 나간다는 결과를 미리 말한다"


def test_ask_copy_matches_the_pane_titles():
    """확인 시트 문장의 근거 = 원래 버튼 title(네이버에 안 보냄 · 발주확인이 남으면 목록에 남음 · 알림)."""
    pane = (TEMPLATE.parent / "partials" / "naver_workbench_pane.html").read_text(encoding="utf-8")
    assert "네이버에는 아무것도 보내지 않습니다 — 이 주문을 &#39;확인함&#39;으로 표시합니다. 발주확인이 남아 있으면" in pane
    assert "네이버에 아무것도 보내지 않습니다(조회만)" in pane and "담당자·관리자에게 알림이 갑니다" in pane


def test_more_items_carry_a_one_line_consequence():
    js = _js()
    item = _extract_function(js, "moreItem")
    assert "fx.textContent = sends ? MORE_FX_SEND : MORE_FX_QUIET;" in item
    assert "btn.setAttribute('aria-describedby', fx.id);" in item and "innerHTML" not in item
    assert "var MORE_FX_SEND = '네이버로 보냄 · 되돌릴 수 없음';" in js
    assert "'wb-create'" not in js[js.index("var NAVER_SEND_IDS"):js.index("];", js.index("var NAVER_SEND_IDS"))], (
        "주문 만들기는 FOMS 안의 일이다")
    phone = _phone_css()
    assert "color: #b45309;" in _rule(phone, "    .wb-more__fx--send")


# --------------------------------------------------------------------------- #
# N-02 — pane 을 불러오는 동안 잠금
# --------------------------------------------------------------------------- #

def test_load_pane_locks_the_bar_until_its_own_response_lands():
    js = _js()
    load = _extract_function(js, "loadPane")
    assert load.index("setLayerBusy(true);") < load.index("await fetch(")
    finally_part = load[load.index("} finally {"):]
    assert "if (token === paneToken) {" in finally_part and "setLayerBusy(false);" in finally_part, (
        "늦게 온 응답은 새 선택의 잠금을 풀지 않는다")
    assert "fillMoreSheet();" in _extract_function(js, "swapPane")
    assert "if (proxy.getAttribute('aria-disabled') === 'true') {" in _extract_function(js, "proxyClick")
    phone = _phone_css()
    assert "cursor: progress;" in _rule(phone, "    .naver-workbench .wb-layer__primary[aria-disabled=\"true\"],\n"
                                              "    .wb-layer__more[aria-disabled=\"true\"]")


@_needs_node
def test_busy_bar_closes_sheets_and_refuses_to_open_more():
    result = _run(("setLayerBusy", "closeSheet", "openMoreSheet"), FAKE_DOM + """
var filled = 0, shown = 0;
function fillMoreSheet() { filled += 1; return true; }
function showSheet() { shown += 1; }
function onSheetClose() {}
els['wb-more'].open = true; els['wb-ask'].open = true;
askPending = {run: function () {}, linkId: '7'};
setLayerBusy(true);
var busy = {layer: els['wb-layer'].getAttribute('aria-busy'), primary: els['wb-layer-primary'].getAttribute('aria-disabled'),
            more: els['wb-more-open'].getAttribute('aria-disabled'), closed: closed.slice(), pending: askPending};
openMoreSheet();
var whileBusy = shown;
setLayerBusy(false);
var cleared = [els['wb-layer'].hasAttribute('aria-busy'), els['wb-more-open'].hasAttribute('aria-disabled')];
openMoreSheet();
// 대조군: 관리 확인 시트(주문 없음)는 pane 교체로 닫지 않는다.
closed = []; els['wb-ask'].open = true; askPending = {run: function () {}, linkId: ''};
setLayerBusy(true);
out({busy: busy, whileBusy: whileBusy, after: shown, filled: filled,
     cleared: cleared,
     adminKept: closed.indexOf('wb-ask') === -1 && !!askPending});""")
    assert result["busy"] == {"layer": "true", "primary": "true", "more": "true",
                              "closed": ["wb-more", "wb-ask"], "pending": None}
    assert result["whileBusy"] == 0 and result["after"] == 1 and result["filled"] == 1
    assert result["cleared"] == [False, False]
    assert result["adminKept"] is True


@_needs_node
def test_confirm_runs_only_while_the_same_order_is_open():
    """확인 시트를 연 뒤 다른 주문으로 넘어갔으면(N-02) `확인` 을 눌러도 나가지 않는다."""
    result = _run(("runAsk",), """
var lead = '5', ran = 0, closed = [];
function paneLeadId() { return lead; }
function closeSheet(id) { closed.push(id); }
askPending = {run: function () { ran += 1; }, linkId: '5'}; runAsk();
askPending = {run: function () { ran += 1; }, linkId: '5'}; lead = '6'; runAsk();
askPending = {run: function () { ran += 10; }, linkId: ''}; runAsk();
runAsk();
process.stdout.write(JSON.stringify({ran: ran, closed: closed.length, left: askPending}));""")
    assert result == {"ran": 11, "closed": 4, "left": None}


# --------------------------------------------------------------------------- #
# N-13 — 관리 시트 확인
# --------------------------------------------------------------------------- #

@_needs_node
def test_admin_card_buttons_ask_first_on_phone_and_pc():
    """확인 단계는 폰 관리 시트와 PC 카드 모두(PC 는 2026-09-29 사용자 결정 ③). 문장만 자리에 맞게 갈린다."""
    result = _run(("inAdminSheet", "askRunNow", "askBackfill", "rangeDays"), FAKE_DOM + """
var asked = [], runs = [], fills = [];
function openAsk(spec) { asked.push(spec); return true; }
function submitRunNow() { runs.push('run'); }
function submitBackfill() { fills.push('fill'); }
var since = {textContent: '9월 29일 08:25:57 뒤에 들어온 주문을 바로 받아와요.'};
function btn(inSheet) {
  return {closest: function (sel) {
    if (sel === '#wb-asheet') { return inSheet ? {} : null; }
    return {querySelector: function () { return since; }};
  }};
}
askRunNow(btn(false));
askRunNow(btn(true));
var runsBefore = runs.length;
asked[0].run();
els['wb-backfill-from'].value = '2026-07-01'; els['wb-backfill-to'].value = '2026-09-28';
askBackfill(btn(false));
askBackfill(btn(true));
var fillsBefore = fills.length;
els['wb-backfill-from'].value = '';
askBackfill(btn(true));
out({runsBefore: runsBefore, runsAfter: runs.length, runDesk: asked[0], runPhone: asked[1],
     fillDesk: asked[2], fillPhone: asked[3], fillsBefore: fillsBefore, fillEmpty: fills.length, n: asked.length,
     days: [rangeDays('2026-07-01', '2026-09-28'), rangeDays('2026-09-28', '2026-09-28'),
            rangeDays('2026-09-28', '2026-07-01'), rangeDays('', '2026-09-28')]});""")
    assert result["runsBefore"] == 0, "PC·폰 모두 묻기만 — 확인 전 POST 0건"
    assert result["runsAfter"] == 1
    assert result["fillsBefore"] == 0
    assert result["fillEmpty"] == 1 and result["n"] == 4, "빈 날짜는 묻지 않고 기존 안내로 간다"
    for spec in (result["runDesk"], result["runPhone"]):
        assert spec["title"] == "지금 새 주문을 받아올까요?"
        assert spec["who"].endswith("뒤에 들어온 주문을 바로 받아와요.")
    assert "끝나면 버튼 아래 줄에 결과가 보여요." in result["runDesk"]["facts"]
    assert "시트를 닫아도 계속 받아요. 끝나면 이 시트에 결과가 보여요." in result["runPhone"]["facts"]
    for spec in (result["fillDesk"], result["fillPhone"]):
        assert spec["title"] == "과거 주문 90일치를 가져올까요?"
        assert spec["who"] == "2026-07-01 ~ 2026-09-28 · 90일" and spec["go"] == "90일치 가져오기"
    assert "하루씩 훑어서 몇 분 걸려요. 진행은 버튼 아래 줄에 보여요." in result["fillDesk"]["facts"]
    assert "하루씩 훑어서 몇 분 걸려요. 시트를 닫아도 계속돼요." in result["fillPhone"]["facts"]
    assert result["days"] == [90, 1, 0, 0]
    for spec in (result["runDesk"], result["runPhone"], result["fillDesk"], result["fillPhone"]):
        assert "네이버에는 아무것도 보내지 않아요." in spec["facts"] and spec["cancel"] == "그만두기"


def test_nothing_is_sent_to_naver_by_the_sweep_or_the_backfill():
    """확인 시트의 '네이버에는 아무것도 보내지 않아요' 근거 — 스윕·백필·클레임 재읽기에 쓰기 호출이 없다."""
    client = (NAVER_DIR / "client.py").read_text(encoding="utf-8")
    writers = ("confirm_place_orders", "dispatch_product_orders", "request_cancel_product_order",
               "approve_cancel_product_order", "request_return_product_order", "approve_return_product_order",
               "reject_return_product_order")
    for writer in writers:
        assert f"    def {writer}(" in client, writer   # 대조군: 쓰기 메서드 이름이 실제로 이것이다
    for name in ("ingest.py", "backfill.py", "claim_watch.py"):
        source = (NAVER_DIR / name).read_text(encoding="utf-8")
        for writer in writers:
            assert f".{writer}(" not in source, (name, writer)
    assert ".get_product_orders(" in (NAVER_DIR / "ingest.py").read_text(encoding="utf-8"), "읽기 호출은 있다"


# --------------------------------------------------------------------------- #
# N-44 — 손잡이 줄은 바탕이 아니다
# --------------------------------------------------------------------------- #

def test_grip_space_is_padding_inside_the_inner_box():
    phone = _phone_css()
    assert "    .wb-hsheet__in { padding: 8px 0 calc(12px + env(safe-area-inset-bottom, 0px)); }" in phone
    grip = _rule(phone, "    .wb-hsheet__grip")
    assert "margin: 0 auto 4px;" in grip and "margin: 8px" not in grip
    foot = _rule(phone, "    .wb-hsheet__foot")
    assert "position: sticky;" in foot and "bottom: 0;" in foot
    assert "min-height: 52px;" in _rule(phone, "    .wb-hsheet__dismiss")
    everywhere = _outside_media(CSS.read_text(encoding="utf-8").replace("\r\n", "\n"))
    for phone_only in (".wb-hsheet__foot", ".wb-ask", ".wb-more__fx"):
        assert phone_only not in everywhere, phone_only


def test_backdrop_close_is_decided_by_coordinates():
    click = _extract_function(_js(), "onClick")
    head = click[:click.index("var box = target.closest('input.wb-pick');")]
    assert "backdropHit(target.getBoundingClientRect(), event.clientX, event.clientY)" in head
    assert head.index("backdropHit(") < head.index("closeHistSheet();") < head.index("closeSheet(target.id);")


@_needs_node
def test_backdrop_hit_is_outside_the_sheet_rect_only():
    result = _run(("backdropHit",), """
var sheet = {left: 0, top: 388, right: 390, bottom: 844};
process.stdout.write(JSON.stringify({grip: backdropHit(sheet, 195, 392), edge: backdropHit(sheet, 0, 388),
  above: backdropHit(sheet, 195, 200), side: backdropHit(sheet, 400, 500)}));""")
    assert result == {"grip": False, "edge": False, "above": True, "side": True}
