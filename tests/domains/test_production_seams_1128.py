"""0-둘 이음매 셋 — 동작 그대로(설계서 2026-11-28 흐름 셋 §4-1 "0-둘" · §4-3 약속 3 · 10).

되돌리면 실패: 알람 빈 틀이 쿼리를 내거나 예외를 던지기 · 약속한 함수 이름 · 인자를 바꾸기 · ``parts_in_use`` 가 지금
``cards_used`` 와 다른 값을 내기(도면 있는 주문 — 0장 주문은 ``@order`` 줄만, ⓑ 검토 3) · ``BASIC_ALLOWED_PARTS`` 값이 재단 · 조립 둘이 아니게 되기(2026-11-28 조립 없음이 조립을 더했다).
대조군: 옛 ``BASIC_ALLOWED_PART`` 는 재단 그대로 · 재단 · 조립 BASIC 은 완료, 엣지 · 검수 BASIC 은 미완료.
"""
from __future__ import annotations

import inspect
from types import SimpleNamespace

from foms.services.production import floor_alarm, part_constants as pc
from foms.services.production.part_progress import cards_used, mark_finished, parts_in_use


class _NoTouch:
    """닿으면 터지는 세션 — 빈 틀은 세션을 읽지도 않는다(쿼리 0)."""

    def __getattr__(self, name):
        raise AssertionError(f"세션에 닿았다: {name}")


def _m(key, part, state):
    return SimpleNamespace(drawing_key=key, part=part, state=state)


def test_floor_alarm_shell_returns_at_once_without_touching_the_session():
    db = _NoTouch()
    assert floor_alarm.enabled() is False
    assert floor_alarm.note_mark(db, object(), object(), {"changed": True}) is None
    assert floor_alarm.note(db, "hold", 1, object(), reason="자재") is None
    assert floor_alarm.note(None, "모르는 종류", None, None) is None  # 예외 0
    assert floor_alarm.flush(db) is None


def test_floor_alarm_shell_keeps_the_promised_names_and_arguments():
    def params(fn):
        return [(p.name, p.kind) for p in inspect.signature(fn).parameters.values()]

    pos, kw = inspect.Parameter.POSITIONAL_OR_KEYWORD, inspect.Parameter.VAR_KEYWORD
    assert params(floor_alarm.enabled) == []
    assert [n for n, _ in params(floor_alarm.note_mark)] == ["db", "actor", "req", "data"]
    note = params(floor_alarm.note)
    assert note[:4] == [("db", pos), ("kind", pos), ("order_id", pos), ("actor", pos)] and note[4][1] == kw
    assert [n for n, _ in params(floor_alarm.flush)] == ["db"]


def test_parts_in_use_equals_cards_used_today():
    cases = (
        [],
        [_m("k1", "cut", "NONE"), _m("old", "edge", "NONE")],
        [_m("old", "edge", "NEED"), _m("k1", "cut", "BASIC")],
        [_m("k1", "paint", "DONE")],
        [_m("k1", "assemble", "DONE"), _m("k2", "inspect", "NEED"), _m("k3", "cut", "NONE")],
    )
    drawn = [{"key": k} for k in ("k1", "k2", "k3")]  # 도면 있는 주문(0장 주문은 아래 — 옛 판 줄을 안 센다)
    for marks in cases:
        for sd in ({"drawing_current_files": drawn},
                   {"drawing_current_files": drawn, "production": {"steps": [{"key": "cut", "done": True}]}}):
            assert parts_in_use(sd, marks) == cards_used(marks)
    assert parts_in_use({"drawing_current_files": drawn}, cases[2]) == {"edge", "cut"}  # 대조군 — 빈 값끼리 같은 것이 아니다
    # 확정 도면 0장이면 미정 아닌 @order 줄의 파트만(2026-11-28 ⓑ 검토 3 — 도면이 n → 0장이 된 주문의 옛 판 줄은 안 센다)
    for sd in (None, {}, {"production": {"steps": [{"key": "cut", "done": True}]}}):
        assert parts_in_use(sd, cases[2]) == set()
        assert parts_in_use(sd, cases[2] + [_m("@order", "edge", "DONE"), _m("@order", "cut", "NONE")]) == {"edge"}


def test_basic_allowed_parts_is_cut_and_assemble_and_mark_finished_reads_it():
    assert pc.BASIC_ALLOWED_PARTS == ("cut", "assemble")  # 조립 = '조립 없음'(사장님 2026-11-28 "조립만")
    assert pc.BASIC_ALLOWED_PART == "cut"
    for part in ("cut", "assemble"):
        assert mark_finished(part, "BASIC") is True and mark_finished(part, "DONE") is True
    for part in ("edge", "inspect"):
        assert mark_finished(part, "BASIC") is False and mark_finished(part, "DONE") is True
