"""ERP 할 일 목록(설계서 2026-11-14-foms-graft 3.3 · 3.4) — 선언 · 넣을 값 검사 · 겹침 열쇠.

완료 기준: 할 일 열 개가 설계서 표 그대로 · ``policy_id`` 가 모두 지금 정책 표에 있음 · ``mode = human`` 은 넣을 값 · 정책이 없음 ·
수준 상한 0 ~ 2(3 없음) · 넣을 값은 정한 칸만 · 꼴(날짜 오늘 이후 · 시간대 · 가림 검사 0 · 길이) · 틀리면 칸 이름만 · 겹침 열쇠가
같은 값이면 같고 다르면 다름 · 거절 까닭 다섯 · 실패 말 여섯. 지어낸 값만 쓴다. DB · 바깥 호출 없음.
"""

from __future__ import annotations

import datetime

import pytest

from foms.services.erp_actions import registry as r
from foms.services.erp_ontology.objects import OBJECT_TYPES
from foms.services.orders.order_mutation_policy import POLICY_REGISTRY

TODAY = datetime.date(2026, 11, 14)
PHONE = "01" + "0" + "5550" + "1234"  # 합성 휴대폰(실행 때 만든다)
SPEC_TABLE = {  # 설계서 3.3 표 — 이름 · 정책 · 갈래 · 수준 상한
    "schedule_construction": ("CONSTRUCTION_SCHEDULE_EDIT", "run", 2),
    "move_construction": ("CONSTRUCTION_SCHEDULE_EDIT", "run", 2),
    "schedule_as_visit": ("ERP_EDIT", "run", 2),
    "register_as": ("CONSTRUCTION_EDIT", "run", 2),
    "send_measure_alimtalk": ("STAFF_MUTATION", "run", 1),
    "add_construction_note": ("ERP_EDIT", "run", 2),
    "advance_stage": ("STAFF_MUTATION", "link", 1),
    "assign_draftsman": ("STAFF_MUTATION", "link", 1),
    "move_measurement": ("ERP_EDIT", "link", 1),
    "cancel_order": (None, "human", 0),
}


def parse(name, body):
    return r.parse_params(name, body, today=TODAY)


def shape_fields(name, body):
    with pytest.raises(r.ActionShapeError) as caught:
        parse(name, body)
    assert caught.value.code == "ACTION_SHAPE"
    return caught.value.fields


# ── 선언 ────────────────────────────────────────────────────────────────
def test_ten_actions_follow_the_spec_table():
    assert {name: (s.policy_id, s.mode, s.level_cap) for name, s in r.ACTIONS.items()} == SPEC_TABLE
    assert list(r.ACTIONS) == list(SPEC_TABLE)
    assert all(name == spec.name and len(name) <= 40 for name, spec in r.ACTIONS.items())  # 표 칸 action String(40)


def test_every_policy_id_is_in_the_policy_registry():
    used = {spec.policy_id for spec in r.ACTIONS.values() if spec.mode != r.MODE_HUMAN}
    assert used and used <= set(POLICY_REGISTRY)


def test_human_actions_take_no_values_and_have_no_policy():
    humans = [spec for spec in r.ACTIONS.values() if spec.mode == r.MODE_HUMAN]
    assert [spec.name for spec in humans] == ["cancel_order"]
    assert all(spec.params == () and spec.policy_id is None and spec.level_cap == 0 for spec in humans)
    assert all(not spec.phone_ok and not spec.wam_inline for spec in humans)
    assert shape_fields("cancel_order", {}) == ("action",)  # 제안 · 실행 길 없음
    assert r.level_label(r.ACTIONS["cancel_order"]) == "사람만"


def test_levels_stop_at_two_and_modes_are_known():
    assert r.LEVELS == (0, 1, 2) and r.MAX_LEVEL == 2 and 3 not in r.LEVEL_LABELS
    assert all(spec.mode in r.MODES and 0 <= spec.level_cap <= r.MAX_LEVEL for spec in r.ACTIONS.values())
    assert all(spec.level_cap >= 1 for spec in r.ACTIONS.values() if spec.mode != r.MODE_HUMAN)
    assert r.ACTIONS["send_measure_alimtalk"].level_cap == 1  # 손님에게 나가는 글


def test_targets_kinds_and_inline_flags():
    types = {obj.type for obj in OBJECT_TYPES}
    assert all(spec.target in types for spec in r.ACTIONS.values())
    assert all(p.kind in r.PARAM_KINDS for spec in r.ACTIONS.values() for p in spec.params)
    assert [n for n, s in r.ACTIONS.items() if s.wam_inline] == ["add_construction_note"]
    assert all(s.mode == r.MODE_RUN for s in r.ACTIONS.values() if s.phone_ok)
    no_private = {"phone", "address", "amount", "price", "name", "customer"}
    assert not any(p.name in no_private for s in r.ACTIONS.values() for p in s.params)  # 전화 · 주소 · 금액 꼴 없음


def test_time_slots_are_the_construction_schedule_choices():
    from foms.services.orders.construction_schedule import TIME_CHOICES

    assert r.TIME_SLOTS == TIME_CHOICES


def test_reject_codes_and_failure_messages():
    assert r.REJECT_CODES == ("wrong_date", "misread", "no_slot", "already_done", "other")
    assert set(r.REJECT_LABELS) == set(r.REJECT_CODES) and all(r.REJECT_LABELS.values())
    assert set(r.FAILURES) == {"ACTION_NOT_OPEN", "ACTION_BASE_CHANGED", "ACTION_PRECONDITION", "ACTION_FORBIDDEN",
                               "ACTION_SHAPE", "ACTION_FAILED"}
    assert r.message("ACTION_NOT_OPEN") == r.FAILURES["ACTION_NOT_OPEN"]
    assert r.message("WHATEVER") == r.FAILURES["ACTION_FAILED"]


def test_specs_carry_what_the_screens_need():
    rows = {row["name"]: row for row in r.specs()}
    assert list(rows) == list(r.ACTIONS)
    row = rows["schedule_construction"]
    assert (row["label"], row["mode"], row["level_label"], row["phone_ok"]) == ("시공 잡기", "run", "2 제안", True)
    assert [p["name"] for p in row["params"]] == ["date", "time"]
    assert [c["value"] for c in row["params"][1]["choices"]] == list(r.TIME_SLOTS)
    assert rows["cancel_order"]["params"] == [] and rows["cancel_order"]["level_label"] == "사람만"


# ── 넣을 값 검사 ─────────────────────────────────────────────────────────
def test_good_values_are_cleaned():
    assert parse("schedule_construction", {"date": "2026-11-20", "time": "오전"}) == {"date": "2026-11-20",
                                                                                     "time": "오전"}
    assert parse("move_construction", {"date": "2026-11-14"}) == {"date": "2026-11-14", "time": ""}  # 오늘은 된다
    assert parse("add_construction_note", {"note": "  합성 메모\n둘째 줄 "}) == {"note": "합성 메모 둘째 줄"}
    assert parse("send_measure_alimtalk", {}) == {}
    assert parse("register_as", {"as_content": "합성 문짝이 처짐"}) == {"as_content": "합성 문짝이 처짐"}


def test_wrong_values_name_only_the_fields():
    assert shape_fields("schedule_construction", {"date": "2026-11-13"}) == ("date",)  # 지난 날
    assert shape_fields("schedule_construction", {"date": "2026-02-30"}) == ("date",)
    assert shape_fields("schedule_construction", {"date": "2026/11/20"}) == ("date",)
    assert shape_fields("schedule_construction", {"date": 20261120}) == ("date",)
    assert shape_fields("schedule_construction", {"time": "저녁"}) == ("date", "time")
    assert shape_fields("schedule_as_visit", {}) == ("date",)
    assert shape_fields("add_construction_note", {"note": "   "}) == ("note",)
    assert shape_fields("add_construction_note", {"note": "합" * 201}) == ("note",)
    leak = shape_fields("add_construction_note", {"note": f"손님 번호 {PHONE}"})
    assert leak == ("note",)


def test_values_outside_the_declared_fields_are_refused_without_echoing_them():
    with pytest.raises(r.ActionShapeError) as caught:
        parse("schedule_construction", {"date": "2026-11-20", "phone": PHONE})
    assert caught.value.fields == ("params",)
    assert PHONE not in str(caught.value)
    assert shape_fields("schedule_construction", ["date"]) == ("params",)
    assert shape_fields("nope", {}) == ("action",) and shape_fields(None, {}) == ("action",)


def test_parse_uses_the_korean_today_by_default(monkeypatch):
    monkeypatch.setattr(r, "get_today_kst", lambda: datetime.date(2026, 11, 21))
    with pytest.raises(r.ActionShapeError):
        r.parse_params("schedule_construction", {"date": "2026-11-20"})
    assert r.parse_params("schedule_construction", {"date": "2026-11-21"})["date"] == "2026-11-21"


# ── 겹침 열쇠 ────────────────────────────────────────────────────────────
def test_dedupe_key_is_stable_and_separates_different_values():
    base = r.dedupe_key("schedule_construction", 7, {"date": "2026-11-20", "time": "오전"})
    assert base == r.dedupe_key("schedule_construction", 7, {"time": "오전", "date": "2026-11-20"})  # 칸 순서 무관
    assert base.startswith("schedule_construction:7:") and len(base) <= 120
    others = {
        r.dedupe_key("schedule_construction", 7, {"date": "2026-11-21", "time": "오전"}),
        r.dedupe_key("schedule_construction", 7, {"date": "2026-11-20", "time": "오후"}),
        r.dedupe_key("schedule_construction", 8, {"date": "2026-11-20", "time": "오전"}),
        r.dedupe_key("move_construction", 7, {"date": "2026-11-20", "time": "오전"}),
    }
    assert base not in others and len(others) == 4
    assert r.dedupe_key("send_measure_alimtalk", None, None) == r.dedupe_key("send_measure_alimtalk", None, {})
    assert r.dedupe_key("send_measure_alimtalk", None, {}).startswith("send_measure_alimtalk:-:")
    with pytest.raises(r.ActionShapeError):
        r.dedupe_key("nope", 7, {})
    with pytest.raises(r.ActionShapeError):
        r.dedupe_key("schedule_construction", True, {})
