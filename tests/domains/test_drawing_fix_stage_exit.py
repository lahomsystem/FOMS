"""생산 넘어간 주문의 도면 수정 D3 고침 — 단계를 나가면 [수정 시작] 표시가 같은 쓰기에서 풀린다(사장님 답 "둘 다", 2026-11-25).

* 생산 단계에서 다른 단계로 가는 모든 길(제작 완료 — 관리자 뚫기 포함 · 강제 단계 변경 단건 · 일괄 · 일반 단계 변경 · 옛 상태 쓰기)이
  ``drawing_fix_marks.release_on_stage_exit`` 한 함수를 같은 쓰기 안에서 부른다 → ``drawing_fix.fixing`` 이 비고, 공장 '바뀐 것'에
  [수정 취소]와 같은 "도면 수정 취소" 한 줄(누가 = 그 쓰기를 한 사람, 폰 알림 없음).
* 생산 → 시공(제작 완료)도 나감이다. 시공 → 생산(완료 취소 · 수정 제작)은 지울 것이 없다(나갈 때 지웠다). 열린 공장 요청은 같은
  함수가 닫는다(D4 — ``done`` + ``via: stage_exit``, 자세한 시험은 ``test_drawing_fix_reject_api.py``). ``clear_fixing_on_stage_exit``
  자체는 요청을 건드리지 않는다.
* 대조군: 생산 안에서의 쓰기(제작 취소 · 공정 칸)는 안 지운다. 다시 생산으로 와도 옛 막힘이 살아나지 않는다(D1 검토 지적).
* 시공 대기 상세: 고치는 중인 도면에만 [수정 취소] — 누르면 풀리고 패킹 줄 409 도 풀린다. 고치는 중이 없으면 단추 없음(대조군).

되돌리면 실패: 제작 완료 뒤 시공 대기에 막힘이 남음 · 강제 되돌림 뒤 다시 생산으로 오면 옛 막힘이 살아남 · '바뀐 것'에 줄 없음 ·
공장 요청까지 지움 · 생산 안 쓰기가 표시를 지움. 이름은 모두 지어낸 값이다.
"""
from __future__ import annotations

import pytest

from db import db_session
from foms.services.orders import drawing_fix as fx
from foms.services.orders.drawing_fix_marks import FIX_STOPPED_EVENT, VIA_STAGE_EXIT, clear_fixing_on_stage_exit
from foms.services.production.part_mark_gates import DRAWING_REVISING
from foms.services.production_change_alerts import collect_production_change_alerts
from models import Order, OrderEvent
from tests.support.drawing_fix_workbench_seed import day, factory_request, login, make_order, people, sd_of
from tests.support.production_steps_seed import mark_order_inspected

FIX = {"sheet:s1": {"no": 2, "by_user_id": None, "by_name": "김도면", "at": "2026-11-25T05:10:00Z"}}


@pytest.fixture
def who():
    return people()


def _fixing_order(stage: str = "PRODUCTION", **kw) -> int:
    return make_order(3, stage=stage, cdate=day(3), extra={"drawing_fix": {"fixing": dict(FIX), "log": [],
                                                                           **kw.pop("fix_extra", {})}}, **kw)


def _stops(oid: int) -> list[OrderEvent]:
    db_session.expire_all()
    return db_session.query(OrderEvent).filter_by(order_id=oid, event_type=FIX_STOPPED_EVENT).all()


def _assert_released(oid: int, *, by_id: int, by_name: str) -> None:
    sd = sd_of(oid)
    assert sd["drawing_fix"]["fixing"] == {} and fx.fixing_idents(sd) == frozenset()
    assert sd["drawing_fix"]["log"][-1] | {"at": None} == {"act": "stop", "idents": ["sheet:s1"], "numbers": [2],
                                                           "by_name": by_name, "at": None, "via": VIA_STAGE_EXIT}
    [event] = _stops(oid)
    assert event.created_by_user_id == by_id and event.payload["numbers"] == [2] and event.payload["via"] == VIA_STAGE_EXIT
    assert event.payload["by_name"] == by_name


# --- 순수 규칙 ------------------------------------------------------------------


@pytest.mark.parametrize("from_stage,to_stage,cleared", [
    ("PRODUCTION", "CONSTRUCTION", True), ("PRODUCTION", "CONFIRM", True), ("생산", "시공", True), ("PRODUCTION", "ON_HOLD", True),
    ("PRODUCTION", "PRODUCTION", False), ("CONSTRUCTION", "PRODUCTION", False), ("CONFIRM", "PRODUCTION", False),
    ("CONSTRUCTION", "CS", False),
])
def test_only_leaving_production_clears(from_stage, to_stage, cleared):
    request = factory_request("2026-11-25T01:00:00Z", ["sheet:s0"], [1])
    sd = {"drawing_current_files": [{"key": f"k{j}", "sheet_id": f"s{j}"} for j in range(3)],
          "drawing_fix": {"fixing": dict(FIX), "requests": [request], "log": []}}
    rows = clear_fixing_on_stage_exit(sd, from_stage=from_stage, to_stage=to_stage, by_name="한관리", at="2026-11-25T06:00:00Z")
    assert bool(rows) is cleared and (sd["drawing_fix"]["fixing"] == {}) is cleared
    assert sd["drawing_fix"]["requests"] == [request]                    # 이 함수는 공장 요청을 안 건드린다(D4 는 따로 닫는다)


# --- 단계를 바꾸는 길마다 ------------------------------------------------------------


def test_admin_punched_production_complete_releases_in_the_same_write(client, who):
    oid = _fixing_order()
    mark_order_inspected(oid)
    login(client, who.admin)
    res = client.post(f"/api/orders/{oid}/production/complete",
                      json={"admin_override": True, "override_reason": "시험 — 도면 고치는 중 건너뜀"})
    assert res.status_code == 200, res.get_json()
    assert sd_of(oid)["workflow"]["stage"] == "CONSTRUCTION"
    _assert_released(oid, by_id=who.admin.id, by_name=who.admin.name)
    db_session.expire_all()
    alerts = collect_production_change_alerts(db_session, [db_session.get(Order, oid)], None)[oid]["alerts"]
    assert [(a["label"], a["detail"], a["by_name"]) for a in alerts if a["label"] == "도면 수정 취소"] == [
        ("도면 수정 취소", "도면 2", who.admin.name)]
    assert fx.blocked(sd_of(oid)).idents == frozenset()                   # 시공 대기에 막힘이 안 남는다


def test_stage_override_back_to_confirm_and_return_does_not_resurrect(client, who):
    oid = _fixing_order()
    login(client, who.admin)
    res = client.post(f"/api/orders/{oid}/workflow/stage-override",
                      json={"to_stage": "CONFIRM", "reason": "고객이 컨펌을 다시 보자고 함", "confirm": True})
    assert res.status_code == 200, res.get_json()
    _assert_released(oid, by_id=who.admin.id, by_name=who.admin.name)
    res = client.post(f"/api/orders/{oid}/workflow/stage-override",
                      json={"to_stage": "PRODUCTION", "reason": "다시 생산으로 보냄", "confirm": True})
    assert res.status_code == 200, res.get_json()
    sd = sd_of(oid)
    assert sd["workflow"]["stage"] == "PRODUCTION" and fx.blocked(sd).idents == frozenset() and len(_stops(oid)) == 1


def test_bulk_stage_override_releases_every_order(client, who):
    first, second = _fixing_order(), _fixing_order()
    login(client, who.admin)
    res = client.post("/api/orders/workflow/stage-override/bulk",
                      json={"order_ids": [first, second], "to_stage": "CONFIRM", "reason": "일괄로 컨펌 되돌림", "confirm": True})
    assert res.status_code == 200, res.get_json()
    for oid in (first, second):
        _assert_released(oid, by_id=who.admin.id, by_name=who.admin.name)


def test_general_status_change_releases(client, who):
    oid = _fixing_order()
    login(client, who.admin)
    res = client.post("/api/update_order_status", json={"order_id": oid, "status": "CONFIRM", "admin_override": True,
                                                         "override_reason": "고객 요청으로 컨펌 되돌림"})
    assert res.status_code == 200, res.get_json()
    assert sd_of(oid)["workflow"]["stage"] == "CONFIRM"
    _assert_released(oid, by_id=who.admin.id, by_name=who.admin.name)


def test_legacy_board_status_write_releases(client, who):
    """물류 보드 옛 길(``_sync_erp_stage``)이 단계를 '보류'로 옮기면 그것도 나감이다."""
    oid = _fixing_order()
    login(client, who.admin)
    res = client.post("/api/update_order_status", json={"order_id": oid, "status": "ON_HOLD"})
    assert res.status_code == 200, res.get_json()
    assert sd_of(oid)["workflow"]["stage"] == "ON_HOLD"
    _assert_released(oid, by_id=who.admin.id, by_name=who.admin.name)


def test_field_status_write_releases_once(client, who):
    """칸 하나 고치기(``update_order_field`` status)로 시공에 가도 같은 함수 한 번 — 이벤트 한 줄."""
    oid = _fixing_order()
    login(client, who.admin)
    res = client.post("/api/update_order_field", json={"order_id": oid, "field": "status", "value": "CONSTRUCTION"})
    assert res.status_code == 200, res.get_json()
    assert sd_of(oid)["workflow"]["stage"] == "CONSTRUCTION"
    _assert_released(oid, by_id=who.admin.id, by_name=who.admin.name)
    kept = _fixing_order()                                                  # 단계를 안 옮기는 상태 글(보류 표시)은 안 지운다
    assert client.post("/api/update_order_field", json={"order_id": kept, "field": "status", "value": "ON_HOLD"}).status_code == 200
    assert sd_of(kept)["workflow"]["stage"] == "PRODUCTION" and fx.fixing_idents(sd_of(kept)) == frozenset({"sheet:s1"})


# --- 대조군 --------------------------------------------------------------------------


def test_writes_inside_production_keep_fixing_and_requests(client, who):
    oid = _fixing_order(fix_extra={"requests": [factory_request("2026-11-25T01:00:00Z", ["sheet:s0"], [1])]})
    login(client, who.admin)
    assert client.post(f"/api/orders/{oid}/production/steps", json={"key": "assemble", "done": True}).status_code in (200, 409)
    sd = sd_of(oid)
    assert fx.fixing_idents(sd) == frozenset({"sheet:s1"}) and len(sd["drawing_fix"]["requests"]) == 1 and not _stops(oid)
    mark_order_inspected(oid)
    res = client.post(f"/api/orders/{oid}/production/complete",
                      json={"admin_override": True, "override_reason": "시험 — 뚫고 시공으로"})
    assert res.status_code == 200, res.get_json()
    sd = sd_of(oid)
    assert sd["drawing_fix"]["fixing"] == {} and len(sd["drawing_fix"]["requests"]) == 1   # 요청 줄은 남고(기록)
    assert sd["drawing_fix"]["requests"][0]["state"] == "done" and sd["drawing_fix"]["requests"][0]["via"] == "stage_exit"  # D4 — 닫힘


def test_coming_back_from_construction_has_nothing_to_clear(client, who):
    oid = make_order(3, stage="CONSTRUCTION", cdate=day(3))
    login(client, who.admin)
    res = client.post(f"/api/orders/{oid}/workflow/stage-override",
                      json={"to_stage": "PRODUCTION", "reason": "수정 제작으로 생산에 다시", "confirm": True})
    assert res.status_code == 200, res.get_json()
    assert "drawing_fix" not in sd_of(oid) and not _stops(oid)


# --- 시공 대기 상세의 [수정 취소] -------------------------------------------------------


def _packing_ready(oid: int) -> None:
    order = db_session.get(Order, oid)
    order.scheduled_date = day(0)
    db_session.commit()


def test_waiting_order_with_fixing_shows_stop_and_releases_packing(client, who):
    oid = _fixing_order(stage="CONSTRUCTION", factory2=("s2",))
    _packing_ready(oid)
    login(client, who.staff)
    html = client.get(f"/erp/drawing-workbench/{oid}").get_data(as_text=True)
    assert html.count('data-dwp-act="stop"') == 1 and 'data-dwp-act="start"' not in html
    assert "workbench-drawing-fix.js" in html and "도면 고치는 중 · 김도면" in html
    login(client, who.admin)
    url = f"/api/erp/shipment/packing/{oid}"
    refused = client.post(url, json={"updates": [{"key": "sheet:s1", "checked": True}]})
    assert refused.status_code == 409 and refused.get_json()["data"]["code"] == DRAWING_REVISING
    login(client, who.staff)
    res = client.post(f"/api/orders/{oid}/drawing/fix/stop", json={"targets": [{"sheet_id": "s1"}]})
    assert res.status_code == 200 and res.get_json()["data"]["changed"] is True
    assert fx.blocked(sd_of(oid)).idents == frozenset()
    login(client, who.admin)
    assert client.post(url, json={"updates": [{"key": "sheet:s1", "checked": True}]}).status_code == 200
    html = client.get(f"/erp/drawing-workbench/{oid}").get_data(as_text=True)
    assert "data-dwp-act" not in html                                    # 다 풀리면 단추 없음


def test_waiting_order_without_fixing_has_no_button(client, who):
    oid = make_order(3, stage="CONSTRUCTION", cdate=day(3))
    login(client, who.staff)
    html = client.get(f"/erp/drawing-workbench/{oid}").get_data(as_text=True)
    assert "공장 진행" in html and "data-dwp-act" not in html and "workbench-drawing-fix.js" not in html
