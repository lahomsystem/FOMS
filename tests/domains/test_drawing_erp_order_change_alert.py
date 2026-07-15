"""ERP Order 변경 → 도면팀 알림 SSOT 테스트."""
from __future__ import annotations

import copy
import datetime as dt

import pytest

from db import db_session
from models import Notification, Order, User
from foms.services.notifications.drawing_order_change import (
    HISTORY_ACTION,
    NOTIFICATION_TYPE,
    ack_drawing_order_change,
    apply_drawing_order_change_alert,
    compute_drawing_relevant_changes,
    is_order_change_pending,
    should_alert_drawing_team,
    summarize_changes,
)


def _base_sd(**overrides):
    sd = {
        "workflow": {"stage": "DRAWING"},
        "drawing": {"status": "IN_PROGRESS"},
        "drawing_status": "IN_PROGRESS",
        "site": {"address_full": "서울 강남구 1"},
        "schedule": {
            "measurement": {"date": "2026-07-20"},
            "construction": {"date": "2026-07-25"},
        },
        "items": [{"product_name": "붙박이장", "width": "1200", "height": "2400"}],
        "drawing_transfer_history": [],
    }
    sd.update(overrides)
    return sd


def test_compute_changes_detects_address_and_dims():
    old = _base_sd()
    new = _base_sd()
    new["site"]["address_full"] = "서울 서초구 2"
    new["items"][0]["width"] = "1300"
    changes = compute_drawing_relevant_changes(old, new)
    paths = {c["path"] for c in changes}
    assert "site.address" in paths
    assert "items" in paths


def test_compute_changes_empty_when_irrelevant():
    old = _base_sd()
    new = _base_sd()
    new["payment"] = {"deposit": 100}
    assert compute_drawing_relevant_changes(old, new) == []


def test_gate_blocks_pending_without_assignee():
    order = Order(id=1, status="RECEIVED")
    sd = _base_sd(workflow={"stage": "RECEIVED"}, drawing={"status": "PENDING"}, drawing_status="PENDING")
    assert should_alert_drawing_team(order, sd) is False


def test_gate_allows_drawing_stage():
    order = Order(id=1, status="DRAWING")
    sd = _base_sd()
    assert should_alert_drawing_team(order, sd) is True


def test_summarize_and_pending_flag():
    changes = [
        {"path": "schedule.construction.date", "label": "시공일", "from": "A", "to": "B"},
        {"path": "items", "label": "제품/치수/옵션", "from": "이전 스펙", "to": "변경됨"},
    ]
    note = summarize_changes(changes)
    assert "시공일" in note
    sd = _base_sd()
    sd["drawing"]["order_change_pending"] = True
    assert is_order_change_pending(sd) is True


@pytest.fixture
def drawing_order(app):
    """DRAWING stage ERP order fixture."""
    with app.app_context():
        db = db_session()
        order = Order(
            customer_name="테스트고객",
            phone="010",
            address="서울",
            product="붙박이장",
            status="DRAWING",
            received_date="2026-07-01",
            is_erp_order=True,
            structured_data=_base_sd(),
        )
        db.add(order)
        db.commit()
        db.refresh(order)
        yield order
        db.rollback()


def test_apply_creates_history_notification_and_pending(app, drawing_order):
    with app.app_context():
        db = db_session()
        order = db.get(Order, drawing_order.id)
        old = copy.deepcopy(order.structured_data)
        new = copy.deepcopy(old)
        new["items"][0]["width"] = "1500"
        notif, created = apply_drawing_order_change_alert(
            db,
            order,
            old,
            new,
            actor_user_id=None,
            actor_name="실측담당",
        )
        assert created is True
        assert notif is not None
        assert notif.notification_type == NOTIFICATION_TYPE
        assert notif.target_team == "DRAWING"
        history = new.get("drawing_transfer_history") or []
        assert history[-1]["action"] == HISTORY_ACTION
        assert is_order_change_pending(new) is True
        db.rollback()


def test_debounce_merges_within_60s(app, drawing_order):
    with app.app_context():
        db = db_session()
        order = db.get(Order, drawing_order.id)
        old = copy.deepcopy(order.structured_data)
        new = copy.deepcopy(old)
        new["schedule"]["construction"]["date"] = "2026-07-28"
        n1, c1 = apply_drawing_order_change_alert(
            db, order, old, new, actor_user_id=7, actor_name="A"
        )
        assert c1 is True
        mid = copy.deepcopy(new)
        new2 = copy.deepcopy(new)
        new2["site"]["address_full"] = "부산"
        n2, c2 = apply_drawing_order_change_alert(
            db, order, mid, new2, actor_user_id=7, actor_name="A"
        )
        assert c2 is False
        assert n2 is not None and n1 is not None and n2.id == n1.id
        history = new2.get("drawing_transfer_history") or []
        assert len([h for h in history if h.get("action") == HISTORY_ACTION]) == 1
        note = history[-1]["note"]
        assert "시공일" in note and "주소" in note
        db.rollback()


def test_ack_clears_pending(app, drawing_order):
    with app.app_context():
        db = db_session()
        order = db.get(Order, drawing_order.id)
        sd = copy.deepcopy(order.structured_data)
        sd["drawing_transfer_history"] = [{
            "action": HISTORY_ACTION,
            "note": "치수 변경",
            "acked": False,
            "at": dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }]
        sd["drawing"]["order_change_pending"] = True
        order.structured_data = sd
        assert ack_drawing_order_change(db, order, actor_user_id=1, actor_name="도면") is True
        assert is_order_change_pending(order.structured_data) is False
        db.rollback()


def test_deep_link_includes_erp_order_changed(app):
    from foms.api.notifications import _resolve_notification_deep_link

    notif = Notification(
        order_id=4364,
        notification_type=NOTIFICATION_TYPE,
        title="t",
        message="m",
    )
    sd = {
        "drawing_transfer_history": [{
            "action": HISTORY_ACTION,
            "at": "2026-07-15 12:00:00",
            "by_user_id": 1,
        }]
    }
    link = _resolve_notification_deep_link(notif, sd)
    assert link["deep_tab"] == "timeline"
    assert "/erp/drawing-workbench/4364" in (link["deep_link_url"] or "")
    assert "tab=timeline" in (link["deep_link_url"] or "")
