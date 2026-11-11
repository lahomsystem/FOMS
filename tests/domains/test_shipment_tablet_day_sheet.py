"""태블릿 하루치 출고표 묶음 · 사람별 집계(build_tablet_day_sheet)와 자수 나누기(D25) 시험 (DB 불필요)."""

from types import SimpleNamespace

import pytest

from foms.services.shipment.tablet_day_sheet import build_tablet_day_sheet
from foms.web.shipment import dashboard as shipment_dashboard


def _row(oid, workers=None, units=0.0, status="RECEIVED"):
    """줄 하나. 자수는 shipment_visible_items 한 품목(spec_width mm ÷ 300)으로 만든다."""
    items = [{"spec_width": str(int(units * 300))}] if units else []
    return SimpleNamespace(
        id=oid,
        status=status,
        is_erp_order=True,
        structured_data={"shipment": {"construction_workers": list(workers or [])}, "items": items},
        shipment_visible_items=items,
    )


def _settings(*entries):
    return [
        {"name": n, "capacity": c, "off_dates": list(off)}
        for n, c, off in entries
    ]


@pytest.fixture
def units_by_id(monkeypatch):
    """visible_spec_units 를 줄 id → 자수 표로 바꿔 품목 계산 규칙과 떼어 놓는다."""
    table: dict[int, float] = {}
    monkeypatch.setattr(
        "foms.services.shipment.tablet_day_sheet.visible_spec_units",
        lambda order: table.get(order.id, 0.0),
    )
    return table


def _keys(sheet):
    return [g["key"] for g in sheet["groups"]]


def test_group_order_unassigned_then_settings_then_extra_by_name(units_by_id):
    rows = [
        _row(1, ["하늘팀"]),
        _row(2, ["김팀"]),
        _row(3, []),
        _row(4, ["가람팀"]),
        _row(5, ["박팀"]),
    ]
    settings = _settings(("박팀", 10, ()), ("김팀", 10, ()))

    sheet = build_tablet_day_sheet(rows, settings, "2026-11-11")

    assert _keys(sheet) == ["", "박팀", "김팀", "가람팀", "하늘팀"]
    assert sheet["groups"][0]["unassigned"] is True
    assert sheet["groups"][0]["color_index"] is None
    assert sheet["total"] == 5
    assert sheet["unassigned"] == 1


def test_numbers_continue_across_groups_and_as_rows_go_last(units_by_id):
    rows = [
        _row(1, ["김팀"], status="AS"),
        _row(2, ["김팀"]),
        _row(3, ["박팀"]),
        _row(4, ["김팀"], status="AS_RECEIVED"),
        _row(5, ["김팀"]),
    ]
    settings = _settings(("김팀", 10, ()), ("박팀", 10, ()))

    sheet = build_tablet_day_sheet(rows, settings, "2026-11-11")

    kim, park = sheet["groups"]
    assert [r["order"].id for r in kim["rows"]] == [2, 5, 1, 4]
    assert [r["is_as"] for r in kim["rows"]] == [False, False, True, True]
    assert [r["no"] for r in kim["rows"]] == [1, 2, 3, 4]
    assert [r["no"] for r in park["rows"]] == [5]


def test_two_worker_row_units_split_in_half(units_by_id):
    units_by_id.update({1: 22.4, 2: 6.0})
    rows = [_row(1, ["김팀", "박팀"]), _row(2, ["김팀"])]
    settings = _settings(("김팀", 30, ()), ("박팀", 30, ()))

    sheet = build_tablet_day_sheet(rows, settings, "2026-11-11")

    people = {p["name"]: p for p in sheet["people"]}
    assert people["김팀"]["units"] == pytest.approx(11.2 + 6.0)
    assert people["박팀"]["units"] == pytest.approx(11.2)
    assert people["김팀"]["count"] == 2
    assert people["박팀"]["count"] == 1
    # 줄 자수는 나누지 않은 줄 합 그대로
    assert sheet["groups"][0]["rows"][0]["units"] == pytest.approx(22.4)


def test_as_row_counts_but_adds_no_units(units_by_id):
    units_by_id.update({1: 9.0, 2: 3.0})
    rows = [_row(1, ["김팀"], status="AS_COMPLETED"), _row(2, ["김팀"])]

    sheet = build_tablet_day_sheet(rows, _settings(("김팀", 10, ())), "2026-11-11")

    kim = sheet["people"][0]
    assert kim["count"] == 2
    assert kim["units"] == pytest.approx(3.0)
    as_row = [r for r in sheet["groups"][0]["rows"] if r["is_as"]][0]
    assert as_row["units"] == 0.0


def test_over_capacity_and_off_day(units_by_id):
    units_by_id.update({1: 12.0, 2: 4.0})
    rows = [_row(1, ["김팀"]), _row(2, ["박팀"])]
    settings = _settings(("김팀", 10, ()), ("박팀", 10, ("2026-11-11",)), ("이팀", 10, ("2026-11-12",)))

    sheet = build_tablet_day_sheet(rows, settings, "2026-11-11")

    people = {p["name"]: p for p in sheet["people"]}
    assert people["김팀"]["over"] is True
    assert people["박팀"]["over"] is False
    assert people["박팀"]["off"] is True
    assert people["이팀"]["off"] is False
    assert people["김팀"]["capacity"] == 10.0


def test_off_is_false_when_no_target_date(units_by_id):
    settings = _settings(("김팀", 10, ("2026-11-11",)))

    sheet = build_tablet_day_sheet([_row(1, ["김팀"])], settings, None)

    assert sheet["people"][0]["off"] is False


def test_names_not_in_settings_trim_and_dedupe(units_by_id):
    units_by_id.update({1: 8.0})
    rows = [_row(1, ["  지역팀 ", "지역팀", "", "  ", "김팀"]), _row(2, ["지역팀"])]
    settings = _settings(("김팀", 10, ()), ("박팀", 10, ()))

    sheet = build_tablet_day_sheet(rows, settings, "2026-11-11")

    assert _keys(sheet) == ["지역팀"]
    assert [w["name"] for w in sheet["groups"][0]["rows"][0]["workers"]] == ["지역팀", "김팀"]
    names = [p["name"] for p in sheet["people"]]
    assert names == ["김팀", "박팀", "지역팀"]
    extra = sheet["people"][2]
    assert extra["in_settings"] is False
    assert extra["capacity"] is None and extra["over"] is False
    assert extra["count"] == 2
    # 두 명(중복 제거 뒤) 줄이라 반씩
    assert extra["units"] == pytest.approx(4.0)
    assert sheet["people"][0]["units"] == pytest.approx(4.0)


def test_color_index_consistent_across_groups_rows_and_people(units_by_id):
    rows = [
        _row(1, ["박팀", "최팀"]),
        _row(2, ["김팀"]),
        _row(3, []),
        _row(4, ["박팀"]),
    ]
    settings = _settings(("김팀", 10, ()), ("박팀", 10, ()), ("이팀", 10, ()), ("최팀", 10, ()))

    sheet = build_tablet_day_sheet(rows, settings, "2026-11-11")

    # 묶음 순서(김 · 박) → 둘째로만 나온 최 → 줄 없는 이
    expected = {"김팀": 1, "박팀": 2, "최팀": 3, "이팀": 4}
    assert {g["key"]: g["color_index"] for g in sheet["groups"] if g["key"]} == {"김팀": 1, "박팀": 2}
    for g in sheet["groups"]:
        for r in g["rows"]:
            for w in r["workers"]:
                assert w["color_index"] == expected[w["name"]]
    assert {p["name"]: p["color_index"] for p in sheet["people"]} == expected


def test_color_index_wraps_after_ten(units_by_id):
    names = [f"팀{i:02d}" for i in range(12)]
    rows = [_row(i + 1, [n]) for i, n in enumerate(names)]
    settings = _settings(*[(n, 10, ()) for n in names])

    sheet = build_tablet_day_sheet(rows, settings, "2026-11-11")

    assert [g["color_index"] for g in sheet["groups"]] == [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 1, 2]


def test_empty_rows(units_by_id):
    settings = _settings(("김팀", 10, ()), ("박팀", 5, ()))

    sheet = build_tablet_day_sheet([], settings, "2026-11-11")

    assert sheet["groups"] == []
    assert sheet["total"] == 0 and sheet["unassigned"] == 0
    assert [(p["name"], p["count"], p["units"], p["color_index"]) for p in sheet["people"]] == [
        ("김팀", 0, 0.0, 1),
        ("박팀", 0, 0.0, 2),
    ]


def test_real_visible_spec_units_used_without_patch():
    """가짜 없이 실제 visible_spec_units(width/300) 로도 나눠 센다."""
    rows = [_row(1, ["김팀", "박팀"], units=4.0)]
    sheet = build_tablet_day_sheet(rows, _settings(("김팀", 10, ()), ("박팀", 10, ())), "2026-11-11")

    assert sheet["groups"][0]["rows"][0]["units"] == pytest.approx(4.0)
    assert [p["units"] for p in sheet["people"]] == [pytest.approx(2.0), pytest.approx(2.0)]


# ── compute_team_remaining_units_for_date (D25) ───────────────────────────────

class _FakeQuery:
    """db.query(...) 사슬을 받아 마지막 .all() 에서 주어진 주문을 돌려준다."""

    def __init__(self, orders):
        self._orders = orders

    def __getattr__(self, _name):
        return lambda *a, **k: self

    def all(self):
        return self._orders


def _remaining(monkeypatch, orders, units, settings):
    monkeypatch.setattr(
        shipment_dashboard, "order_spec_units",
        lambda o, target_date=None: units[o.id],
    )
    db = SimpleNamespace(query=lambda *a, **k: _FakeQuery(orders))
    return shipment_dashboard.compute_team_remaining_units_for_date(db, "2026-11-11", settings)


def test_remaining_units_split_by_worker_count(monkeypatch):
    orders = [_row(1, ["김팀", "박팀"]), _row(2, ["김팀"])]
    settings = _settings(("김팀", 30, ()), ("박팀", 30, ()))

    remaining = _remaining(monkeypatch, orders, {1: 22.4, 2: 5.0}, settings)

    assert remaining["김팀"] == pytest.approx(30 - 11.2 - 5.0)
    assert remaining["박팀"] == pytest.approx(30 - 11.2)


def test_remaining_units_counts_unknown_name_in_head_count(monkeypatch):
    """설정에 없는 이름도 사람 수에 들어간다 — 세 명이면 셋으로 나눈다(중복 이름은 한 명)."""
    orders = [_row(1, ["김팀", " 지역팀", "지역팀 ", "박팀"])]
    settings = _settings(("김팀", 10, ()), ("박팀", 10, ()))

    remaining = _remaining(monkeypatch, orders, {1: 9.0}, settings)

    assert remaining == {"김팀": pytest.approx(7.0), "박팀": pytest.approx(7.0)}


def test_remaining_units_single_worker_unchanged(monkeypatch):
    remaining = _remaining(
        monkeypatch, [_row(1, ["김팀"])], {1: 6.5}, _settings(("김팀", 10, ()))
    )

    assert remaining["김팀"] == pytest.approx(3.5)
