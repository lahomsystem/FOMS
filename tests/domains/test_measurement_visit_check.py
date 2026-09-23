"""실측 방문 체크 순수 함수 계약 (foms/services/measurement/visit_check.py)."""

import pytest

from foms.services.measurement.visit_check import (
    MEASUREMENT_VISITS_CAP,
    MEASUREMENT_VISITS_KEY,
    apply_visit_mark,
    build_measurement_glance_groups,
    is_visit_marked,
    normalize_visit_date,
    visit_entry,
)

_MARK_KW = {"at_iso": "2026-09-23T14:05:11+09:00", "by_user_id": 12, "by_name": "최진호"}


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("2026-09-23", "2026-09-23"),
        ("20260923", None),
        ("2026-02-30", None),
        ("2026-9-23", None),
        (" 2026-09-23", None),
        ("2026-09-23T00:00", None),
        ("", None),
        (None, None),
        (20260923, None),
    ],
)
def test_normalize_visit_date_is_strict_iso(raw, expected):
    assert normalize_visit_date(raw) == expected


def test_mark_then_unmark_reports_changed():
    sd = {}
    assert apply_visit_mark(sd, "2026-09-23", True, **_MARK_KW) is True
    entry = sd[MEASUREMENT_VISITS_KEY]["2026-09-23"]
    assert entry == {"at": _MARK_KW["at_iso"], "by_user_id": 12, "by_name": "최진호"}
    assert is_visit_marked(sd, "2026-09-23") is True
    assert visit_entry(sd, "2026-09-23") == entry

    assert apply_visit_mark(sd, "2026-09-23", False, **_MARK_KW) is True
    assert "2026-09-23" not in sd[MEASUREMENT_VISITS_KEY]
    assert is_visit_marked(sd, "2026-09-23") is False


def test_unmark_returns_true_only_when_key_existed():
    sd = {MEASUREMENT_VISITS_KEY: {"2026-09-23": {"at": "x", "by_user_id": 1, "by_name": "a"}}}
    assert apply_visit_mark(sd, "2026-09-23", False, **_MARK_KW) is True
    assert sd[MEASUREMENT_VISITS_KEY] == {}


def test_same_state_is_not_a_change():
    original = {"at": "old", "by_user_id": 1, "by_name": "먼저 누른 사람"}
    sd = {MEASUREMENT_VISITS_KEY: {"2026-09-23": dict(original)}}
    assert apply_visit_mark(sd, "2026-09-23", True, **_MARK_KW) is False
    assert sd[MEASUREMENT_VISITS_KEY]["2026-09-23"] == original  # 첫 기록을 덮지 않는다

    empty = {}
    assert apply_visit_mark(empty, "2026-09-23", False, **_MARK_KW) is False
    assert MEASUREMENT_VISITS_KEY not in empty


def test_cap_evicts_oldest_dates_first():
    visits = {
        f"2026-08-{day:02d}": {"at": "x", "by_user_id": 1, "by_name": "a"}
        for day in range(1, MEASUREMENT_VISITS_CAP + 1)
    }
    sd = {MEASUREMENT_VISITS_KEY: visits}
    assert apply_visit_mark(sd, "2026-09-23", True, **_MARK_KW) is True
    kept = sd[MEASUREMENT_VISITS_KEY]
    assert len(kept) == MEASUREMENT_VISITS_CAP
    assert "2026-08-01" not in kept
    assert "2026-08-02" in kept
    assert "2026-09-23" in kept


def test_cap_keeps_the_date_just_marked_even_if_oldest():
    visits = {
        f"2026-08-{day:02d}": {"at": "x", "by_user_id": 1, "by_name": "a"}
        for day in range(1, MEASUREMENT_VISITS_CAP + 1)
    }
    sd = {MEASUREMENT_VISITS_KEY: visits}
    assert apply_visit_mark(sd, "2026-07-01", True, **_MARK_KW) is True
    kept = sd[MEASUREMENT_VISITS_KEY]
    assert len(kept) == MEASUREMENT_VISITS_CAP
    assert "2026-07-01" in kept
    assert "2026-08-01" not in kept


@pytest.mark.parametrize("broken", [[], "x", 3, None])
def test_non_dict_visits_value_is_repaired(broken):
    sd = {MEASUREMENT_VISITS_KEY: broken}
    assert is_visit_marked(sd, "2026-09-23") is False
    assert apply_visit_mark(sd, "2026-09-23", True, **_MARK_KW) is True
    assert isinstance(sd[MEASUREMENT_VISITS_KEY], dict)
    assert is_visit_marked(sd, "2026-09-23") is True


def test_non_dict_entry_is_not_marked():
    sd = {MEASUREMENT_VISITS_KEY: {"2026-09-23": True}}
    assert is_visit_marked(sd, "2026-09-23") is False
    assert visit_entry(sd, "2026-09-23") is None
    assert is_visit_marked(None, "2026-09-23") is False
    assert is_visit_marked({}, None) is False


def _row(oid, manager, *, done=False, phone=None):
    return {"id": oid, "manager_name": manager, "manager_phone": phone, "measurement_visit_done": done}


def test_groups_follow_row_order_and_only_merge_consecutive_runs():
    rows = [
        _row(1, "최진호", done=True, phone="010-1111-2222"),
        _row(2, " 최진호 ", phone="010-9999-9999"),
        _row(3, "김영업"),
        _row(4, "최진호", done=True),
    ]
    groups = build_measurement_glance_groups(rows)
    assert [g["manager_name"] for g in groups] == ["최진호", "김영업", "최진호"]
    assert [[r["id"] for r in g["rows"]] for g in groups] == [[1, 2], [3], [4]]
    assert [(g["done"], g["total"]) for g in groups] == [(1, 2), (0, 1), (1, 1)]
    assert groups[0]["manager_phone"] == "010-1111-2222"  # 첫 행에 번호가 있으면 그 값
    assert groups[0]["key"] == "최진호"


def test_group_phone_falls_back_to_first_non_empty_row_phone():
    """첫 주문에 번호가 없어도 묶음 전화 링크가 사라지지 않는다(사용자 요구: 이름·전화 버튼으로 바로 전화)."""
    rows = [
        _row(1, "최진호", phone=None),
        _row(2, "최진호", phone="-"),
        _row(3, "최진호", phone="  "),
        _row(4, "최진호", phone="010-3333-4444"),
        _row(5, "최진호", phone="010-5555-6666"),
        _row(6, "김영업", phone=None),
    ]
    groups = build_measurement_glance_groups(rows)
    assert [g["manager_phone"] for g in groups] == ["010-3333-4444", None]
    assert groups[0]["total"] == 5


def test_group_key_is_case_insensitive_and_dash_means_unassigned():
    rows = [_row(1, "Alice"), _row(2, "ALICE "), _row(3, "-"), _row(4, None), _row(5, "  ")]
    groups = build_measurement_glance_groups(rows)
    assert [g["key"] for g in groups] == ["alice", ""]
    assert groups[0]["manager_name"] == "Alice"
    assert groups[1]["manager_name"] == "담당 미정"
    assert groups[1]["total"] == 3


def test_groups_empty_rows():
    assert build_measurement_glance_groups([]) == []
    assert build_measurement_glance_groups(None) == []
