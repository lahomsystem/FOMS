"""워크벤치 처리 탭 — 왼쪽 줄이 pane 과 **같은 말**을 하는가 (2026-09-09 신고).

담당자가 본 화면: 추가결제 3건 묶음이 발송처리까지 끝났는데(pane 은 `발송처리 완료`)
왼쪽 큐 줄은 여전히 `규격 입력할 차례` 였다. 원인은 판정이 두 벌이었다는 것 —
서버는 이미 `spec_filled`·`dispatched` 를 알고 있었는데 목록 템플릿만 `group.order_id`
하나로 다시 판정했다(:func:`_attach_row_flags` docstring 의 H1 과 같은 부류).

이 파일이 무는 것은 두 겹이다.

* **결함 A(서버 판정 한 벌)**: 목록 줄의 라벨이 그 집의 실제 상태를 따른다.
  판정부는 :func:`foms.web.admin.naver_ingest._row_view` 하나뿐이다.
* **결함 B(pane → 줄 옮기기)**: pane 프래그먼트 루트가 표시값 3종을 실어 오고,
  JS 순수 함수 세 벌이 그 값을 왼쪽 줄로 옮긴다.

**음성 대조군을 같은 화면에 함께 시드한다.** 세 집을 한 번의 요청으로 받아 줄마다
잘라 보지 않으면 "판정이 통째로 죽었다"가 green 으로 샌다 — 발송·규격 집만 보면
라벨을 전부 `지금 처리 가능` 으로 만들어도 통과한다.
"""

from __future__ import annotations

import json
import pathlib
import shutil
import subprocess
import tempfile

from sqlalchemy.orm.attributes import flag_modified

from db import db_session
from models import ExternalOrderLink, Order
from tests.services.integrations.test_naver_dock_width_live import (
    _extract_function,
    _needs_node,
)
from tests.services.integrations.test_naver_workbench import (  # noqa: F401
    TRIAGE_PATH,
    _collected,
    _login,
    _row_of,
    workbench_on,
)

#: pane 프래그먼트 경로 — JS 가 `#wb-pane` 만 갈아 끼울 때 부르는 그 주소.
PANE_PATH = "/admin/naver-ingest/triage/pane"

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
_WORKBENCH_JS = _REPO_ROOT / "static" / "js" / "admin" / "naver-workbench.js"


# --------------------------------------------------------------------------- #
# 픽스처 보조 — 규격·발송 표식
# --------------------------------------------------------------------------- #

def _link_order(link: ExternalOrderLink, *, spec: bool,
                customer_name: str = "임선경") -> Order:
    """링크에 FOMS 주문을 붙인다.

    규격 SSOT 는 ``structured_data['items'][*]['spec_rows']`` 다 — **품목 안**이고
    최상위 ``spec_rows`` 가 아니다(:func:`naver_ingest.order_has_spec_rows`).
    최상위에 넣으면 판정부가 늘 "규격 없음"으로 읽어 이 파일이 아무것도 재현하지 못한다.

    Args:
        link: 주문을 붙일 링크.
        spec: True 면 규격 행을 한 줄 넣는다.
        customer_name: 붙는 주문의 고객명(목록 이름 칸이 이 값을 쓴다).

    Returns:
        만들어 붙인 :class:`models.Order`.
    """
    rows = [{"width": "1200", "height": "2400"}] if spec else []
    order = Order(received_date="2026-09-09", customer_name=customer_name,
                  phone="010-7777-8888", address="서울 강남구 1 101호",
                  product="붙박이장", status="RECEIVED",
                  structured_data={"items": [{"name": "붙박이장", "spec_rows": rows}]})
    db_session.add(order)
    db_session.commit()
    row = db_session.get(ExternalOrderLink, int(link.id))
    row.order_id = int(order.id)
    row.sync_status = "LINKED"
    db_session.commit()
    return order


def _mark_dispatched(link: ExternalOrderLink,
                     stamp: str = "2026-09-09T01:53:00") -> None:
    """워커가 남기는 **우리 쪽** 발송 표식을 써 넣는다(UTC naive isoformat).

    ``dispatched`` 는 집 전체가 나갔을 때만 True 라, 형제가 있으면 형제에도 찍어야 한다.

    Args:
        link: 링크 행.
        stamp: 발송 시각 문자열.
    """
    row = db_session.get(ExternalOrderLink, int(link.id))
    state = dict(row.triage_state or {})
    state["fulfillment"] = dict(state.get("fulfillment") or {}, dispatched_at=stamp)
    row.triage_state = state
    flag_modified(row, "triage_state")
    db_session.commit()


def _work_body(client) -> str:
    """처리 탭 전체 렌더 마크업."""
    response = client.get(f"{TRIAGE_PATH}?f=all")
    assert response.status_code == 200, response.status_code
    return response.get_data(as_text=True)


# --------------------------------------------------------------------------- #
# 결함 A — 목록 줄의 라벨이 그 집의 실제 상태를 따른다
# --------------------------------------------------------------------------- #

def test_row_labels_follow_the_real_state_of_each_household(client, workbench_on):
    """한 화면 안에서 네 집이 **각각 다른** 말을 한다(음성 대조군 포함).

    · 발송까지 끝난 집 → `발송까지 끝남` (`규격 입력할 차례` 가 아니다 — 신고 본문)
    · 규격이 이미 들어간 집 → `발송할 차례`
    · **주문은 있고 규격은 없고 발송 전인 집 → 여전히 `규격 입력할 차례`** (음성 대조군)
    · 주문이 아직 없는 집 → `지금 처리 가능` + `주문 만들기` 배지(배지 억제의 양성 대조군)

    네 줄을 **한 번의 요청**으로 함께 본다. 라벨 갈래를 통째로 한 값으로 굳혀도
    대조군 두 줄이 곧바로 빨개진다.
    """
    _login(client)
    done = _collected(order_no="N-ROWSYNC-DONE", product="발송끝 붙박이장", amount=300000)
    _link_order(done, spec=False, customer_name="발송끝 고객")
    _mark_dispatched(done)

    filled = _collected(order_no="N-ROWSYNC-SPEC", product="규격완료 붙박이장", amount=300000)
    _link_order(filled, spec=True, customer_name="규격완료 고객")

    plain = _collected(order_no="N-ROWSYNC-PLAIN", product="규격전 붙박이장", amount=300000)
    _link_order(plain, spec=False, customer_name="규격전 고객")

    _collected(order_no="N-ROWSYNC-FRESH", product="주문전 붙박이장", amount=300000)

    body = _work_body(client)

    done_row = _row_of(body, "발송끝 붙박이장")
    assert "발송까지 끝남" in done_row, done_row
    assert "규격 입력할 차례" not in done_row, "발송이 끝난 집이 규격을 입력하라고 말한다"
    assert "badge bg-primary" not in done_row, "라벨과 정면으로 부딪히는 `규격 입력` 배지가 남았다"

    filled_row = _row_of(body, "규격완료 붙박이장")
    assert "발송할 차례" in filled_row, filled_row
    assert "규격 입력할 차례" not in filled_row, "규격이 이미 들어간 집이다"

    # 음성 대조군 — 같은 모집단, 같은 화면. 이 줄까지 바뀌면 판정이 죽은 것이다.
    plain_row = _row_of(body, "규격전 붙박이장")
    assert "규격 입력할 차례" in plain_row, plain_row
    assert "발송까지 끝남" not in plain_row, plain_row
    assert "발송할 차례" not in plain_row, plain_row

    # 양성 대조군 — 배지 억제 조건이 통째로 꺼진 것이 아님을 이 줄이 증명한다.
    fresh_row = _row_of(body, "주문전 붙박이장")
    assert "지금 처리 가능" in fresh_row, fresh_row
    assert '<span class="badge bg-primary">주문 만들기</span>' in fresh_row, fresh_row


def test_a_claimed_household_reads_as_locked_even_after_dispatch(client, workbench_on):
    """클레임 잠금이 발송보다 **위**다 — 손대지 않을 집을 `발송까지 끝남` 이라 부르지 않는다.

    사다리에서 잠금이 아래로 내려가면, 취소가 확정된 집이 "다 끝났다"로 읽혀
    담당자가 그냥 지나친다. 발송 표식과 클레임을 한 집에 함께 놓고 순서를 못박는다.
    """
    _login(client)
    link = _collected(order_no="N-ROWSYNC-CLAIM", product="취소된 붙박이장",
                      amount=300000, claim_status="CANCEL_DONE")
    _link_order(link, spec=False, customer_name="취소 고객")
    _mark_dispatched(link)

    row = _row_of(_work_body(client), "취소된 붙박이장")

    assert "손대지 않음" in row, row
    assert "발송까지 끝남" not in row, "잠긴 집이 발송 갈래로 떨어졌다"
    assert "규격 입력할 차례" not in row, row


# --------------------------------------------------------------------------- #
# 결함 B ① 서버 — pane 프래그먼트가 줄 표시값을 실어 온다
# --------------------------------------------------------------------------- #

def test_the_pane_fragment_carries_the_same_row_view_as_the_list(client, workbench_on):
    """pane 루트의 표시값 3종이 같은 집의 목록 줄과 **글자까지** 같다.

    ``data-row-link-ids`` 는 집 형제를 전부 담아야 한다 — 목록 줄의 ``data-link-id`` 는
    화면 모집단 안 최대금액 링크라 pane 의 대표와 갈릴 수 있고, 그때 JS 가 맞출 줄을
    못 찾는다(계약 §행 매칭 함정).
    """
    _login(client)
    lead = _collected(order_no="N-ROWSYNC-PANE", product="pane 붙박이장", amount=300000)
    sibling = _collected(order_no="N-ROWSYNC-PANE", product="pane 구성옵션", amount=0)
    _link_order(lead, spec=False, customer_name="pane 고객")
    _mark_dispatched(lead)
    _mark_dispatched(sibling)

    row = _row_of(_work_body(client), "pane 붙박이장")
    assert "발송까지 끝남" in row, row

    fragment = client.get(f"{PANE_PATH}?link_id={lead.id}").get_data(as_text=True)
    head = fragment.strip().split(">")[0]

    assert 'data-row-kind="done"' in head, head
    assert 'data-row-can="발송까지 끝남"' in head, head
    ids = head.split('data-row-link-ids="')[1].split('"')[0].split(",")
    assert sorted(ids) == sorted([str(lead.id), str(sibling.id)]), head


def test_the_pane_fragment_omits_the_row_view_when_nothing_is_open(client, workbench_on):
    """연 집이 없으면 세 속성을 **아예 안 낸다**(음성 대조군).

    빈 값이라도 실어 보내면 JS 가 그 값으로 왼쪽 줄을 덮어쓴다 — 라벨이 빈 칸이 된다.
    link_id 없이 부르는 프래그먼트는 400 이므로, 빈 pane 은 전체 렌더 첫 화면에서 본다.
    """
    _login(client)

    assert client.get(PANE_PATH).status_code == 400

    pane_head = _work_body(client).split('<div id="wb-pane')[1].split(">")[0]

    assert "data-row-kind=" not in pane_head, pane_head
    assert "data-row-link-ids=" not in pane_head, pane_head


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
function makeRow(linkId, kind, canText) {
    var attrs = { 'data-link-id': linkId, 'data-row-kind': kind };
    var can = { classList: makeClassList(), textContent: canText };
    return {
        can: can,
        classList: makeClassList(),
        getAttribute: function (name) {
            return Object.prototype.hasOwnProperty.call(attrs, name) ? attrs[name] : null;
        },
        setAttribute: function (name, value) { attrs[name] = value; },
        querySelector: function (sel) { return sel === '.wb-can' ? can : null; }
    };
}
function makePane(kind, can, linkIds) {
    var attrs = {
        'data-row-kind': kind, 'data-row-can': can, 'data-row-link-ids': linkIds
    };
    return {
        getAttribute: function (name) {
            return Object.prototype.hasOwnProperty.call(attrs, name) ? attrs[name] : null;
        }
    };
}
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
        _extract_function(source, "pickRowForView"),
        _extract_function(source, "applyRowView"),
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
    createElement: function () {
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
        _extract_function(source, "pickRowForView"),
        _extract_function(source, "applyRowView"),
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
