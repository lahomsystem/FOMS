"""여러 명 같이 작업 — 문장 속 이름은 "외 n명" + 맞는 토씨, 칸 표시는 "외 n" 그대로(설계서 2026-11-25 multi-holder Q20).

셋 · 넷 · 다섯이 작업하는 줄로 서버가 만드는 문장을 글자 그대로 단언한다: 넘김 · 경합("먼저 시작했어요" · "먼저 완료했어요" ·
"그사이 … 완료했어요") · 남의 완료 되돌리기 거절 · 검수 막힘 · 검수 완료 먼저 · 공장 옮김 막힘 · 보내기 전 경고. "명"은 받침이 있어
토씨가 이 · 을 · 에게(지금 토씨 함수 그대로). 둘까지는 이름만(지금 글 그대로). 이름은 모두 지어낸 값이다.

되돌리면 실패: 문장에 칸 꼴 "외 2이" 쓰기 · 칸 표시에 "명" 붙이기.
"""
from __future__ import annotations

import datetime
from types import SimpleNamespace

from foms.services.drawing_fix_progress import drawing_parts, worked_sentence, worked_warnings
from foms.services.orders.drawing_factory import sheet_work, work_block_message, work_people
from foms.services.production import mark_crew as mc
from foms.services.production.factory_scope import elsewhere_line
from foms.services.production.part_mark_gates import inspect_gate
from foms.services.production.part_mark_rules import MARK_COLUMNS
from foms.services.production.part_progress import marks_by_part
from tests.support.production_part_claim_seed import code, login, make_order, make_user, mark

T0 = datetime.datetime(2026, 11, 25, 0, 10)
CUT3 = ("이시영", "김재단", "박재단")


def _row(key: str, part: str, people, *, done: bool = False):
    """새 코드가 쓴 꼴의 표시 줄(목록 + 요약 칸). ``done`` 이면 모두 자기 몫 완료."""
    crew = [mc.member(100 + j, name, mc.to_iso(T0), done_at=mc.to_iso(T0) if done else None,
                      done_uid=100 + j if done else None, done_name=name if done else None)
            for j, name in enumerate(people)]
    base = {column: None for column in MARK_COLUMNS}
    base.update(mc.summarize(crew), holders=crew, drawing_key=key, part=part, updated_at=T0)
    return SimpleNamespace(**base)


def test_sentence_form_counts_people_and_cell_form_stays():
    assert mc.name_sentence(["이시영", "김재단"]) == "이시영 · 김재단"  # 둘까지는 지금 그대로
    assert mc.name_sentence(["이시영", "김재단", "박재단"]) == "이시영 · 김재단 외 1명"
    assert mc.name_line(["이시영", "김재단", "박재단"]) == "이시영 · 김재단 외 1"  # 칸 표시는 그대로
    assert elsewhere_line("cut", "need", picked=mc.name_line(CUT3), done=None) == "이시영 · 김재단 외 1 작업 중"


# --------------------------------------------------------------------------- #
# 쓰기 API 글(넘김 · 경합 · 거절)
# --------------------------------------------------------------------------- #
def _crew(client, order, names, part="cut"):
    people = [make_user(name, part=part) for name in names]
    for who in people:
        login(client, who)
        assert mark(client, order, 0, part, "take", "none").status_code == 200
    return people


def test_late_take_and_conflicts_use_counted_sentence(client):
    order = make_order(2)
    _crew(client, order, CUT3)
    login(client, make_user("최재단", part="cut"))
    four = mark(client, order, 0, "cut", "take", "none").get_json()["data"]
    assert four["notice"] == "이시영 · 김재단 외 1명이 먼저 시작했어요."
    login(client, make_user("정재단", part="cut"))
    five = mark(client, order, 0, "cut", "take", "none").get_json()["data"]
    assert five["notice"] == "이시영 · 김재단 외 2명이 먼저 시작했어요."
    basic = mark(client, order, 1, "cut", "basic", "none")  # 대조: 빈 장은 그대로 됨
    assert basic.status_code == 200
    login(client, make_user("한재단", part="cut"))
    clash = mark(client, order, 0, "cut", "basic", "none")
    assert (code(clash), clash.get_json()["error"]) == ("MARK_CONFLICT", "이시영 · 김재단 외 3명이 먼저 시작했어요.")


def test_finished_crew_sentences_for_late_take_takeover_and_undo(client):
    order = make_order(1)
    people = _crew(client, order, CUT3)
    for who in people:
        login(client, who)
        assert mark(client, order, 0, "cut", "done", "need").status_code == 200
    login(client, make_user("최재단", part="cut"))
    late = mark(client, order, 0, "cut", "take", "none")
    assert late.get_json()["error"] == "이시영 · 김재단 외 1명이 먼저 완료했어요"
    swap = mark(client, order, 0, "cut", "takeover", "need", seen_by=people[0].id)
    assert swap.get_json()["error"] == "그사이 이시영 · 김재단 외 1명이 완료했어요. 더 할 일은 없어요."
    undo = mark(client, order, 0, "cut", "undo", "done")
    assert (code(undo), undo.get_json()["error"]) == (
        "UNDO_NOT_MINE", "내가 완료한 것만 되돌릴 수 있어요. 이시영 · 김재단 외 1명이 완료한 것은 이시영 · 김재단 외 1명에게 말해 주세요.")


# --------------------------------------------------------------------------- #
# 검수 문 · 공장 옮김 막힘 · 보내기 전 경고(순수)
# --------------------------------------------------------------------------- #
def test_inspect_gate_sentences():
    marks = [_row("k", "cut", CUT3)]
    left = inspect_gate({}, marks, "k", "inspect", "take")
    assert left.message == ("아직 검수할 수 없어요. 재단(이시영 · 김재단 외 1명 작업 중) · 엣지(담당 미정) · 조립(담당 미정)이 "
                            "미완료예요. 완료되면 검수할 수 있어요.")
    assert left.extra["left"][0] == {"part": "cut", "holder": "이시영 · 김재단 외 1"}  # 자료 칸은 칸 꼴 그대로
    inspected = [_row("k", "inspect", ("윤검수", "강검수", "오검수", "임검수"), done=True)]
    first = inspect_gate({}, inspected, "k", "edge", "undo")
    assert first.message == ("윤검수 · 강검수 외 2명이 이 장 검수를 완료했어요. 엣지 완료를 취소하려면 윤검수 · 강검수 외 2명에게 "
                             "검수 완료부터 취소해 달라고 해 주세요.")


def _move(rows):
    work = sheet_work("k", rows)
    return work, work_block_message(work, from_factory=1, to_factory=2, people=work_people("k", rows, work))


def test_factory_move_block_sentences():
    held, held_text = _move([_row("k", "edge", ("김민준", "박엣지", "최엣지"))])
    assert held == {"kind": "held", "part": "edge", "name": "김민준 · 박엣지 외 1"}  # 자료 칸은 칸 꼴 · 꼴 그대로
    assert held_text == ("2공장으로 옮길 수 없어요 — 1공장 김민준 · 박엣지 외 1명이 엣지 작업 중이에요. "
                         "김민준 · 박엣지 외 1명에게 시작 취소를 부탁한 뒤 다시 해 주세요.")
    _done, done_text = _move([_row("k", "edge", ("김민준", "박엣지", "최엣지", "정엣지"), done=True)])
    assert done_text == ("2공장으로 옮길 수 없어요 — 1공장에서 김민준 · 박엣지 외 2명이 엣지를 이미 완료한 장이에요. "
                         "이미 완료한 장은 옮기지 않아요.")
    _two, two_text = _move([_row("k", "edge", ("김민준", "박엣지"))])  # 대조: 둘까지는 지금 글
    assert "1공장 김민준 · 박엣지가 엣지 작업 중이에요. 김민준 · 박엣지에게 시작 취소를" in two_text


def test_send_warning_sentence_and_cell_name():
    marks = [_row("k", "edge", ("박엣지", "최엣지", "김엣지"))]
    parts = drawing_parts({"key": "k"}, marks_by_part(marks), hand_parts=(), step_names={}, made=False)
    assert parts["edge"] == {"state": "working", "name": "박엣지 · 최엣지 외 1"}  # 공장 진행 칸(칸 표시) · 자료 꼴 그대로
    warned = worked_warnings({}, marks, [(3, {"key": "k"})])
    assert warned[0]["text"] == "도면 3은 박엣지 · 최엣지 외 1명이 엣지 작업 중인 도면입니다. 보내면 공장에서 다시 작업해야 합니다."
    two = drawing_parts({"key": "k"}, marks_by_part([_row("k", "edge", ("박엣지", "최엣지"))]), hand_parts=(),
                        step_names={}, made=False)
    assert worked_sentence(3, two) == "도면 3은 박엣지 · 최엣지가 엣지 작업 중인 도면입니다. 보내면 공장에서 다시 작업해야 합니다."  # 대조: 둘
