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
    assert "items.0.width" in paths
    width_ch = next(c for c in changes if c["path"] == "items.0.width")
    assert width_ch["from"] == "1200"
    assert width_ch["to"] == "1300"
    assert "W" in width_ch["label"]


def test_compute_changes_detects_manager():
    """담당자(parties.manager) 변경은 도면 타임라인에 반드시 잡혀야 함."""
    old = _base_sd(parties={"manager": {"name": "한용희"}, "customer": {"name": "고객"}})
    new = _base_sd(parties={"manager": {"name": "꿈돌이"}, "customer": {"name": "고객"}})
    changes = compute_drawing_relevant_changes(old, new)
    assert any(c["path"] == "parties.manager.name" for c in changes)
    mgr = next(c for c in changes if c["path"] == "parties.manager.name")
    assert mgr["from"] == "한용희"
    assert mgr["to"] == "꿈돌이"
    assert mgr["label"] == "담당자"


def test_compute_changes_item_option_before_after():
    """색상·옵션 등도 before→after로 표기."""
    old = _base_sd()
    old["items"][0]["color"] = "화이트"
    old["items"][0]["option"] = "푸쉬"
    new = _base_sd()
    new["items"][0]["color"] = "포그그레이"
    new["items"][0]["option"] = "손잡이형"
    changes = compute_drawing_relevant_changes(old, new)
    by_path = {c["path"]: c for c in changes}
    assert by_path["items.0.color"]["from"] == "화이트"
    assert by_path["items.0.color"]["to"] == "포그그레이"
    assert by_path["items.0.option"]["from"] == "푸쉬"
    assert by_path["items.0.option"]["to"] == "손잡이형"
    note = summarize_changes(changes)
    assert "화이트→포그그레이" in note or "색상" in note


def test_compute_changes_empty_when_operational_only():
    """drawing/quest 등 운영 JSON만 바뀌면 주문변경 이력 없음."""
    old = _base_sd()
    new = _base_sd()
    new["drawing"] = {"status": "TRANSFERRED", "order_change_pending": True}
    new["quests"] = {"DRAWING": {"done": True}}
    new["drawing_transfer_history"] = [{"action": "TRANSFER"}]
    assert compute_drawing_relevant_changes(old, new) == []


def test_compute_changes_detects_payment():
    old = _base_sd()
    new = _base_sd()
    new["payment"] = {"deposit": 100000}
    changes = compute_drawing_relevant_changes(old, new)
    assert any(c["path"] == "payment" for c in changes)


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
        {"path": "items.0.width", "label": "항목1 W(가로)", "from": "1200", "to": "1300"},
    ]
    note = summarize_changes(changes)
    assert "시공일" in note
    assert "1200→1300" in note
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
        # 실 User FK(Notification.created_by_user_id) — 하드코딩 7은 FK-ON 워커에서 red.
        actor = User(username="debounce_actor", password="x", role="STAFF", name="A", is_active=True)
        db.add(actor)
        db.commit()
        actor_id = actor.id
        order = db.get(Order, drawing_order.id)
        old = copy.deepcopy(order.structured_data)
        new = copy.deepcopy(old)
        new["schedule"]["construction"]["date"] = "2026-07-28"
        n1, c1 = apply_drawing_order_change_alert(
            db, order, old, new, actor_user_id=actor_id, actor_name="A"
        )
        assert c1 is True
        mid = copy.deepcopy(new)
        new2 = copy.deepcopy(new)
        new2["site"]["address_full"] = "부산"
        n2, c2 = apply_drawing_order_change_alert(
            db, order, mid, new2, actor_user_id=actor_id, actor_name="A"
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


def test_compute_changes_spec_rows_human_not_json():
    """스펙행 변경은 JSON 금지 — WxDxH 사람 표기. 스펙과 동일하면 스펙행 행 생략."""
    from foms.services.notifications.drawing_order_change import (
        format_spec_rows_display,
        humanize_order_change_changes,
    )

    assert (
        format_spec_rows_display(
            [{"spec_depth": "620", "spec_height": "2350", "spec_width": "3920"}]
        )
        == "3920x620x2350"
    )
    legacy = humanize_order_change_changes(
        [
            {
                "path": "items.0.spec_rows",
                "label": "항목1 스펙행",
                "from": '[{"spec_depth": "620", "spec_height": "2350", "spec_width": "3920"}]',
                "to": '[{"spec_depth": "620", "spec_height": "2350", "spec_width": "4000"}]',
            }
        ]
    )
    assert legacy[0]["from"] == "3920x620x2350"
    assert legacy[0]["to"] == "4000x620x2350"
    assert "{" not in legacy[0]["from"] and "[" not in legacy[0]["to"]

    old = _base_sd()
    old["items"][0] = {
        "product_name": "붙박이장",
        "spec": "3920x620x2350",
        "spec_width": "3920",
        "spec_depth": "620",
        "spec_height": "2350",
        "spec_rows": [{"spec_width": "3920", "spec_depth": "620", "spec_height": "2350"}],
    }
    new = _base_sd()
    new["items"][0] = {
        "product_name": "붙박이장",
        "spec": "4000x620x2350",
        "spec_width": "4000",
        "spec_depth": "620",
        "spec_height": "2350",
        "spec_rows": [{"spec_width": "4000", "spec_depth": "620", "spec_height": "2350"}],
    }
    changes = compute_drawing_relevant_changes(old, new)
    by_path = {c["path"]: c for c in changes}
    assert "items.0.spec_rows" not in by_path  # 스펙과 동일 → 중복 숨김
    assert by_path["items.0.spec"]["from"] == "3920x620x2350"
    assert by_path["items.0.spec"]["to"] == "4000x620x2350"
    for c in changes:
        assert "{" not in c["from"] and "{" not in c["to"]
        assert not str(c["from"]).lstrip().startswith("[")
        assert not str(c["to"]).lstrip().startswith("[")


def test_all_change_values_forbid_json():
    """결제·비고·옵션 list 등 모든 from/to 에 JSON 표기 금지."""
    from foms.services.notifications.drawing_order_change import (
        format_value_for_display,
        humanize_order_change_changes,
    )

    assert format_value_for_display({"amount": 1000, "method": "카드"}) == "금액 1000, 결제방법 카드"
    assert "{" not in format_value_for_display([{"a": 1}, {"b": 2}])

    old = _base_sd(notes={"address_note": "엘리베이터 없음", "phone_note": "오후만"})
    new = _base_sd(notes={"address_note": "엘리베이터 있음", "phone_note": "오후만"})
    changes = compute_drawing_relevant_changes(old, new)
    for c in changes:
        for side in ("from", "to"):
            v = str(c[side])
            assert not v.lstrip().startswith("{"), c
            assert not v.lstrip().startswith("["), c
            assert '"address_note"' not in v

    legacy = humanize_order_change_changes(
        [
            {
                "path": "notes.object",
                "label": "비고(상세)",
                "from": '{"phone_note": "a", "address_note": "b"}',
                "to": '{"phone_note": "a", "address_note": "c"}',
            }
        ]
    )
    assert "{" not in legacy[0]["from"] and "{" not in legacy[0]["to"]
    assert "주소 특이사항" in legacy[0]["to"] or "c" in legacy[0]["to"]
