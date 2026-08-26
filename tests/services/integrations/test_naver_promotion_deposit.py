"""네이버 승격 시 실결제 총액은 **예약금**으로 앉는다 (2026-08-26 사용자 확정).

왜 이 파일이 있나
-----------------
네이버에서 받은 돈은 계약 총액이 아니라 **선금**이다. 그런데 지금까지 승격은
``productOrder.totalPaymentAmount`` 를 품목 행 ``price`` 로만 흘려보냈다 — 그러면 실측도
하기 전에 출고가(= 품목합)가 확정된 것처럼 보이고, 사람이 나중에 진짜 항목 금액을 넣으면
결제액이 두 번 세어진다.

여기서 못박는 계약 여섯:

1. 승격 뒤 ``erp_deposit_amount_from_structured`` 가 **집 합계**를 돌려준다.
2. 품목 행은 **남아 있다**(품명·옵션·수량 보존). 비운 것은 ``price`` 뿐이다.
3. 상품주문이 여러 건인 집(본품 2 + 추가구성상품 1)도 예약금은 **합산 총액 하나**다.
4. ``totals.balance_amount`` 는 0 이다 — 실측 후 사람이 항목 금액을 넣어야 잔금이 뜬다.
5. **붙이기는 예약금을 여전히 안 건드린다**(D-1). 승격 정책이 붙이기로 새면 이미 청구한
   금액이 조용히 바뀐다.
6. 네이버 원본 금액은 어디에도 사라지지 않는다(``naver.payment`` · 행별 원본 결제액 ·
   집 합계).
"""

from __future__ import annotations

import copy
from typing import Any

from werkzeug.security import generate_password_hash

from db import db_session
from foms.services.erp_display import erp_deposit_amount_from_structured
from foms.services.integrations.naver_commerce.constants import (
    ACTOR_USERNAME,
    OWNER_USERNAME,
)
from foms.services.integrations.naver_commerce.promotion import (
    ITEM_PAID_AMOUNT_KEY,
    attach_link_to_order,
    promote_link_to_order,
)
from models import ExternalOrderLink, Order, User

#: 상품주문 상세 1건 원형. 금액·이름·역할만 갈아 끼워 쓴다.
DETAIL: dict[str, Any] = {
    "order": {"orderId": "2026082612345", "ordererName": "김주문",
              "ordererTel": "010-1111-2222", "orderDate": "2026-08-26T10:00:00.000+09:00",
              "paymentDate": "2026-08-26T10:01:00.000+09:00", "paymentMeans": "카드"},
    "productOrder": {
        "productOrderId": "PO-D1", "productOrderStatus": "PAYED",
        "productName": "붙박이장 세트", "productOption": "색상: 화이트 / 폭: 2400",
        "quantity": 2, "totalPaymentAmount": 1_229_000,
        "unitPrice": 614_500,
        "sellerProductCode": "LAHOM-BIB-2400",
        "shippingAddress": {"name": "이수취", "tel1": "010-3333-4444",
                            "baseAddress": "서울특별시 강남구 테헤란로 1",
                            "detailedAddress": "101동 1001호", "zipCode": "06232"},
    },
}


def _accounts() -> tuple[User, User]:
    """수집봇(actor)·미배정 보류함(owner) 계정."""
    actor = User(username=ACTOR_USERNAME, password=generate_password_hash("pw"),
                 name="네이버 수집봇", role="MANAGER", team="CS", is_active=True)
    owner = User(username=OWNER_USERNAME, password=generate_password_hash("pw"),
                 name="미배정", role="STAFF", team="SALES", is_active=True)
    db_session.add_all([actor, owner])
    db_session.commit()
    return (actor, owner)


def _link(product_order_id: str, *, name: str, amount: int, quantity: int = 1,
          option: str = "", order_no: str = "2026082612345",
          product_class: str = "") -> ExternalOrderLink:
    """같은 묶음(같은 주문번호·같은 수취인)의 상품주문 링크 1건."""
    payload = copy.deepcopy(DETAIL)
    payload["order"]["orderId"] = order_no
    po = payload["productOrder"]
    po["productOrderId"] = product_order_id
    po["productName"] = name
    po["productOption"] = option
    po["quantity"] = quantity
    po["totalPaymentAmount"] = amount
    if product_class:
        po["productClass"] = product_class
    link = ExternalOrderLink(channel="NAVER", external_id=product_order_id,
                             external_order_no=order_no, raw_snapshot=payload,
                             sync_status="COLLECTED")
    db_session.add(link)
    db_session.commit()
    return link


def _promote(link: ExternalOrderLink) -> Order:
    """링크 1건을 승격하고 만들어진 주문을 돌려준다."""
    actor, owner = _accounts()
    order_id, created = promote_link_to_order(
        db_session, link_id=link.id, actor_user_id=actor.id, owner_user_id=owner.id)
    db_session.commit()
    assert created is True
    return db_session.get(Order, order_id)


# --------------------------------------------------------------------------- #
# ① 예약금 = 실결제 총액
# --------------------------------------------------------------------------- #

def test_paid_amount_lands_in_deposit(app):
    """승격 뒤 예약금이 실결제 총액이다 — 품목 금액이 아니라 선금 자리로 간다."""
    link = _link("PO-D1", name="붙박이장 세트", amount=1_229_000, quantity=2,
                 option="색상: 화이트 / 폭: 2400")

    order = _promote(link)

    sd = order.structured_data or {}
    assert erp_deposit_amount_from_structured(sd) == 1_229_000
    assert sd["payment"]["deposit"] == 1_229_000, "정본 자리는 payment.deposit 이다"
    # 입금 확정은 FINANCE 권한 게이트다 — 수집이 대신 눌러 줄 수 없다.
    assert sd["payment"]["deposit_confirmed"] is False


def test_item_rows_survive_with_zero_price(app):
    """품목 행은 남고 금액만 비워진다 — 무엇을 샀는지가 사라지면 규격을 못 채운다."""
    link = _link("PO-D1", name="붙박이장 세트", amount=1_229_000, quantity=2,
                 option="색상: 화이트 / 폭: 2400")

    order = _promote(link)

    items = (order.structured_data or {}).get("items") or []
    assert len(items) == 1, "행을 지우면 안 된다"
    row = items[0]
    assert row["product_name"] == "붙박이장 세트"
    assert row["options"] == "색상: 화이트 / 폭: 2400"
    assert row["quantity"] == 2
    assert row["price"] == 0, "실측 전 항목 금액은 사람이 넣는다"


# --------------------------------------------------------------------------- #
# ② 여러 상품주문이 한 집일 때도 예약금은 합산 총액 하나
# --------------------------------------------------------------------------- #

def test_multi_product_order_group_sums_into_one_deposit(app):
    """본품 2 + 추가구성상품 1 인 집도 예약금은 **합산 총액 하나**다.

    추가구성상품은 항목 행이 되지 않고 본품 행 금액에 합쳐진다(매핑 계약). 그래서 행이
    2개여도 예약금은 3건 합계여야 한다 — 행별로 나눠 넣거나 대표 건만 넣으면 안 된다.
    """
    main1 = _link("PO-M1", name="로라 무몰딩 180cm", amount=1_115_800, quantity=2)
    _link("PO-A1", name="TYPE C", amount=60_000, quantity=2,
          product_class="추가구성상품")
    _link("PO-M2", name="로라 무몰딩 30cm", amount=1_314_600, quantity=14)

    order = _promote(main1)

    total = 1_115_800 + 60_000 + 1_314_600
    sd = order.structured_data or {}
    assert erp_deposit_amount_from_structured(sd) == total
    items = sd["items"]
    assert len(items) == 2, "본품만 항목 행이 된다"
    assert [row["price"] for row in items] == [0, 0]
    assert {row["quantity"] for row in items} == {2, 14}, "수량은 보존된다"
    # Order.payment_amount 플랫 컬럼(= 예약금 투영)도 같은 총액이다.
    assert order.payment_amount == total


# --------------------------------------------------------------------------- #
# ③ 잔금 0 — 실측 후 사람이 항목 금액을 넣어야 잔금이 뜬다
# --------------------------------------------------------------------------- #

def test_balance_is_zero_right_after_promotion(app):
    """서버 재계산 결과 잔금이 0 이다(음수로 새지 않는다)."""
    link = _link("PO-D1", name="붙박이장 세트", amount=1_229_000)

    order = _promote(link)

    totals = (order.structured_data or {})["totals"]
    assert totals["items_total"] == 0
    assert totals["deposit_amount"] == 1_229_000
    assert totals["balance_amount"] == 0, "실측 전에는 청구할 잔금이 없다"
    assert totals["final_amount"] == 0
    assert totals["shipping_price"] == 0


def test_balance_appears_after_a_human_fills_item_prices(app):
    """사람이 항목 금액을 채우면 그때 잔금이 선다 — 예약금이 그대로 차감된다.

    승격이 "잔금 0"으로 굳혀 놓는 게 아니라, **아직 모르는 값이라 0**이라는 것을 못박는다.
    """
    from foms.services.orders.structured_form_projection import recompute_totals

    link = _link("PO-D1", name="붙박이장 세트", amount=1_229_000)
    order = _promote(link)

    sd = copy.deepcopy(order.structured_data or {})
    sd["items"][0]["price"] = 2_000_000  # 실측 후 사람이 입력한 항목 금액
    totals = recompute_totals(sd)

    assert totals["items_total"] == 2_000_000
    assert totals["balance_amount"] == 2_000_000 - 1_229_000


# --------------------------------------------------------------------------- #
# ④ 원본 금액은 잃지 않는다
# --------------------------------------------------------------------------- #

def test_original_naver_amounts_are_not_lost(app):
    """비운 금액은 어딘가에 그대로 남는다 — 정보가 사라지면 역산할 방법이 없다."""
    main1 = _link("PO-M1", name="로라 무몰딩 180cm", amount=1_115_800, quantity=2)
    _link("PO-A1", name="TYPE C", amount=60_000, quantity=2,
          product_class="추가구성상품")
    _link("PO-M2", name="로라 무몰딩 30cm", amount=1_314_600, quantity=14)

    order = _promote(main1)

    sd = order.structured_data or {}
    total = 1_115_800 + 60_000 + 1_314_600
    # 집 합계
    assert sd["naver"]["group_payment_total"] == total
    # 행별 원본 결제액(본품 + 그 본품에 귀속된 추가구성상품)
    by_id = {row["naver_product_order_id"]: row for row in sd["items"]}
    assert by_id["PO-M1"][ITEM_PAID_AMOUNT_KEY] == 1_115_800 + 60_000
    assert by_id["PO-M2"][ITEM_PAID_AMOUNT_KEY] == 1_314_600
    assert sum(row[ITEM_PAID_AMOUNT_KEY] for row in sd["items"]) == total
    # 추가구성상품 원본 행과 네이버 결제 상세도 그대로다.
    assert by_id["PO-M1"]["naver_addons"][0]["price"] == 60_000
    assert sd["naver"]["payment"]["unit_price"] == 614_500
    # 원본 결제액이 화면 금액식에 섞이면 안 된다(읽는 키는 price 하나다).
    assert erp_deposit_amount_from_structured(sd) == total
    assert sd["totals"]["items_total"] == 0


# --------------------------------------------------------------------------- #
# ⑤ 붙이기는 여전히 예약금을 안 건드린다 (D-1 회귀 방지)
# --------------------------------------------------------------------------- #

def test_attach_still_never_writes_the_deposit(app):
    """승격 정책이 **붙이기**로 새지 않는다.

    붙이기(추가결제·재결제)는 이미 청구가 끝난 집의 후속이라, 결제액을 예약금에 자동
    반영하면 고객에게 이미 말한 잔금이 조용히 바뀐다(2026-08-19 D-1 확정: 기록만).
    """
    actor, _owner = _accounts()
    order = Order(received_date="2026-08-01", customer_name="김고객",
                  phone="010-3333-4444", address="서울특별시 강남구 테헤란로 1 101동 1001호",
                  product="붙박이장", status="RECEIVED", payment_amount=500_000,
                  is_erp_order=True,
                  structured_data={"payment": {"deposit": 500_000},
                                   "items": [{"product_name": "붙박이장",
                                              "quantity": 1, "price": 3_000_000}]})
    db_session.add(order)
    db_session.commit()
    order_id = int(order.id)
    link = _link("PO-ATT1", name="추가 결제", amount=250_000, order_no="2026082699999")

    attached, returned_order_id, changed = attach_link_to_order(
        db_session, link_id=int(link.id), order_id=order_id, relation="ADDON",
        actor_user_id=actor.id)
    db_session.commit()

    assert (attached, returned_order_id, changed) == (1, order_id, True)
    refreshed = db_session.get(Order, order_id)
    sd = refreshed.structured_data or {}
    # 붙이기가 JSONB 를 **실제로 다시 썼다**는 것부터 확인한다 — 아무것도 안 쓰였다면
    # 아래 검증이 저절로 참이 돼 계약을 못 지킨다.
    assert sd["pricing"]["extra_payments"], "추가결제 기록이 안 남았다 — 테스트가 헛돌고 있다"
    assert sd["payment"]["deposit"] == 500_000, "붙이기가 예약금을 자동으로 고쳤다(D-1 위반)"
    assert sd["items"][0]["price"] == 3_000_000, "붙이기가 항목 금액을 비웠다(승격 정책 누출)"


# --------------------------------------------------------------------------- #
# ⑥ 두 번 부르면 돈이 사라진다 — 그 자리를 가드가 막는다 (2026-08-26 CEO 리뷰 H-1)
# --------------------------------------------------------------------------- #

def test_second_call_never_wipes_the_deposit(app):
    """이미 옮겨진 structured_data 에 다시 불러도 예약금이 0이 되지 않는다.

    두 번째 호출은 품목 행 ``price`` 가 이미 0이라 합계도 0이고, 가드가 없으면 그 0으로
    예약금·집 합계·행별 원본을 **동시에** 덮는다. 지금은 갓 매핑한 dict 위에서만 도니
    도달할 수 없지만, 재승격·보정 스크립트가 기존 주문에 한 번 부르면 그 주문의 돈이
    조용히 0이 된다 — 화면에는 "예약금 0원"으로만 보인다.
    """
    from foms.services.integrations.naver_commerce.promotion import (
        apply_paid_amount_as_deposit,
    )

    structured = {
        "items": [{"product_name": "붙박이장", "quantity": 1, "price": 1_229_000}],
        "naver": {},
    }

    first = apply_paid_amount_as_deposit(structured)
    second = apply_paid_amount_as_deposit(structured)

    assert first == 1_229_000
    assert second == 1_229_000, "두 번째 호출이 0을 돌려주면 호출자가 0을 기록한다"
    assert structured["payment"]["deposit"] == 1_229_000, "예약금이 지워졌다"
    assert structured["naver"]["group_payment_total"] == 1_229_000, "집 합계가 지워졌다"
    assert structured["items"][0]["naver_paid_amount"] == 1_229_000, "행별 원본이 지워졌다"


def test_the_deposit_mover_is_not_public_api():
    """``__all__`` 에 없다 — 갓 매핑한 dict 전용이라 "쓰라고 만든 것" 으로 읽히면 안 된다."""
    from foms.services.integrations.naver_commerce import promotion

    assert "apply_paid_amount_as_deposit" not in promotion.__all__
    assert "ITEM_PAID_AMOUNT_KEY" in promotion.__all__, "상수는 읽는 쪽이 필요하다"
