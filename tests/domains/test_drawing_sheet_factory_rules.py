"""장의 공장 — 순수 규칙(설계서 2026-11-23 §4-13 · §4-14 '살아 있음' · §4-15 · §6-3, 3단계 ③). 쿼리 0.

``foms/services/orders/drawing_factory.py`` 의 함수 뜻을 고정한다(다음 묶음 화면 · 공장별 완료 · 상차 줄이 그대로 쓴다).
API(권한 · 막음 · 쓰기)는 ``test_drawing_sheet_factory_api.py``. 이름은 모두 지어낸 값이다.

되돌리면 실패: 시트 신원보다 key 를 먼저 봄 · 표가 비었는데 2공장으로 봄 · 1 · 2 밖 값을 믿음 · NONE 줄을 '일 시작'으로 · 기본을 완료 밖으로 ·
완료보다 담당을 먼저 알림 · 글 꼴 · 새 key 가 와도 공장 완료가 살아 있음 · 1공장뿐인 주문에 상차 줄 · 시공 대기 뒤에 "(제작 중)".
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from foms.services.orders.drawing_factory import (
    FactoryChange,
    SheetFactoryRefusal,
    apply_factory_changes,
    change_note,
    change_rows,
    current_factories,
    factory_by_key,
    factory_by_sheet,
    factory_done_entry,
    factory_done_message,
    hand_checked_parts,
    has_second_factory,
    load_split,
    plan_factory_changes,
    present_factories,
    sheet_factory,
    sheet_work,
    strip_client_factory_state,
    work_block_message,
)


def _sd(n: int = 3, *, table=None, stage: str = "PRODUCTION", direct: int = 0, wizard=(), done=None) -> dict:
    files = [{"key": f"k/d{j}.png", "filename": f"d{j}.png", "sheet_id": f"s{j}"} for j in range(n)]
    files += [{"key": f"k/up{j}.pdf", "filename": f"up{j}.pdf"} for j in range(direct)]
    sd = {"workflow": {"stage": stage}, "drawing_current_files": files,
          "drawing_wizard": {"sheets": [{"id": f"s{j}", "name": f"방{j}"} for j in range(n)] + [{"id": w, "name": w} for w in wizard]}}
    if table is not None:
        sd["drawing_factory"] = table
    if done is not None:
        sd["production"] = {"factory_done": done}
    return sd


def _mark(key: str, part: str, state: str, *, picked="", done_by=""):
    return SimpleNamespace(drawing_key=key, part=part, state=state, picked_by_name=picked or None, done_by_name=done_by or None)


# --------------------------------------------------------------------------- #
# 읽기
# --------------------------------------------------------------------------- #
def test_sheet_factory_reads_sheet_then_key_then_first_factory():
    sd = _sd(direct=1, table={"sheets": {"s1": 2}, "files": {"k/up0.pdf": 2, "k/d2.png": 2}})
    assert sheet_factory(sd, {"sheet_id": "s1", "key": "k/d1.png"}) == 2
    assert sheet_factory(sd, {"sheet_id": "s0", "key": "k/d0.png"}) == 1
    assert sheet_factory(sd, {"key": "k/up0.pdf"}) == 2  # 직접 올린 파일은 key 로
    assert sheet_factory(sd, {"key": "k/up9.pdf"}) == 1  # 같은 파일을 새로 올리면 새 key → 1공장(§16)
    assert sheet_factory(sd, {"sheet_id": "s9", "key": "k/new.png"}) == 1  # 시트 복제 = 새 신원 → 1공장
    one = _sd(table={"sheets": {"s1": 1}, "files": {"k/d1.png": 2}})
    assert sheet_factory(one, {"sheet_id": "s1", "key": "k/d1.png"}) == 1  # 시트 칸이 있으면 그 값이 먼저
    for bad in ({"sheets": {"s1": 3}}, {"sheets": {"s1": True}}, {"sheets": {"bad id!": 2}}, {"sheets": ["s1"]}, "2"):
        assert sheet_factory(_sd(table=bad), {"sheet_id": "s1"}) == 1, bad
    assert sheet_factory({}, {"sheet_id": "s1"}) == 1 and sheet_factory(None, {"key": "x"}) == 1


def test_current_present_and_sparse_maps():
    sd = _sd(direct=1, wizard=("s7",), table={"sheets": {"s1": 2, "s7": 2, "gone": 2}, "files": {"k/up0.pdf": 2}})
    assert [f for _e, f in current_factories(sd)] == [1, 2, 1, 2]
    assert present_factories(sd) == (1, 2) and has_second_factory(sd) is True
    assert factory_by_sheet(sd) == {"s1": 2, "s7": 2}  # 안 보낸 시트 포함, 어디에도 없는 열쇠는 뺀다
    assert factory_by_key(sd) == {"k/d1.png": 2, "k/up0.pdf": 2}
    plain = _sd()
    assert present_factories(plain) == (1,) and has_second_factory(plain) is False
    assert factory_by_sheet(plain) == {} and factory_by_key(plain) == {} and load_split(plain) is None
    only_unsent = _sd(wizard=("s7",), table={"sheets": {"s7": 2}})
    assert has_second_factory(only_unsent) is False  # 안 보낸 시트만 2공장 = 지금 장은 모두 1공장


# --------------------------------------------------------------------------- #
# 일이 시작된 장 · 걸린 것 글
# --------------------------------------------------------------------------- #
def test_sheet_work_none_only_is_not_started_and_done_beats_held():
    key = "k/d0.png"
    assert sheet_work(key, []) is None
    assert sheet_work(key, [_mark(key, "cut", "NONE"), _mark("k/d1.png", "edge", "DONE", done_by="김민준")]) is None
    held = [_mark(key, "edge", "NEED", picked="김민준"), _mark(key, "assemble", "NEED", picked="이조립")]
    assert sheet_work(key, held) == {"kind": "held", "part": "edge", "name": "김민준"}
    basic = held + [_mark(key, "cut", "BASIC", done_by="김재단")]
    assert sheet_work(key, basic) == {"kind": "done", "part": "cut", "name": "김재단"}  # 기본 = 완료(§4-1)


def test_block_messages_say_who_and_what_like_the_spec():
    done = {"kind": "done", "part": "cut", "name": "김재단"}
    assert work_block_message(done, from_factory=1, to_factory=2) == (
        "2공장으로 옮길 수 없어요 — 1공장에서 김재단이 재단을 이미 완료한 장이에요. 이미 완료한 장은 옮기지 않아요.")
    held = {"kind": "held", "part": "edge", "name": "김민준"}
    assert work_block_message(held, from_factory=1, to_factory=2) == (
        "2공장으로 옮길 수 없어요 — 1공장 김민준이 엣지 담당이에요. 김민준에게 맡기 취소를 부탁한 뒤 다시 해 주세요.")
    back = {"kind": "done", "part": "edge", "name": "최가은"}
    assert work_block_message(back, from_factory=2, to_factory=1).startswith(
        "1공장으로 옮길 수 없어요 — 2공장에서 최가은이 엣지를 이미 완료한 장이에요.")
    nameless = work_block_message({"kind": "held", "part": "inspect", "name": ""}, from_factory=1, to_factory=2)
    assert "1공장 다른 사람이 검수 담당이에요. 담당에게 맡기 취소를" in nameless
    entry = {"keys": [], "at": "2026-11-24T07:10:00", "by_name": "강검수"}
    assert factory_done_message(2, entry) == "2공장은 강검수가 11/24 16:10에 제작 완료했어요. 옮기려면 2공장 완료부터 취소해 주세요."


# --------------------------------------------------------------------------- #
# 공장 완료 표지 '살아 있음'(§4-14 — 3단계 ⑥ 이 쓴다, 여기서는 읽기만)
# --------------------------------------------------------------------------- #
def test_factory_done_entry_lives_only_while_current_keys_are_inside():
    table = {"sheets": {"s1": 2, "s2": 2}}
    entry = {"keys": ["k/d1.png", "k/d2.png"], "at": "2026-11-24T07:10:00", "by_name": "강검수"}
    assert factory_done_entry(_sd(table=table, done={"2": entry}), 2) == entry
    assert factory_done_entry(_sd(table=table, done={"2": entry}), 1) is None
    newer = _sd(table=table, done={"2": entry})
    newer["drawing_current_files"][2]["key"] = "k/d2_v2.png"  # 새 판(새 key)이 오면 저절로 풀린다
    assert factory_done_entry(newer, 2) is None
    fewer = _sd(n=2, table=table, done={"2": entry})  # 품목 취소로 장이 빠짐 = 완료 그대로
    assert factory_done_entry(fewer, 2) == entry
    assert factory_done_entry(_sd(done={"2": entry}), 2) is None  # 2공장 장이 없음 = 있는 공장이 아님(버림)


# --------------------------------------------------------------------------- #
# 상차 줄(§4-15)
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(("stage", "done", "text"), [
    ("PRODUCTION", None, "상차 1공장 3장(제작 중) · 2공장 2장(제작 중)"),
    ("PRODUCTION", {"1": {"keys": ["k/d0.png", "k/d1.png", "k/d2.png"]}}, "상차 1공장 3장 · 2공장 2장(제작 중)"),
    ("CONSTRUCTION", None, "상차 1공장 3장 · 2공장 2장"),
    ("CONFIRM", None, "상차 1공장 3장 · 2공장 2장"),
])
def test_load_split_counts_each_factory_and_tails_unfinished_in_production(stage, done, text):
    sd = _sd(n=5, stage=stage, done=done, table={"sheets": {"s3": 2, "s4": 2}})
    split = load_split(sd)
    assert split["text"] == text
    assert [(f["factory"], f["sheets"]) for f in split["factories"]] == [(1, 3), (2, 2)]


# --------------------------------------------------------------------------- #
# 옮김 계획 · 쓰기(순수)
# --------------------------------------------------------------------------- #
def _no_marks():
    raise AssertionError("표시 줄을 읽으면 안 되는 경우")


def test_plan_skips_same_values_and_reads_marks_for_current_sheets_in_any_stage():
    sd = _sd(wizard=("s7",), table={"sheets": {"s1": 2}})
    assert plan_factory_changes(sd, [{"sheet_id": "s1", "factory": 2}, {"sheet_id": "s0", "factory": 1}],
                                stage="PRODUCTION", load_marks=_no_marks) == []
    unsent = plan_factory_changes(sd, [{"sheet_id": "s7", "factory": 2}], stage="PRODUCTION", load_marks=_no_marks)
    assert unsent == [FactoryChange("sheet", "s7", 1, 2, ())]  # 안 보낸 시트만 = 표시 줄을 안 읽는다
    early = plan_factory_changes(sd, [{"sheet_id": "s0", "factory": 2}], stage="DRAWING", load_marks=lambda: [])
    assert early == [FactoryChange("sheet", "s0", 1, 2, ("k/d0.png",))]  # 한 번도 생산에 안 간 주문 = 표시 줄 없음 → 됨
    by_key = plan_factory_changes(sd, [{"key": "k/d2.png", "factory": 2}], stage="CONFIRM", load_marks=lambda: [])
    assert by_key == [FactoryChange("sheet", "s2", 1, 2, ("k/d2.png",))]  # 시트 신원이 있는 파일을 key 로 보내도 시트로


def test_plan_refuses_unknown_done_order_and_started_sheets_all_or_nothing():
    sd = _sd(direct=1)
    with pytest.raises(SheetFactoryRefusal) as unknown:
        plan_factory_changes(sd, [{"sheet_id": "nope", "factory": 2}], stage="DRAWING", load_marks=_no_marks)
    assert unknown.value.code == "DRAWING_NOT_CURRENT" and unknown.value.status == 409
    with pytest.raises(SheetFactoryRefusal) as shape:  # 모양이 다른 시트 신원은 key 로 넘어가지 않고 그 값을 알려 준다
        plan_factory_changes(sd, [{"sheet_id": "방 1!", "key": "k/d0.png", "factory": 2}], stage="DRAWING", load_marks=_no_marks)
    assert shape.value.extra == {"sheet_id": "방 1!"}
    with pytest.raises(SheetFactoryRefusal) as late:
        plan_factory_changes(sd, [{"sheet_id": "s0", "factory": 2}], stage="CONSTRUCTION", load_marks=_no_marks)
    assert (late.value.code, late.value.message) == ("ORDER_DONE", "이미 제작 완료한 주문이에요.")
    marks = [_mark("k/d1.png", "edge", "NEED", picked="김민준")]
    with pytest.raises(SheetFactoryRefusal) as busy:
        plan_factory_changes(sd, [{"sheet_id": "s0", "factory": 2}, {"sheet_id": "s1", "factory": 2}],
                             stage="PRODUCTION", load_marks=lambda: marks)
    assert busy.value.code == "SHEET_HAS_WORK" and busy.value.message.startswith("2공장으로 옮길 수 없어요 — 1공장 김민준이")
    assert [b["key"] for b in busy.value.extra["blocked"]] == ["k/d1.png"]


@pytest.mark.parametrize("stage", ["CONFIRM", "DRAWING", None])
def test_started_sheet_is_refused_even_after_stage_was_moved_back(stage):
    """강제 단계 변경으로 생산에서 고객컨펌 · 도면으로 되돌린 주문 — 표시 줄이 남아 있으면 단계와 상관없이 막는다."""
    marks = [_mark("k/d0.png", "cut", "DONE", done_by="김재단")]
    with pytest.raises(SheetFactoryRefusal) as busy:
        plan_factory_changes(_sd(stage=stage or ""), [{"sheet_id": "s0", "factory": 2}], stage=stage, load_marks=lambda: marks)
    assert busy.value.code == "SHEET_HAS_WORK" and busy.value.extra["blocked"][0]["kind"] == "done"


def test_hand_checked_step_blocks_every_current_sheet_like_finished_work():
    """반장이 공정 칸을 통째 손 체크(그 파트 카드 0장) = 모든 장이 그 공정 완료 → 옮기지 못한다(사장님 '아무도 맡거나 완료하지
    않은 장만'). 카드를 쓴 파트는 칸이 켜져 있어도 장마다 표시 줄로 본다(대조군)."""
    sd = _sd(wizard=("s7",))
    sd["production"] = {"steps": [{"key": k, "done": k in ("cut", "edge")} for k in ("cut", "edge", "assemble", "inspect")]}
    assert hand_checked_parts(sd, []) == ("cut", "edge")
    with pytest.raises(SheetFactoryRefusal) as hand:
        plan_factory_changes(sd, [{"sheet_id": "s0", "factory": 2}], stage="PRODUCTION", load_marks=lambda: [])
    assert hand.value.code == "SHEET_HAS_WORK"
    assert hand.value.message == ("2공장으로 옮길 수 없어요 — 재단 · 엣지가 이미 완료로 체크된 주문이에요. "
                                  "옮기려면 공정 체크부터 해제해 주세요.")
    assert hand.value.extra["blocked"][0]["kind"] == "hand" and hand.value.extra["blocked"][0]["parts"] == ["cut", "edge"]
    one = work_block_message({"kind": "hand", "part": "cut", "parts": ["cut"], "name": ""}, from_factory=1, to_factory=2)
    assert one.endswith("재단이 이미 완료로 체크된 주문이에요. 옮기려면 공정 체크부터 해제해 주세요.")
    used = [_mark("k/d1.png", "cut", "NEED", picked="김재단"), _mark("k/d2.png", "edge", "NONE")]  # 재단은 카드를 썼다
    assert hand_checked_parts(sd, used) == ("edge",)  # 엣지는 NONE 줄만 = 카드를 안 쓴 파트
    assert plan_factory_changes(sd, [{"sheet_id": "s7", "factory": 2}], stage="PRODUCTION", load_marks=_no_marks)  # 안 보낸 시트는 됨


def test_residual_factory_done_is_ignored_outside_production_but_work_still_blocks():
    sd = _sd(stage="CONFIRM", table={"sheets": {"s2": 2}},
             done={"2": {"keys": ["k/d2.png"], "at": "2026-11-24T07:10:00", "by_name": "강검수"}})
    assert plan_factory_changes(sd, [{"sheet_id": "s0", "factory": 2}], stage="CONFIRM", load_marks=lambda: [])  # 취소할 화면이 없다


def test_strip_client_factory_state_removes_both_server_owned_fields():
    sd = {"drawing_factory": {"sheets": {"s1": 2}}, "production": {"steps": [], "factory_done": {"2": {}}}, "items": []}
    assert strip_client_factory_state(sd) == ["drawing_factory", "production.factory_done"]
    assert sd == {"production": {"steps": []}, "items": []}
    assert strip_client_factory_state({"items": []}) == [] and strip_client_factory_state(None) == []


def test_plan_refuses_moves_in_or_out_of_a_finished_factory():
    table = {"sheets": {"s2": 2}}
    sd = _sd(table=table, done={"2": {"keys": ["k/d2.png"], "at": "2026-11-24T07:10:00", "by_name": "강검수"}})
    for item in ({"sheet_id": "s0", "factory": 2}, {"sheet_id": "s2", "factory": 1}):
        with pytest.raises(SheetFactoryRefusal) as done:
            plan_factory_changes(sd, [item], stage="PRODUCTION", load_marks=lambda: [])
        assert done.value.code == "FACTORY_DONE" and done.value.extra == {"factory": 2}


def test_apply_writes_twos_only_removes_ones_and_prunes_stale_keys():
    sd = _sd(direct=1, table={"sheets": {"s1": 2, "gone": 2}, "files": {"k/old.pdf": 2}})
    changes = [FactoryChange("sheet", "s1", 2, 1, ("k/d1.png",)), FactoryChange("sheet", "s2", 1, 2, ("k/d2.png",)),
               FactoryChange("file", "k/up0.pdf", 1, 2, ("k/up0.pdf",))]
    rows = change_rows(sd, changes)
    apply_factory_changes(sd, changes, by_name="오가람", at_iso="2026-11-24T01:00:00")
    assert sd["drawing_factory"] == {"sheets": {"s2": 2}, "files": {"k/up0.pdf": 2}, "at": "2026-11-24T01:00:00",
                                     "by_name": "오가람"}
    assert [(r["index"], r["total"], r["name"], r["from"], r["to"]) for r in rows] == [
        (2, 4, "방1", 2, 1), (3, 4, "방2", 1, 2), (4, 4, "up0.pdf", 1, 2)]
    assert change_note(rows) == "도면 2/4 2공장 → 1공장, 도면 3/4 1공장 → 2공장, 도면 4/4 1공장 → 2공장"
    unsent = change_rows(_sd(wizard=("s7",)), [FactoryChange("sheet", "s7", 1, 2, ())])
    assert change_note(unsent) == "시트 's7' 1공장 → 2공장"
