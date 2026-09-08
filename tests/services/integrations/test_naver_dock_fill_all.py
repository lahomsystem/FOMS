"""네이버 도크 '전부 넣기' — 일괄 입력 계약 (2026-09-08, Node 실행).

**왜 생겼나.** 칩 자동 입력을 낸 그날 담당자가 이어서 말했다 — "지금 나머지는 버튼을
눌러야 입력되게 돼 있는데, 일괄 입력 가능한 버튼도 만들어". 한 항목을 채우려면 칩을 네 번
눌러야 했고, 그 넷은 언제나 같은 넷이다(제품명·색상·손잡이·W 총폭).

**무엇을 지키나.** 일괄 입력은 한 번에 네 칸을 건드리므로 칩 하나보다 사고가 크다.

* 한 칸을 노리는 칩이 둘일 수 있다(``제품`` 과 ``사이즈`` 는 둘 다 제품명 칸이다).
  뒤엣것으로 덮으면 제품명이 ``150（무몰딩）`` 같은 숫자로 바뀐다 — **먼저 나온 칩**이
  이긴다.
* 확인창이 칸마다 뜨면 최대 네 번이다. 네 번 뜨는 확인창은 읽히지 않는다 — **한 번만**
  뜨고, 그 안에 덮어쓸 칸을 전부 적는다.
* 확인창을 **취소했는데 아무것도 안 들어가면** 사람이 다시 칩을 네 번 누른다. 취소는
  "덮어쓰지 마라"는 뜻이지 "빈 칸도 두라"는 뜻이 아니다 — 빈 칸은 잃을 값이 없다.
* 값을 넣고 ``input``·``change`` 를 **칸마다** 쏴야 자동저장이 듣는다
  (``erp-order-autosave.js:416-417`` 가 ``#erp-order`` 에서 캡처로 듣는다).
* 네 칸을 각각 ``scrollIntoView`` + ``focus`` 하면 화면이 네 번 흔들리고 마지막 칸만
  남는다 — **첫 칸 하나만** 데려간다.
"""

from __future__ import annotations

import pytest

from tests.services.integrations.test_naver_dock_autofill_wire import _run
from tests.services.integrations.test_naver_dock_width_live import _needs_node, _source

#: 일괄 입력 판단에 관여하는 함수 전부(선언은 호이스팅되므로 순서는 상관없다).
_BULK_FUNCTIONS = (
    "dockIsBlankValue",
    "dockFieldLabel",
    "dockItemLabel",
    "dockSpecRowCount",
    "dockPickItemRow",
    "dockFieldFor",
    "dockApplyValue",
    "dockBulkTargets",
    "dockBulkConfirmText",
    "dockFillAll",
)

#: 네 칸이 **서로 다른 노드**인 가짜 화면. 기존 ``makeScene`` 은 한 칸짜리라 일괄 입력을
#: 못 본다 — 칸이 하나면 "칸마다 이벤트를 쐈나"도 "첫 칸만 데려갔나"도 증명되지 않는다.
_SCENE = """
function makeBulkScene(opts) {
    var spec = opts || {};
    var fields = {
        product_name: stubEl({ label: '제품명', value: spec.product_name || '' }),
        color: stubEl({ label: '색상', value: spec.color || '' }),
        handle: stubEl({ label: '손잡이', value: spec.handle || '' }),
        spec_width: stubEl({ label: 'W', value: spec.spec_width || '' })
    };
    var specRows = [];
    var count = spec.specRows === undefined ? 1 : spec.specRows;
    for (var i = 0; i < count; i++) specRows.push(stubEl({ label: '규격행' + (i + 1) }));
    var row = stubEl({
        label: '항목 1',
        dataset: { itemIdx: '0' },
        find: {
            'data-erp="product_name"': fields.product_name,
            'data-erp="color"': fields.color,
            'data-erp="handle"': fields.handle,
            'data-erp="spec_width"': fields.spec_width
        },
        findAll: { '.erp-spec-row': specRows }
    });
    firedEvents = [];
    return { row: row, rows: [row], fields: fields };
}

var PLAN = [
    { target: 'product_name', value: '150（무몰딩）' },
    { target: 'color', value: '클린 화이트' },
    { target: 'handle', value: '푸쉬타입' },
    { target: 'spec_width', value: '3720' }
];

function yes() { return true; }
function no() { return false; }
function record(box) {
    return function (text) { box.push(text); return box.answer; };
}
"""


# --------------------------------------------------------------------------- #
# 계획 세우기 — 칸마다 하나 (먼저 나온 칩이 이긴다)
# --------------------------------------------------------------------------- #

@_needs_node
def test_bulk_plan_keeps_the_first_chip_for_each_field():
    """한 칸을 노리는 칩이 둘이면 **먼저 나온 것**만 쓴다.

    실사례가 제품명이다 — ``제품: 로라 무몰딩 여닫이 / 사이즈: 150（무몰딩）`` 는 둘 다
    제품명 칸을 가리키고, 네이버는 ``제품`` 을 먼저 낸다. 뒤엣것이 이기면 제품명 칸이
    숫자로 바뀐다. 칩을 하나씩 누르는 길은 그대로라, 사이즈 값을 넣고 싶으면 그 칩을 누른다.
    """
    got = _run(("dockBulkTargets",), """dockBulkTargets([
        { value: '로라 무몰딩 여닫이', target: 'product_name' },
        { value: '150（무몰딩）', target: 'product_name' },
        { value: '클린 화이트', target: 'color' }
    ])""")

    assert got == [
        {"target": "product_name", "value": "로라 무몰딩 여닫이"},
        {"target": "color", "value": "클린 화이트"},
    ]


@_needs_node
def test_bulk_plan_drops_copy_only_chips_and_empty_values():
    """복사 전용 칩(칸 이름 없음)과 빈 값은 계획에 들어가지 않는다.

    예약금 칩이 그 자리다 — 칸 이름이 없으므로 일괄 입력에도 **절대** 실리지 않는다.
    이 결정은 2026-09-08 에 명시로 확정됐다: 돈은 사람이 넣는다.
    """
    got = _run(("dockBulkTargets",), """dockBulkTargets([
        { value: '피닉스바', target: '' },
        { value: '158,000', target: '' },
        { value: '', target: 'color' },
        { value: '푸쉬타입', target: 'handle' }
    ])""")

    assert got == [{"target": "handle", "value": "푸쉬타입"}]


# --------------------------------------------------------------------------- #
# 빈 칸만 있을 때 — 확인창 없이 네 칸
# --------------------------------------------------------------------------- #

@_needs_node
def test_fill_all_puts_every_blank_field_without_asking():
    """네 칸이 다 비어 있으면 **묻지 않고** 넣는다.

    ``'상담'`` 은 빈 값으로 센다(신규 항목의 색상·손잡이 기본값). 여기서 묻기 시작하면
    신규 항목마다 확인창이 뜨고, 확인창이 늘 뜨면 사람이 읽지 않고 누른다.
    """
    got = _run(_BULK_FUNCTIONS, setup=_SCENE, expression="""(function () {
    var scene = makeBulkScene({ color: '상담', handle: '상담' });
    var asked = [];
    asked.answer = false;
    var out = dockFillAll(PLAN, scene.rows, null, record(asked));
    return {
        ok: out.ok, itemLabel: out.itemLabel, filled: out.filled, skipped: out.skipped,
        asked: asked.length,
        values: {
            product_name: scene.fields.product_name.value,
            color: scene.fields.color.value,
            handle: scene.fields.handle.value,
            spec_width: scene.fields.spec_width.value
        },
        events: firedEvents.map(function (e) { return e.type + (e.bubbles ? '+bubble' : ''); })
    };
})()""")

    assert got["ok"] is True
    assert got["asked"] == 0, "빈 칸만 있는데 확인창이 떴다"
    assert got["itemLabel"] == "항목 1"
    assert got["filled"] == ["제품명", "색상", "손잡이", "W(가로·총폭)"]
    assert got["skipped"] == []
    assert got["values"] == {"product_name": "150（무몰딩）", "color": "클린 화이트",
                             "handle": "푸쉬타입", "spec_width": "3720"}
    # 칸마다 두 발 — 하나라도 빠지면 화면에는 보이는데 저장이 안 된다.
    assert got["events"] == ["input+bubble", "change+bubble"] * 4


@_needs_node
def test_fill_all_reveals_only_the_first_field():
    """데려가는 칸은 **첫 칸 하나**다 — 네 번 스크롤하면 화면이 흔들린다."""
    got = _run(_BULK_FUNCTIONS, setup=_SCENE, expression="""(function () {
    var scene = makeBulkScene({});
    dockFillAll(PLAN, scene.rows, null, no);
    return ['product_name', 'color', 'handle', 'spec_width'].map(function (key) {
        return [scene.fields[key].scrolled, scene.fields[key].focused];
    });
})()""")

    assert got == [[True, True], [False, False], [False, False], [False, False]]


# --------------------------------------------------------------------------- #
# 값이 있는 칸 — 확인창은 한 번, 취소해도 빈 칸은 채운다
# --------------------------------------------------------------------------- #

@_needs_node
def test_fill_all_asks_once_and_lists_every_field_it_would_overwrite():
    """확인창은 **한 번**만 뜨고, 덮어쓸 칸을 전부 글자로 적는다.

    되돌리기가 없다 — ``field.value =`` 대입은 브라우저 네이티브 undo 스택도 지운다.
    이 문구가 유일한 게이트라 '지금 값'과 '넣을 값'이 둘 다 보여야 한다.
    """
    got = _run(_BULK_FUNCTIONS, setup=_SCENE, expression="""(function () {
    var scene = makeBulkScene({ product_name: '로라 무몰딩 여닫이', color: '포그 그레이' });
    var asked = [];
    asked.answer = false;
    dockFillAll(PLAN, scene.rows, null, record(asked));
    return { count: asked.length, text: asked[0] };
})()""")

    assert got["count"] == 1, "확인창이 칸마다 떴다"
    text = got["text"]
    assert "항목 1" in text and "사람이 볼 칸 2개" in text
    assert "· 제품명: 로라 무몰딩 여닫이 → 150（무몰딩）" in text
    assert "· 색상: 포그 그레이 → 클린 화이트" in text
    assert "손잡이" not in text, "비어 있는 칸까지 확인창에 적었다"
    assert "취소하면 비어 있는 칸 2개만 넣습니다" in text


@_needs_node
def test_cancelling_keeps_the_written_values_and_still_fills_the_blanks():
    """취소는 "덮어쓰지 마라"다 — 빈 칸은 그래도 채운다(잃을 값이 없다).

    취소가 전부 취소면 사람은 칩을 다시 네 번 눌러야 한다. 그러면 일괄 입력 버튼이
    존재할 이유가 사라진다.
    """
    got = _run(_BULK_FUNCTIONS, setup=_SCENE, expression="""(function () {
    var scene = makeBulkScene({ product_name: '로라 무몰딩 여닫이', color: '포그 그레이' });
    var out = dockFillAll(PLAN, scene.rows, null, no);
    return {
        ok: out.ok, filled: out.filled, skipped: out.skipped,
        product_name: scene.fields.product_name.value,
        color: scene.fields.color.value,
        handle: scene.fields.handle.value,
        spec_width: scene.fields.spec_width.value
    };
})()""")

    assert got["ok"] is True
    assert got["filled"] == ["손잡이", "W(가로·총폭)"]
    assert got["skipped"] == ["제품명", "색상"]
    assert got["product_name"] == "로라 무몰딩 여닫이", "취소했는데 덮어썼다"
    assert got["color"] == "포그 그레이", "취소했는데 덮어썼다"
    assert got["handle"] == "푸쉬타입"
    assert got["spec_width"] == "3720"


@_needs_node
def test_accepting_overwrites_every_field_in_plan_order():
    """승낙하면 계획 순서 그대로 네 칸을 전부 덮는다."""
    got = _run(_BULK_FUNCTIONS, setup=_SCENE, expression="""(function () {
    var scene = makeBulkScene({ product_name: '옛 이름', color: '포그 그레이',
                                handle: '바 타입', spec_width: '1500' });
    var out = dockFillAll(PLAN, scene.rows, null, yes);
    return {
        filled: out.filled, skipped: out.skipped,
        values: ['product_name', 'color', 'handle', 'spec_width'].map(function (key) {
            return scene.fields[key].value;
        })
    };
})()""")

    assert got["filled"] == ["제품명", "색상", "손잡이", "W(가로·총폭)"]
    assert got["skipped"] == []
    assert got["values"] == ["150（무몰딩）", "클린 화이트", "푸쉬타입", "3720"]


# --------------------------------------------------------------------------- #
# 규격 행이 여럿 — 비어 있어도 사람이 본다
# --------------------------------------------------------------------------- #

@_needs_node
def test_many_spec_rows_make_the_width_field_a_question_even_when_blank():
    """규격 행이 둘 이상이면 W 칸이 비어 있어도 묻는다 — 어느 행인지는 사람의 판단이다.

    칩 하나 경로(``dockFillFromChip``)와 **같은 규칙**이다. 두 길이 다르면 사람이 어느
    쪽에서 물어볼지 예측하지 못한다.
    """
    got = _run(_BULK_FUNCTIONS, setup=_SCENE, expression="""(function () {
    var scene = makeBulkScene({ specRows: 3 });
    var asked = [];
    asked.answer = false;
    var out = dockFillAll(PLAN, scene.rows, null, record(asked));
    return { text: asked[0], filled: out.filled, skipped: out.skipped,
             width: scene.fields.spec_width.value };
})()""")

    assert "규격 행이 3개입니다 — 1행에 넣습니다." in got["text"]
    assert got["skipped"] == ["W(가로·총폭)"]
    assert got["filled"] == ["제품명", "색상", "손잡이"]
    assert got["width"] == "", "규격 행이 여럿인데 확인 없이 W 칸에 넣었다"


# --------------------------------------------------------------------------- #
# 넣을 것이 없을 때 — 조용히 성공했다고 말하지 않는다
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("expression, reason", [
    ("dockFillAll([], [], null, yes)", "넣을 칩이 없습니다"),
    ("dockFillAll(PLAN, [], null, yes)", "넣을 항목이 없습니다"),
])
@_needs_node
def test_fill_all_says_why_it_did_nothing(expression: str, reason: str):
    """넣을 칩이나 항목이 없으면 **이유를 글자로** 말한다(성공으로 위장하지 않는다)."""
    got = _run(_BULK_FUNCTIONS, setup=_SCENE,
               expression="(function () { var out = " + expression
                          + "; return { ok: out.ok, reason: out.reason }; })()")

    assert got["ok"] is False
    assert got["reason"] == reason


# --------------------------------------------------------------------------- #
# 버튼이 실제로 화면에 있고 눌린다 (판단 함수만 맞아도 화면에 없으면 없는 기능이다)
# --------------------------------------------------------------------------- #

def test_the_dock_head_carries_the_fill_all_button_and_the_click_path():
    """머리줄에 버튼이 서고, 클릭 위임이 그 버튼을 **칩보다 먼저** 잡는다.

    판단 함수만 맞고 버튼이 없으면 담당자에게는 없는 기능이다. 클릭 위임이 칩 갈래보다
    뒤에 오면, 버튼에 칩 속성이 생기는 순간(오타 하나면 된다) 칩 갈래가 먼저 먹는다.
    """
    source = _source()

    assert "data-naver-dock-fill-all" in source, "일괄 입력 버튼이 화면에 없다"
    assert "naver-dock-fillall" in source, "버튼에 스타일 걸이가 없다"
    fill_at = source.index("closest('[data-naver-dock-fill-all]')")
    chip_at = source.index("closest('[data-naver-dock-copy]')")
    assert fill_at < chip_at, "칩 갈래가 일괄 입력 갈래보다 먼저 잡는다"


def test_the_button_locks_itself_when_the_order_has_more_than_one_main():
    """본품이 둘 이상이면 버튼을 잠근다 — 어느 집 값을 넣을지는 사람의 판단이다.

    한 주문에 집이 둘이면 도크에 본품 블록이 둘 그려지고, 칩도 두 벌이다. 그때 '먼저 나온
    칩'은 그저 **첫째 집**이라는 뜻이라 두 번째 집을 편집 중인 사람에게는 틀린 값이다.
    """
    source = _source()
    at = source.index("data-naver-dock-fill-all")
    window = source[at:at + 600]

    assert "state.mains.length > 1" in window, "본품 2개 이상일 때 잠그는 갈래가 없다"
    assert "disabled = true" in window
