"""제품마다 '시공 끝' 판정 순수 함수 (2단계 설계서 2절 · 4.1)."""
from __future__ import annotations

import copy

from foms.services.orders import item_construction_done as icd

UID_A = "aaaaaaaa-0000-4000-8000-000000000001"
UID_B = "bbbbbbbb-0000-4000-8000-000000000002"
UID_C = "cccccccc-0000-4000-8000-000000000003"


def _sd(order_date="2026-11-05, 2026-11-17", items=None, done=None):
    sd = {"schedule": {"construction": {"date": order_date}}, "items": items or []}
    if done is not None:
        sd[icd.DONE_KEY] = done
    return sd


def _split_sd(done=None):
    """5687 모양 — 화장대 · 베란다장은 11/05, 부엌가구는 날짜 없음(주문 날짜를 물려받아 11/17 까지)."""
    return _sd(items=[
        {"uid": UID_A, "product_name": "화장대", "construction_date": "2026-11-05"},
        {"uid": UID_B, "product_name": "베란다장", "construction_date": "2026-11-05"},
        {"uid": UID_C, "product_name": "부엌가구"},
    ], done=done)


def _mark(day="2026-11-05"):
    return {"date": day, "at": "x", "by_user_id": 1, "by_name": "시공", "source": "visit", "attempt_id": None}


def test_consecutive_days_without_item_dates_is_not_split():
    sd = _sd(order_date="2026-11-05, 2026-11-06", items=[
        {"uid": UID_A, "product_name": "붙박이장"}, {"uid": UID_B, "product_name": "화장대"},
    ])
    assert icd.is_split_order(sd) is False
    assert icd.is_partial_open(sd) is False


def test_split_order_by_item_last_dates():
    sd = _split_sd()
    assert icd.is_split_order(sd) is True
    lines = icd.item_lines(sd)
    assert [line.last_date for line in lines] == ["2026-11-05", "2026-11-05", "2026-11-17"]
    assert icd.is_partial_open(sd) is False  # 아직 아무것도 안 찍음


def test_partial_open_after_first_visit_and_message():
    sd = _split_sd(done={UID_A: _mark(), UID_B: _mark()})
    assert icd.is_partial_open(sd) is True
    assert [line.name for line in icd.remaining_lines(sd)] == ["부엌가구"]
    assert icd.blocked_message(sd) == "11/17 부엌가구 시공이 남아 있어요"


def test_all_done_is_not_partial_open():
    sd = _split_sd(done={UID_A: _mark(), UID_B: _mark(), UID_C: _mark("2026-11-17")})
    assert icd.is_partial_open(sd) is False
    assert icd.remaining_lines(sd) == []
    assert icd.is_split_order(sd) is True


def test_cancelled_item_is_neither_remaining_nor_split_source():
    sd = _split_sd(done={UID_A: _mark(), UID_B: _mark()})
    sd["items"][2]["cancel"] = {"at": "x", "source": "after_confirm"}
    assert icd.remaining_lines(sd) == []
    assert icd.is_partial_open(sd) is False


def test_unknown_uid_in_done_map_is_ignored():
    sd = _split_sd(done={"dddddddd-0000-4000-8000-000000000004": _mark()})
    assert icd.has_done_marks(sd) is False
    assert icd.is_partial_open(sd) is False


def test_visit_candidates_precheck_by_last_date():
    rows = icd.visit_candidates(_split_sd(), "2026-11-05")
    assert [(r["name"], r["precheck"]) for r in rows] == [
        ("화장대", True), ("베란다장", True), ("부엌가구", False),
    ]
    assert rows[2]["last_label"] == "11/17"


def test_apply_marks_mints_uid_for_legacy_item_and_skips_done():
    sd = _sd(items=[
        {"product_name": "화장대", "construction_date": "2026-11-05"},
        {"uid": UID_C, "product_name": "부엌가구", "construction_date": "2026-11-17"},
    ])
    before = copy.deepcopy(sd)
    marked = icd.apply_done_marks(sd, ["idx:0"], day_iso="2026-11-05", at_iso="t",
                                  user_id=3, user_name="시공팀", attempt_id=9)
    assert len(marked) == 1
    new_uid = sd["items"][0]["uid"]
    assert marked == [new_uid] and len(new_uid) == 36
    assert sd[icd.DONE_KEY][new_uid]["attempt_id"] == 9
    assert before["items"][0].get("uid") is None  # 원본 사본은 그대로
    # 이미 끝난 제품 · 모르는 참조는 건너뛴다
    assert icd.apply_done_marks(sd, [new_uid, "idx:9", ""], day_iso="2026-11-05", at_iso="t",
                                user_id=3, user_name="시공팀") == []


def test_remove_done_mark_drops_key_when_empty():
    sd = _split_sd(done={UID_A: _mark()})
    assert icd.remove_done_mark(sd, UID_A)["date"] == "2026-11-05"
    assert icd.DONE_KEY not in sd
    assert icd.remove_done_mark(sd, UID_A) is None


def test_non_dict_inputs_are_safe():
    assert icd.item_lines(None) == []
    assert icd.is_split_order("x") is False
    assert icd.done_map({icd.DONE_KEY: ["bad"]}) == {}
    assert icd.remaining_summary({}) == ""
