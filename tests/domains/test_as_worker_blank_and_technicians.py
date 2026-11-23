"""AS 줄 시공자 비우기 · 출고 설정 AS 기사 (설계서 docs/specs/2026-11-23-as-worker-blank-and-as-technicians_SPEC.md).

접수 때 비우기 · 취소 때 되돌리기는 tests/domains/test_as_cancel_restore.py · test_as_received_date_kst.py 가 본다.
여기는 비우는 조건(순수 함수) · 설정 저장/읽기 · 이름판 자료 · 화면 연결.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[2]


def _read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


@pytest.mark.parametrize(
    ("stage", "workers", "expected"),
    [
        ("CS", ["가짜기사"], True),            # 시공이 끝난 주문 — 비운다
        ("COMPLETED", ["가짜기사"], True),
        (None, ["가짜기사"], True),
        ("CONSTRUCTION", ["가짜기사"], False),  # 시공이 남은 주문 — 남은 시공일의 시공자라 건드리지 않는다
        ("PRODUCTION", ["가짜기사"], False),
        ("CS", [], False),                      # 이미 빈 칸 — 되돌릴 것이 없다
        ("CS", None, False),
    ],
)
def test_clears_workers_on_register(stage, workers, expected) -> None:
    from foms.services.orders.as_cycle_service import clears_workers_on_register

    shipment = {} if workers is None else {"construction_workers": workers}
    assert clears_workers_on_register(SimpleNamespace(erp_stage_code=stage), shipment) is expected
    assert clears_workers_on_register(SimpleNamespace(erp_stage_code=stage), None) is False


def test_settings_schema_accepts_as_technicians_and_keeps_them_when_absent() -> None:
    from foms.services.erp_shipment_settings import _project_loaded_settings, normalize_as_technicians
    from foms.services.shipment_reference import (
        ShipmentReferenceDuplicateError,
        project_to_legacy_shape,
        validate_reference_payload,
    )

    canonical = validate_reference_payload({"as_technicians": [" 가짜AS기사 ", "", "가짜AS둘"]})
    assert canonical["as_technicians"] == ["가짜AS기사", "가짜AS둘"]
    # key 를 안 보내면 canonical 에 없다 → 저장 병합이 기존 값을 지우지 않는다(시공자 마스터와 같은 규칙).
    assert "as_technicians" not in validate_reference_payload({})
    with pytest.raises(ShipmentReferenceDuplicateError):
        validate_reference_payload({"as_technicians": ["가짜AS기사", "가짜AS기사"]})

    assert project_to_legacy_shape({"as_technicians": ["가짜AS기사"]})["as_technicians"] == ["가짜AS기사"]
    assert project_to_legacy_shape({})["as_technicians"] == []
    loaded = _project_loaded_settings({"as_technicians": ["가짜AS기사", {"name": "가짜AS둘"}, "가짜AS기사", " "]})
    assert loaded["as_technicians"] == ["가짜AS기사", "가짜AS둘"]
    assert normalize_as_technicians("가짜") == []


def _row(oid, workers, status="RECEIVED"):
    return SimpleNamespace(
        id=oid, status=status, is_erp_order=True, shipment_visible_items=[],
        structured_data={"shipment": {"construction_workers": list(workers)}, "items": []},
    )


def test_day_sheet_people_mark_as_technicians() -> None:
    from foms.services.shipment.tablet_day_sheet import build_tablet_day_sheet

    settings = [{"name": "가짜시공자", "capacity": 60, "off_dates": []}]
    sheet = build_tablet_day_sheet(
        [_row(1, ["가짜시공자"]), _row(2, ["가짜떠돌이"])], settings, "2026-11-23",
        as_technicians=["가짜AS기사", "가짜시공자", "가짜떠돌이", " "],
    )
    people = {p["name"]: p for p in sheet["people"]}
    assert list(people) == ["가짜시공자", "가짜떠돌이", "가짜AS기사"]
    # 시공자 설정에도 있는 이름은 시공자다(자수 · 쉬는 날이 붙는다) — AS 기사 표식 없음.
    assert people["가짜시공자"]["as_tech"] is False and people["가짜시공자"]["in_settings"] is True
    assert people["가짜떠돌이"]["as_tech"] is True
    tech = people["가짜AS기사"]
    assert tech["as_tech"] is True and tech["count"] == 0 and tech["capacity"] is None and tech["off"] is False
    assert 1 <= tech["color_index"] <= 10
    # 안 넘기면(시공 탭 · 협력사 출고 탭) 지금 그대로 — AS 기사 줄이 없다.
    plain = build_tablet_day_sheet([_row(1, ["가짜시공자"])], settings, "2026-11-23")
    assert [p["name"] for p in plain["people"]] == ["가짜시공자"] and plain["people"][0]["as_tech"] is False


def test_screens_are_wired() -> None:
    assign = _read("static/js/shipment/tablet-ship-assign.js")
    assert "function shownPeople(on)" in assign and "p.as_tech" in assign and "data-is-as" in assign
    as_dash = _read("static/js/cs/as-dashboard.js")
    assert ".concat((data.settings && data.settings.as_technicians) || [])" in as_dash
    settings = _read("templates/shipment/partials/settings_body.html")
    assert 'id="list-as_technicians"' in settings and "out.as_technicians = [];" in settings
    route = _read("foms/web/shipment/dashboard.py")
    assert "as_technicians=settings.get('as_technicians')" in route
    api = _read("foms/api/cs/as_orders.py")
    assert "_confirmed_construction_worker_name" not in api and "cw_name" not in api
