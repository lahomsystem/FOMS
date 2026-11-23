"""생산 파트 진행 · 완료 판정 · 검수 순서 · 손 체크 막힘 — 순수 계산(설계서 2026-11-23 §4-1 ~ §4-3 · §4-7, 쿼리 0).

되돌리면 실패: NONE 줄만 있는 파트를 카드를 쓴 파트로 치기 · 카드를 쓴 주문을 칸 규칙으로만 보기(3/5 에서 완료 · 칸을 안 켜도
완료) · 카드를 안 쓴 파트의 칸 체크를 무시 · 재단 BASIC 을 미완료로 치기 · 다른 장 때문에 이 장 검수를 막기 · 손 체크 막힘 글자를
바꾸기 · 칸 ``via`` 를 끌 때 남기기.
대조군: 카드를 안 쓴 주문은 지금 칸 규칙과 같은 답 · 같은 글(지금 시험 그대로) · 카드를 안 쓴 파트 칸 체크는 늘 된다.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from foms.services.production import steps as steps_mod
from foms.services.production.part_mark_gates import inspect_gate, step_cell_gate
from foms.services.production.part_progress import (
    cards_used,
    complete_block_body,
    complete_ready,
    complete_state,
    inspect_left,
    inspect_ready,
    part_done,
    part_progress,
    step_api_extras,
)
from tests.support.production_steps_seed import inspected_steps

KEYS = ("k1", "k2", "k3", "k4", "k5")


def _sd(n: int = 5, *, on: tuple[str, ...] = ()) -> dict:
    steps = [dict(s, done=s["key"] in on, at=None, by_name="박반장" if s["key"] in on else None)
             for s in inspected_steps()]
    return {"drawing_current_files": [{"key": k} for k in KEYS[:n]], "production": {"steps": steps}}


def _m(key: str, part: str, state: str, holder: str | None = None, done_by: str | None = None) -> SimpleNamespace:
    return SimpleNamespace(drawing_key=key, part=part, state=state, picked_by_name=holder, done_by_name=done_by)


def _all(part: str, state: str = "DONE", n: int = 5) -> list[SimpleNamespace]:
    return [_m(k, part, state) for k in KEYS[:n]]


# --------------------------------------------------------------------------- #
# §4-1 낱말
# --------------------------------------------------------------------------- #
def test_cards_used_skips_none_only_parts_and_counts_old_keys():
    assert cards_used([]) == set()
    assert cards_used([_m("k1", "cut", "NONE"), _m("old", "edge", "NONE")]) == set()  # 맡았다 취소 = 안 쓴 것
    assert cards_used([_m("old", "edge", "NEED"), _m("k1", "cut", "BASIC")]) == {"edge", "cut"}  # 옛 판 key 도 표지
    assert cards_used([_m("k1", "paint", "DONE")]) == set()  # 모르는 파트는 버린다


def test_part_progress_card_part_counts_sheets_and_basic_finishes_cut():
    marks = [_m("k1", "cut", "DONE"), _m("k2", "cut", "BASIC"), _m("k3", "cut", "DONE"), _m("k4", "cut", "NEED")]
    progress = part_progress(_sd(on=("cut",)), marks, "cut")  # 옛 칸이 켜져 있어도 카드가 기준(§4-2 옛 칸)
    assert (progress["uses_cards"], progress["done"], progress["done_n"], progress["total_n"]) == (True, False, 3, 5)
    assert progress["left_keys"] == ["k4", "k5"]
    edge_basic = [_m(k, "edge", "BASIC") for k in KEYS]  # BASIC 은 재단만 완료로 친다
    assert part_progress(_sd(), edge_basic, "edge")["done"] is False


def test_part_progress_part_without_cards_follows_the_step():
    checked = part_progress(_sd(on=("edge",)), [], "edge")
    assert (checked["uses_cards"], checked["done"], checked["done_n"], checked["left_keys"]) == (False, True, 5, [])
    off = part_progress(_sd(), [_m("k1", "edge", "NONE")], "edge")
    assert (off["done"], off["done_n"], off["left_keys"]) == (False, 0, list(KEYS))


def test_zero_drawings_falls_back_to_the_step_even_with_cards():
    marks = [_m("old", "cut", "DONE")]
    assert part_done(_sd(0), marks, "cut") is False and part_done(_sd(0, on=("cut",)), marks, "cut") is True


def test_factory_argument_is_reserved_for_the_second_factory_phase():
    with pytest.raises(NotImplementedError):
        part_progress(_sd(), [], "cut", factory=2)


# --------------------------------------------------------------------------- #
# §4-3 제작 완료 — 다섯 줄 + 도면 0장
# --------------------------------------------------------------------------- #
ALL_FOUR_BY_CARDS = _all("cut") + _all("edge") + _all("assemble") + _all("inspect")
COMPLETE_ROWS = [
    # (이름, sd, marks, ready)
    ("no_cards_no_steps", _sd(), [], True),
    ("no_cards_some_steps", _sd(on=("cut", "edge")), [], False),
    ("no_cards_four_steps", _sd(on=("cut", "edge", "assemble", "inspect")), [], True),
    ("cards_four_done_mixed", _sd(on=("edge",)), _all("cut") + _all("assemble") + _all("inspect"), True),
    ("cards_one_short", _sd(on=("cut", "edge", "assemble", "inspect")), ALL_FOUR_BY_CARDS[:-1], False),
]


@pytest.mark.parametrize("name,sd,marks,ready", COMPLETE_ROWS, ids=[r[0] for r in COMPLETE_ROWS])
def test_complete_state_table(name, sd, marks, ready):
    assert complete_state(sd, marks)["ready"] is ready and complete_ready(sd, marks) is ready
    assert (complete_block_body(sd, marks) is None) is ready


def test_cards_order_blocks_even_without_any_step_on():
    """2026-11-21 '칸을 쓴 주문만 막기'의 고침 — 카드를 쓴 주문은 칸을 하나도 안 켜도 막는다(§18 둘째)."""
    body = complete_block_body(_sd(), [_m("k1", "cut", "DONE")])
    assert body["code"] == "STEPS_INCOMPLETE" and body["missing_steps"][0] == {"key": "cut", "label": "재단"}
    assert body["message"] == "아직 미완료가 있어요 — 재단 4장 · 엣지 5장 · 조립 5장 · 검수 5장"
    assert body["left"] == {"cut": 4, "edge": 5, "assemble": 5, "inspect": 5}


def test_no_cards_body_is_exactly_the_old_step_rule():
    """대조군: 카드를 안 쓴 주문은 지금 글 · 꼴 그대로(``steps.production_complete_block_body`` 를 그대로 부른다)."""
    sd = _sd(on=("cut",))
    assert complete_block_body(sd, []) == steps_mod.production_complete_block_body(sd)
    assert complete_block_body(sd, [])["message"] == "검수까지 끝나야 제작 완료할 수 있어요. (남은 공정: 엣지 · 조립 · 검수)"
    assert complete_block_body(sd, [_m("k1", "cut", "NONE")]) == steps_mod.production_complete_block_body(sd)


def test_cards_order_with_zero_drawings_needs_all_four_steps():
    marks = [_m("gone", "cut", "DONE")]
    body = complete_block_body(_sd(0), marks)
    assert body["message"] == "도면이 없어요 — 공정 칸을 체크하거나 관리자에게 말해 주세요."
    assert complete_ready(_sd(0, on=("cut", "edge", "assemble", "inspect")), marks) is True


# --------------------------------------------------------------------------- #
# §4-7 검수 순서 — 장마다
# --------------------------------------------------------------------------- #
def test_inspect_ready_per_sheet_with_basic_cut_and_hand_checked_part():
    marks = [_m("k1", "cut", "BASIC"), _m("k1", "edge", "DONE"), _m("k1", "assemble", "DONE"),
             _m("k2", "cut", "NEED", holder="김재단")]
    assert inspect_ready(_sd(), marks, "k1") is True  # 재단 BASIC = 완료 · k2 가 안 끝나도 k1 검수는 된다
    assert inspect_left(_sd(), marks, "k2") == [
        {"part": "cut", "label": "재단", "holder": "김재단"},
        {"part": "edge", "label": "엣지", "holder": None},
        {"part": "assemble", "label": "조립", "holder": None}]
    no_edge_cards = [_m("k1", "cut", "DONE"), _m("k1", "assemble", "DONE")]
    assert inspect_ready(_sd(), no_edge_cards, "k1") is False
    assert inspect_ready(_sd(on=("edge",)), no_edge_cards, "k1") is True  # 카드를 안 쓴 엣지 = 칸 체크로


@pytest.mark.parametrize("action", ["take", "done", "takeover"])
def test_inspect_gate_blocks_until_ready_and_names_holders(action):
    marks = [_m("k1", "edge", "NEED", holder="김민준")]
    gate = inspect_gate(_sd(), marks, "k1", "inspect", action)
    assert gate.code == "INSPECT_NOT_READY" and gate.status == 409
    assert gate.message == ("아직 검수할 수 없어요. 재단(담당 미정) · 엣지(담당 김민준) · 조립(담당 미정)이 미완료예요. "
                            "완료되면 검수할 수 있어요.")
    assert gate.extra["left"] == [{"part": "cut", "holder": None}, {"part": "edge", "holder": "김민준"},
                                  {"part": "assemble", "holder": None}]
    assert inspect_gate(_sd(), marks, "k1", "inspect", "release") is None  # 옛 검수 맡기 취소는 된다
    assert inspect_gate(_sd(), marks, "k1", "inspect", "undo") is None


def test_inspect_done_first_blocks_undo_of_earlier_parts_on_that_sheet():
    marks = [_m("k1", "inspect", "DONE", done_by="윤검수")]
    gate = inspect_gate(_sd(), marks, "k1", "edge", "undo")
    assert gate.code == "INSPECT_DONE_FIRST"
    assert gate.message == ("윤검수가 이 장 검수를 완료했어요. 엣지 완료를 취소하려면 윤검수에게 검수 완료부터 취소해 "
                            "달라고 해 주세요.")
    assert "기본을 취소하려면" in inspect_gate(_sd(), marks, "k1", "cut", "undo", undo_basic=True).message
    assert inspect_gate(_sd(), marks, "k2", "edge", "undo") is None  # 다른 장은 그대로
    assert inspect_gate(_sd(), [_m("k1", "inspect", "NEED")], "k1", "edge", "undo") is None


# --------------------------------------------------------------------------- #
# §4-2 공정 칸 손 체크 — 두 경우
# --------------------------------------------------------------------------- #
def test_step_cell_gate_card_part_with_sheets_left_refuses_with_exact_message():
    marks = [_m(k, "cut", "DONE") for k in KEYS[:3]]  # 사장님 예: 5장 중 3장만 완료
    gate = step_cell_gate(_sd(), marks, "cut", True)
    assert (gate.status, gate.code) == (409, "PART_USES_CARDS")
    assert gate.message == "도면 2장이 아직 미완료예요. 남은 도면을 완료하면 자동으로 체크돼요."
    assert gate.extra == {"part": "cut", "left": 2, "total": 5}
    assert gate.body() == {"success": False, "data": {"code": "PART_USES_CARDS", "part": "cut", "left": 2, "total": 5},
                           "error": gate.message}
    assert step_cell_gate(_sd(), marks, "cut", False) is None  # 미완료가 있으면 끄기는 된다


def test_step_cell_gate_card_part_all_done_refuses_turning_off_only():
    gate = step_cell_gate(_sd(on=("cut",)), _all("cut"), "cut", False)
    assert gate.code == "STEP_SET_BY_CARDS"
    assert gate.message == "도면을 모두 완료해서 체크된 공정이에요. 취소하려면 그 파트 도면에서 [되돌리기]를 눌러 주세요."
    assert step_cell_gate(_sd(), _all("cut"), "cut", True) is None  # 미완료 0장 = 지금처럼 켜짐


def test_step_cell_gate_never_blocks_parts_without_cards_or_zero_drawings():
    """대조군: 카드를 안 쓴 파트(NONE 줄만 포함) · 확정 도면 0장 주문은 지금처럼 켜고 끈다."""
    for marks in ([], [_m("k1", "cut", "NONE")], _all("edge")):
        for done in (True, False):
            assert step_cell_gate(_sd(), marks, "cut", done) is None
    assert step_cell_gate(_sd(0), [_m("gone", "cut", "NEED")], "cut", True) is None


def test_step_api_extras_carry_sheet_count_and_progress():
    extras = step_api_extras(_sd(on=("edge",)), [_m("k1", "cut", "DONE")])
    assert extras["sheets"] == 5
    assert extras["parts"]["cut"] == {"uses_cards": True, "done": False, "done_n": 1, "total_n": 5, "via": None,
                                      "left_n": 4}
    assert extras["parts"]["edge"]["uses_cards"] is False and extras["parts"]["edge"]["done"] is True


def test_set_production_step_via_is_set_on_and_removed_off():
    sd: dict = {}
    steps_mod.set_production_step(sd, "cut", True, by_name="박반장", at_iso="t", via=steps_mod.STEP_VIA_SHEET)
    cut = sd["production"]["steps"][0]
    assert (cut["done"], cut["by_name"], cut["via"]) == (True, "박반장", "sheet")
    steps_mod.set_production_step(sd, "cut", False, by_name="박반장", at_iso="t")
    assert "via" not in sd["production"]["steps"][0] and sd["production"]["steps"][0]["by_name"] is None
    assert part_progress(_sd(on=("cut",)), [], "cut")["via"] is None  # 3판 전 옛 칸 — via 없음
