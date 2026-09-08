"""네이버 도크 자동 입력 — 화면 배선 계약 (2026-09-08, Node 실행).

**왜 Node 로 도나.** 도크 JS 는 즉시실행 IIFE 라 통째로는 Node 에서 돌지 않는다
(``document`` 를 만진다). 그래서 판단을 맡은 **순수 함수만 통째로 뜯어** Node 에 태우고,
DOM 은 스텁 객체로 흉내 낸다 — 진짜 브라우저가 아니어도 **판단과 이벤트 발사는 진짜로
실행된다**. 뜯는 도구(:func:`_extract_function`)와 건너뛰기 마크(``_needs_node``)는
:mod:`tests.services.integrations.test_naver_dock_width_live` 것을 그대로 쓴다 — 두 벌로
만들면 규칙이 갈린다.

**무엇을 지키나.** 2026-09-08 담당자가 "자동 기입 금지"를 네 칸(제품명·색상·손잡이·총폭)에
한해 뒤집었다. 값을 **어디에 넣을지·덮어쓸지**의 판단은 전부 화면에 있다. 그 판단이
틀어졌을 때 나는 일:

* ``'상담'`` 을 빈 값으로 안 세면 신규 항목의 색상·손잡이는 **언제나** 확인창이 뜬다
  (기본값이 ``'상담'`` 이다 — ``erp-order-shared.js:1370-1372`` ``defaultConsult``).
  담당자가 칩마다 확인창을 닫아야 하면 그냥 손으로 붙여 넣는 편이 빠르다.
* 확인창 없이 덮어쓰면 되돌릴 길이 없다 — ``field.value =`` 대입은 브라우저 네이티브
  undo 스택을 지운다(계약 §4.3 이 수용한 위험). 확인창이 **유일한 게이트**다.
* ``input``·``change`` 를 버블로 안 쏘면 자동저장이 못 듣는다(``#erp-order`` 에서 캡처로
  듣는다 — ``erp-order-autosave.js:416-417``). 화면에는 값이 보이는데 저장은 안 된다.
* 예약금 칩에 칸 이름이 붙으면 **돈이 자동으로 들어간다** — 이 결정만은 뒤집히지 않았다.
"""

from __future__ import annotations

import json
import pathlib
import re
import shutil
import subprocess
import tempfile
from typing import Any, Sequence

import pytest

from tests.services.integrations.test_naver_dock_width_live import (
    _extract_function,
    _needs_node,
    _source,
    _squash,
)

#: 자동 입력 판단에 관여하는 함수 전부 — 선언은 호이스팅되므로 순서는 상관없다.
_FILL_FUNCTIONS = (
    "dockIsBlankValue",
    "dockFieldLabel",
    "dockFillConfirmText",
    "dockPickItemRow",
    "dockFieldFor",
    "dockItemLabel",
    "dockSpecRowCount",
    "dockApplyValue",
    "dockChipsOf",
    "dockFillFromChip",
)

#: Node 하네스 — 이벤트·DOM 스텁. 진짜 브라우저 대신이지만 **호출은 진짜로 일어난다**.
_PREAMBLE = r"""
function Event(type, opts) {
    this.type = type;
    this.bubbles = !!(opts && opts.bubbles);
}

var firedEvents = [];    // dockApplyValue 가 쏜 이벤트 기록(순서 그대로)
var seenSelectors = [];  // 화면이 물어본 셀렉터 기록

function pickBySelector(map, selector) {
    if (Object.prototype.hasOwnProperty.call(map, selector)) return map[selector];
    var keys = Object.keys(map);
    for (var i = 0; i < keys.length; i++) {
        if (selector.indexOf(keys[i]) !== -1) return map[keys[i]];
    }
    return null;
}

function stubEl(props) {
    var spec = props || {};
    var node = {
        value: spec.value === undefined ? '' : spec.value,
        label: spec.label || '',
        classes: (spec.classes || []).slice(),
        dataset: spec.dataset || {},
        find: spec.find || {},
        findAll: spec.findAll || {},
        isConnected: spec.isConnected === undefined ? true : spec.isConnected,
        focused: false,
        scrolled: false
    };
    node.classList = {
        contains: function (name) { return node.classes.indexOf(name) !== -1; },
        add: function (name) { node.classes.push(name); },
        remove: function (name) { node.classes.splice(node.classes.indexOf(name), 1); }
    };
    node.className = node.classes.join(' ');
    node.querySelector = function (selector) {
        seenSelectors.push(selector);
        return pickBySelector(node.find, selector);
    };
    node.querySelectorAll = function (selector) {
        seenSelectors.push(selector);
        return pickBySelector(node.findAll, selector) || [];
    };
    node.dispatchEvent = function (event) {
        firedEvents.push({ type: event.type, bubbles: event.bubbles });
        return true;
    };
    node.focus = function () { node.focused = true; };
    node.scrollIntoView = function () { node.scrolled = true; };
    node.setAttribute = function () {};
    node.getAttribute = function () { return null; };
    node.contains = function (other) { return other === node; };
    return node;
}

function itemRow(label, classes) {
    return stubEl({ label: label, classes: classes || [] });
}

/* 항목 한 개짜리 가짜 화면 — 값 칸 하나와 규격 행 n 개. */
function makeScene(opts) {
    var spec = opts || {};
    var field = stubEl({ value: spec.current === undefined ? '' : spec.current });
    var specRows = [];
    var count = spec.specRows === undefined ? 1 : spec.specRows;
    for (var i = 0; i < count; i++) specRows.push(stubEl({ label: '규격행' + (i + 1) }));
    var row = stubEl({
        label: '항목 1',
        dataset: { itemIdx: '0' },
        find: { 'spec_width': field, 'data-erp=': field },
        findAll: { '.erp-spec-row': specRows }
    });
    firedEvents = [];
    return { row: row, field: field, rows: [row] };
}
"""


def _run(functions: Sequence[str], expression: str, *, setup: str = "") -> Any:
    """도크 JS 함수들을 Node 에 태워 ``expression`` 값을 받아온다.

    Args:
        functions: 뜯어 실을 함수 이름들.
        expression: 값을 낼 JS 식(JSON 으로 직렬화된다).
        setup: 식 앞에 둘 준비 코드.

    Returns:
        ``expression`` 의 값(파이썬 객체).
    """
    source = _source()
    parts = [_PREAMBLE]
    for name in functions:
        try:
            parts.append(_extract_function(source, name))
        except (ValueError, AssertionError) as exc:
            pytest.fail(f"도크 JS 에 {name} 함수가 없다(자동 입력 계약 미착지): {exc}")
    parts.append(setup)
    parts.append("var __out;")
    parts.append("try { __out = { ok: true, data: (" + expression + ") }; }")
    parts.append("catch (err) { __out = { ok: false,"
                 " error: String((err && err.stack) || err) }; }")
    parts.append("process.stdout.write(JSON.stringify(__out));")
    node = shutil.which("node")
    assert node, "node 가 PATH 에 없다"
    with tempfile.TemporaryDirectory(prefix="naver-dock-fill-") as tmp:
        path = pathlib.Path(tmp) / "dock_fill_check.js"
        path.write_text("\n".join(parts), encoding="utf-8")
        proc = subprocess.run([node, str(path)], capture_output=True, text=True,
                              encoding="utf-8", timeout=60)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    result = json.loads(proc.stdout)
    assert result["ok"], result["error"]
    return result["data"]


# ── 빈 칸 판정 (계약 §4.3) ──

@_needs_node
def test_blank_value_counts_the_default_consult_placeholder_as_empty():
    """``'상담'`` 은 **빈 값**이다 — 신규 항목의 색상·손잡이 기본값이 그것이다.

    ``erp-order-shared.js:1370-1372`` ``defaultConsult`` 가 새 항목의 색상·손잡이·내부·
    옵션·기타를 ``'상담'`` 으로 채운다. 이걸 값으로 세면 첫 입력부터 확인창이 뜬다.
    사람이 실제로 적어 넣은 ``'상 담'`` 은 값이다 — 공백까지 지워 세면 안 된다.
    """
    got = _run(("dockIsBlankValue",),
               "['', '   ', '상담', '포그 그레이', '상 담', '0']"
               ".map(function (v) { return dockIsBlankValue(v); })")

    assert got == [True, True, True, False, False, False]


# ── 어느 항목에 넣나 (계약 §4.1) ──

@_needs_node
def test_pick_item_row_follows_the_person_then_the_visible_row():
    """네 갈래를 전부 — 사람이 만진 항목 → 보이는 항목 → 펼쳐진 항목 → 첫 항목.

    이 순서가 무너지면 값이 **사람이 보고 있지 않은 항목**에 조용히 들어간다. 마스터-
    디테일에서 선택 안 된 행에는 ``erp-item-row--md-hidden`` 이 붙고
    (``erp-items-master-detail.js:125``), 모바일 아코디언은 한 번에 하나만 펼친다
    (``erp-order-shared.js:1242``) — 그 둘이 "지금 보고 있는 항목"의 화면상 정본이다.

    ``lastTouchedHidden`` 이 이 테스트의 진짜 함정이다. 레일 항목은 ``role=option`` 인
    div 라 클릭해도 포커스가 옮겨 가지 않는다(``erp-items-master-detail.js`` 의
    ``selectItem`` 에 ``focus()`` 가 없다). "항목 1 색상 칸에 타이핑 → 레일에서 항목 3
    선택" 뒤 마지막 포커스는 항목 1 에 남아 있고, 그 행은 ``display:none`` 이다
    (``erp-items-master-detail.css`` 의 ``erp-item-row--md-hidden``). 포커스만 보고
    고르면 값이 **보이지 않는 항목**에 들어가고 스크롤·포커스도 아무 반응이 없다.
    """
    setup = """
var plain = itemRow('A');
var open = itemRow('B', ['is-open']);
var hidden = itemRow('H', ['erp-item-row--md-hidden']);
var hidden2 = itemRow('H2', ['erp-item-row--md-hidden']);
var gone = itemRow('GONE');
gone.isConnected = false;
function labelOf(row) { return row ? row.label : null; }
"""
    got = _run(("dockPickItemRow",), setup=setup, expression="""({
    lastTouched: labelOf(dockPickItemRow([plain, open], plain)),
    lastTouchedGone: labelOf(dockPickItemRow([plain, open], gone)),
    lastTouchedHidden: labelOf(dockPickItemRow([hidden, plain], hidden)),
    skipsHidden: labelOf(dockPickItemRow([hidden, plain], null)),
    prefersOpen: labelOf(dockPickItemRow([plain, open], null)),
    allHidden: labelOf(dockPickItemRow([hidden, hidden2], null)),
    empty: dockPickItemRow([], null)
})""")

    assert got["lastTouched"] == "A", "마지막으로 만진 항목을 안 고른다"
    assert got["lastTouchedGone"] == "B", "사라진 항목을 고른 채로 멈췄다"
    assert got["lastTouchedHidden"] == "A", "숨겨진(안 보이는) 항목에 값을 넣는다"
    assert got["skipsHidden"] == "A", "마스터-디테일에서 숨은 행을 골랐다"
    assert got["prefersOpen"] == "B", "펼쳐진 항목을 우선하지 않는다"
    assert got["allHidden"] == "H", "고를 것이 없을 때 첫 항목으로 안 떨어진다"
    assert got["empty"] is None, "항목이 없는데 무언가를 골랐다"


# ── 어느 칸에 넣나 (계약 §4.2) ──

@_needs_node
def test_field_for_reads_the_first_spec_row_width_and_the_data_erp_contract():
    """총폭은 **첫 규격 행의 W 칸**, 나머지는 ``data-erp`` 계약으로 찾는다.

    화면 요약·마스터-디테일 레일·규격 계산기가 이미 첫 규격 행을 그 항목의 대표 W 로
    읽는다 — 네 번째 정의를 만들지 않는다. 폼의 ``id``·``name`` 은 여전히 안 본다
    (폼 불가침 계약에서 살아남은 부분).
    """
    setup = """
var width = stubEl({ label: 'W' });
var color = stubEl({ label: 'C' });
var row = stubEl({ find: { 'spec_width': width, 'data-erp="color"': color } });
var got = { width: dockFieldFor(row, 'spec_width'), color: dockFieldFor(row, 'color') };
"""
    got = _run(("dockFieldFor",), setup=setup, expression="""({
    width: got.width ? got.width.label : null,
    color: got.color ? got.color.label : null,
    selectors: seenSelectors
})""")

    assert got["width"] == "W"
    assert got["color"] == "C"
    assert set(got["selectors"]) == {
        '.erp-spec-row [data-erp="spec_width"][data-spec-row]',
        '[data-erp="color"]',
    }, "계약이 정한 셀렉터가 아니다"


# ── 확인창 문구 (계약 §4.3 — 유일한 게이트라 글자까지 정본이다) ──

@_needs_node
def test_confirm_text_restates_what_changes_to_what():
    """확인창은 **무엇을 무엇으로 바꾸는지** 글자로 다시 말한다.

    되돌리기(undo)를 만들지 않기로 했으므로 이 문구가 유일한 게이트다. 지금 값이 여기
    적히지 않으면 사람은 무엇을 잃는지 모르고 확인을 누른다.
    """
    got = _run(("dockFillConfirmText",), expression="""({
    overwrite: dockFillConfirmText('항목 2', '색상', '포그 그레이', '클린 화이트', ''),
    blankWithNote: dockFillConfirmText('항목 1', 'W(가로·총폭)', '', '3720',
        '규격 행이 3개입니다 — 1행에 넣습니다.')
})""")

    assert got["overwrite"] == "\n".join([
        "항목 2 · 색상",
        "지금 값: 포그 그레이",
        "넣을 값: 클린 화이트",
        "",
        "덮어쓸까요? (취소하면 그대로 둡니다)",
    ])
    assert got["blankWithNote"] == "\n".join([
        "항목 1 · W(가로·총폭)",
        "지금 값: (비어 있음)",
        "넣을 값: 3720",
        "규격 행이 3개입니다 — 1행에 넣습니다.",
        "",
        "여기에 넣을까요? (취소하면 그대로 둡니다)",
    ])


# ── 넣은 뒤 이벤트 (계약 §4.4) ──

@_needs_node
def test_apply_value_fires_input_then_change_as_bubbling_events():
    """값을 넣고 ``input`` → ``change`` 를 **버블로** 쏜다.

    자동저장이 ``#erp-order`` 에서 두 이벤트를 캡처로 듣는다
    (``erp-order-autosave.js:416-417``). 안 쏘거나 버블을 끄면 화면에는 값이 보이는데
    저장은 안 된다 — 사람이 새로고침하면 사라진다.
    """
    setup = """
var field = stubEl({ value: '포그 그레이' });
dockApplyValue(field, '클린 화이트');
"""
    got = _run(("dockApplyValue",), setup=setup,
               expression="({ value: field.value, fired: firedEvents })")

    assert got["value"] == "클린 화이트"
    assert got["fired"] == [
        {"type": "input", "bubbles": True},
        {"type": "change", "bubbles": True},
    ], "자동저장이 듣는 두 이벤트를 순서대로 버블로 쏘지 않는다"


# ── 판단 전체 (계약 §4.1~§4.4) ──

@_needs_node
def test_fill_puts_the_value_in_a_blank_field_without_asking():
    """빈 칸(``'상담'`` 포함) + 규격 1행이면 **묻지 않고** 넣는다.

    신규 항목의 색상은 ``'상담'`` 이다. 여기서 확인창이 뜨면 기능이 손 붙여넣기보다
    느려진다.
    """
    setup = """
var scn = makeScene({ current: '상담', specRows: 1 });
var calls = [];
var res = dockFillFromChip('color', '클린 화이트', scn.rows, null, function (text) {
    calls.push(text);
    return true;
});
"""
    got = _run(_FILL_FUNCTIONS, setup=setup, expression="""({
    res: res, calls: calls, value: scn.field.value, fired: firedEvents
})""")

    assert got["calls"] == [], "빈 칸인데 확인창을 띄웠다"
    assert got["res"]["ok"] is True
    assert got["res"]["itemLabel"] == "항목 1"
    assert got["res"]["fieldLabel"] == "색상"
    assert got["value"] == "클린 화이트"
    assert [event["type"] for event in got["fired"]] == ["input", "change"]


@_needs_node
def test_fill_asks_once_before_overwriting_and_obeys_the_answer():
    """값이 있으면 **확인창 1회** — 취소하면 칸이 그대로 남는다.

    되돌리기가 없으므로 취소가 실제로 값을 지키지 못하면 담당자가 적어 둔 값이 영영
    사라진다.
    """
    setup = """
var yes = makeScene({ current: '포그 그레이', specRows: 1 });
var yesCalls = [];
var accepted = dockFillFromChip('color', '클린 화이트', yes.rows, null,
    function (text) { yesCalls.push(text); return true; });
var yesValue = yes.field.value;
var no = makeScene({ current: '포그 그레이', specRows: 1 });
var noCalls = [];
var refused = dockFillFromChip('color', '클린 화이트', no.rows, null,
    function (text) { noCalls.push(text); return false; });
"""
    got = _run(_FILL_FUNCTIONS, setup=setup, expression="""({
    accepted: accepted, refused: refused,
    yesCalls: yesCalls, noCalls: noCalls,
    yesValue: yesValue, noValue: no.field.value, fired: firedEvents
})""")

    assert len(got["yesCalls"]) == 1, "확인창이 없거나 여러 번 뜬다"
    assert "지금 값: 포그 그레이" in got["yesCalls"][0]
    assert got["accepted"]["ok"] is True and got["yesValue"] == "클린 화이트"
    assert len(got["noCalls"]) == 1
    assert got["refused"]["ok"] is False
    assert got["refused"]["reason"] == "넣지 않았습니다"
    assert got["noValue"] == "포그 그레이", "취소했는데 값이 덮였다"
    assert got["fired"] == [], "취소했는데 이벤트를 쐈다(자동저장이 저장한다)"


@_needs_node
def test_fill_asks_even_for_a_blank_width_when_the_item_has_many_spec_rows():
    """규격 행이 2개 이상이면 **칸이 비어 있어도** 묻는다 — 어느 행인지가 사람의 판단이다."""
    setup = """
var scn = makeScene({ current: '', specRows: 2 });
var calls = [];
var res = dockFillFromChip('spec_width', '3720', scn.rows, null, function (text) {
    calls.push(text);
    return true;
});
"""
    got = _run(_FILL_FUNCTIONS, setup=setup,
               expression="({ res: res, calls: calls, value: scn.field.value })")

    assert len(got["calls"]) == 1, "규격 행이 여럿인데 안 물었다"
    assert "규격 행이 2개입니다 — 1행에 넣습니다." in got["calls"][0]
    assert got["res"]["ok"] is True
    assert got["value"] == "3720"


@_needs_node
def test_fill_says_so_when_there_is_no_item_or_no_target():
    """넣을 자리가 없으면 **넣지 않고 이유를 말한다** — 칩은 복사만 하고 끝난다.

    항목이 0개인 새 주문, 그리고 ``target`` 이 빈 칩(사이즈·서랍 같은 복사 전용)이
    오늘의 경로 그대로 남는지를 함께 본다.
    """
    setup = """
makeScene({});
var noneCalls = [];
var noItem = dockFillFromChip('color', '클린 화이트', [], null, function (text) {
    noneCalls.push(text);
    return true;
});
var plain = makeScene({ current: '', specRows: 1 });
var plainCalls = [];
var noTarget = dockFillFromChip('', '150（무몰딩）', plain.rows, null, function (text) {
    plainCalls.push(text);
    return true;
});
"""
    got = _run(_FILL_FUNCTIONS, setup=setup, expression="""({
    noItem: noItem, noneCalls: noneCalls,
    noTarget: noTarget, plainCalls: plainCalls,
    plainValue: plain.field.value, fired: firedEvents
})""")

    assert got["noItem"]["ok"] is False
    assert got["noItem"]["reason"] == "넣을 항목이 없습니다"
    assert got["noneCalls"] == []
    assert got["noTarget"]["ok"] is False, "칸 이름이 없는 칩이 어딘가에 값을 넣었다"
    assert got["plainCalls"] == []
    assert got["plainValue"] == ""
    assert got["fired"] == []


# ── 옛 응답 호환 (계약 §1) ──

@_needs_node
def test_chips_of_wraps_the_old_string_copies():
    """``copy_chips`` 가 없는 옛 응답도 **오늘과 똑같이** 복사 전용으로 그린다.

    도크 payload 는 서버가 따로 진화한다 — 배포 순서 하나로 칩이 사라지면 안 된다.
    """
    got = _run(("dockChipsOf",), expression="""({
    old: dockChipsOf({ copies: ['화이트', '푸쉬타입'] }),
    fresh: dockChipsOf({ copies: ['화이트'],
        copy_chips: [{ value: '화이트', target: 'color' }] }),
    empty: dockChipsOf({})
})""")

    assert got["old"] == [{"value": "화이트", "target": ""},
                          {"value": "푸쉬타입", "target": ""}]
    assert got["fresh"] == [{"value": "화이트", "target": "color"}]
    assert got["empty"] == []


# ── 배선 못박기 — 소스 문자열은 여기 3줄뿐이다 ──

def test_click_delegation_and_deposit_card_wiring():
    """칩 클릭이 칸 이름을 넘기고, **예약금 칩에는 칸 이름을 달지 않는다**.

    위 Node 검증은 함수 안쪽만 본다. 이 세 줄이 그 함수들이 실제로 화면에 연결돼
    있음을, 그리고 돈 칸만은 여전히 사람이 넣는다는 결정이 살아 있음을 지킨다.
    """
    source = _source()
    # 줄바꿈·들여쓰기와 여는 괄호 뒤 공백만 지운다 — 토큰 순서는 그대로 대조한다.
    wired = re.sub(r"\(\s+", "(", _squash(source))

    assert ("dockFillFromChip(copy.getAttribute('data-naver-dock-target') || '', value,"
            in wired), "칩 클릭이 칸 이름을 읽어 넘기지 않는다"
    assert "data-naver-dock-target', 'spec_width'" in source, (
        "총폭 칩이 W 칸을 가리키지 않는다")
    assert "setAttribute('data-naver-dock-target'" not in _extract_function(
        source, "buildDepositCard"), "예약금 칩에 칸 이름이 붙었다 — 돈은 사람이 넣는다"
