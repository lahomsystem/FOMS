"""워크벤치 줄 표시값 — pane 의 값을 왼쪽 줄로 옮기는 JS (2026-09-09 신고).

:mod:`tests.services.integrations.test_naver_workbench_row_sync` 의 **화면 절반**이다.
그쪽이 서버 판정 한 벌(``_row_view``)과 pane 프래그먼트가 싣는 값을 물고, 이 파일은
그 값을 실제로 옮기는 JS 를 **Node 로 돌려** 확인한다. 한 파일이 500줄 래칫에 걸려
같은 계약을 축으로 갈랐다(2026-09-09).

문자열 존재 단언은 쓰지 않는다. 함수를 뜯어 스텁에 물리고 **상태가 어떻게 변했나**를
본다 — 갈래를 ``if (false)`` 로 꺼도 통과하는 단언은 아무것도 지키지 않는다.
"""

from __future__ import annotations

import json
import pathlib
import shutil
import subprocess
import tempfile

from tests.services.integrations.test_naver_dock_width_live import (
    _extract_function,
    _needs_node,
)

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
_WORKBENCH_JS = _REPO_ROOT / "static" / "js" / "admin" / "naver-workbench.js"


# --------------------------------------------------------------------------- #
# 결함 B ② 화면 — JS 순수 함수를 Node 로 **실제 실행**한다
#
# 문자열 존재 단언은 쓰지 않는다. 함수를 뜯어 스텁에 물리고 **상태가 어떻게 변했나**를
# 본다 — 갈래를 `if (false)` 로 꺼도 통과하는 단언은 아무것도 지키지 않는다.
# --------------------------------------------------------------------------- #

#: 줄·pane 을 흉내 낸 최소 DOM 스텁. classList 는 더한 이름과 지운 이름을 각각 모아 둔다.
_DOM_STUBS = """
function makeClassList() {
    var state = { added: [], removed: [] };
    state.add = function (name) { state.added.push(name); };
    state.remove = function (name) { state.removed.push(name); };
    return state;
}
function makeElement(tag) {
    return { tag: tag, className: '', textContent: '', parentNode: null };
}
function isBadge(node) {
    return String(node.className || '').split(' ').indexOf('badge') !== -1;
}
function makeStrip(badges, can) {
    var children = [];
    var strip = {
        children: children,
        querySelector: function (sel) { return sel === '.wb-can' ? can : null; },
        querySelectorAll: function (sel) {
            if (sel !== '.badge') { return []; }
            return children.filter(isBadge);
        },
        insertBefore: function (node, anchor) {
            var at = children.indexOf(anchor);
            if (at === -1) { children.push(node); } else { children.splice(at, 0, node); }
            node.parentNode = strip;
        },
        removeChild: function (node) {
            var at = children.indexOf(node);
            if (at !== -1) { children.splice(at, 1); }
        }
    };
    (badges || []).forEach(function (badge) {
        var span = makeElement('span');
        span.className = 'badge ' + badge.cls;
        span.textContent = badge.text;
        span.parentNode = strip;
        children.push(span);
    });
    children.push(can);
    return strip;
}
function stripText(strip) {
    return strip.children.filter(isBadge).map(function (node) { return node.textContent; });
}
function makeRow(linkId, kind, canText, badges) {
    var attrs = { 'data-link-id': linkId, 'data-row-kind': kind };
    var can = { classList: makeClassList(), textContent: canText, className: 'wb-can' };
    var strip = makeStrip(badges, can);
    return {
        can: can,
        strip: strip,
        classList: makeClassList(),
        getAttribute: function (name) {
            return Object.prototype.hasOwnProperty.call(attrs, name) ? attrs[name] : null;
        },
        setAttribute: function (name, value) { attrs[name] = value; },
        querySelector: function (sel) {
            if (sel === '.wb-can') { return can; }
            if (sel === '.wb-row__line3') { return strip; }
            return null;
        }
    };
}
function makePane(kind, can, linkIds, badgesJson) {
    var attrs = {
        'data-row-kind': kind, 'data-row-can': can, 'data-row-link-ids': linkIds,
        'data-row-badges': typeof badgesJson === 'undefined' ? null : badgesJson
    };
    return {
        getAttribute: function (name) {
            return Object.prototype.hasOwnProperty.call(attrs, name) ? attrs[name] : null;
        }
    };
}
var document = { createElement: makeElement };
"""


def _run_row_view_js(scenario: str) -> dict:
    """워크벤치 JS 의 줄 동기화 순수 함수 세 벌을 Node 에 태워 돌린다.

    도크 테스트의 ``_source`` 는 도크 JS 전용이라 쓰지 않는다 — 워크벤치 JS 를 직접 읽는다.
    통째로는 즉시실행 IIFE 라 Node 에서 돌지 않으므로 함수만 뜯어낸다.

    Args:
        scenario: 스텁을 만들고 결과를 ``process.stdout`` 에 JSON 으로 쓰는 본문.

    Returns:
        시나리오가 찍은 JSON 을 파싱한 dict.
    """
    source = _WORKBENCH_JS.read_text(encoding="utf-8")
    script = "\n".join([
        _extract_function(source, "readRowView"),
        _extract_function(source, "safeBadgeList"),
        _extract_function(source, "pickRowForView"),
        _extract_function(source, "applyRowView"),
        _extract_function(source, "applyRowBadges"),
        _DOM_STUBS,
        scenario,
    ])
    node = shutil.which("node")
    assert node, "node 가 PATH 에 없다"
    with tempfile.TemporaryDirectory(prefix="naver-wb-rowsync-") as tmp:
        path = pathlib.Path(tmp) / "row_view_check.js"
        path.write_text(script, encoding="utf-8")
        proc = subprocess.run([node, str(path)], capture_output=True, text=True,
                              encoding="utf-8", timeout=60)
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


_APPLY_SCENARIO = """
var pane = makePane('done', '발송까지 끝남', '7,9');
var other = makeRow('3', 'go', '지금 처리 가능');
var target = makeRow('9', 'spec', '규격 입력할 차례');
var view = readRowView(pane);
var picked = pickRowForView([other, target], view.linkIds);
applyRowView(picked, view);
process.stdout.write(JSON.stringify({
    picked_is_target: picked === target,
    can_text: target.can.textContent,
    row_removed: target.classList.removed,
    row_added: target.classList.added,
    can_removed: target.can.classList.removed,
    can_added: target.can.classList.added,
    kind_attr: target.getAttribute('data-row-kind'),
    other_text: other.can.textContent,
    other_added: other.classList.added
}));
"""


_BADGE_SCENARIO = """
var BADGES = [
    { text: '3건 묶음', cls: 'bg-light text-dark' },
    { text: '주문 #5200', cls: 'bg-light text-dark' }
];
var pane = makePane('done', '발송까지 끝남', '7,9', JSON.stringify(BADGES));
var target = makeRow('9', 'spec', '규격 입력할 차례', [
    { text: '3건 묶음', cls: 'bg-light text-dark' },
    { text: '발주확인 할 차례', cls: 'bg-warning text-dark' },
    { text: '발송기한 10-01', cls: 'bg-light text-dark' }
]);
applyRowView(target, readRowView(pane));

var quiet = makeRow('9', 'spec', '규격 입력할 차례', [
    { text: '발주확인 할 차례', cls: 'bg-warning text-dark' }
]);
applyRowView(quiet, readRowView(makePane('done', '발송까지 끝남', '7,9')));

var emptied = makeRow('9', 'spec', '규격 입력할 차례', [
    { text: '발주확인 할 차례', cls: 'bg-warning text-dark' }
]);
applyRowView(emptied, readRowView(makePane('done', '발송까지 끝남', '7,9', '[]')));

var broken = makeRow('9', 'spec', '규격 입력할 차례', [
    { text: '발주확인 할 차례', cls: 'bg-warning text-dark' }
]);
applyRowView(broken, readRowView(makePane('done', '발송까지 끝남', '7,9', '{oops')));

process.stdout.write(JSON.stringify({
    repainted: stripText(target.strip),
    classes: target.strip.children.filter(isBadge).map(function (n) { return n.className; }),
    label_last: target.strip.children[target.strip.children.length - 1].className,
    quiet: stripText(quiet.strip),
    emptied: stripText(emptied.strip),
    broken: stripText(broken.strip)
}));
"""


_PICK_SCENARIO = """
var rows = [makeRow('3', 'go', 'ㄱ'), makeRow('9', 'spec', 'ㄴ')];
var hitView = readRowView(makePane('done', '발송까지 끝남', '7,9'));
var missView = readRowView(makePane('done', '발송까지 끝남', '7,8'));
var empty = readRowView(makePane(null, null, null));
var untouched = makeRow('9', 'spec', '규격 입력할 차례');
applyRowView(untouched, empty);
process.stdout.write(JSON.stringify({
    hit_is_second: pickRowForView(rows, hitView.linkIds) === rows[1],
    miss_is_null: pickRowForView(rows, missView.linkIds) === null,
    hit_ids: hitView.linkIds,
    empty_kind: empty.kind,
    untouched_text: untouched.can.textContent,
    untouched_added: untouched.classList.added
}));
"""


@_needs_node
def test_apply_row_view_swaps_the_label_and_the_colour_band():
    """`규격 입력할 차례` 줄에 발송 완료 pane 을 먹이면 글자·클래스·기억이 함께 바뀐다."""
    result = _run_row_view_js(_APPLY_SCENARIO)

    assert result["picked_is_target"] is True, result
    assert result["can_text"] == "발송까지 끝남", result
    # 옛 클래스는 줄이 들고 있던 data-row-kind 로 지운다 — JS 는 갈래 목록을 안 갖는다.
    assert "wb-row--spec" in result["row_removed"], result
    assert "wb-can--spec" in result["can_removed"], result
    assert "wb-row--done" in result["row_added"], result
    assert "wb-can--done" in result["can_added"], result
    # 다음 교체 때 지울 이름을 알아야 하므로 기억을 다시 심는다.
    assert result["kind_attr"] == "done", result
    # 음성 대조군 — 고르지 않은 줄은 한 글자도 안 건드린다.
    assert result["other_text"] == "지금 처리 가능", result
    assert result["other_added"] == [], result


@_needs_node
def test_apply_row_view_repaints_the_badge_strip_from_the_server_list():
    """배지 띠도 pane 이 실어 온 목록대로 다시 그린다 — 옛 배지는 남지 않는다.

    신고 화면의 줄은 `발주확인 할 차례`·`발송기한 10-01` 을 달고 있었는데 같은 줄의
    라벨은 `발송까지 끝남` 으로 바뀌었다. 배지를 안 갈면 한 줄이 두 말을 한다.

    음성 대조군 셋을 함께 돌린다 — 배지를 통째로 지우는 갈래로 굳어도 곧바로 빨개진다.
    · 속성을 안 실은 pane → 옛 배지 **그대로**(서버가 안 보냈으면 건드리지 않는다)
    · 빈 배열을 실은 pane → 전부 지운다(배지가 없는 집이 있다)
    · 깨진 JSON → 그대로 둔다(파싱 실패를 "배지 없음"으로 읽지 않는다)
    """
    result = _run_row_view_js(_BADGE_SCENARIO)

    assert result["repainted"] == ["3건 묶음", "주문 #5200"], result
    assert result["classes"] == ["badge bg-light text-dark"] * 2, result
    # 라벨은 배지 **뒤**에 남는다 — 앞으로 밀리면 줄 끝의 글자가 사라진다.
    assert result["label_last"] == "wb-can", result
    assert result["quiet"] == ["발주확인 할 차례"], result
    assert result["emptied"] == [], result
    assert result["broken"] == ["발주확인 할 차례"], result


@_needs_node
def test_pick_row_for_view_matches_by_link_membership_not_by_the_lead_id():
    """대표 링크 id 가 갈려도 **형제 포함**으로 줄을 찾고, 없으면 조용히 null 이다."""
    result = _run_row_view_js(_PICK_SCENARIO)

    # 줄의 data-link-id 가 pane 의 목록 안에 있기만 하면 맞다(대표가 갈려도 찾는다).
    assert result["hit_is_second"] is True, result
    assert result["hit_ids"] == ["7", "9"], result
    # 음성 대조군 1 — 목록 밖 집을 열면 맞출 줄이 없다.
    assert result["miss_is_null"] is True, result
    # 음성 대조군 2 — 값을 안 실어 온 pane 은 아무 줄도 안 덮는다.
    assert result["empty_kind"] == "", result
    assert result["untouched_text"] == "규격 입력할 차례", result
    assert result["untouched_added"] == [], result


# --------------------------------------------------------------------------- #
# 결함 B ③ 배선 — pane 을 갈아 끼우는 그 자리가 줄을 실제로 맞추는가
#
# 위의 순수 함수 세 벌은 "값을 옮길 줄 안다"까지만 증명한다. 화면에서 결함 B 를 실제로
# 없애는 것은 swapPane 마지막 줄 하나(`syncRowFromPane(next)`)라, 그 줄을 지워도 위
# 시나리오는 전부 green 이다 — 갈래를 꺼도 통과하는 단언(계약 §새 테스트에 요구하는 것).
# 그래서 swapPane 을 통째로 뜯어 실제로 돌리고, **줄의 글자와 클래스가 바뀌었나**를 본다.
# --------------------------------------------------------------------------- #

#: swapPane 이 만지는 바깥세상 스텁 — 문서·모달 정리·목록 밖 경고. 호출 흔적을 남긴다.
_SWAP_STUBS = """
var swapLog = { teardown: 0, offlist: 0, replaced: null };
var swapRows = [];
var currentPane = null;
function paneAttr(html, name) {
    var mark = name + '="';
    var at = html.indexOf(mark);
    if (at === -1) { return null; }
    var rest = html.slice(at + mark.length);
    return rest.slice(0, rest.indexOf('"'));
}
function makeParsedPane(html) {
    return { getAttribute: function (name) { return paneAttr(html, name); } };
}
var document = {
    createElement: function (tag) {
        // 배지 span 은 _DOM_STUBS 의 노드로 만든다 — 이 스텁이 아래에서 document 를
        // 통째로 덮으므로, 여기서 갈래를 안 두면 swapPane 경로에서만 배지가 안 그려진다.
        if (tag === 'span') { return makeElement('span'); }
        var holder = { innerHTML: '' };
        holder.querySelector = function (sel) {
            if (sel !== '#wb-pane' || holder.innerHTML.indexOf('id="wb-pane"') === -1) {
                return null;
            }
            return makeParsedPane(holder.innerHTML);
        };
        return holder;
    },
    getElementById: function (id) { return id === 'wb-pane' ? currentPane : null; },
    querySelectorAll: function (sel) { return sel === 'a.wb-row' ? swapRows : []; }
};
function teardownModals() { swapLog.teardown += 1; }
function applyOfflistFlag() { swapLog.offlist += 1; }
function makeCurrentPane() {
    return { replaceWith: function (node) { swapLog.replaced = node; } };
}
"""


def _run_swap_pane_js(scenario: str) -> dict:
    """``swapPane`` 을 배선째 Node 에 태워 돌린다.

    순수 함수만 뜯어 돌리면 "옮길 줄 안다"까지만 증명된다. 여기서는 교체 함수 자체를
    돌려 **왼쪽 줄이 실제로 바뀌는가**를 본다 — 배선이 끊기면 이 함수가 빨개진다.

    Args:
        scenario: 스텁을 세우고 ``swapPane`` 을 부른 뒤 결과를 JSON 으로 찍는 본문.

    Returns:
        시나리오가 찍은 JSON 을 파싱한 dict.
    """
    source = _WORKBENCH_JS.read_text(encoding="utf-8")
    script = "\n".join([
        _extract_function(source, "readRowView"),
        _extract_function(source, "safeBadgeList"),
        _extract_function(source, "pickRowForView"),
        _extract_function(source, "applyRowView"),
        _extract_function(source, "applyRowBadges"),
        _extract_function(source, "syncRowFromPane"),
        _extract_function(source, "swapPane"),
        _DOM_STUBS,
        _SWAP_STUBS,
        scenario,
    ])
    node = shutil.which("node")
    assert node, "node 가 PATH 에 없다"
    with tempfile.TemporaryDirectory(prefix="naver-wb-swap-") as tmp:
        path = pathlib.Path(tmp) / "swap_pane_check.js"
        path.write_text(script, encoding="utf-8")
        proc = subprocess.run([node, str(path)], capture_output=True, text=True,
                              encoding="utf-8", timeout=60)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    return json.loads(proc.stdout)


#: 서버가 실제로 내는 모양의 pane 프래그먼트 두 벌 — 값을 실은 것과 안 실은 것.
_SWAP_SCENARIO = """
var LOADED = '<div id="wb-pane" class="wb-pane" data-row-kind="done"'
    + ' data-row-can="발송까지 끝남" data-row-link-ids="7,9"><p>끝</p></div>';
var BARE = '<div id="wb-pane" class="wb-pane"><p>고른 집이 없다</p></div>';

var other = makeRow('3', 'go', '지금 처리 가능');
var target = makeRow('9', 'spec', '규격 입력할 차례');
swapRows = [other, target];
currentPane = makeCurrentPane();
swapPane(LOADED);
var afterLoaded = {
    can_text: target.can.textContent,
    row_added: target.classList.added,
    can_added: target.can.classList.added,
    kind_attr: target.getAttribute('data-row-kind'),
    other_text: other.can.textContent,
    replaced: swapLog.replaced !== null,
    teardown: swapLog.teardown,
    offlist: swapLog.offlist
};

var lonely = makeRow('9', 'spec', '규격 입력할 차례');
swapRows = [lonely];
currentPane = makeCurrentPane();
swapPane(BARE);
var afterBare = { can_text: lonely.can.textContent, added: lonely.classList.added };

var threw = '';
try {
    currentPane = null;
    swapPane(LOADED);
} catch (error) {
    threw = String(error.message || error);
}

process.stdout.write(JSON.stringify({
    loaded: afterLoaded, bare: afterBare, threw: threw
}));
"""


@_needs_node
def test_swapping_the_pane_also_repaints_the_left_row():
    """pane 을 갈아 끼우면 **그 자리에서** 왼쪽 줄이 새 말을 한다(결함 B 배선).

    · 값을 실은 pane → 같은 집의 줄이 `규격 입력할 차례` 에서 `발송까지 끝남` 으로 바뀐다.
    · 고른 집이 없는 pane → 줄을 한 글자도 안 덮는다(음성 대조군).
    · 프래그먼트에 pane 이 없으면 던진다 — 조용히 반만 갈아 끼우지 않는다.

    ``syncRowFromPane(next)`` 한 줄을 지우거나 ``if (false)`` 로 감싸면 첫 갈래가 곧바로
    빨개진다. 순수 함수 시나리오만으로는 그 줄이 없어도 전부 통과했다.
    """
    result = _run_swap_pane_js(_SWAP_SCENARIO)

    loaded = result["loaded"]
    assert loaded["can_text"] == "발송까지 끝남", loaded
    assert "wb-row--done" in loaded["row_added"], loaded
    assert "wb-can--done" in loaded["can_added"], loaded
    assert loaded["kind_attr"] == "done", loaded
    # pane 교체 자체도 함께 일어난다 — 줄만 고치고 pane 을 안 바꾸면 반대로 어긋난다.
    assert loaded["replaced"] is True, loaded
    assert loaded["teardown"] == 1 and loaded["offlist"] == 1, loaded
    # 음성 대조군 1 — 집이 다른 줄은 그대로다.
    assert loaded["other_text"] == "지금 처리 가능", loaded

    # 음성 대조군 2 — 값을 안 실어 온 pane 은 줄을 비우지 않는다.
    assert result["bare"]["can_text"] == "규격 입력할 차례", result["bare"]
    assert result["bare"]["added"] == [], result["bare"]

    assert "pane fragment missing" in result["threw"], result["threw"]
