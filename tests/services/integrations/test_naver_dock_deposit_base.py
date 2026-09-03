"""ERP 에서 만든 주문에 네이버 돈이 붙으면 **원래 예약금 위에 더한다** (2026-09-03).

사용자 실화면(주문 #5112): 워크벤치 정리 계획은 "지금 값 100,000원에 1,107,560원을 더해
1,207,560원으로 고치세요" 라고 말했는데, 같은 주문의 도크는 "지금 값 100,000원에
1,007,560원을 더해 1,107,560원으로" 라고 말했다. 도크가 예약금 정답을 **네이버 결제액**
하나로 놓아, ERP 에서 직접 받아 둔 100,000원이 안내에서 증발한 것이다. 그 숫자는
``잔금 = 출고가 − 예약금`` 을 타고 고객 청구로 나간다.

여기서 못박는 것:

* 이 주문으로 만들어진 집(``NEW``)이 없는 주문(= ERP 에서 직접 만든 주문)은 예약금 정답이
  ``원래 예약금 + 살아 있는 네이버 결제액`` 이다.
* 그 "원래 예약금"은 네이버 돈이 **처음 붙는 순간** 주문에 새긴다
  (``pricing.naver_deposit_base``) — 두 번째 붙이기가 덮어쓰면, 사람이 이미 반영해 올려
  둔 값이 바닥값으로 둔갑해 안내가 부풀어 오른다.
* 새긴 값이 없는 **옛 붙이기**만 지금 예약금으로 되짚는다. 되짚기는 추정이라 저장하지
  않는다(설계서 §7.3 — 추정을 데이터로 굳히지 않는다).
* 네이버에서 만들어진 주문(``NEW`` 집이 있다)은 바닥값이 0 이다 — 오늘과 같은 안내.
"""

from __future__ import annotations

import copy
from typing import Optional

from sqlalchemy.orm.attributes import flag_modified
from werkzeug.security import generate_password_hash

from db import db_session
from foms.services.integrations.naver_commerce.dock import build_dock_payload
from foms.services.integrations.naver_commerce.promotion import (
    NAVER_DEPOSIT_BASE_KEY,
    attach_link_to_order,
)
from models import ExternalOrderLink, Order, User

_ADDON_NO = "2026090299873311"
_SEQ = [0]


def _uid() -> str:
    _SEQ[0] += 1
    return f"base{_SEQ[0]}"


def _actor() -> User:
    user = User(username=f"dock_base_{_uid()}", password=generate_password_hash("pw"),
                role="STAFF", team="CS", name="접수 담당", is_active=True)
    db_session.add(user)
    db_session.commit()
    return user


def _snapshot(*, amount: int, order_no: str = _ADDON_NO) -> dict:
    """상품주문 상세 1건."""
    return {
        "order": {"orderId": order_no, "ordererName": "이빛나리",
                  "ordererTel": "010-1111-2222"},
        "productOrder": {
            "productOrderId": f"PO-{_uid()}",
            "productName": "붙박이장 로라",
            "productOption": "사이즈: 3000 / 색상: 화이트",
            "totalPaymentAmount": amount,
            "quantity": 1,
            "shippingAddress": {"name": "이빛나리", "tel1": "010-3333-4444",
                                "baseAddress": "인천 서구 당하 1",
                                "detailedAddress": "308-1303"},
        },
    }


def _erp_order(*, deposit: int, base: Optional[int] = None) -> Order:
    """ERP 에서 직접 만든 주문 — 네이버 출신이 아니다(``source`` 를 찍지 않는다)."""
    structured: dict = {"payment": {"deposit": deposit},
                        "items": [{"product_name": "붙박이장", "quantity": 1,
                                   "price": 3_000_000}]}
    if base is not None:
        structured["pricing"] = {NAVER_DEPOSIT_BASE_KEY: base}
    order = Order(received_date="2026-09-02", customer_name="이빛나리",
                  phone="010-3333-4444", address="인천 서구 당하 1 308-1303",
                  product="붙박이장", status="RECEIVED", payment_amount=deposit,
                  is_erp_order=True, structured_data=structured)
    db_session.add(order)
    db_session.commit()
    return order


def _link(order: Optional[Order], snapshot: dict, *, relation: str = "ADDON",
          order_no: str = _ADDON_NO) -> ExternalOrderLink:
    link = ExternalOrderLink(
        channel="NAVER",
        external_id=snapshot["productOrder"]["productOrderId"],
        order_id=order.id if order is not None else None,
        external_order_no=order_no,
        sync_status="LINKED" if order is not None else "COLLECTED",
        relation=relation,
        raw_snapshot=snapshot,
    )
    db_session.add(link)
    db_session.commit()
    return link


# --------------------------------------------------------------------------- #
# 1. 실화면 재현 — 원래 예약금 위에 더한다
# --------------------------------------------------------------------------- #

def test_erp_native_order_adds_naver_money_on_top_of_the_existing_deposit(app):
    """주문 #5112 실화면: 100,000 + 1,107,560 = 1,207,560 — 워크벤치와 같은 말."""
    order = _erp_order(deposit=100_000, base=100_000)
    _link(order, _snapshot(amount=1_107_560))

    hint = build_dock_payload(db_session, order)["deposit_hint"]

    assert hint["state"] == "differs"
    assert hint["base"] == 100_000
    assert hint["live_total"] == 1_107_560
    assert hint["target"] == 1_207_560
    assert hint["copy_value"] == "1207560"
    assert hint["sentence"] == "지금 값 100,000원에 1,107,560원을 더해 1,207,560원으로 고치세요."


def test_old_attach_without_a_stamped_base_falls_back_to_the_current_deposit(app):
    """새긴 값이 없는 옛 붙이기도 같은 답을 낸다 — 지금 예약금을 바닥값으로 되짚는다."""
    order = _erp_order(deposit=100_000)
    _link(order, _snapshot(amount=1_107_560))

    hint = build_dock_payload(db_session, order)["deposit_hint"]

    assert hint["base"] == 100_000
    assert hint["target"] == 1_207_560


def test_after_the_person_applies_it_the_answer_stops_moving(app):
    """사람이 고쳐 넣은 뒤에는 ``match`` — 며칠 뒤 화면이 같은 돈을 또 더하지 않는다."""
    order = _erp_order(deposit=1_207_560, base=100_000)
    _link(order, _snapshot(amount=1_107_560))

    hint = build_dock_payload(db_session, order)["deposit_hint"]

    assert hint["state"] == "match"
    assert hint["target"] == 1_207_560
    assert "고치세요" not in hint["sentence"]
    # 바닥값이 있는 주문은 "네이버 결제액과 같다"가 아니다 — 셈이 두 단계인 걸 말한다.
    assert "원래 예약금 100,000원 + 네이버 결제액 1,107,560원" in hint["sentence"]


def test_applied_deposit_without_a_stamped_base_is_read_back_correctly(app):
    """새긴 값이 없어도 이미 반영된 주문을 다시 "더하라"고 말하지 않는다."""
    order = _erp_order(deposit=1_207_560)
    _link(order, _snapshot(amount=1_107_560))

    hint = build_dock_payload(db_session, order)["deposit_hint"]

    assert hint["base"] == 100_000
    assert hint["state"] == "match"


# --------------------------------------------------------------------------- #
# 2. 네이버 출신 주문은 오늘 그대로
# --------------------------------------------------------------------------- #

def test_naver_born_order_keeps_a_zero_base(app):
    """``NEW`` 집이 있으면 예약금 자체가 네이버 돈이다 — 바닥값 0, 안내도 오늘과 같다."""
    order = _erp_order(deposit=500_000)
    _link(order, _snapshot(amount=500_000, order_no="2026082545684381"),
          relation="NEW", order_no="2026082545684381")
    _link(order, _snapshot(amount=120_000))

    hint = build_dock_payload(db_session, order)["deposit_hint"]

    assert hint["base"] == 0
    assert hint["target"] == 620_000
    assert "120,000원을 더해" in hint["sentence"]


# --------------------------------------------------------------------------- #
# 3. 바닥값은 처음 붙일 때 새기고, 두 번째 붙이기는 덮지 않는다
# --------------------------------------------------------------------------- #

def test_attach_stamps_the_base_once_and_never_overwrites_it(app):
    """첫 붙이기가 그때의 예약금을 새긴다. 둘째 붙이기는 손대지 않는다."""
    actor = _actor()
    order = _erp_order(deposit=100_000)
    order_id = int(order.id)
    first = _link(None, _snapshot(amount=1_107_560))

    attach_link_to_order(db_session, link_id=int(first.id), order_id=order_id,
                         relation="ADDON", actor_user_id=actor.id)
    db_session.commit()

    stamped = (db_session.get(Order, order_id).structured_data or {})["pricing"]
    assert stamped[NAVER_DEPOSIT_BASE_KEY] == 100_000

    # 사람이 안내대로 예약금을 고쳐 넣은 뒤, 같은 주문에 두 번째 집이 붙는다.
    refreshed = db_session.get(Order, order_id)
    sd = copy.deepcopy(refreshed.structured_data or {})
    sd["payment"]["deposit"] = 1_207_560
    refreshed.structured_data = sd
    flag_modified(refreshed, "structured_data")
    db_session.commit()

    second = _link(None, _snapshot(amount=60_000, order_no="2026090299999999"),
                   order_no="2026090299999999")
    attach_link_to_order(db_session, link_id=int(second.id), order_id=order_id,
                         relation="ADDON", actor_user_id=actor.id)
    db_session.commit()

    pricing = (db_session.get(Order, order_id).structured_data or {})["pricing"]
    assert pricing[NAVER_DEPOSIT_BASE_KEY] == 100_000, "둘째 붙이기가 바닥값을 덮었다"
    hint = build_dock_payload(db_session, db_session.get(Order, order_id))["deposit_hint"]
    assert hint["target"] == 100_000 + 1_107_560 + 60_000
