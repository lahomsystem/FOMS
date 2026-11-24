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
    assert "as_tech" not in people["가짜시공자"] and people["가짜시공자"]["in_settings"] is True
    assert people["가짜떠돌이"]["as_tech"] is True
    tech = people["가짜AS기사"]
    assert tech["as_tech"] is True and tech["count"] == 0 and tech["capacity"] is None and tech["off"] is False
    assert 1 <= tech["color_index"] <= 10
    # 안 넘기면(시공 탭 · 협력사 출고 탭) 지금 그대로 — AS 기사 줄이 없다.
    plain = build_tablet_day_sheet([_row(1, ["가짜시공자"])], settings, "2026-11-23")
    assert [p["name"] for p in plain["people"]] == ["가짜시공자"] and "as_tech" not in plain["people"][0]


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


def test_order_screen_adopts_the_cleared_workers_before_it_saves() -> None:
    """주문 화면 AS 접수: 접수 응답의 시공자 값(비웠으면 빈 배열)을 화면 칸에 반영한 **뒤에** 주문을 저장한다.

    2026-11-24 운영 제보 — 접수가 비운 직후(1초 뒤) 화면 저장이 칸에 남은 옛 시공자를 다시 써 넣었다
    (원장: AS_RECEIVED 로 비움 → ORDER_STRUCTURED_SAVED 로 다시 채움).
    """
    js = _read("static/js/orders/erp-order-shared.js")
    assert "function erpApplyAsRegisterWorkers(workers)" in js
    helper = js[js.index("function erpApplyAsRegisterWorkers(workers)"):]
    helper = helper[:helper.index("function erpConfirmConstructionWorkerOverwrite()")]
    assert 'getElementById("erp-construction-workers")' in helper and "sd.shipment.construction_workers = names;" in helper
    flow = js[js.index("/as/register`"):]
    apply_at = flow.index("erpApplyAsRegisterWorkers(regData.construction_workers);")
    assert apply_at < flow.index("await erpSaveStructured({ redirect: false });")
    api = _read("foms/api/cs/as_orders.py")
    assert '"construction_workers": shipment.get("construction_workers") or [],' in api  # 응답이 지금 값을 돌려준다


def test_unassigned_as_rows_go_to_the_bottom_group() -> None:
    """시공자 없는 시공 줄은 맨 위, 시공자 없는 AS 줄은 맨 아래 묶음(사장님 2026-11-24 "배정 안 된 AS 건은 하단 배치")."""
    from foms.services.shipment.tablet_day_sheet import build_tablet_day_sheet, pc_card_rows

    rows = [_row(1, [], status="AS_RECEIVED"), _row(2, ["가짜시공자"]), _row(3, []), _row(4, ["가짜시공자"], status="AS_RECEIVED"),
            _row(5, [], status="AS_RECEIVED")]
    sheet = build_tablet_day_sheet(rows, [{"name": "가짜시공자", "capacity": 60, "off_dates": []}], "2026-11-24")
    order = [[r["order"].id for r in g["rows"]] for g in sheet["groups"]]
    assert order == [[3], [2, 4], [1, 5]]
    assert [(g["unassigned"], g["as_unassigned"]) for g in sheet["groups"]] == [(True, False), (False, False), (True, True)]
    assert [r["no"] for g in sheet["groups"] for r in g["rows"]] == [1, 2, 3, 4, 5]
    assert sheet["unassigned"] == 3  # 위 알약 숫자는 둘을 합친 수 그대로
    cards = {o.id: o.pc_card for o in pc_card_rows(sheet)}
    assert cards[3]["miss"] and not cards[3]["as_miss"] and cards[1]["miss"] and cards[1]["as_miss"] and cards[1]["count"] == 2
    # 시공자 없는 줄이 AS 뿐이면 위 묶음 없이 아래 묶음만.
    only_as = build_tablet_day_sheet([_row(1, [], status="AS_RECEIVED"), _row(2, ["가짜시공자"])], [], "2026-11-24")
    assert [[r["order"].id for r in g["rows"]] for g in only_as["groups"]] == [[2], [1]]
    assert "AS · " in _read("templates/shipment/partials/dashboard_main.html") and "g.as_unassigned" in _read("templates/shipment/partials/tablet_ship_grid.html")
