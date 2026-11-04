"""출고 화면 협력사 희망 판 — 시공일 정하기 API · 권한 · 기록(설계서 2026-11-04-shipment-partner-request-board).

대조군: 협력사 아닌 주문(404) · 이미 정한 주문(409) · 시공 · 도면팀(403) · 7일 밖 기록 · 협력사 아닌 주문 기록.
"""
from __future__ import annotations

import datetime

from sqlalchemy.orm.attributes import flag_modified

from db import db_session
from foms.services.datetime_kst import get_today_kst, now_utc_naive
from foms.services.orders.order_mutation_policy import POLICY_REGISTRY, evaluate_policy, load_policy_manifest
from foms.services.partners.schedule_request import recent_partner_schedule_changes, shipment_pending_requests
from models import Notification, Order, OrderFieldChange, User
from tests.security.partner_fixtures import (  # noqa: F401 — pytest fixture 재노출
    _PAYLOAD,
    _client,
    _create,
    _user,
    world,
)


def _day(n: int) -> str:
    return (get_today_kst() + datetime.timedelta(days=n)).isoformat()


def _order(app, partner_id, *, hope=None, time="", name="희망고객") -> int:
    extra = {"requested_construction_date": hope or _day(3), "requested_construction_time": time}
    resp = _create(app, partner_id, {**_PAYLOAD, "customer_name": name, **extra})
    assert resp.status_code == 200, resp.get_json()
    return resp.get_json()["data"]["order_id"]


def _confirm(app, user_id, order_id, date, time=""):
    client = _client(app, db_session.get(User, user_id))
    return client.post(f"/api/erp/shipment/partner-requests/{order_id}/confirm", json={"date": date, "time": time})


def _set(app, user_id, order_id, date, time=""):
    client = _client(app, db_session.get(User, user_id))
    return client.post(f"/api/orders/{order_id}/construction-schedule", json={"date": date, "time": time})


def test_confirm_hope_date_fills_schedule_and_leaves_pending(app, world):
    order_id = _order(app, world["partner_a"], hope=_day(3), time="오전")
    resp = _confirm(app, world["staff"], order_id, _day(3), "오전")
    assert resp.status_code == 200, resp.get_json()
    data = resp.get_json()["data"]
    assert data["date"] == _day(3) and data["time"] == "오전" and data["moved"] is False
    db_session.expire_all()
    order = db_session.get(Order, order_id)
    assert order.erp_construction_date == _day(3)
    assert order.structured_data["schedule"]["construction"] == {"date": _day(3), "time": "오전"}
    assert all(p["id"] != order_id for p in shipment_pending_requests(db_session))
    # 협력사 직원 알림(전역 훅 — 처음 정할 때도 보낸다)
    partner_ids = {world["partner_a"], world["partner_a2"]}
    notes = db_session.query(Notification).filter(Notification.order_id == order_id,
                                                  Notification.notification_type == "PARTNER_CONSTRUCTION_DATE").all()
    assert {n.target_user_id for n in notes} == partner_ids
    # 변경 원장 · 판 기록
    assert db_session.query(OrderFieldChange).filter(OrderFieldChange.order_id == order_id,
                                                     OrderFieldChange.path == "schedule.construction.date").count() == 1
    history = [h for h in recent_partner_schedule_changes(db_session) if h["order_id"] == order_id]
    assert history and history[0]["after"] == _day(3) and history[0]["hope"] == _day(3) and history[0]["before"] == ""
    assert history[0]["actor_name"] == db_session.get(User, world["staff"]).name


def test_confirm_other_day_is_moved_and_second_confirm_conflicts(app, world):
    order_id = _order(app, world["partner_a"], hope=_day(3))
    resp = _confirm(app, world["staff"], order_id, _day(5))
    assert resp.status_code == 200 and resp.get_json()["data"]["moved"] is True
    again = _confirm(app, world["staff"], order_id, _day(6))
    assert again.status_code == 409 and again.get_json()["code"] == "ALREADY_SCHEDULED"
    db_session.expire_all()
    assert db_session.get(Order, order_id).erp_construction_date == _day(5)


def test_confirm_keeps_existing_construction_time(app, world):
    order_id = _order(app, world["partner_a"])
    order = db_session.get(Order, order_id)
    sd = dict(order.structured_data)
    sd["schedule"] = {"construction": {"time": "오후"}}
    order.structured_data = sd
    flag_modified(order, "structured_data")
    db_session.commit()
    resp = _confirm(app, world["staff"], order_id, _day(3), "오전")
    assert resp.status_code == 200 and resp.get_json()["data"]["time"] == "오후"


def test_confirm_input_errors(app, world):
    order_id = _order(app, world["partner_a"])
    assert _confirm(app, world["staff"], order_id, "").status_code == 400
    assert _confirm(app, world["staff"], order_id, _day(-1)).status_code == 400
    assert _confirm(app, world["staff"], order_id, _day(3), "10:30").status_code == 400
    db_session.expire_all()
    assert not db_session.get(Order, order_id).erp_construction_date


def test_confirm_permissions(app, world):
    shipment = _user(team="SHIPMENT").id
    construction = _user(team="CONSTRUCTION").id
    drawing = _user(team="DRAWING").id
    order_ids = [_order(app, world["partner_a"], name=f"고객{i}") for i in range(4)]
    assert _confirm(app, construction, order_ids[0], _day(3)).status_code == 403
    assert _confirm(app, drawing, order_ids[0], _day(3)).status_code == 403
    assert _confirm(app, world["partner_a"], order_ids[0], _day(3)).status_code == 403
    assert _confirm(app, shipment, order_ids[0], _day(3)).status_code == 200
    assert _confirm(app, world["sales"], order_ids[1], _day(3)).status_code == 200
    assert _confirm(app, world["admin"], order_ids[2], _day(3)).status_code == 200
    assert _client(app, None).post(f"/api/erp/shipment/partner-requests/{order_ids[3]}/confirm",
                                   json={"date": _day(3)}).status_code in (401, 302)


def test_confirm_rejects_non_partner_order(app, world):
    order_id = _order(app, world["partner_a"])
    order = db_session.get(Order, order_id)
    order.partner_org_id = None
    db_session.commit()
    assert _confirm(app, world["staff"], order_id, _day(3)).status_code == 404


def test_shipment_team_changes_schedule_but_not_whole_form(app, world):
    shipment = _user(team="SHIPMENT").id
    order_id = _order(app, world["partner_a"])
    assert _confirm(app, world["staff"], order_id, _day(3)).status_code == 200
    resp = _set(app, shipment, order_id, _day(4), "종일")
    assert resp.status_code == 200, resp.get_json()
    data = resp.get_json()["data"]
    assert data["before_date"] == _day(3) and data["date"] == _day(4) and data["time"] == "종일"
    assert "change_reason_required" in data and data["change_set"]
    db_session.expire_all()
    assert db_session.get(Order, order_id).erp_construction_date == _day(4)
    # 폼 전체 저장은 CS · 영업 그대로 — 운영 before_request 가드(시험에서는 꺼짐)가 보는 정책으로 판정한다.
    manifest = load_policy_manifest()["routes"]
    assert manifest["erp_orders_structured.api_put_order_structured"]["policy_id"] == "ERP_EDIT"
    assert manifest["erp_shipment.api_set_construction_schedule"]["policy_id"] == "CONSTRUCTION_SCHEDULE_EDIT"
    shipment_user = db_session.get(User, shipment)
    assert not evaluate_policy(POLICY_REGISTRY["ERP_EDIT"], shipment_user).allowed
    assert evaluate_policy(POLICY_REGISTRY["CONSTRUCTION_SCHEDULE_EDIT"], shipment_user).allowed
    assert _set(app, _user(team="CONSTRUCTION").id, order_id, _day(5)).status_code == 403


def test_history_only_partner_orders_within_window(app, world):
    order_id = _order(app, world["partner_a"])
    other_id = _order(app, world["partner_a"], name="옛기록")
    plain_id = _order(app, world["partner_a"], name="우리주문")
    for oid in (order_id, other_id, plain_id):
        assert _confirm(app, world["staff"], oid, _day(3)).status_code == 200
    old = db_session.query(OrderFieldChange).filter(OrderFieldChange.order_id == other_id).all()
    for row in old:
        row.created_at = now_utc_naive() - datetime.timedelta(days=8)
    plain = db_session.get(Order, plain_id)
    plain.partner_org_id = None
    db_session.commit()
    ids = {h["order_id"] for h in recent_partner_schedule_changes(db_session)}
    assert order_id in ids and other_id not in ids and plain_id not in ids
