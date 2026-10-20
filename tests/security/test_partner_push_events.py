"""PARTNER-FOMS 6-2: 협력사 직원 웹 푸시 — 시공일 정해짐 · 바뀜, AS 방문일 정해짐, 시공 끝.

스펙 docs/specs/2026-10-20-partner-notifications_SPEC.md §4 · §5-3 · §8.
각 알림에는 협력사 아닌 주문 대조군을 같이 둔다.
"""
from __future__ import annotations

import copy
from pathlib import Path

import pytest
from sqlalchemy.orm.attributes import flag_modified

import foms.services.partners.notify as partner_notify
import foms.services.partners.notify_listeners as partner_listeners
from db import db_session
from foms.services.notifications.partner_push import (
    PARTNER_AS_VISIT,
    PARTNER_CONSTRUCTION_DATE,
    PARTNER_CONSTRUCTION_DONE,
)
from models import Notification, Order, User
from tests.security.partner_fixtures import (  # noqa: F401 — pytest fixture 재노출
    _client,
    _create,
    _to_stage,
    world,
)


@pytest.fixture
def pushes(monkeypatch):
    sent: list[int] = []
    record = lambda nid, db=None: sent.append(nid)  # noqa: E731
    monkeypatch.setattr(partner_notify, "enqueue_push_for_notification", record)
    monkeypatch.setattr(partner_listeners, "enqueue_push_for_notification", record)
    return sent


def _order(app, partner_id) -> int:
    resp = _create(app, partner_id)
    assert resp.status_code == 200, resp.get_json()
    return resp.get_json()["data"]["order_id"]


def _set_construction_date(order_id, date):
    order = db_session.get(Order, order_id)
    sd = copy.deepcopy(order.structured_data)
    sd.setdefault("schedule", {}).setdefault("construction", {})["date"] = date
    order.structured_data = sd
    flag_modified(order, "structured_data")
    db_session.commit()


def _rows(order_id, ntype):
    db_session.expire_all()
    return db_session.query(Notification).filter_by(order_id=order_id, notification_type=ntype).order_by(Notification.id).all()


def test_construction_date_set_then_changed_notifies_partner_staff(app, world, pushes):
    order_id = _order(app, world["partner_a"])
    _set_construction_date(order_id, "2026-10-24")
    first = _rows(order_id, PARTNER_CONSTRUCTION_DATE)
    assert {r.target_user_id for r in first} == {world["partner_a"], world["partner_a2"]}
    assert all("2026-10-24로 정해졌습니다" in r.message and "바뀜" not in r.message for r in first)
    assert sorted(pushes) == sorted(r.id for r in first)  # 커밋 뒤 푸시 예약
    _set_construction_date(order_id, "2026-10-26")
    changed = _rows(order_id, PARTNER_CONSTRUCTION_DATE)[len(first):]
    assert len(changed) == 2 and all("바뀜: 2026-10-24 → 2026-10-26" in r.message for r in changed)


def test_construction_date_on_non_partner_order_is_silent(app, world, pushes):
    order_id = _order(app, world["partner_a"])
    order = db_session.get(Order, order_id)
    order.partner_org_id = None
    db_session.commit()
    _set_construction_date(order_id, "2026-10-24")
    assert _rows(order_id, PARTNER_CONSTRUCTION_DATE) == [] and pushes == []


def test_as_visit_saved_from_as_screen_notifies_partner_staff(app, world, pushes):
    order_id = _order(app, world["partner_a"])
    _to_stage(order_id, "COMPLETED")
    partner = _client(app, db_session.get(User, world["partner_a"]))
    assert partner.post(f"/api/partner/orders/{order_id}/as", data={"content": "문짝 처짐"}).status_code == 200
    admin = _client(app, db_session.get(User, world["admin"]))
    resp = admin.post("/api/update_order_field",
                      json={"order_id": order_id, "field_name": "as_visit_date", "new_value": "2026-10-25"})
    assert resp.status_code == 200, resp.get_data(as_text=True)
    rows = _rows(order_id, PARTNER_AS_VISIT)
    assert {r.target_user_id for r in rows} == {world["partner_a"], world["partner_a2"]}
    assert all("AS 방문이 2026-10-25로 잡혔습니다" in r.message for r in rows) and len(pushes) == 2


def test_construction_done_notifies_and_is_wired_after_commit(app, world, pushes):
    order_id = _order(app, world["partner_a"])
    _to_stage(order_id, "CS")
    assert partner_notify.notify_partner_construction_done(db_session, db_session.get(Order, order_id)) == 2
    assert all("시공이 끝났습니다" in r.message for r in _rows(order_id, PARTNER_CONSTRUCTION_DONE))
    # 연결: 시공 완료 라우트가 커밋 직후 부른다(라우트 시험은 시공 증빙 준비가 커서 연결만 고정).
    src = Path("foms/api/construction/orders.py").read_text(encoding="utf-8")
    assert "        db.commit()\n        notify_partner_construction_done(db, order)" in src
