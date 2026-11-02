"""그림 읽기 규칙(설계서 17.11 (c) · (d) · D90 · D96) — 벽 쪽마다 150 빼기 · 내경 그대로 · 기준 모름 두 끝 · 표시 벽만 ·
합친 범위 · 1.5배 넘으면 안 씀 · 10mm 내림/올림 · 한 값 '약 ○mm' · 꼴 검사 · 글 칸 없음 · 공간 짝 · 손님 글이 그림을 이김.

순수 함수 시험(네트워크 · DB 없음). 값은 합성 mm 뿐 — 금액은 적지 않는다.
"""

from __future__ import annotations

import json
import re

import pytest

from foms.services.cs_agent import image_rules as ir
from foms.services.cs_agent import image_step as ist
from foms.services.cs_agent.drafting_read import MEMO_IMAGE_HEAD
from foms.services.cs_agent.image_read import BatchOutcome, _ranges
from foms.services.cs_agent.image_settings import MODE_DRAFT, MODE_NOTE, MODE_OFF
from tests.support.cs_image_support import answer, room, wall
from tests.support.cs_quote_support import ask, space


def read(*spaces, **kw):
    return ir.read_result(json.dumps(answer(*spaces, **kw)))


def wall_of(**kw):
    return ir.read_result(json.dumps(answer(room("안방", wall(**kw))))).spaces[0].walls[0]


# ── 벽 하나 — D90 · D96 ──────────────────────────────────────────────────
@pytest.mark.parametrize("ends,cut", [("both_walls", 300), ("one_wall", 150), ("no_wall", 0)])
def test_center_line_walls_lose_150_per_wall_side(ends, cut):
    got = ir.wall_range(wall_of(low=3000, high=3300, basis="center_line", ends=ends))
    assert got == (3000 - cut, 3300 - cut, cut)  # 두 끝 모두 같은 몫을 뺀다


def test_inner_dimensions_are_used_as_is_even_between_two_walls():
    assert ir.wall_range(wall_of(low=2410, high=2690, basis="inner", ends="both_walls")) == (2410, 2690, 0)


def test_unknown_basis_spans_both_bases_lower_end_cut_upper_end_as_is():
    assert ir.wall_range(wall_of(low=2700, high=2700, basis="unknown", ends="both_walls")) == (2400, 2700, 300)
    assert ir.wall_range(wall_of(low=2700, basis="unknown", ends="one_wall")) == (2550, 2700, 150)
    found, code = ir.space_range(read(room("안방", wall(2700, basis="unknown"))).spaces[0])
    assert code is None and found.basis_unknown and (found.low, found.high) == (2400, 2700)


def test_rounding_floors_the_lower_end_and_ceils_the_upper_end_to_10mm():
    assert ir.wall_range(wall_of(low=2715, high=2731, basis="inner")) == (2710, 2740, 0)
    assert ir.wall_range(wall_of(low=2715, high=2731, basis="center_line")) == (2410, 2440, 300)


def test_a_wall_that_vanishes_after_the_cut_is_dropped():
    assert ir.wall_range(wall_of(low=250, basis="center_line")) is None  # 300 빼면 0 아래


# ── 벽 고르기 · 합친 범위 ────────────────────────────────────────────────
def test_marked_walls_win_over_other_usable_walls():
    space_ = read(room("안방", wall(2700, marked=True), wall(4200), target="marked")).spaces[0]
    found, _ = ir.space_range(space_)
    assert (found.low, found.high, found.walls) == (2400, 2400, 1)


def test_without_marks_all_usable_walls_are_joined_and_blocked_walls_skipped():
    space_ = read(room("안방", wall(2700), wall(3000), wall(9000, usable=False, blocked=("window",)))).spaces[0]
    found, _ = ir.space_range(space_)
    assert (found.low, found.high, found.walls) == (2400, 2700, 2)


def test_a_joined_range_wider_than_one_and_a_half_times_is_not_used():
    found, code = ir.space_range(read(room("안방", wall(2300), wall(3800))).spaces[0])  # 2000 ~ 3500 → 1.75배
    assert (found, code) == (None, "wall_unclear")
    found, code = ir.space_range(read(room("안방", wall(2300), wall(3300))).spaces[0])  # 2000 ~ 3000 = 1.5배 — 경계 안
    assert code is None and (found.low, found.high) == (2000, 3000)
    assert ir.space_range(read(room("안방")).spaces[0]) == (None, "no_dimensions")


# ── 꼴 검사 · 글 칸 없음 ─────────────────────────────────────────────────
def _string_leaves(schema, path=""):
    """스키마 안의 글(string) 칸 가운데 고른 값(enum)이 없는 것."""
    if isinstance(schema, dict):
        if schema.get("type") == "string" and "enum" not in schema:
            yield path
        for key, value in schema.items():
            yield from _string_leaves(value, f"{path}.{key}")
    elif isinstance(schema, list):
        for value in schema:
            yield from _string_leaves(value, path)


def test_the_schema_has_no_free_text_field_anywhere():
    schema = ir.image_schema()
    assert list(_string_leaves(schema)) == []  # 단지명 · 동호수 · 이름이 돌아올 자리가 없다
    assert schema["additionalProperties"] is False and set(schema["required"]) == set(schema["properties"])
    assert schema["properties"]["spaces"]["items"]["properties"]["room"]["enum"][:2] == ["안방", "작은방"]


def test_bad_fields_are_dropped_and_a_broken_shape_fails_the_whole_result():
    got = read(room("안방", wall(2700), {**wall(2800), "read_min_mm": 2.5}, {**wall(2800), "read_min_mm": 200_000},
                    {**wall(3000, 2800)}, {**wall(2800), "basis": "outer"}))
    assert [w.read_min_mm for w in got.spaces[0].walls] == [2700]  # 정수 아님 · 100m 넘음 · 거꾸로 · 고른 값 밖은 버림
    assert read(room("거실방", wall(2700))).spaces == ()  # 방 이름이 목록 밖이면 그 공간을 버린다
    for broken in ("not json", json.dumps([1]), json.dumps({**answer(), "confidence": "sure"}),
                   json.dumps({**answer(), "is_drawing": "yes"}), json.dumps({**answer(), "personal_seen": ["?"]})):
        with pytest.raises(ValueError):
            ir.read_result(broken)


def test_a_face_or_person_seen_by_the_model_marks_the_result():
    assert read(personal=("face",)).face_seen and read(personal=("person", "address")).face_seen
    assert not read(personal=("complex_name", "unit_number")).face_seen and read().personal_seen == ()


def test_result_json_round_trips_and_stores_codes_only():
    original = read(room("작은방", wall(2700, marked=True), target="marked", marks=("circle",)), reasons=("scale_estimated",))
    stored = ir.result_json(original)
    assert ir.read_result(json.dumps(stored)) == original
    vocabulary = set(_enums(ir.image_schema()))
    assert set(_strings(stored)) <= vocabulary  # 남는 글은 모두 고른 값(코드)뿐 — 자유 글이 없다


def _enums(schema):
    if isinstance(schema, dict):
        yield from schema.get("enum", ())
        for value in schema.values():
            yield from _enums(value)
    elif isinstance(schema, list):
        for value in schema:
            yield from _enums(value)


def _strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for item in value.values():
            yield from _strings(item)
    elif isinstance(value, list):
        for item in value:
            yield from _strings(item)


# ── 공간 짝 · 쓰는 법(직원 참고만 · 초안에 씀) ───────────────────────────
def outcome_of(*spaces, **kw):
    read_ = read(*spaces, **kw)
    return BatchOutcome(read=read_, ranges=tuple(_ranges(read_)), images=1)


def test_note_mode_never_fills_the_width_and_writes_one_numbers_only_line():
    use = ist.use_reading(ask(space(width=0), size_in_attachment=True), outcome_of(room("안방", wall(2700, 3000))),
                          mode=MODE_NOTE, min_confidence="medium")
    assert use.ask is None and use.lines == ()
    assert use.note == f"{MEMO_IMAGE_HEAD}] 평면도 · 안방(글) · 벽 1 · 범위 2,400~2,700mm(벽 포함 300 뺌) · 확신 보통 — 직원 확인"
    assert re.search(r"\d\s*(원|만)", use.note) is None  # 금액 없음


def test_draft_mode_fills_the_width_range_for_the_paired_space():
    quote = ask(space(width=0), unknown=("width",), size_in_attachment=True)
    use = ist.use_reading(quote, outcome_of(room("안방", wall(2700, 3000), target="inferred")), mode=MODE_DRAFT,
                          min_confidence="medium")
    (filled,) = use.ask.spaces
    assert (filled.width_mm, filled.width_max_mm, use.ask.unknown, use.ask.size_in_attachment) == (2400, 2700, (), False)
    assert use.lines[0] == ist.DRAWING_HEAD and "안방(으)로 보이는 자리 기준으로 2,400~2,700mm" in use.lines[1]
    assert use.note.endswith("— 초안에 씀") and use.fallback_note.endswith("— 직원 확인")


def test_a_single_read_value_is_said_as_about_n_mm():
    use = ist.use_reading(ask(space(width=0), size_in_attachment=True), outcome_of(room("안방", wall(2700, basis="inner"))),
                          mode=MODE_DRAFT, min_confidence="medium")
    assert (use.ask.spaces[0].width_mm, use.ask.spaces[0].width_max_mm) == (2700, 0)
    assert "약 2,700mm" in use.lines[1] and "약 2,700mm(내경 그대로)" in use.note


@pytest.mark.parametrize("change", [
    dict(confidence="low"), dict(reasons=("wall_unclear",)), dict(reasons=("room_unclear",)),
    dict(reasons=("marks_conflict",)), dict(personal=("face",)),
])
def test_unusable_results_only_add_a_staff_line(change):
    use = ist.use_reading(ask(space(width=0), size_in_attachment=True),
                          outcome_of(room("안방", wall(2700, 3000)), **change), mode=MODE_DRAFT, min_confidence="medium")
    assert use.ask is None and use.note.endswith("— 직원 확인")


def test_high_only_confidence_setting_rejects_medium():
    use = ist.use_reading(ask(space(width=0), size_in_attachment=True), outcome_of(room("안방", wall(2700, 3000))),
                          mode=MODE_DRAFT, min_confidence="high")
    assert use.ask is None


def test_space_pairing_one_to_one_ignores_names_but_several_must_match():
    one = ist.use_reading(ask(space(width=0, space="작은방"), size_in_attachment=True),
                          outcome_of(room("안방", wall(2700, 3000))), mode=MODE_DRAFT, min_confidence="medium")
    assert one.ask is not None  # 손님이 '방'이라고만 씀 — 하나씩이면 짝
    two = ask(space(width=0, space="안방"), space(width=0, space="작은방"), size_in_attachment=True)
    unmatched = ist.use_reading(two, outcome_of(room("안방", wall(2700, 3000)), room("드레스룸", wall(2700))),
                                mode=MODE_DRAFT, min_confidence="medium")
    assert unmatched.ask is None  # room_unclear
    matched = ist.use_reading(two, outcome_of(room("작은방", wall(2700)), room("안방", wall(3000))),
                              mode=MODE_DRAFT, min_confidence="medium")
    assert [s.width_mm for s in matched.ask.spaces] == [2700, 2400]


def test_customer_text_beats_the_drawing():
    quote = ask(space(width=2500, door="sliding", handle="push", height_mm=2300), size_in_attachment=True)
    use = ist.use_reading(quote, outcome_of(room("안방", wall(2700, 3000), door="hinged", handle="bar", height=2400)),
                          mode=MODE_DRAFT, min_confidence="medium")
    assert use.ask is None  # 가로를 아는 공간은 그림 범위로 덮지 않는다(가로를 모르는 공간이 없다)
    unknown = ask(space(width=0, door="sliding", handle="unknown"), size_in_attachment=True)
    filled = ist.use_reading(unknown, outcome_of(room("안방", wall(2700, 3000), door="hinged", handle="bar", height=2400)),
                             mode=MODE_DRAFT, min_confidence="medium").ask.spaces[0]
    assert (filled.door, filled.handle, filled.height_mm) == ("sliding", "bar", 2400)  # 문 방식은 손님 글, 나머지는 그림


def test_off_mode_and_missing_reads_change_nothing():
    quote = ask(space(width=0), size_in_attachment=True)
    assert ist.use_reading(quote, outcome_of(room("안방", wall(2700))), mode=MODE_OFF, min_confidence="medium") == \
        ist.DrawingUse()
    use = ist.use_reading(quote, None, mode=MODE_DRAFT, min_confidence="medium")
    assert (use.ask, use.note) == (None, f"{MEMO_IMAGE_HEAD}] 읽지 못함(time_cap) — 직원 확인")
    use = ist.use_reading(quote, BatchOutcome(codes=("skipped_face",)), mode=MODE_NOTE, min_confidence="medium")
    assert use.note == f"{MEMO_IMAGE_HEAD}] 읽지 못함(skipped_face) — 직원 확인"
