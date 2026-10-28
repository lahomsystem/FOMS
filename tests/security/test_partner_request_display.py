"""협력사 희망 시공일 표시(사용자 2026-10-28) — 확정 전에는 협력사 목록 · ERP 대시보드 · 출고 화면에 "희망"으로 보인다.

희망일은 ``partner_intake.requested_construction`` 에만 있고 우리 시공일(``schedule.construction``)은 출고 담당자가
정한다(스펙 docs/specs/2026-10-19-partner-foms-mode_SPEC.md §18). 대조군: 희망일 없는 협력사 주문, 시공일 확정 뒤.
"""
from __future__ import annotations

from sqlalchemy.orm.attributes import flag_modified

from db import db_session
from foms.services.partners.schedule_request import pending_request_texts, shipment_pending_requests
from models import Order, User
from tests.security.partner_fixtures import (  # noqa: F401 — pytest fixture 재노출
    _PAYLOAD,
    _client,
    _create,
    world,
)

_REQ = {"requested_construction_date": "2026-11-03", "requested_construction_time": "오후"}


def _order(app, partner_id, extra=None, name="홍길동") -> int:
    resp = _create(app, partner_id, {**_PAYLOAD, "customer_name": name, **(extra or {})})
    assert resp.status_code == 200, resp.get_json()
    return resp.get_json()["data"]["order_id"]


def _confirm(order_id, date):
    order = db_session.get(Order, order_id)
    sd = dict(order.structured_data)
    sd["schedule"] = {"construction": {"date": date, "time": "오전"}}
    order.structured_data = sd
    flag_modified(order, "structured_data")
    order.erp_construction_date = date
    db_session.commit()


def test_pending_request_reads_only_unconfirmed_requests(app, world):
    asked = _order(app, world["partner_a"], _REQ, name="희망고객")
    plain = _order(app, world["partner_a"], name="희망없음")
    assert pending_request_texts(db_session, {asked, plain}) == {asked: "2026-11-03 오후"}
    pending = shipment_pending_requests(db_session)
    assert [(p["id"], p["text"]) for p in pending] == [(asked, "2026-11-03 오후")]
    assert pending[0]["customer_name"] == "희망고객" and pending[0]["partner_name"]
    _confirm(asked, "2026-11-05")
    assert pending_request_texts(db_session, {asked}) == {}
    assert shipment_pending_requests(db_session) == []


def test_partner_list_shows_request_until_confirmed(app, world):
    asked = _order(app, world["partner_a"], _REQ)
    client = _client(app, db_session.get(User, world["partner_a"]))
    page = client.get("/partner").get_data(as_text=True)
    assert "2026-11-03 오후 <span class=\"text-muted small\">(희망)</span>" in page
    _confirm(asked, "2026-11-05")
    page = client.get("/partner").get_data(as_text=True)
    assert "2026-11-05" in page and "(희망)" not in page


def test_erp_dashboard_and_shipment_show_pending_request(app, world):
    asked = _order(app, world["partner_a"], _REQ, name="희망고객")
    admin = _client(app, db_session.get(User, world["admin"]))
    dash = admin.get("/erp/dashboard?q=희망고객&from_dashboard=1").get_data(as_text=True)
    assert "협력사 희망 2026-11-03 오후 · 확정 대기" in dash
    ship = admin.get("/erp/shipment").get_data(as_text=True)
    assert "data-partner-pending-requests" in ship and f"/edit/{asked}" in ship
    _confirm(asked, "2026-11-05")
    assert "협력사 희망 2026-11-03" not in admin.get("/erp/dashboard?q=희망고객&from_dashboard=1").get_data(as_text=True)
    assert "data-partner-pending-requests" not in admin.get("/erp/shipment").get_data(as_text=True)


def test_items_save_goes_back_to_list(app, world):
    order_id = _order(app, world["partner_a"])
    client = _client(app, db_session.get(User, world["partner_a"]))
    detail = client.get(f"/partner/orders/{order_id}").get_data(as_text=True)
    assert 'data-pp-items-url=' in detail and 'data-pp-list-url="/partner' in detail
    with open("static/js/partner/partner-order.js", encoding="utf-8") as fh:
        script = fh.read()
    assert "window.location.href = button.getAttribute('data-pp-list-url')" in script
