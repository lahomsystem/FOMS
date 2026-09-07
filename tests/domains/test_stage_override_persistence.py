"""STATE-FORM-01 후속: 명시적 stage-override 는 이후 폼 저장에 취소되지 않는다.

회귀 배경: 실측일이 남아 있는 주문을 「단계 강제 변경」으로 접수로 되돌린 뒤 저장하면,
저장 뒤 실행되는 실측일 자동 전진(RECEIVED→MEASURE)이 매번 override 를 취소했다.
계약:
- override 표식(``workflow.stage_override``)이 지금 단계를 가리키고 실측일도 그대로면
  자동 전진을 건너뛴다.
- 실측일을 새로 잡으면 표식이 무효가 되어 자동 전진이 다시 동작한다.
"""
from __future__ import annotations

import copy

from db import db_session
from models import Order
from sqlalchemy.orm.attributes import flag_modified

from tests.domains.test_state_form import _login, _make_erp_order


def test_override_to_received_survives_later_form_save(client):
    """실측일이 잡힌 주문을 접수로 강제 변경하면, 이후 폼 저장이 실측으로 되돌리지 않는다.

    회귀: 저장 후 자동 전진(실측일 존재)이 방금 건 override 를 매번 덮어써서
    사용자가 "강제 변경 후 저장하면 계속 이전 단계로 돌아간다" 고 신고했다.
    """
    _login(client, "sf_override_sticky")
    order = _make_erp_order(stage="MEASURE")
    sd0 = copy.deepcopy(order.structured_data)
    sd0["schedule"] = {"measurement": {"date": "2026-08-10"}}
    order.structured_data = sd0
    flag_modified(order, "structured_data")
    db_session.commit()
    order_id = order.id

    resp = client.post(
        f"/api/orders/{order_id}/workflow/stage-override",
        json={"to_stage": "RECEIVED", "reason": "실측 취소 — 접수로 되돌림", "confirm": True},
    )
    assert resp.status_code == 200, resp.get_json()

    db_session.expire_all()
    sd = copy.deepcopy(db_session.get(Order, order_id).structured_data)
    sd["workflow"]["stage"] = "RECEIVED"
    save = client.put(
        f"/api/orders/{order_id}/structured",
        json={"structured_data": sd, "structured_schema_version": 1},
    )
    assert save.status_code == 200, save.get_json()

    db_session.expire_all()
    saved = db_session.get(Order, order_id)
    assert saved.status == "RECEIVED"
    assert saved.structured_data["workflow"]["stage"] == "RECEIVED"


def test_measurement_date_reset_after_override_advances_again(client):
    """override 로 접수에 둔 뒤 실측일을 새로 잡으면 자동 전진은 다시 동작한다."""
    _login(client, "sf_override_then_new_date")
    order = _make_erp_order(stage="MEASURE")
    sd0 = copy.deepcopy(order.structured_data)
    sd0["schedule"] = {"measurement": {"date": "2026-08-10"}}
    order.structured_data = sd0
    flag_modified(order, "structured_data")
    db_session.commit()
    order_id = order.id

    resp = client.post(
        f"/api/orders/{order_id}/workflow/stage-override",
        json={"to_stage": "RECEIVED", "reason": "실측 취소 — 접수로 되돌림", "confirm": True},
    )
    assert resp.status_code == 200, resp.get_json()

    db_session.expire_all()
    sd = copy.deepcopy(db_session.get(Order, order_id).structured_data)
    sd["workflow"]["stage"] = "RECEIVED"
    sd["schedule"] = {"measurement": {"date": "2026-08-20"}}
    save = client.put(
        f"/api/orders/{order_id}/structured",
        json={"structured_data": sd, "structured_schema_version": 1},
    )
    assert save.status_code == 200, save.get_json()

    db_session.expire_all()
    saved = db_session.get(Order, order_id)
    assert saved.status == "MEASURE"
    assert saved.structured_data["workflow"]["stage"] == "MEASURE"
