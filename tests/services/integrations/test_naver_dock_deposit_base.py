"""네이버 돈이 ERP 주문에 **처음 붙는 순간** 바닥값(원래 예약금)을 새긴다 (2026-09-03).

``pricing.naver_deposit_base`` 는 붙이기(:func:`promotion.attach_link_to_order`)가 한 번만 새기고
둘째 붙이기는 덮어쓰지 않는다 — 사람이 이미 반영해 올려 둔 값이 바닥값으로 둔갑하면 안 된다.

읽는 쪽 이력: 도크는 2026-09-03~2026-09-10 사이 이 값을 읽어 예약금 목표액(바닥값 + 네이버 결제액)
문장을 만들었다. 2026-09-10 사용자 지시로 도크가 결제 금액 한 줄만 그리게 되면서 읽는 곳이 0 이 되고,
2026-09-11 에 그 읽기(``_deposit_base``·목표액 키)를 걷어냈다. 새김 자체는 데이터 사실이라 그대로다 —
쓸 곳이 생기기 전까지 이 파일은 **새김 규약**만 지킨다.
"""

from __future__ import annotations

import copy
from typing import Optional

from sqlalchemy.orm.attributes import flag_modified
from werkzeug.security import generate_password_hash

from db import db_session
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

# --------------------------------------------------------------------------- #
# 2. 네이버 출신 주문은 오늘 그대로
# --------------------------------------------------------------------------- #

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
