# -*- coding: utf-8 -*-
"""네이버 수집 워크벤치 폰 P1 과업(2026-09-30 · 감사 원장 N-04~N-10·N-14·N-35·N-36) 계약.

* N-05 — 상세 상품주문 표(680px)가 폰에서 절반만 보였다 → 같은 표를 CSS 로 상품 카드로 편다. 16자리 번호는
  `<details class="wb-mno">` 로 접는다(서버는 펼친 채 주고 JS 가 폰에서만 접는다 — 데스크톱은 여닫는 줄을 숨긴다).
* N-04 · N-35 — 경고 띠 표(640px)의 할 일 버튼이 화면 밖이었다 → 폰에서 주문마다 카드 · 버튼 44px · 접기 한 번.
  띠 버튼의 같은 id 5번 중복 → 클래스 + data-order-id.
* N-06 — 머리가 하나도 고정되지 않았다 → 폰에서 탭 줄 + 도구줄 sticky(목록 채우기는 그대로).
* N-07 · N-36 — 체크박스가 줄 링크 안에 있었고 93% 줄에 흐린 체크박스 → 링크 밖 형제 label, 폰은 고를 수 있는
  줄에만 52px 칸. 데스크톱은 같은 자리에 같은 모양(잠긴 칸은 누름을 줄에 넘긴다).
* N-08 — 파란 채움 `주문 만들기` 배지 → 모든 폭에서 옅은 바탕 라벨.
* N-09 · N-10 — 잠긴 줄 opacity .62(2.40:1) · `미등록` #ffc107(1.63:1) → 토큰 색으로 4.5:1 이상(폰).
* N-14 — 이력 카드에서 네이버 진행 단계를 0×0 으로 숨겼다 → 둘째 줄로 되살리고 같은 배지 셋은 접는다.

음성 대조군: 각 시나리오 안에 둔다(잠긴 줄 · 데스크톱 길 · 폰이 아닐 때 등). HEAD 코드로 돌리면 이 파일이 빨갛다.
"""

from __future__ import annotations

import json
import pathlib
import re
import shutil
import subprocess
import tempfile

from foms.web.admin import naver_ingest
from tests.services.integrations.test_naver_dock_width_live import _extract_function, _needs_node
from tests.services.integrations.test_naver_workbench import _collected
from tests.services.integrations.test_naver_workbench_mobile import (
    CSS,
    JS,
    PHONE_MEDIA,
    TEMPLATE,
    TRIAGE_PATH,
    _contrast,
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

PANE = pathlib.Path(TEMPLATE).parent / "partials" / "naver_workbench_pane.html"


def _css() -> tuple[str, str]:
    """(폰 미디어 블록, 미디어 쿼리 밖 규칙)."""
    css = CSS.read_text(encoding="utf-8").replace("\r\n", "\n")
    return _media_block(css, PHONE_MEDIA), _outside_media(css)


def _js() -> str:
    return JS.read_text(encoding="utf-8").replace("\r\n", "\n")


def _node(names: tuple[str, ...], scenario: str) -> dict:
    """뜯어낸 함수 + 시나리오를 Node 로 돌려 stdout JSON 을 읽는다."""
    js = _js()
    script = "\n".join([_extract_function(js, name) for name in names] + [scenario])
    with tempfile.TemporaryDirectory(prefix="naver-wb-p1-") as tmp:
        path = pathlib.Path(tmp) / "p1.js"
        path.write_text(script, encoding="utf-8")
        proc = subprocess.run([shutil.which("node"), str(path)], capture_output=True, text=True,
                              encoding="utf-8", timeout=60)
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


def _hex_pair(body: str) -> tuple[str, str]:
    """규칙 본문의 (글자색, 바탕색) — `!important` 가 붙어 있어도 읽는다."""
    fg = re.search(r"(?<![-\w])color:\s*(#[0-9a-fA-F]{6})", body)
    bg = re.search(r"background(?:-color)?:\s*(#[0-9a-fA-F]{6})", body)
    assert fg and bg, body
    return fg.group(1), bg.group(1)


def _rowboxes(body: str) -> list[str]:
    """목록 줄 상자(체크 label + 줄 링크)들 — 줄 링크 끝(`</a>`)까지."""
    return [('<div class="wb-rowbox' + chunk).split("</a>")[0]
            for chunk in body.split('<div class="wb-rowbox')[1:]]


# --------------------------------------------------------------------------- #
# N-07 · N-36 체크 칸
# --------------------------------------------------------------------------- #

def test_checkbox_is_a_sibling_of_the_row_link_not_inside_it(client, workbench_on, monkeypatch):
    """체크박스는 줄 링크 밖 형제 label 안이다. 고를 수 있는 줄 = `--pick`, 잠긴 줄 = `--off`(disabled 그대로)."""
    _empty_strips(monkeypatch)
    _login(client)
    _collected(order_no="N-P1-OPEN", product="고를 집", amount=100000, place_status="")
    _collected(order_no="N-P1-LOCK", product="잠긴 집", amount=100000, place_status="",
               claim_status="CANCEL_DONE", address="부산 1", tel="010-4444-0001")

    body = client.get(TRIAGE_PATH, query_string={"tab": "work"}).get_data(as_text=True)

    boxes = _rowboxes(body)
    assert len(boxes) == body.count('<a class="wb-row') == 2
    for box in boxes:
        link = box[box.index('<a class="wb-row'):]
        assert 'class="wb-pick"' not in link, "체크박스가 줄 링크 안에 있다(N-36)"
        assert box.index('class="wb-pick"') < box.index('<a class="wb-row'), "label 이 링크 앞 형제가 아니다"
        assert 'class="wb-row__pickslot" aria-hidden="true"' in link
    open_box = next(box for box in boxes if "고를 집" in box)
    lock_box = next(box for box in boxes if "잠긴 집" in box)
    assert open_box.startswith('<div class="wb-rowbox wb-rowbox--pick">')
    assert '<label class="wb-pickbox">' in open_box and "disabled" not in open_box.split("<a ")[0]
    # 음성 대조군: 잠긴 줄은 --pick 이 아니고, 체크박스는 disabled + 칸이 누름을 줄에 넘긴다.
    assert lock_box.startswith('<div class="wb-rowbox">')
    assert '<label class="wb-pickbox wb-pickbox--off">' in lock_box and "disabled" in lock_box
    assert 'style="' not in "".join(boxes)


def test_phone_draws_the_check_cell_only_on_pickable_rows_and_desktop_keeps_its_place():
    phone, everywhere = _css()

    # 폰: 체크 칸은 기본 숨김, 고를 수 있는 줄에서만 줄 높이 전체 · 44px 이상.
    assert "    .wb-pickbox { display: none; }" in phone
    cell = _rule(phone, "    .wb-rowbox--pick > .wb-pickbox")
    assert "display: flex;" in cell and "top: 0;" in cell and "bottom: 1px;" in cell
    assert int(re.search(r"width: (\d+)px;", cell).group(1)) >= 44
    assert "grid-template-columns: 5px 52px minmax(0, 1fr);" in _rule(phone, "    .wb-rowbox--pick > .wb-row")
    # 데스크톱: 예전 자리(색띠 5 + 틈 10 · 윗 여백 12) · 잠긴 칸은 누름을 줄에 넘긴다 · 찾기 숨김은 상자째.
    pick = _rule(everywhere, ".wb-pickbox")
    assert "position: absolute;" in pick and "top: 12px;" in pick and "left: 15px;" in pick
    assert ".wb-pickbox--off { pointer-events: none; }" in everywhere
    assert ".wb-row__pickslot { width: 15px; }" in everywhere
    assert ".wb-rowbox[hidden] { display: none; }" in everywhere
    assert ".wb-pick:disabled { pointer-events: none; }" in everywhere


@_needs_node
def test_find_hides_the_whole_row_box_and_unchecks_hidden_picks():
    """찾기는 줄 링크와 줄 상자를 함께 숨긴다 — 체크 칸만 떠 있지 않다. 숨은 상자의 체크는 풀린다."""
    result = _node(("applyFind", "clearHiddenPicks"), """
function Box(find, checked) {
    this.hidden = false; this.classList = { contains: function (c) { return c === 'wb-rowbox'; } };
    this.row = { hidden: false, parentNode: this, getAttribute: function () { return find; } };
    this.box = { checked: checked };
}
var boxes = [new Box('김하늘 n-1', true), new Box('박도윤 n-2', true)];
var note = { textContent: '' };
var document = {
    querySelectorAll: function (sel) {
        if (sel.indexOf('#wb-queue a.wb-row') === 0) { return boxes.map(function (b) { return b.row; }); }
        if (sel === '#wb-queue .wb-rowbox[hidden] input.wb-pick:checked') {
            return boxes.filter(function (b) { return b.hidden && b.box.checked; }).map(function (b) { return b.box; });
        }
        return [];
    },
    getElementById: function (id) { return id === 'wb-find-note' ? note : null; }
};
function syncBulk() {}
applyFind('박도윤');
process.stdout.write(JSON.stringify({
    rows: boxes.map(function (b) { return [b.row.hidden, b.hidden, b.box.checked]; }), note: note.textContent }));
""")
    assert result["rows"] == [[True, True, False], [False, False, True]], result
    assert result["note"] == "1주문 / 2주문"


# --------------------------------------------------------------------------- #
# N-08 · N-09 · N-10 대비
# --------------------------------------------------------------------------- #

def test_create_order_badge_is_a_soft_label_on_every_width():
    _, everywhere = _css()
    rule = _rule(everywhere, ".naver-workbench .wb-row__line3 .badge.bg-primary")
    fg, bg = _hex_pair(rule)
    assert (fg, bg) == ("#4a55b8", "#f3f4ff"), "채움 파랑이 아니라 옅은 바탕 라벨"
    assert _contrast(fg, bg) >= 4.5


def test_locked_rows_drop_opacity_and_meet_aa_on_phone():
    phone, everywhere = _css()
    assert "opacity: .62" in _rule(everywhere, ".wb-row--locked .wb-row__body"), "데스크톱은 그대로(대조군)"
    assert "{ opacity: 1; }" in phone.split("    .wb-row--locked .wb-row__body")[-1][:20]
    row_bg = re.search(r"#[0-9a-f]{6}", _rule(phone, "    .wb-row--stop,\n    .wb-row--locked")).group(0)
    text = _rule(phone, "    .wb-row--locked .wb-row__when")
    assert _contrast(re.search(r"#[0-9a-f]{6}", text).group(0), row_bg) >= 4.5
    for badge in ("bg-danger", "bg-secondary"):
        fg, bg = _hex_pair(_rule(phone, f"    .naver-workbench .wb-row__line3 .badge.{badge}"))
        assert _contrast(fg, bg) >= 4.5, badge


def test_unset_expiry_is_readable_in_the_admin_sheet(client, workbench_on, monkeypatch):
    _empty_strips(monkeypatch)
    _patch_ingest(monkeypatch, expires_on=None, days_left=None)
    _login(client)
    body = client.get(TRIAGE_PATH, query_string={"tab": "all"}).get_data(as_text=True)
    assert '<div class="wb-ingest__v text-warning wb-expiry-unset">미등록</div>' in body

    phone, _ = _css()
    fg, bg = _hex_pair(_rule(phone, "    .wb-asheet .wb-expiry-unset"))
    assert (fg, bg) == ("#b45309", "#fffbeb") and _contrast(fg, bg) >= 4.5


# --------------------------------------------------------------------------- #
# N-04 · N-35 경고 띠
# --------------------------------------------------------------------------- #

def _ghost_row(order_id: int) -> dict:
    return {"order_id": order_id, "customer_name": f"고객{order_id}", "naver_amount_total": 100000,
            "claim_phase": "done", "claim_text": "취소 완료", "naver_link_count": 2, "status_label": "주문접수",
            "measure": {"code": "none", "text": "실측일 없음", "basis_text": ""}, "can_discard": True,
            "discard_block": "", "repay_candidates": [], "repay_expected": None, "discard_needs_reason": False,
            "lead_link_id": 1}


def test_ghost_band_buttons_use_classes_not_repeated_ids(client, workbench_on, monkeypatch):
    _empty_strips(monkeypatch)
    rows = [_ghost_row(4477), _ghost_row(4478), _ghost_row(4479)]
    monkeypatch.setattr(naver_ingest, "_ghost_view", lambda db: {"count": len(rows), "rows": rows})
    _login(client)
    body = client.get(TRIAGE_PATH, query_string={"tab": "work"}).get_data(as_text=True)

    ids = re.findall(r'\sid="(wb-[^"]+)"', body)
    assert sorted({i for i in ids if ids.count(i) > 1}) == [], "문서 안 중복 id"
    for order_id in (4477, 4478, 4479):
        row = body.split(f'data-ghost-order-id="{order_id}"')[1].split("</tr>")[0]
        assert 'class="btn btn-sm btn-outline-danger wb-ghost-discard"' in row
        assert 'class="btn btn-sm btn-outline-secondary wb-ghost-repay-expected"' in row
        assert f'data-order-id="{order_id}"' in row
        assert '<td data-label="재결제 연결">' in row
    click = _extract_function(_js(), "onClick")
    for cls, handler in (("wb-ghost-discard", "submitGhostDiscard"),
                         ("wb-ghost-repay-expected", "submitGhostRepayExpected")):
        assert f"if (btn.classList.contains('{cls}')) {{\n                {handler}(btn);" in click, cls


def test_phone_alert_tables_become_cards_with_half_width_44px_buttons():
    phone, _ = _css()
    assert "min-width: 640px" not in phone and "min-width: 820px" not in phone, "가로 스크롤 표로 되돌아갔다"
    assert "display: block; min-width: 0;" in _rule(phone, "    .wb-scroll > .wb-ghost__list,\n    .wb-scroll > .wb-result__list")
    assert ".wb-ghost__list thead { display: none; }" in phone
    acts = _rule(phone, "    .wb-ghost__list td:last-child,\n    .wb-result__list td:last-child")
    assert "display: flex;" in acts and "flex-wrap: wrap;" in acts
    button = _rule(phone, "    .wb-ghost__list td:last-child > .btn,\n    .wb-result__list td:last-child > .btn")
    assert "min-height: 44px;" in button and "min-width: calc(50% - 4px);" in button


@_needs_node
def test_opening_the_summary_opens_every_strip_once():
    """요약 띠를 펼치면 안의 띠(<details>)도 펴진다 — 접기는 한 번. 접을 때는 건드리지 않는다(대조군)."""
    result = _node(("toggleAlerts", "openAlertStrips"), """
var strips = [{ open: false }, { open: false }];
var body = { querySelectorAll: function (sel) { return sel === 'details.wb-ghost' ? strips : []; } };
var document = { getElementById: function (id) { return id === 'wb-alerts-body' ? body : null; } };
var btn = { v: 'false', getAttribute: function () { return this.v; }, setAttribute: function (k, v) { this.v = v; } };
toggleAlerts(btn);
var afterOpen = strips.map(function (s) { return s.open; });
strips[0].open = false;
toggleAlerts(btn);
process.stdout.write(JSON.stringify({ afterOpen: afterOpen, afterClose: strips.map(function (s) { return s.open; }),
                                      expanded: btn.v }));
""")
    assert result == {"afterOpen": [True, True], "afterClose": [False, True], "expanded": "false"}, result
    assert "openAlertStrips();" in _extract_function(_js(), "applyAlertsOpen")


# --------------------------------------------------------------------------- #
# N-05 상품 카드
# --------------------------------------------------------------------------- #

def test_pane_member_rows_carry_a_foldable_number_and_phone_units(client, workbench_on, monkeypatch):
    _empty_strips(monkeypatch)
    first, _ = _seed_rows()
    _login(client)
    body = client.get(TRIAGE_PATH, query_string={"tab": "work", "link_id": first.id}).get_data(as_text=True)

    table = body.split('class="wb-cmp wb-cmp--members"')[1].split("</table>")[0]
    assert '<details class="wb-mno" open>' in table, "서버는 펼친 채 준다(JS 가 없으면 번호를 잃지 않는다)"
    mno = table.split('<details class="wb-mno" open>')[1].split("</details>")[0]
    assert f'<span class="wb-mno__v">{first.external_id}</span>' in mno
    assert "상품주문번호 보기" in mno and "번호 접기" in mno
    assert '1,284,000<span class="wb-won">원</span>' in table
    assert table.count('<span class="wb-won">원</span>') == 2, "줄 금액 + 합계"
    assert 'style="' not in table


def test_phone_turns_the_member_table_into_cards_and_desktop_hides_phone_parts():
    phone, everywhere = _css()
    assert "#wb-pane .wb-cmp--members { display: block; min-width: 0; }" in phone
    assert ".wb-cmp--members { min-width: calc(680px * var(--wb-fs, 1)); }" in everywhere, "데스크톱 표 폭은 그대로"
    card = _rule(phone, "    #wb-pane .wb-cmp--members tr")
    assert "display: grid;" in card and "minmax(0, 1fr)" in card
    assert "grid-column: 4;" in _rule(phone, "    #wb-pane .wb-cmp--members tbody td:nth-child(5)"), "금액은 제품 오른쪽"
    assert "white-space: normal !important;" in _rule(phone, "    #wb-pane .wb-cmp--members tbody td:nth-child(3)")
    assert "min-height: 44px;" in _rule(phone, "    #wb-pane .wb-mno__sum")
    assert ".wb-mno__sum,\n.wb-won { display: none; }" in everywhere


@_needs_node
def test_member_numbers_fold_only_on_phone():
    scenario = """
var items = [{ open: true }, { open: true }];
var pane = { querySelectorAll: function (sel) { return sel === 'details.wb-mno[open]' ? items : []; } };
var PHONE = %s;
function isPhone() { return PHONE; }
foldMemberNos(pane);
foldMemberNos({});
process.stdout.write(JSON.stringify(items.map(function (i) { return i.open; })));
"""
    assert _node(("foldMemberNos",), scenario % "true") == [False, False]
    assert _node(("foldMemberNos",), scenario % "false") == [True, True], "데스크톱은 펼친 채"
    js = _js()
    assert "foldMemberNos(next);" in _extract_function(js, "swapPane")
    assert "foldMemberNos(document);" in _extract_function(js, "init")


# --------------------------------------------------------------------------- #
# N-06 머리 고정
# --------------------------------------------------------------------------- #

def test_phone_keeps_tabs_and_tools_stuck_while_scrolling():
    phone, everywhere = _css()
    head = phone.split("    .naver-workbench .wb-bar--head {")[-1].split("}")[0]
    assert "position: sticky;" in head and "top: var(--wb-head-stick, 0px);" in head
    tools = phone.split("    .naver-workbench .wb-bar--tools {")[1].split("}")[0]
    assert "position: sticky;" in tools and "top: var(--wb-tools-top, 0px);" in tools
    assert "order: 7;" in phone.split("    .wb-tabs {")[-1].split("}")[0], "탭이 머리줄 맨 아래 줄"
    assert "--wb-head-stick" not in everywhere and "--wb-tools-top" not in everywhere, "데스크톱은 그대로"


@_needs_node
def test_sticky_offsets_are_measured_from_the_tab_row():
    """머리줄 top = -(탭 위 높이 - 4), 도구줄 top = 머리줄 높이 - 그 값. 폰이 아니면 두 변수를 지운다(대조군)."""
    scenario = """
var props = {};
var tabs = { getBoundingClientRect: function () { return { top: 150 }; } };
var head = { querySelector: function () { return tabs; },
             getBoundingClientRect: function () { return { top: 10, height: 200 }; } };
var root = { querySelector: function () { return head; },
             style: { setProperty: function (k, v) { props[k] = v; }, removeProperty: function (k) { props[k] = 'GONE'; } } };
var PHONE = %s;
function isPhone() { return PHONE; }
syncStickyHead(root);
process.stdout.write(JSON.stringify(props));
"""
    assert _node(("syncStickyHead",), scenario % "true") == {"--wb-head-stick": "-136px", "--wb-tools-top": "64px"}
    assert _node(("syncStickyHead",), scenario % "false") == {"--wb-head-stick": "GONE", "--wb-tools-top": "GONE"}
    js = _js()
    assert "syncStickyHead(root);" in _extract_function(js, "syncNavOffset")
    assert "syncStickyHead(next);" in js.split("async function softRefresh(")[1].split("\n    }\n")[0]


# --------------------------------------------------------------------------- #
# N-14 이력 카드 · 핀
# --------------------------------------------------------------------------- #

def test_history_cards_show_the_naver_stage_and_fold_repeated_badges(client, workbench_on, monkeypatch):
    _empty_strips(monkeypatch)
    _collected(order_no="N-P1-HIST", product="이력 붙박이장", amount=100000, place_status="")
    _login(client)
    body = client.get(TRIAGE_PATH, query_string={"tab": "all"}).get_data(as_text=True)
    assert "wb-st__b--st-collected" in body and "wb-st__b--rel-new" in body
    assert 'class="wb-pipe"' in body

    phone, everywhere = _css()
    pipe = phone.split("    .wb-hist tbody tr[data-find] .wb-st > .wb-st__v:nth-child(4) {")
    assert "display: none;" in pipe[1].split("}")[0], "예전 숨김 규칙(대조군)이 먼저 있다"
    assert "display: flex;" in pipe[-1].split("}")[0] and "grid-row: 2;" in pipe[-1].split("}")[0]
    hide = phone.split("    .wb-hist tbody tr[data-find] .wb-st__b--st-collected,")[1].split("}")[0]
    assert ".wb-st__b--rel-new" in hide and ".wb-hist__nofoms" in hide and "display: none;" in hide
    todo = _rule(phone, "    .wb-hist tbody tr[data-find] .wb-pipe__s")
    assert _contrast(re.search(r"color: (#[0-9a-f]{6})", todo).group(1), "#ffffff") >= 4.5
    assert "wb-st__b--st-collected" not in everywhere, "데스크톱 이력 표는 그대로"


def test_workbench_pins_moved_to_20260930b():
    markup = TEMPLATE.read_text(encoding="utf-8")
    assert markup.count("?v=20260930b") == 2
    assert "?v=20260930a" not in markup
    assert PANE.exists()
