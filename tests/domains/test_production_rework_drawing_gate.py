"""수정 제작도 도면이 수정 중이면 막는다 — 사용자 결정(2026-09-29, 도면 결함 2차 2a-2 뒤처리).

제작완료(CONSTRUCTION) 주문을 다시 제작중으로 되돌리는 ``POST /api/orders/<id>/production/rework``
는 run 을 바로 연다. 도면이 수정 중(RETURNED·TRANSFERRED)이면 옛 도면으로 다시 만들 수 있으므로
[제작 시작] (a) 와 같은 판정(``revision_in_flight_block``)으로 막는다. 관리자는 사유를 적고 뚫는다.
"""
from __future__ import annotations

import pytest

from tests.support.confirm_seed import confirmed_drawing_sd, login_as, reload_order, seed_erp_order, seed_user

_OVERRIDE = {"admin_override": True, "override_reason": "현장 긴급 재제작 — 관리자 확인"}


def _finished_order(tag: str, drawing_status: str) -> int:
    sales = seed_user(f"rw_s_{tag}", team="SALES")
    drafter = seed_user(f"rw_d_{tag}", team="DRAWING")
    return seed_erp_order("CONSTRUCTION", sales=sales, drafter=drafter,
                          **confirmed_drawing_sd(drawing_status=drawing_status))


@pytest.mark.parametrize("drawing_status", ["RETURNED", "TRANSFERRED"])
def test_rework_refuses_while_drawing_revision_in_flight(client, drawing_status):
    oid = _finished_order(f"blk_{drawing_status.lower()}", drawing_status)
    login_as(client, seed_user(f"rw_admin_{drawing_status.lower()}", role="ADMIN", team=None))

    res = client.post(f"/api/orders/{oid}/production/rework", json={})

    assert res.status_code == 409, res.get_json()
    body = res.get_json()
    assert body["code"] == "DRAWING_STATUS"
    assert body["drawing_status"] == drawing_status
    assert "rw_s_blk" in body["message"]  # 생산팀 문구에 영업 담당 이름
    order = reload_order(oid)
    assert order.erp_stage_code == "CONSTRUCTION"
    assert "rework" not in (order.structured_data.get("production") or {})


def test_rework_allowed_when_drawing_confirmed(client):
    oid = _finished_order("ok", "CONFIRMED")
    login_as(client, seed_user("rw_admin_ok", role="ADMIN", team=None))

    res = client.post(f"/api/orders/{oid}/production/rework", json={})

    assert res.status_code == 200, res.get_json()
    assert reload_order(oid).erp_stage_code == "PRODUCTION"


def test_admin_override_punches_the_rework_drawing_gate(client):
    oid = _finished_order("ovr", "RETURNED")
    login_as(client, seed_user("rw_admin_ovr", role="ADMIN", team=None))

    res = client.post(f"/api/orders/{oid}/production/rework", json=dict(_OVERRIDE))

    assert res.status_code == 200, res.get_json()
    assert reload_order(oid).erp_stage_code == "PRODUCTION"
