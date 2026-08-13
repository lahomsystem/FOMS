"""주문 변경 사유 저장 경로 계약 (ORDER-REASON-00 T4).

여기서 고정하는 것: 저장이 **막히지 않는다**, 사유 요구 판정이 응답으로 내려간다(화면이
서버 판정을 그대로 쓴다), 그리고 그 표식이 ``security_logs.detail`` 예산을 깨지 않는다.

정본: docs/specs/2026-08-13-order-change-reason_SPEC.md
"""

import copy

from werkzeug.security import generate_password_hash

from db import db_session
from foms.services.audit_writer import SECURITY_DETAIL_LIMIT
from models import Order, SecurityLog, User


def _login_as_admin(client, username="reason-admin"):
    user = User(
        username=username,
        password=generate_password_hash("admin"),
        role="ADMIN",
        team="CS",
        name="Reason Admin",
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    with client.session_transaction() as sess:
        sess["user_id"] = user.id
        sess["username"] = user.username
        sess["role"] = user.role
    return user


def _create_order(items=None) -> Order:
    order = Order(
        received_date="2026-08-13",
        customer_name="홍길동",
        phone="010-1234-5678",
        address="서울 테헤란로 123",
        product="붙박이장",
        status="RECEIVED",
        is_erp_order=True,
        structured_data={
            "workflow": {"stage": "RECEIVED"},
            "shipment": {},
            "schedule": {"measurement": {"date": "2026-08-14"}},
            "parties": {"customer": {"name": "홍길동", "phone": "010-1234-5678"}},
            "totals": {"final_amount": "1,300,000"},
            "items": items if items is not None else [{"product_name": "붙박이장", "price": "500000"}],
            "site": {"address_full": "서울 테헤란로 123", "address_main": "서울 테헤란로 123",
                     "address_detail": ""},
        },
    )
    db_session.add(order)
    db_session.commit()
    return order


def _save(client, order_id: int, mutate):
    order = db_session.get(Order, order_id)
    sd = copy.deepcopy(order.structured_data)
    mutate(sd)
    response = client.put(f"/api/orders/{order_id}/structured",
                          json={"structured_data": sd, "structured_schema_version": 1})
    assert response.status_code == 200, response.get_data(as_text=True)[:200]
    db_session.expire_all()
    return response


def _last_header(order_id: int) -> SecurityLog:
    return (
        db_session.query(SecurityLog)
        .filter(SecurityLog.action == "ORDER_STRUCTURED_SAVED", SecurityLog.target_id == order_id)
        .order_by(SecurityLog.id.desc())
        .first()
    )


def test_amount_save_asks_for_reason(client):
    """금액이 바뀐 저장은 사유 요구 표식을 응답과 감사 헤더 양쪽에 남긴다.

    바꾸는 값은 **입력**인 품목 단가다 — ``totals`` 로 보내봐야 서버가 재계산으로 덮는다.
    """
    _login_as_admin(client)
    order = _create_order()

    response = _save(client, order.id, lambda sd: sd["items"][0].update({"price": "620000"}))
    payload = response.get_json()

    assert payload["success"] is True
    assert payload["change_reason_required"] is True
    assert payload["change_set"]

    header = _last_header(order.id)
    assert header.detail["reason_required"] is True
    assert header.detail["change_set"] == payload["change_set"]


def test_non_sensitive_save_does_not_ask(client):
    """연락처만 바뀐 저장은 묻지 않는다 — 매번 물으면 직원이 아무 값이나 고른다."""
    _login_as_admin(client, "reason-admin-2")
    order = _create_order()

    response = _save(client, order.id,
                     lambda sd: sd["parties"]["customer"].update({"phone": "010-9999-0000"}))
    payload = response.get_json()

    assert payload["change_reason_required"] is False
    header = _last_header(order.id)
    assert "reason_required" not in header.detail


def test_save_succeeds_without_any_reason(client):
    """사유는 저장을 막지 않는다 — 사유 때문에 주문 저장이 실패하면 영업이 멈춘다."""
    _login_as_admin(client, "reason-admin-3")
    order = _create_order()

    response = _save(client, order.id,
                     lambda sd: sd["schedule"]["measurement"].update({"date": "2026-08-20"}))

    assert response.status_code == 200
    assert response.get_json()["change_reason_required"] is True
    db_session.expire_all()
    assert db_session.get(Order, order.id).structured_data["schedule"]["measurement"]["date"] == "2026-08-20"


def test_reason_flag_does_not_blow_detail_budget(client):
    """품목 대량 변경 + 사유 표식이 함께 와도 detail 이 통째 표식으로 바뀌지 않는다.

    ``normalize_security_detail`` 은 4,000자를 넘는 detail 을 ``{'truncated':True,'size':N}``
    로 바꾼다 — 그러면 변경 목록만이 아니라 ``mode``·주문 맥락까지 사라진다.
    """
    _login_as_admin(client, "reason-admin-4")
    items = [{"product_name": f"품목{i}", "price": str(100000 + i)} for i in range(46)]
    order = _create_order(items=items)

    def mutate(sd):
        for index, item in enumerate(sd["items"]):
            item["price"] = str(900000 + index)

    response = _save(client, order.id, mutate)
    assert response.get_json()["change_reason_required"] is True

    header = _last_header(order.id)
    assert header.detail.get("mode") == "full"          # 맥락이 살아 있다
    assert header.detail["reason_required"] is True
    # 46개 단가 + 서버가 재계산한 파생 totals — 원장은 전량, detail 은 상한·예산 안에서만.
    assert header.detail["change_count"] >= 46
    assert len(str(header.detail)) < SECURITY_DETAIL_LIMIT


def test_inline_save_reports_reason_requirement(client, monkeypatch):
    """인라인(blur 자동저장)도 같은 판정을 응답에 싣는다 — 화면은 모달 대신 배너를 띄운다."""
    monkeypatch.setenv("FOMS_INLINE_EDIT_ENABLED", "1")
    _login_as_admin(client, "reason-admin-5")
    order = _create_order()

    response = client.patch(
        f"/api/orders/{order.id}/structured/fields",
        json={"field": "schedule.measurement.date", "value": "2026-08-25"},
    )
    assert response.status_code == 200, response.get_data(as_text=True)[:300]
    payload = response.get_json()

    assert payload["change_reason_required"] is True
    assert payload["change_set"]
