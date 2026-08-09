"""금액 변경 이벤트 SSOT 계약 (T2).

``PAYMENT_CHANGED`` OrderEvent 의 **유일한 emit 지점**은
``foms/services/order_payment_sync.py`` 의 전역 ``before_flush`` 훅이다. 라우트별 emit 은
0줄이다 — 결제확인 토글 라우트를 한 글자도 고치지 않고 이벤트가 잡히는 것이 이 설계의 검증
조건이다.

여기서 고정하는 계약:

* 금액을 움직이는 **모든 쓰기 경로**(전체저장 PUT · 결제확인 토글 · 요청 밖 스크립트/워커)가
  변경된 field 마다 이벤트를 정확히 **1건** 남긴다.
* payload 는 ``{"field", "from", "to", "source"}``, 자유입력은 파싱 합계
  (``from_amount``/``to_amount``)를 병기한다.
* before(이전 값)는 **DB 에서 읽는다** — 정본 저장 패턴(deepcopy → 재할당 →
  ``flag_modified``)이 attribute history 의 old 를 파괴하므로 ``get_history`` 로는 잡히지
  않는다. 레거시 ``payments``(복수형) 블록은 서버 extractor 재사용으로 자동 폴백된다.
* 허위 이벤트 0: 값 무변경 · 같은 트랜잭션 왕복(11060→0→11060) · draft 자동저장 ·
  주문 생성 · ``Order.shipping_fee`` 변경(기존 ``SHIPPING_FEE_CHANGED`` 만).

**라우트 매트릭스 중 2경로는 구조적으로 N/A 다**(테스트 대신 계약으로 고정):

* 빠른수정 ``POST /api/update_order_field`` — ``ORDER_UPDATE_ALLOWED_FIELDS``
  (``foms/api/orders/field_update.py:25``)에 payment 계열 필드가 **0개**다. 금액을 이 경로로
  보낼 방법이 없으므로 "1건" 케이스가 성립하지 않는다 →
  :func:`test_quick_field_update_has_no_payment_capable_field` 가 그 전제를 고정하고,
  :func:`test_quick_field_update_scheduled_date_emits_no_payment_event` 가 허위 이벤트 0을 본다.
* 레거시 주문수정 폼 ``POST /edit/<id>`` — 폼이 쓰는 금액은 flat 컬럼
  ``Order.payment_amount`` 뿐이고 ``structured_data.payment`` 는 건드리지 않는다
  (``foms/web/orders/edit.py:196-229``). 할인 입력 자체가 없다 →
  :func:`test_legacy_edit_form_emits_no_payment_event` 가 허위 이벤트 0을 본다.
  (두 경로에 금액 쓰기가 생기면 SSOT 훅이 코드 수정 없이 자동으로 포착한다.)
"""

from __future__ import annotations

import copy
from typing import Any

import pytest
from sqlalchemy.orm.attributes import flag_modified
from werkzeug.security import generate_password_hash

from db import db_session
from models import Order, OrderEvent, User

_EVENT = "PAYMENT_CHANGED"


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def _make_user(username: str, *, role: str = "ADMIN", team: str | None = None) -> User:
    """테스트 사용자 1명 생성(커밋 포함)."""
    user = User(
        username=username,
        password=generate_password_hash("pw"),
        role=role,
        team=team,
        name=f"{username} 이름",
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    return user


def _login(client, user: User) -> None:
    """테스트 클라이언트 세션에 로그인 상태를 심는다."""
    with client.session_transaction() as sess:
        sess["user_id"] = user.id
        sess["username"] = user.username
        sess["role"] = user.role


def _erp_sd(payment: dict[str, Any] | None = None, **extra: Any) -> dict:
    """필수값(고객/전화/주소/제품명)을 갖춘 최소 ERP structured_data + payment 블록."""
    sd: dict[str, Any] = {
        "workflow": {"stage": "RECEIVED"},
        "parties": {"customer": {"name": "금액 고객", "phone": "010-1234-5678"}},
        "site": {"address_full": "서울 테헤란로 123", "address_main": "서울 테헤란로 123"},
        "items": [{"product_name": "붙박이장", "price": 1000000}],
        "schedule": {},
        "shipment": {},
    }
    if payment is not None:
        sd["payment"] = payment
    sd.update(extra)
    return sd


def _make_order(*, sd: dict[str, Any] | None = None, is_erp_order: bool = True) -> Order:
    """주문 1건 생성(커밋 포함). 생성 flush 는 이벤트 대상이 아니다."""
    order = Order(
        received_date="2026-08-01",
        customer_name="금액 고객",
        phone="010-1234-5678",
        address="서울 테헤란로 123",
        product="붙박이장",
        status="RECEIVED",
        manager_name="담당",
        is_erp_order=is_erp_order,
        structured_data=sd,
        erp_stage_code="RECEIVED" if is_erp_order else None,
    )
    db_session.add(order)
    db_session.commit()
    return order


def _events(order_id: int, event_type: str = _EVENT) -> list[OrderEvent]:
    """해당 주문의 이벤트를 생성순으로 반환."""
    db_session.expire_all()
    return (
        db_session.query(OrderEvent)
        .filter(OrderEvent.order_id == order_id, OrderEvent.event_type == event_type)
        .order_by(OrderEvent.id.asc())
        .all()
    )


def _changes(order_id: int) -> list[tuple[str, Any, Any]]:
    """이벤트 payload 의 ``(field, from, to)`` 목록."""
    return [(e.payload["field"], e.payload["from"], e.payload["to"]) for e in _events(order_id)]


def _mutate_payment(order: Order, **fields: Any) -> None:
    """정본 패턴(deepcopy → 수정 → 재할당 → flag_modified)으로 payment 를 고친다."""
    sd = copy.deepcopy(order.structured_data or {})
    payment = sd.get("payment")
    if not isinstance(payment, dict):
        payment = {}
    payment.update(fields)
    sd["payment"] = payment
    order.structured_data = sd
    flag_modified(order, "structured_data")


# --------------------------------------------------------------------------- #
# 1. 전체저장 PUT (실제 라우트)
# --------------------------------------------------------------------------- #
def test_put_full_save_discount_change_emits_single_event(client):
    """PUT /api/orders/<id>/structured 로 할인을 바꾸면 이벤트 정확히 1건.

    주문 4414 에서 할인 11,060원이 무음으로 사라진 실사고의 회귀 테스트다.
    """
    user = _make_user("pay_put_disc", role="ADMIN")
    user_id = user.id
    _login(client, user)
    order_id = _make_order(sd=_erp_sd({"discount": 11060, "deposit": 300000})).id

    resp = client.put(
        f"/api/orders/{order_id}/structured",
        json={"structured_data": _erp_sd({"discount": 0, "deposit": 300000})},
    )
    assert resp.status_code == 200, resp.get_data(as_text=True)
    assert resp.get_json()["success"] is True

    events = _events(order_id)
    assert len(events) == 1
    assert events[0].payload["field"] == "payment.discount"
    assert events[0].payload["from"] == 11060
    assert events[0].payload["to"] == 0
    assert events[0].payload["source"] not in (None, "", "system")
    assert events[0].created_by_user_id == user_id


def test_put_full_save_deposit_change_emits_single_event(client):
    """전체저장 PUT 의 예약금 변경 → 이벤트 1건(정수 비교)."""
    _login(client, _make_user("pay_put_dep", role="ADMIN"))
    order_id = _make_order(sd=_erp_sd({"deposit": "300,000"})).id

    resp = client.put(
        f"/api/orders/{order_id}/structured",
        json={"structured_data": _erp_sd({"deposit": 500000})},
    )
    assert resp.status_code == 200, resp.get_data(as_text=True)
    assert _changes(order_id) == [("payment.deposit", 300000, 500000)]


def test_put_full_save_emits_one_event_per_changed_field(client):
    """한 저장에서 두 field 가 바뀌면 field 별 1건씩 = 2건(합쳐서 1건이 아니다)."""
    _login(client, _make_user("pay_put_multi", role="ADMIN"))
    order_id = _make_order(sd=_erp_sd({"deposit": 100000, "discount": 5000})).id

    resp = client.put(
        f"/api/orders/{order_id}/structured",
        json={"structured_data": _erp_sd({"deposit": 200000, "discount": 7000})},
    )
    assert resp.status_code == 200, resp.get_data(as_text=True)
    assert sorted(_changes(order_id)) == [
        ("payment.deposit", 100000, 200000),
        ("payment.discount", 5000, 7000),
    ]


def test_put_full_save_free_input_change_records_raw_text_and_parsed_amount(client):
    """자유입력은 원문 문자열이 diff 축이고 파싱 합계를 병기한다."""
    _login(client, _make_user("pay_put_free", role="ADMIN"))
    order_id = _make_order(sd=_erp_sd({"free_input": "배송비 : 30,000"})).id

    resp = client.put(
        f"/api/orders/{order_id}/structured",
        json={"structured_data": _erp_sd({"free_input": "배송비 : 50,000"})},
    )
    assert resp.status_code == 200, resp.get_data(as_text=True)

    events = _events(order_id)
    assert len(events) == 1
    payload = events[0].payload
    assert payload["field"] == "payment.free_input"
    assert (payload["from"], payload["to"]) == ("배송비 : 30,000", "배송비 : 50,000")
    assert (payload["from_amount"], payload["to_amount"]) == (30000, 50000)


def test_put_full_save_cash_receipt_and_balance_note_changes_emit_events(client):
    """현금영수증·잔금 메모(문자열 2종)도 각각 1건씩 남는다."""
    _login(client, _make_user("pay_put_text", role="ADMIN"))
    order_id = _make_order(
        sd=_erp_sd({"cash_receipt": "010-1111-2222", "balance_note": "시공 후 입금"})
    ).id

    resp = client.put(
        f"/api/orders/{order_id}/structured",
        json={"structured_data": _erp_sd({"cash_receipt": "", "balance_note": "카드 결제"})},
    )
    assert resp.status_code == 200, resp.get_data(as_text=True)
    assert sorted(_changes(order_id)) == [
        ("payment.balance_note", "시공 후 입금", "카드 결제"),
        ("payment.cash_receipt", "010-1111-2222", ""),
    ]


# --------------------------------------------------------------------------- #
# 2. 결제확인 토글 (실제 라우트 — 라우트 편집 0줄)
# --------------------------------------------------------------------------- #
def test_payment_confirm_toggle_emits_event_without_route_edit(client):
    """POST .../payment-confirm 토글 → ``payment.deposit_confirmed`` 이벤트 1건.

    이 라우트는 T2 에서 한 줄도 고치지 않았다 — SSOT 훅이 자동 포착하는 것이 정답이다.
    """
    user = _make_user("pay_confirm", role="ADMIN")
    user_id = user.id
    _login(client, user)
    order_id = _make_order(sd=_erp_sd({"deposit": 300000})).id

    resp = client.post(
        f"/api/orders/{order_id}/payment-confirm",
        json={"type": "deposit", "confirmed": True},
    )
    assert resp.status_code == 200, resp.get_data(as_text=True)
    assert resp.get_json()["success"] is True

    events = _events(order_id)
    assert len(events) == 1
    assert (events[0].payload["field"], events[0].payload["from"], events[0].payload["to"]) == (
        "payment.deposit_confirmed",
        False,
        True,
    )
    assert events[0].created_by_user_id == user_id


def test_payment_confirm_balance_toggle_off_emits_event(client):
    """잔금 확인 해제(True → False)도 이벤트 1건."""
    _login(client, _make_user("pay_confirm_off", role="ADMIN"))
    order_id = _make_order(sd=_erp_sd({"deposit": 0, "balance_confirmed": True})).id

    resp = client.post(
        f"/api/orders/{order_id}/payment-confirm",
        json={"type": "balance", "confirmed": False},
    )
    assert resp.status_code == 200, resp.get_data(as_text=True)
    assert _changes(order_id) == [("payment.balance_confirmed", True, False)]


# --------------------------------------------------------------------------- #
# 3. 레거시 ``payments``(복수형) 폴백 — 서버 extractor 재사용의 실효 확인
# --------------------------------------------------------------------------- #
def test_legacy_payments_block_is_read_as_same_value(client):
    """레거시 ``payments.deposit`` 만 있던 주문을 같은 값의 ``payment.deposit`` 으로 저장 → 0건.

    폴백을 못 읽으면 before=0 으로 잡혀 허위 "0 → 300000" 이벤트가 난다.
    """
    _login(client, _make_user("pay_legacy", role="ADMIN"))
    order_id = _make_order(sd=_erp_sd(None, payments={"deposit": 300000})).id

    resp = client.put(
        f"/api/orders/{order_id}/structured",
        json={"structured_data": _erp_sd({"deposit": 300000})},
    )
    assert resp.status_code == 200, resp.get_data(as_text=True)
    assert _events(order_id) == []


# --------------------------------------------------------------------------- #
# 4. 허위 이벤트 0
# --------------------------------------------------------------------------- #
def test_unchanged_save_emits_no_event(client):
    """같은 금액으로 다시 저장하면 이벤트 0건."""
    _login(client, _make_user("pay_noop", role="ADMIN"))
    payment = {"deposit": 300000, "discount": 11060, "free_input": "배송비 : 30,000"}
    order_id = _make_order(sd=_erp_sd(dict(payment))).id

    resp = client.put(
        f"/api/orders/{order_id}/structured",
        json={"structured_data": _erp_sd(dict(payment))},
    )
    assert resp.status_code == 200, resp.get_data(as_text=True)
    assert _events(order_id) == []


def test_round_trip_within_one_transaction_emits_no_event(app):
    """같은 트랜잭션에서 11060 → 0 → 11060 왕복이면 이벤트 0건(pending 이벤트 취소).

    2단 쓰기(flush 여러 번)를 하는 라우트가 중간 상태마다 이벤트를 남기지 않는지 본다.
    """
    order = _make_order(sd=_erp_sd({"discount": 11060}))
    order_id = order.id

    _mutate_payment(order, discount=0)
    db_session.flush()
    assert len(_events(order_id)) == 1  # 중간 상태에서는 이벤트가 살아 있다

    _mutate_payment(order, discount=11060)
    db_session.commit()
    assert _events(order_id) == []


def test_multi_flush_forward_change_stays_single_event(app):
    """같은 트랜잭션에서 11060 → 0 → 5000 이면 이벤트는 1건이고 ``to`` 만 갱신된다."""
    order = _make_order(sd=_erp_sd({"discount": 11060}))
    order_id = order.id

    _mutate_payment(order, discount=0)
    db_session.flush()
    _mutate_payment(order, discount=5000)
    db_session.commit()

    assert _changes(order_id) == [("payment.discount", 11060, 5000)]


def test_order_creation_emits_no_event(app):
    """주문 생성은 '이전 값'이 없으므로 이벤트 0건."""
    order_id = _make_order(sd=_erp_sd({"deposit": 300000, "discount": 11060})).id
    assert _events(order_id) == []


def test_draft_order_payment_change_emits_no_event(app):
    """``meta.draft`` 주문의 금액 변경(자동저장 노이즈)은 억제한다."""
    order = _make_order(sd=_erp_sd({"deposit": 100000}, meta={"draft": True}))
    order_id = order.id

    _mutate_payment(order, deposit=250000)
    db_session.commit()
    assert _events(order_id) == []


def test_draft_promotion_emits_no_event(client):
    """draft 승격(전체저장 PUT)은 그 시점 값이 초기값이므로 이벤트 0건."""
    _login(client, _make_user("pay_draft_promote", role="ADMIN"))
    order_id = _make_order(sd=_erp_sd({"deposit": 100000}, meta={"draft": True})).id

    resp = client.put(
        f"/api/orders/{order_id}/structured",
        json={"structured_data": _erp_sd({"deposit": 250000})},
    )
    assert resp.status_code == 200, resp.get_data(as_text=True)
    assert _events(order_id) == []


def test_draft_autosave_route_emits_no_event(client):
    """실제 자동저장 라우트를 두 번 호출해도(금액이 달라져도) 이벤트 0건."""
    _login(client, _make_user("pay_autosave", role="ADMIN"))

    created = client.post("/api/orders/erp/draft", json={"draft_token": "pay-autosave-token"})
    assert created.status_code == 200, created.get_data(as_text=True)
    order_id = created.get_json()["order_id"]

    for deposit in (100000, 250000):
        resp = client.post(
            "/api/orders/erp/draft/autosave",
            json={
                "draft_token": "pay-autosave-token",
                "structured_data": _erp_sd({"deposit": deposit}),
            },
        )
        assert resp.status_code == 200, resp.get_data(as_text=True)

    assert _events(order_id) == []


# --------------------------------------------------------------------------- #
# 5. 캡처 제외 축 — shipping_fee 는 기존 이벤트만
# --------------------------------------------------------------------------- #
def test_admin_shipping_fee_change_emits_no_payment_event(client):
    """수납장 대시보드 배송비 변경 → ``SHIPPING_FEE_CHANGED`` 1건, ``PAYMENT_CHANGED`` 0건.

    ``Order.shipping_fee`` 는 typed writer 가 이미 감사한다 — 중복 이벤트를 만들지 않는다.
    """
    _login(client, _make_user("pay_fee", role="ADMIN"))
    order_id = _make_order(sd=_erp_sd({"deposit": 300000})).id

    resp = client.post(
        f"/api/storage_dashboard/order/{order_id}/field",
        json={"field": "shipping_fee", "value": 30000},
    )
    assert resp.status_code == 200, resp.get_data(as_text=True)

    assert _events(order_id) == []
    fee_events = _events(order_id, "SHIPPING_FEE_CHANGED")
    assert len(fee_events) == 1
    assert fee_events[0].payload["to"] == 30000


# --------------------------------------------------------------------------- #
# 6. 구조적 N/A 경로 — 허위 이벤트 0 + 전제 고정
# --------------------------------------------------------------------------- #
def test_quick_field_update_has_no_payment_capable_field() -> None:
    """빠른수정 allowlist 에 payment 계열 필드가 0개라는 전제를 고정한다.

    이 단언이 깨지면(= 금액을 빠른수정으로 보낼 수 있게 되면) 해당 경로의 "1건" 계약 테스트를
    추가해야 한다.
    """
    from foms.api.orders.field_update import ORDER_UPDATE_ALLOWED_FIELDS

    payment_like = [
        field
        for field in ORDER_UPDATE_ALLOWED_FIELDS
        if any(token in field for token in ("payment", "deposit", "discount", "balance", "cash"))
    ]
    assert payment_like == []


def test_quick_field_update_scheduled_date_emits_no_payment_event(client):
    """빠른수정(시공일)은 금액을 건드리지 않으므로 ``PAYMENT_CHANGED`` 0건."""
    _login(client, _make_user("pay_quick", role="ADMIN"))
    order_id = _make_order(sd=_erp_sd({"deposit": 300000})).id

    resp = client.post(
        "/api/update_order_field",
        json={"order_id": order_id, "field": "scheduled_date", "value": "2026-08-28"},
    )
    assert resp.status_code == 200, resp.get_data(as_text=True)
    assert _events(order_id) == []


def test_legacy_edit_form_emits_no_payment_event(client):
    """레거시 주문수정 폼은 ``structured_data.payment`` 를 쓰지 않으므로 0건.

    폼이 쓰는 금액은 flat 컬럼 ``Order.payment_amount`` 뿐이다(할인 입력 자체가 없다).
    """
    _login(client, _make_user("pay_legacy_form", role="ADMIN", team="CS"))
    order_id = _make_order(sd=_erp_sd({"deposit": 300000, "discount": 11060})).id

    resp = client.post(
        f"/edit/{order_id}",
        data={
            "received_date": "2026-08-01",
            "customer_name": "금액 고객",
            "phone": "010-1234-5678",
            "address": "서울 테헤란로 123",
            "product": "붙박이장",
            "status": "RECEIVED",
            "manager_name": "담당",
            "payment_amount": "990000",
        },
        follow_redirects=False,
    )
    assert resp.status_code in (200, 302), resp.get_data(as_text=True)[:400]
    assert _events(order_id) == []


# --------------------------------------------------------------------------- #
# 7. 요청 밖 쓰기(스크립트·워커·백필)
# --------------------------------------------------------------------------- #
def test_system_writer_outside_request_emits_event_without_actor(app):
    """요청 컨텍스트 밖 쓰기도 포착되고 actor 는 ``None``, source 는 ``"system"``."""
    order = _make_order(sd=_erp_sd({"discount": 11060}))
    order_id = order.id

    _mutate_payment(order, discount=0)
    db_session.commit()

    events = _events(order_id)
    assert len(events) == 1
    assert events[0].payload["source"] == "system"
    assert events[0].created_by_user_id is None


def test_flag_modified_writer_still_yields_correct_before_value(app):
    """정본 저장 패턴(deepcopy → 재할당 → ``flag_modified``) 아래에서도 before 가 정확하다.

    ``flag_modified`` 는 attribute history 의 old 를 파괴한다 — before 를 DB 에서 읽지 않으면
    이 단언이 ``from == 0`` 으로 깨진다(설계 스펙 §2 실증).
    """
    order = _make_order(sd=_erp_sd({"deposit": 777000}))
    order_id = order.id

    _mutate_payment(order, deposit=123000)
    db_session.commit()

    assert _changes(order_id) == [("payment.deposit", 777000, 123000)]


def test_non_payment_structured_write_emits_no_event(app):
    """금액과 무관한 ``structured_data`` 수정은 이벤트 0건(훅이 과잉 반응하지 않는다)."""
    order = _make_order(sd=_erp_sd({"deposit": 300000}))
    order_id = order.id

    sd = copy.deepcopy(order.structured_data)
    sd["site"]["address_full"] = "서울 강남대로 1"
    order.structured_data = sd
    flag_modified(order, "structured_data")
    db_session.commit()

    assert _events(order_id) == []


# --------------------------------------------------------------------------- #
# 8. 노출(라벨)
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("event_type,expected", [("PAYMENT_CHANGED", "금액 변경")])
def test_payment_changed_label_is_registered(event_type: str, expected: str) -> None:
    """타임라인 라벨이 "기타 변경" 폴백이 아니라 "금액 변경" 으로 나온다."""
    from foms.services.order_event_display import translate_event_type_to_korean

    assert translate_event_type_to_korean(event_type) == expected
