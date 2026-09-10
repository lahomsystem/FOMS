"""도크 금액 카드 — 낱말 + 돈 한 줄 (2026-09-10 사용자 지시로 2026-09-09 대조 줄·문장·안내문 폐기, Node 실행).

**왜 바뀌었나.** 2026-09-09 판은 예약금 칸을 읽어 "✓ 같다/⚠ 다르다" 대조 줄을 카드에 세우고,
목표액 문장("지금 값 100,000원에 1,290,850원을 더해 …")과 복사 칩·안내문("시스템이 넣지
않습니다 …")까지 붙였다. 사용자가 주문 #5206 화면에서 그 전부를 **'쓸데없는 설명문'** 으로
지목했다 — 원하는 것은 "추가 결제 금액이 얼마인지만 1,290,850원 간단히". 그래서 카드는
낱말(``relation_label``: 추가 결제·재결제·네이버 결제) + 돈 표기(``live_total_display``)
두 노드만 남는다.

남는 규율(뒤집지 않는다):

* **돈은 사람이 넣는다**(2026-09-08 확정 결정) — 카드에 ``data-naver-dock-target`` 은 없다.
* **폼 불가침** — 대조 줄이 사라졌으니 도크는 예약금 칸을 읽지도 듣지도 않는다(더 좁아졌다).
* **돈 표기는 서버가 만든다** — 화면은 ``live_total_display`` 를 그리기만 하고 다시 포맷하지
  않는다(두 화면이 같은 자릿수·같은 단위로 읽힌다).
"""

from __future__ import annotations

import pathlib

from tests.services.integrations.test_naver_dock_autofill_wire import _run
from tests.services.integrations.test_naver_dock_width_live import _extract_function, _needs_node

DOCK_JS = pathlib.Path("static/js/orders/erp-naver-dock.js").read_text(encoding="utf-8")

#: ``_run`` 의 프리앰블에는 ``el``·``state`` 가 없다 — 카드가 만드는 노드 모양만 받아 적는 스텁.
_STUB = """
function el(tag, className, text) {
    return { tag: tag, className: className || '',
             text: text === undefined || text === null ? '' : String(text),
             children: [],
             appendChild: function (node) { this.children.push(node); return node; } };
}
var state = { depositHint: null };
function shape(card) {
    return card ? { cls: card.className,
                    kids: card.children.map(function (k) { return [k.className, k.text]; }) } : null;
}
"""

#: 주문 #5206 모양의 서버 payload — 옛 키(문장·목표액·복사값)도 그대로 실려 온다.
_ADDON_HINT = ("{ state: 'differs', sentence: '지금 값 100,000원에 1,290,850원을 더해 1,390,850원으로 고치세요.',"
               " target_display: '1,390,850원', copy_value: '1390850', note: '',"
               " relation_label: '추가 결제', live_total_display: '1,290,850원' }")
_MATCH_HINT = _ADDON_HINT.replace("state: 'differs'", "state: 'match'")


@_needs_node
def test_deposit_card_is_the_relation_word_and_the_amount_only():
    """카드 = ``.naver-dock-deposit`` > ``-hd``(낱말) + ``-won``(돈) 두 노드뿐.

    목표액(1,390,850)·문장·복사값은 payload 에 실려 와도 카드 어디에도 없다 —
    사용자가 지운 설명문이 옛 키를 타고 되살아나면 안 된다.
    """
    got = _run(("buildDepositCard",), "shape(buildDepositCard())",
               setup=_STUB + "state.depositHint = " + _ADDON_HINT + ";")

    assert got == {"cls": "naver-dock-deposit",
                   "kids": [["naver-dock-deposit-hd", "추가 결제"],
                            ["naver-dock-deposit-won", "1,290,850원"]]}
    assert "1,390,850" not in str(got)
    assert "고치세요" not in str(got)


@_needs_node
def test_deposit_card_stands_on_the_amount_not_on_the_deposit_state():
    """``state`` 가 ``match`` 여도 카드는 선다 — 2026-09-09 의 "``differs`` 만" 조건 폐기.

    카드는 이제 "고쳐야 한다"는 경고가 아니라 "네이버에서 얼마 결제됐나"를 말하는 자리다.
    낱말과 돈 표기만 있으면 예약금 상태와 무관하게 그린다.
    """
    got = _run(("buildDepositCard",), "shape(buildDepositCard())",
               setup=_STUB + "state.depositHint = " + _MATCH_HINT + ";")

    assert got is not None
    assert len(got["kids"]) == 2
    assert got["kids"][0] == ["naver-dock-deposit-hd", "추가 결제"]


@_needs_node
def test_deposit_card_does_not_stand_without_a_relation_word_or_an_amount():
    """낱말이 비면(보통 주문)·돈 표기가 비면(금액 모름)·hint 가 없으면(옛 payload) 카드 없음."""
    got = _run(("buildDepositCard",), """[
        { relation_label: '', live_total_display: '704,200원' },
        { relation_label: '추가 결제', live_total_display: '' },
        null
    ].map(function (h) { state.depositHint = h; return shape(buildDepositCard()); })""",
               setup=_STUB)

    assert got == [None, None, None]


def test_the_dock_no_longer_reads_or_watches_the_deposit_field():
    """읽을 대조 줄이 없으니 폼을 읽지도 듣지도 않는다 — 폼 불가침 계약은 더 좁아졌다.

    2026-09-09 판은 ``data-erp="deposit_amount"`` 계약 속성으로 예약금 칸을 찾아 값을 견줬고
    ``input``/``change`` 를 문서 전역에서 들었다. 2026-09-10 사용자 지시로 대조 줄이 사라지며
    그 조회·리스너·판정 함수 셋 다 도크 소스에서 빠진다.
    """
    assert 'data-erp="deposit_amount"' not in DOCK_JS, "도크가 예약금 칸을 아직 찾는다"
    assert "erp-deposit-amount" not in DOCK_JS, "도크가 폼 id 를 읽는다"
    for gone in ("syncDepositMatch", "dockDepositMatch", "erpDepositField"):
        assert gone not in DOCK_JS, gone


def test_the_card_carries_no_explainer_nodes_and_no_autofill_target():
    """카드 본문에는 설명 노드가 없고, 자동 입력 칸 이름도 없다(돈은 사람이 넣는다 — 2026-09-08)."""
    body = _extract_function(DOCK_JS, "buildDepositCard")

    assert "setAttribute('data-naver-dock-target'" not in body, (
        "예약금 카드에 자동 입력 칸 이름이 붙었다")
    for gone in ("naver-dock-deposit-say", "naver-dock-deposit-state", "naver-dock-deposit-note",
                 "naver-dock-deposit-acts", "naver-dock-deposit-hint", "data-naver-dock-copy",
                 "hint.sentence", "hint.target", "hint.copy_value", "hint.note"):
        assert gone not in body, gone
    assert "naver-dock-deposit-hd" in body and "naver-dock-deposit-won" in body


def test_the_deposit_explainer_words_are_gone_from_the_dock_source():
    """사용자가 지목한 설명문 낱말들이 도크 소스 어디에도 없다(주석 포함)."""
    for gone in ("예약금(선금)에 넣을 금액", "시스템이 넣지 않습니다", "예약금 칸이 아직 다릅니다",
                 "facts.push(['예약금(선금)'", "depositFactLine"):
        assert gone not in DOCK_JS, gone
