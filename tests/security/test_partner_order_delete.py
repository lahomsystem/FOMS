"""협력사 주문 지우기(설계서 docs/specs/2026-11-04-partner-order-delete_SPEC.md).

라운즈는 자기 회사 주문을 "이대로 만들어 주세요" 전까지 휴지통으로 보낼 수 있다(이유 한 줄 필수). 지우면 감사 · 담당 팀
알림이 같은 트랜잭션에 남고, 커밋 뒤 발주방에 짧은 글이 한 번 간다(시험에서는 가짜 보내기). 대조군: 자기 회사 · 실측 예정 ·
도면 확인 대기는 200, 다른 회사 404 · 생산 409 · 이유 빈칸 400 · 발행 명세서 409. 이름 · 번호는 가짜다.
"""
from __future__ import annotations

import pytest

import foms.services.partners.order_delete as order_delete
from db import db_session
from models import Notification, Order, PartnerStatement, SecurityLog, User
from tests.security.partner_fixtures import _PAYLOAD, _client, _create, world  # noqa: F401 — pytest fixture 재노출

URL = "/api/partner/orders/{}/delete"


@pytest.fixture
def sent(monkeypatch):
    calls = []
    monkeypatch.setattr(order_delete, "is_configured", lambda: True)
    monkeypatch.setattr(order_delete, "get_routing_group_id", lambda _e, data: f"group-{data['push_kind']}")
    monkeypatch.setattr(order_delete, "send_group_message",
                        lambda group_id, text, **kw: calls.append((group_id, text, kw)) or {"success": True})
    return calls


def _order(app, w, stage="MEASURE", key="partner_a"):
    resp = _create(app, w[key], _PAYLOAD)
    assert resp.status_code == 200, resp.get_json()
    oid = resp.get_json()["data"]["order_id"]
    order = db_session.get(Order, oid)
    order.erp_stage_code = stage
    db_session.commit()
    return oid


def _partner(app, w, key="partner_a"):
    return _client(app, db_session.get(User, w[key]))


def test_partner_deletes_own_order_with_reason(app, world, sent):
    oid = _order(app, world)
    client = _partner(app, world)
    assert client.get(f"/partner/orders/{oid}").get_data(as_text=True).count("이 주문 지우기") == 1
    resp = client.post(URL.format(oid), json={"reason": "  고객이   취소함 "})
    assert resp.status_code == 200, resp.get_json()
    data = resp.get_json()["data"]
    assert data["channel_sent"] is True and data["redirect"].endswith("/partner")
    db_session.expire_all()
    order = db_session.get(Order, oid)
    assert order.deleted_at is not None and order.structured_data["delete"]["reason"] == "협력사 삭제: 고객이 취소함"
    log = db_session.query(SecurityLog).filter(SecurityLog.action == "PARTNER_ORDER_DELETED").one()
    assert log.target_id == oid and log.detail["reason"] == "고객이 취소함"
    note = db_session.query(Notification).filter(Notification.notification_type == "PARTNER_ORDER_DELETED").one()
    assert note.target_team == "CS" and "고객이 취소함" in note.message and "휴지통" in note.message
    assert len(sent) == 1 and sent[0][0] == "group-drawing"
    assert "[주문 삭제] 가나가구" in sent[0][1] and f"주문 #{oid}" in sent[0][1] and "이유: 고객이 취소함" in sent[0][1]
    assert client.get(f"/partner/orders/{oid}").status_code == 404
    assert f"/partner/orders/{oid}" not in client.get("/partner").get_data(as_text=True)
    again = client.post(URL.format(oid), json={"reason": "또"})
    assert again.status_code == 404


def test_confirm_stage_ok_but_production_and_blank_reason_blocked(app, world, sent):
    client = _partner(app, world)
    confirm = _order(app, world, stage="CONFIRM")
    blank = client.post(URL.format(confirm), json={"reason": "   "})
    assert blank.status_code == 400 and "이유" in blank.get_json()["error"]
    assert client.post(URL.format(confirm), json={"reason": "중복으로 올림"}).status_code == 200  # 대조군
    made = _order(app, world, stage="PRODUCTION")
    page = client.get(f"/partner/orders/{made}").get_data(as_text=True)
    assert "이 주문 지우기" not in page
    blocked = client.post(URL.format(made), json={"reason": "취소"})
    assert blocked.status_code == 409 and "제작을 시작한" in blocked.get_json()["error"]
    approved = _order(app, world, stage="CONFIRM")
    order = db_session.get(Order, approved)
    order.structured_data = {**order.structured_data, "blueprint": {"customer_confirmed": True}}
    db_session.commit()
    assert client.post(URL.format(approved), json={"reason": "취소"}).status_code == 409
    db_session.expire_all()
    assert db_session.get(Order, made).deleted_at is None and db_session.get(Order, approved).deleted_at is None
    assert len(sent) == 1


def test_other_org_staff_and_statement_blocked(app, world, sent):
    oid = _order(app, world)
    assert _partner(app, world, "partner_b").post(URL.format(oid), json={"reason": "남의 주문"}).status_code == 404
    sales = _client(app, db_session.get(User, world["sales"]))
    assert sales.post(URL.format(oid), json={"reason": "직원"}).status_code == 403
    db_session.add(PartnerStatement(partner_org_id=world["org_a"], order_id=oid, status="ISSUED", doc_no="T-1",
                                    total=1000, supply=909, vat=91, groups=[]))
    db_session.commit()
    resp = _partner(app, world).post(URL.format(oid), json={"reason": "취소"})
    assert resp.status_code == 409 and "거래명세서" in resp.get_json()["error"]
    db_session.expire_all()
    assert db_session.get(Order, oid).deleted_at is None and sent == []


def test_channel_failure_keeps_delete(app, world, monkeypatch):
    monkeypatch.setattr(order_delete, "is_configured", lambda: True)
    monkeypatch.setattr(order_delete, "get_routing_group_id", lambda _e, _d: "g")

    def boom(*_a, **_k):
        raise RuntimeError("채널톡 장애")

    monkeypatch.setattr(order_delete, "send_group_message", boom)
    oid = _order(app, world)
    resp = _partner(app, world).post(URL.format(oid), json={"reason": "고객 취소"})
    assert resp.status_code == 200 and resp.get_json()["data"]["channel_sent"] is False
    db_session.expire_all()
    assert db_session.get(Order, oid).deleted_at is not None
