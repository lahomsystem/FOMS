"""PARTNER-FOMS 18-1: 협력사 주문 정보 — 실측시간 · 희망 시공일 · 보낸 뒤 고치기(PUT /api/partner/orders/<id>/info).

스펙 docs/specs/2026-10-19-partner-foms-mode_SPEC.md §18. 허용 경로마다 거부 대조군(다른 회사 · 단계 · 확정 뒤 · 우리 직원)을 둔다.
"""
from __future__ import annotations

from sqlalchemy.orm.attributes import flag_modified

from db import db_session
from models import Notification, Order, SecurityLog, User
from tests.security.partner_fixtures import (  # noqa: F401 — pytest fixture 재노출
    _PAYLOAD,
    _client,
    _create,
    _to_stage,
    world,
)

_REQ = {"requested_construction_date": "2026-11-03", "requested_construction_time": "오후"}


def _order(app, partner_id, extra=None) -> int:
    resp = _create(app, partner_id, {**_PAYLOAD, **(extra or {})})
    assert resp.status_code == 200, resp.get_json()
    return resp.get_json()["data"]["order_id"]


def _put(app, user_id, order_id, body):
    return _client(app, db_session.get(User, user_id)).put(f"/api/partner/orders/{order_id}/info", json=body)


def _sd(order_id) -> dict:
    db_session.expire_all()
    return db_session.get(Order, order_id).structured_data


def _set_construction(order_id, date):
    order = db_session.get(Order, order_id)
    sd = dict(order.structured_data)
    sd["schedule"] = {"construction": {"date": date, "time": "오전"}}
    order.structured_data = sd
    flag_modified(order, "structured_data")
    db_session.commit()


def _shipment_notes(order_id):
    return db_session.query(Notification).filter(Notification.order_id == order_id,
                                                 Notification.target_team == "SHIPMENT").all()


def test_create_keeps_measure_time_and_request_only_in_intake(app, world):
    order_id = _order(app, world["partner_a"], {"measured_on": "2026-10-20", "measured_time": "오전",
                                                "requested_construction_date": "2026-11-03",
                                                "requested_construction_time": "14:00"})
    sd = _sd(order_id)
    intake = sd["partner_intake"]
    assert intake["measured_on"] == "2026-10-20" and intake["measured_time"] == "오전"
    assert intake["requested_construction"] == {"date": "2026-11-03", "time": "14:00"}
    assert "schedule" not in sd  # 확정 시공일 · 실측 일정은 우리 몫 — 건드리지 않는다
    notes = _shipment_notes(order_id)
    assert len(notes) == 1 and "2026-11-03 14:00" in notes[0].message


def test_create_drops_bad_dates_and_no_request_means_no_shipment_notice(app, world):
    order_id = _order(app, world["partner_a"], {"measured_on": "2026-13-40", "requested_construction_date": "내일"})
    intake = _sd(order_id)["partner_intake"]
    assert intake["measured_on"] is None and intake["requested_construction"] is None
    assert _shipment_notes(order_id) == []


def test_info_edit_while_intake_open_updates_columns_intake_and_history(app, world):
    order_id = _order(app, world["partner_a"])
    body = {"customer_name": "김새이름", "customer_phone": "010-2222-3333", "address": "서울 송파구 송파대로 345 101동",
            "measured_on": "2026-10-22", "measured_time": "10:30", **_REQ}
    resp = _put(app, world["partner_a"], order_id, body)
    assert resp.status_code == 200, resp.get_json()
    assert resp.get_json()["data"]["address_changed"] is True
    order = db_session.get(Order, order_id)
    assert (order.customer_name, order.phone, order.address) == ("김새이름", "010-2222-3333", body["address"])
    sd = order.structured_data
    assert sd["parties"]["customer"]["name"] == "김새이름" and sd["site"]["address_full"] == body["address"]
    intake = sd["partner_intake"]
    assert intake["customer"] == {"name": "김새이름", "phone": "010-2222-3333"}
    assert intake["measured_time"] == "10:30" and intake["requested_construction"]["date"] == "2026-11-03"
    assert intake["info_edits"][-1]["before"]["customer"]["name"] == _PAYLOAD["customer_name"]
    assert db_session.query(SecurityLog).filter_by(action="PARTNER_ORDER_INFO_EDITED", target_id=order_id).count() == 1
    assert db_session.query(Notification).filter_by(order_id=order_id,
                                                    notification_type="PARTNER_ORDER_INFO_EDITED").count() == 1
    assert len(_shipment_notes(order_id)) == 1
    # 같은 희망일을 다시 보내면 출고팀 알림을 또 만들지 않는다.
    assert _put(app, world["partner_a"], order_id, _REQ).status_code == 200
    assert len(_shipment_notes(order_id)) == 1


def test_info_closed_after_drawing_but_request_open_until_confirmed(app, world):
    order_id = _order(app, world["partner_a"])
    _to_stage(order_id, "DRAWING")
    closed = _put(app, world["partner_a"], order_id, {"customer_name": "x", "customer_phone": "1", "address": "y"})
    assert closed.status_code == 409
    assert _put(app, world["partner_a"], order_id, _REQ).status_code == 200  # 희망일은 시공일 확정 전까지
    _set_construction(order_id, "2026-11-05")
    late = _put(app, world["partner_a"], order_id, {"requested_construction_date": "2026-11-07"})
    assert late.status_code == 409
    assert _sd(order_id)["partner_intake"]["requested_construction"]["date"] == "2026-11-03"


def test_info_edit_rejects_other_company_staff_and_empty(app, world):
    order_id = _order(app, world["partner_a"])
    assert _put(app, world["partner_b"], order_id, _REQ).status_code == 404
    assert _put(app, world["staff"], order_id, _REQ).status_code == 403
    assert _put(app, world["partner_a"], order_id, {}).status_code == 400
    blank = _put(app, world["partner_a"], order_id, {"customer_name": "", "customer_phone": "1", "address": "y"})
    assert blank.status_code == 400
    assert _sd(order_id)["partner_intake"].get("info_edits") is None


def test_partner_screens_show_editable_fields_and_staff_sees_request(app, world):
    order_id = _order(app, world["partner_a"], {"requested_construction_date": "2026-11-03",
                                                "requested_construction_time": "오후"})
    client = _client(app, db_session.get(User, world["partner_a"]))
    new = client.get("/partner/orders/new").get_data(as_text=True)
    for part in ('data-pp-phone', 'data-pp-phone-manual', 'data-pp-date', 'name="measured_time"',
                 'name="requested_construction_date"', 'data-pp-time-select', "flatpickr@4.6.13"):
        assert part in new, part
    detail = client.get(f"/partner/orders/{order_id}").get_data(as_text=True)
    assert 'data-pp-info-groups="info request"' in detail and 'value="2026-11-03"' in detail
    assert 'id="ppAddressModal"' in detail
    # 우리 주문 화면: 시공일 칸 아래 "협력사 희망" 한 줄 — 협력사 주문이 아니면 없다(대조군).
    staff = _client(app, db_session.get(User, world["admin"]))
    page = staff.get(f"/edit/{order_id}").get_data(as_text=True)
    assert "data-erp-partner-requested-construction" in page and "협력사 희망: 2026-11-03 오후" in page
    _set_construction(order_id, "2026-11-05")
    locked = client.get(f"/partner/orders/{order_id}").get_data(as_text=True)
    assert "requested_construction_date" not in locked and "시공일 (확정)" in locked
