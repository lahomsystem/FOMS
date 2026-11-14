"""ERP 할 일 목록(설계서 2026-11-14-foms-graft 3.3 · 3.4) — 선언 · 넣을 값 검사 · 겹침 열쇠.

완료 기준: 할 일 열한 개가 설계서 표 그대로 · ``policy_id`` 가 모두 지금 정책 표에 있음 · ``mode = human`` 은 넣을 값 · 정책이 없음 ·
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
    "advance_stage": ("STAFF_MUTATION", "run", 2),  # D206 — 떼어 낸 본체를 승인하면 바로 실행(T14)
    "assign_draftsman": ("STAFF_MUTATION", "run", 2),
    "move_measurement": ("ERP_EDIT", "run", 2),
    "send_construction_alimtalk": ("STAFF_MUTATION", "run", 1),  # 3.13 — 손님에게 나가는 글(T15)
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
def test_actions_follow_the_spec_table():
    assert {name: (s.policy_id, s.mode, s.level_cap) for name, s in r.ACTIONS.items()} == SPEC_TABLE
    assert list(r.ACTIONS) == list(SPEC_TABLE)
    assert all(name == spec.name and len(name) <= 40 for name, spec in r.ACTIONS.items())  # 표 칸 action String(40)


def test_no_link_action_is_left_after_d206_and_phone_follows_the_approval_window():
    """판 1 끝에는 바로가기 할 일이 없다(D206). 사람을 골라야 하는 도면 담당 맡기기만 PC 승인(폰 카드에는 고르기 칸이 없다)."""
    assert [name for name, spec in r.ACTIONS.items() if spec.mode == r.MODE_LINK] == []
    phone = {name: r.ACTIONS[name].phone_ok for name in ("advance_stage", "assign_draftsman", "move_measurement")}
    assert phone == {"advance_stage": True, "assign_draftsman": False, "move_measurement": True}
    assert r.ACTIONS["advance_stage"].params == ()  # 넣을 값 없음 — 팀 · 뚫기 칸이 없다
    (users,) = r.ACTIONS["assign_draftsman"].params
    assert (users.name, users.kind, users.required, users.limit) == ("user_ids", "users", True, r.MAX_USERS)
    assert [p.name for p in r.ACTIONS["move_measurement"].params] == ["date"]


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
    assert r.ACTIONS["send_construction_alimtalk"].level_cap == 1 and r.ACTIONS["send_construction_alimtalk"].params == ()


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
    assert [p["name"] for p in row["params"]] == ["date", "time", "notify_customer"]
    assert [c["value"] for c in row["params"][1]["choices"]] == list(r.TIME_SLOTS)
    assert row["params"][2] == {"name": "notify_customer", "kind": "flag", "label": "손님 알림톡(시공일 안내)",
                                "required": False, "default": True}  # D213 — 처음 값 켬
    assert rows["cancel_order"]["params"] == [] and rows["cancel_order"]["level_label"] == "사람만"
    assert rows["assign_draftsman"]["params"] == [{"name": "user_ids", "kind": "users", "label": "도면 담당",
                                                   "required": True, "limit": r.MAX_USERS}]  # 고를 사람은 승인 창이 연다


# ── 넣을 값 검사 ─────────────────────────────────────────────────────────
def test_good_values_are_cleaned():
    assert parse("schedule_construction", {"date": "2026-11-20", "time": "오전"}) == {
        "date": "2026-11-20", "time": "오전", "notify_customer": True}  # 손님 알림톡 처음 값 켬(D213)
    assert parse("move_construction", {"date": "2026-11-14"}) == {"date": "2026-11-14", "time": "",
                                                                   "notify_customer": True}  # 오늘은 된다
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


def test_users_kind_takes_only_user_numbers_and_may_stay_empty_until_approval():
    """사람 고르기 — 사용자 번호만 · 겹침 뺌 · 상한. 제안 때는 비워 둔다(빠져도 빈 목록) — 승인자가 고른다."""
    assert parse("assign_draftsman", {}) == {"user_ids": []}
    assert parse("assign_draftsman", {"user_ids": []}) == {"user_ids": []}
    assert parse("assign_draftsman", {"user_ids": [7, 3, 7]}) == {"user_ids": [7, 3]}
    for bad in (["7"], [True], [0], [-2], [1.5], "7", {"id": 7}, list(range(1, r.MAX_USERS + 2))):
        assert shape_fields("assign_draftsman", {"user_ids": bad}) == ("user_ids",), bad
    assert shape_fields("assign_draftsman", {"user_ids": [7], "emergency_override": True}) == ("params",)
    assert shape_fields("advance_stage", {"team": "CS"}) == ("params",)  # 팀 · 뚫기 값을 받을 칸이 없다


def test_flag_kind_takes_only_true_or_false():
    flag = r.Param("notify", r.KIND_FLAG, "알림", required=False)
    assert r._clean(flag, True, TODAY) is True and r._clean(flag, False, TODAY) is False
    assert r._clean(flag, "true", TODAY) is None and r._clean(flag, 1, TODAY) is None
    assert r._empty(flag) is False and r._empty(r.ACTIONS["assign_draftsman"].params[0]) == []


def test_notify_customer_defaults_on_and_can_be_turned_off():
    """시공일 두 할 일의 손님 알림톡 칸(D213) — 빠지면 참, 거짓으로 끌 수 있고, 참거짓 말고는 칸 이름만 싣고 거절한다."""
    for name in ("schedule_construction", "move_construction"):
        assert r.ACTIONS[name].params[-1] is r.NOTIFY_CUSTOMER
        assert parse(name, {"date": "2026-11-20", "notify_customer": False})["notify_customer"] is False
        assert shape_fields(name, {"date": "2026-11-20", "notify_customer": "yes"}) == ("notify_customer",)
    assert r._empty(r.NOTIFY_CUSTOMER) is True and r.NOTIFY_CUSTOMER.kind == r.KIND_FLAG


def test_every_proposable_action_names_a_known_notify_team():
    """폰 알림 받는 팀(설계서 3.14 · D215) — 사람만 할 일 빼고 모두, 정규화된 팀 코드로."""
    from foms.services.orders.order_mutation_policy import normalize_team

    teams = {name: spec.notify_team for name, spec in r.ACTIONS.items() if spec.mode != r.MODE_HUMAN}
    assert all(team and normalize_team(team) == team for team in teams.values()), teams
    assert set(teams.values()) <= {"CS", "SALES", "SHIPMENT", "DRAWING"}
    assert r.ACTIONS["cancel_order"].notify_team is None


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
