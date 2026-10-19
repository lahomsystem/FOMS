"""PARTNER-FOMS 6-1: 협력사 직원 웹 푸시 — 알림 만들기 · 도면 확인 차례 · 구독 길 · 함께 고친 것.

스펙 docs/specs/2026-10-20-partner-notifications_SPEC.md §0 · §5 · §8.
각 허용 경로에는 거부 대조군(다른 회사 · 꺼진 직원 · 우리 직원 · 남의 기기 · 남의 알림)을 같이 둔다.
"""
from __future__ import annotations

import copy
from pathlib import Path

import pytest
from sqlalchemy.orm.attributes import flag_modified

import foms.services.partners.notify as partner_notify
from db import db_session
from foms.services.notifications import push_sender
from foms.services.notifications.partner_push import PARTNER_DRAWING_READY
from foms.services.partners.order_list import partner_list_filters, partner_order_board
from models import Notification, NotificationPushSubscription, Order, PartnerOrg, User
from tests.security.partner_fixtures import (  # noqa: F401 — pytest fixture 재노출
    _PAYLOAD,
    _client,
    _create,
    _to_confirm,
    _to_stage,
    _user,
    world,
)

_WRITE = {"X-FOMS-Notification-Write": "1"}


@pytest.fixture
def pushes(monkeypatch):
    sent: list[int] = []
    monkeypatch.setattr(partner_notify, "enqueue_push_for_notification", lambda nid, db=None: sent.append(nid))
    return sent


@pytest.fixture
def push_on(monkeypatch):
    monkeypatch.setenv("FOMS_WEB_PUSH_ENABLED", "1")
    monkeypatch.setenv("VAPID_PUBLIC_KEY", "BPub-test-key")


def _order(app, partner_id) -> int:
    resp = _create(app, partner_id)
    assert resp.status_code == 200, resp.get_json()
    return resp.get_json()["data"]["order_id"]


def _partner_rows(order_id):
    db_session.expire_all()
    return db_session.query(Notification).filter_by(order_id=order_id, notification_type=PARTNER_DRAWING_READY).all()


# --------------------------------------------------------------------------
# 알림 만들기
# --------------------------------------------------------------------------
def test_notify_goes_to_every_active_staff_of_that_company_only(app, world, pushes):
    order_id = _order(app, world["partner_a"])
    _user(role="PARTNER", team=None, org=db_session.get(PartnerOrg, world["org_a"]), name="꺼진 직원", is_active=False)
    order = db_session.get(Order, order_id)
    assert partner_notify.notify_partner_staff(db_session, order, PARTNER_DRAWING_READY) == 2
    rows = _partner_rows(order_id)
    assert {r.target_user_id for r in rows} == {world["partner_a"], world["partner_a2"]}
    assert all("홍*동 고객" in r.message and "서울시" not in r.message for r in rows)  # 이름 가림 · 주소 없음
    assert sorted(pushes) == sorted(r.id for r in rows)
    # 같은 일을 곧바로 다시 → 만들지 않는다.
    assert partner_notify.notify_partner_staff(db_session, db_session.get(Order, order_id), PARTNER_DRAWING_READY) == 0


def test_non_partner_order_gets_no_partner_notification(app, world, pushes):
    order_id = _order(app, world["partner_a"])
    order = db_session.get(Order, order_id)
    order.partner_org_id = None
    db_session.commit()
    assert partner_notify.notify_partner_staff(db_session, order, PARTNER_DRAWING_READY) == 0
    assert _partner_rows(order_id) == [] and pushes == []


def test_drawing_receipt_confirm_notifies_partner_staff(app, world, pushes):
    order_id = _order(app, world["partner_a"])
    order = db_session.get(Order, order_id)
    sd = copy.deepcopy(order.structured_data)
    sd.update({"workflow": {"stage": "DRAWING"}, "drawing_status": "TRANSFERRED", "drawing_current_files": [],
               "drawing_transfer_history": [{"action": "TRANSFER", "files": []}]})
    order.structured_data = sd
    flag_modified(order, "structured_data")
    order.erp_stage_code = "DRAWING"
    order.status = "DRAWING"
    db_session.commit()
    admin = _client(app, db_session.get(User, world["admin"]))
    resp = admin.post(f"/api/orders/{order_id}/confirm-drawing-receipt")
    assert resp.status_code == 200, resp.get_json()
    rows = _partner_rows(order_id)
    assert {r.target_user_id for r in rows} == {world["partner_a"], world["partner_a2"]} and len(pushes) == 2


# --------------------------------------------------------------------------
# 푸시 문구 · 열 주소
# --------------------------------------------------------------------------
def test_partner_push_payload_opens_partner_page_even_with_env_override(app, world, monkeypatch):
    monkeypatch.setenv("FOMS_PUSH_P1_TYPES", "DRAWING_TRANSFERRED")  # 협력사 종류를 빼고 덮어써도
    notif = Notification(id=1, order_id=77, notification_type=PARTNER_DRAWING_READY, target_type="USER",
                         title="t", message="홍*동 고객(#77) 도면이 올라왔습니다.")
    assert push_sender._should_push(notif) is True
    payload = push_sender._build_payload(notif, "홍길동")
    assert payload["data"]["deep_link"] == "/partner/orders/77"
    assert payload["title"] == "협력사 주문 · 도면 확인 차례" and "홍길동" not in payload["body"]


def test_service_worker_allows_partner_deep_links():
    sw = Path("static/sw.js").read_text(encoding="utf-8")
    assert 'indexOf("/partner/")' in sw and 'indexOf("/erp/")' in sw


# --------------------------------------------------------------------------
# 구독 길 — 자기 것만
# --------------------------------------------------------------------------
def test_partner_can_subscribe_own_device_but_not_take_others(app, world, push_on):
    partner = _client(app, db_session.get(User, world["partner_a"]))
    assert partner.get("/erp/api/notifications/push/vapid-public-key").status_code == 200
    body = {"endpoint": "https://push.example/partner-a", "keys": {"p256dh": "k", "auth": "a"}}
    assert partner.post("/erp/api/notifications/push/subscribe", json=body, headers=_WRITE).status_code == 200
    db_session.add(NotificationPushSubscription(user_id=world["staff"], endpoint="https://push.example/staff"))
    db_session.commit()
    stolen = {"endpoint": "https://push.example/staff", "keys": {"p256dh": "k", "auth": "a"}}
    assert partner.post("/erp/api/notifications/push/subscribe", json=stolen, headers=_WRITE).status_code == 403
    # 시험 알림을 남에게 보내기 · 남의 알림 열람 기록은 거부.
    assert partner.post("/erp/api/notifications/push/test", json={"user_id": world["staff"]},
                        headers=_WRITE).status_code == 403
    other = Notification(order_id=None, notification_type="X", target_type="USER", target_user_id=world["staff"],
                         title="t")
    db_session.add(other)
    db_session.commit()
    assert partner.post("/erp/api/notifications/push/event", json={"notification_id": other.id, "event": "opened"},
                        headers=_WRITE).status_code == 404
    # 대조군: 벨 목록 · 관리 주소는 여전히 막혀 있다.
    assert partner.get("/erp/api/notifications").status_code == 403
    assert partner.get("/erp/api/notifications/push/health").status_code == 403


def test_partner_layout_has_push_button_and_manifest(app, world):
    html = _client(app, db_session.get(User, world["partner_a"])).get("/partner").get_data(as_text=True)
    assert "data-pp-push" in html and "partner-push.js" in html and "manifest-partner.json" in html


def test_admin_partner_page_shows_push_device_count(app, world):
    db_session.add(NotificationPushSubscription(user_id=world["partner_a"], endpoint="https://push.example/a1"))
    db_session.commit()
    html = _client(app, db_session.get(User, world["admin"])).get("/admin/partners").get_data(as_text=True)
    assert "알림 받는 기기" in html and '<span class="badge bg-success">1대</span>' in html and ">없음</span>" in html


# --------------------------------------------------------------------------
# 함께 고친 것
# --------------------------------------------------------------------------
def test_turn_counts_only_after_drawing_confirmed(app, world):
    order_id = _order(app, world["partner_a"])
    _to_confirm(order_id, drawing_status="RETURNED")  # 협력사 수정 요청 뒤 — 도면팀 차례
    filters = partner_list_filters({})
    board = partner_order_board(db_session, world["org_a"], world["partner_a"], filters, {})
    assert board["turn_count"] == 0 and board["orders"][0]["stage_label"] == "도면 작업 중"
    _to_confirm(order_id, drawing_status="CONFIRMED")
    board = partner_order_board(db_session, world["org_a"], world["partner_a"], filters, {})
    assert board["turn_count"] == 1 and board["orders"][0]["turn"] is True


def test_partner_as_progress_reads_visit_saved_by_as_screen(app, world):
    order_id = _order(app, world["partner_a"])
    _to_stage(order_id, "COMPLETED")
    client = _client(app, db_session.get(User, world["partner_a"]))
    assert client.post(f"/api/partner/orders/{order_id}/as", data={"content": "문짝 처짐"}).status_code == 200
    order = db_session.get(Order, order_id)
    sd = copy.deepcopy(order.structured_data)
    sd.setdefault("schedule", {})["as_visit"] = {"date": "2026-10-25", "time": "14:00"}  # AS 화면 저장 모양
    order.structured_data = sd
    flag_modified(order, "structured_data")
    db_session.commit()
    html = client.get(f"/partner/orders/{order_id}").get_data(as_text=True)
    assert "2026-10-25 14:00" in html
