# -*- coding: utf-8 -*-
"""도크가 **취소 확정된 집**을 '이번 주문(재결제)' 로 부르던 결함 (2026-09-16).

사용자 제보(운영 #5158 김선미)로 드러났다. 재결제가 **두 번** 일어난 주문이다 —
첫 결제가 취소되고 재결제, 그 재결제도 취소되고 다시 재결제. 운영 실측:

===========================  =========  =========  =====================  =============
집(네이버 주문번호)            관계       상품주문   클레임                  결제액
===========================  =========  =========  =====================  =============
2026090498433601 (09-04)      NEW        9          전부 ``CANCEL_DONE``    1,932,800원
2026090764605051 (09-07)      REPAY      5          전부 ``CANCEL_DONE``    1,134,200원
2026091643473411 (09-16)      REPAY      3          없음(살아 있다)         1,034,800원
===========================  =========  =========  =====================  =============

그런데 도크는 09-14 에 취소 확정된 …5051 집을 ``이번 주문(재결제)`` 라 부르고 그 집 금액
1,134,200원을 함께 세었다. 죽은 집 판정이 ``superseded = has_repay and relation == "NEW"``
한 줄, 즉 **관계 한 축뿐**이었고 클레임은 들어가지 않았기 때문이다. 담당자는 이 화면만 보고
고객에게 청구할 금액을 10만원 틀리게 읽는다.

여기서 못박는 것:

* 취소·반품이 **확정된** 집은 관계와 무관하게 죽은 집이다(``settled``) — 라벨은 ``취소된 결제``.
* 금액 카드(``deposit_hint``)는 살아 있는 집만 센다. 판정은 한 곳(``_household_facts``)이고
  금액은 그 결과를 읽을 뿐이다 — 두 벌로 두면 언젠가 갈린다.
* **확정 전 취소 요청은 죽은 집이 아니다.** 거부될 수 있다 — 거기서 죽었다고 말하면 살아
  있는 청구가 화면에서 사라진다.
* 부분 취소(집의 일부만)도 죽은 집이 아니다.
* 추가결제(``ADDON``) 집과 취소 없는 재결제는 종전 동작 그대로다.
"""

from __future__ import annotations

from db import db_session
from foms.services.integrations.naver_commerce.dock import build_dock_payload
from foms.services.orders.order_create import create_order
from models import ExternalOrderLink, Order, User
from werkzeug.security import generate_password_hash

#: 운영 #5158 의 세 집 — 번호와 금액을 실제 값으로 쓴다(재현이 문서를 겸한다).
_FIRST_NO = "2026090498433601"    # NEW · 9건 · 전부 취소 완료
_DEAD_REPAY_NO = "2026090764605051"   # REPAY · 5건 · 전부 취소 완료
_LIVE_REPAY_NO = "2026091643473411"   # REPAY · 3건 · 살아 있다
_FIRST_AMOUNT = 1_932_800
_DEAD_AMOUNT = 1_134_200
_LIVE_AMOUNT = 1_034_800

_SEQ = [0]


def _uid() -> str:
    _SEQ[0] += 1
    return f"st{_SEQ[0]}"


def _owner() -> User:
    user = User(username=f"dock_settled_{_uid()}", password=generate_password_hash("pw"),
                role="STAFF", team="CS", name="접수 담당", is_active=True)
    db_session.add(user)
    db_session.commit()
    return user


def _snapshot(*, order_no: str, amount: int, claim_status: str = "",
              claim_type: str = "CANCEL") -> dict:
    """상품주문 하나 — ``claim_status`` 를 주면 그 클레임이 걸린 원본이 된다."""
    product_order = {
        "productOrderId": f"PO-{_uid()}",
        "productName": "라홈 로라 무몰딩 붙박이장 작은방 여닫이 푸쉬타입 240cm",
        "productOption": "사이즈: 2400 / 색상: 화이트",
        "productClass": "조합형옵션상품",
        "totalPaymentAmount": amount,
        "quantity": 1,
        "shippingAddress": {"name": "김선미", "tel1": "010-3333-4444",
                            "baseAddress": "서울 강남구 1", "detailedAddress": "101호"},
    }
    if claim_status:
        product_order["claimStatus"] = claim_status
        product_order["claimType"] = claim_type
    return {
        "order": {"orderId": order_no, "ordererName": "김선미",
                  "ordererTel": "010-1111-2222"},
        "productOrder": product_order,
    }


def _naver_order() -> Order:
    owner = _owner()
    order = create_order(
        db_session,
        actor_user_id=owner.id, owner_user_id=owner.id,
        order_fields=dict(received_date="2026-09-04", customer_name="김선미",
                          phone="010-3333-4444", address="서울 강남구 1 101호",
                          product="붙박이장", options="색상: 화이트", status="RECEIVED"),
        structured_data={"source": "NAVER_SMARTSTORE"},
        is_erp_order=True,
    )
    db_session.flush()
    return order


def _link(order: Order, *, order_no: str, relation: str, amount: int,
          claim_status: str = "", claim_type: str = "CANCEL") -> ExternalOrderLink:
    link = ExternalOrderLink(
        channel="NAVER",
        external_id=f"EX-{_uid()}",
        order_id=order.id,
        external_order_no=order_no,
        sync_status="LINKED",
        relation=relation,
        raw_snapshot=_snapshot(order_no=order_no, amount=amount,
                               claim_status=claim_status, claim_type=claim_type),
    )
    db_session.add(link)
    db_session.commit()
    return link


def _fact(payload: dict, order_no: str) -> dict:
    return next(fact for fact in payload["households"] if fact["order_no"] == order_no)


def _kimsunmi(order: Order) -> None:
    """운영 #5158 모양 — 취소 완료 NEW 집 + 취소 완료 REPAY 집 + 살아 있는 REPAY 집."""
    _link(order, order_no=_FIRST_NO, relation="NEW", amount=_FIRST_AMOUNT,
          claim_status="CANCEL_DONE")
    _link(order, order_no=_DEAD_REPAY_NO, relation="REPAY", amount=_DEAD_AMOUNT,
          claim_status="CANCEL_DONE")
    _link(order, order_no=_LIVE_REPAY_NO, relation="REPAY", amount=_LIVE_AMOUNT)


# --------------------------------------------------------------------------- #
# 재현 — 취소 확정된 재결제 집은 '이번 주문' 이 아니다
# --------------------------------------------------------------------------- #

def test_a_settled_repay_household_is_not_this_order(app):
    """★ 재현: 취소 확정된 재결제 집은 `취소된 결제` 이고, 살아 있는 집만 `이번 주문` 이다."""
    order = _naver_order()
    _kimsunmi(order)

    payload = build_dock_payload(db_session, order)

    dead = _fact(payload, _DEAD_REPAY_NO)
    live = _fact(payload, _LIVE_REPAY_NO)

    assert dead["settled"] is True
    assert dead["superseded"] is True
    assert dead["label"] == "취소된 결제", "취소된 집을 이번 주문이라 부른다"
    assert "환불" in dead["note"]

    assert live["settled"] is False
    assert live["superseded"] is False
    assert live["label"] == "이번 주문(재결제)"


def test_the_amount_card_counts_only_the_living_household(app):
    """★ 금액 카드가 **살아 있는 집 하나**만 센다 — 이 결함의 실제 피해가 금액이었다."""
    order = _naver_order()
    _kimsunmi(order)

    payload = build_dock_payload(db_session, order)

    hint = payload["deposit_hint"]
    assert hint["live_total"] == _LIVE_AMOUNT, (
        f"취소된 집 금액이 섞였다 — {hint['live_total']:,}원 "
        f"(기대 {_LIVE_AMOUNT:,}원, 취소분 {_DEAD_AMOUNT:,}·{_FIRST_AMOUNT:,})")
    assert hint["live_total"] != _DEAD_AMOUNT + _LIVE_AMOUNT


def test_the_first_cancelled_household_is_also_called_cancelled(app):
    """첫 결제 집(NEW)도 취소 확정이면 `이전 주문` 이 아니라 `취소된 결제` 다.

    두 사실은 담당자가 할 일이 다르다: 대체된 집은 새 집을 보면 되고, 취소된 집은
    환불이 끝났다는 뜻이다.
    """
    order = _naver_order()
    _kimsunmi(order)

    payload = build_dock_payload(db_session, order)

    assert _fact(payload, _FIRST_NO)["label"] == "취소된 결제"


# --------------------------------------------------------------------------- #
# 음성 대조군 — 넓히면 안 되는 자리
# --------------------------------------------------------------------------- #

def test_a_plain_repay_pair_is_unchanged(app):
    """★ 음성 대조군 ①: 취소가 하나도 없는 NEW+REPAY 두 집은 **종전 그대로**다."""
    order = _naver_order()
    _link(order, order_no=_FIRST_NO, relation="NEW", amount=_FIRST_AMOUNT)
    _link(order, order_no=_LIVE_REPAY_NO, relation="REPAY", amount=_LIVE_AMOUNT)

    payload = build_dock_payload(db_session, order)

    old = _fact(payload, _FIRST_NO)
    new = _fact(payload, _LIVE_REPAY_NO)
    assert old["label"] == "이전 주문" and old["superseded"] is True
    assert old["settled"] is False
    assert new["label"] == "이번 주문(재결제)" and new["superseded"] is False


def test_a_claim_request_is_not_a_dead_household(app):
    """★ 음성 대조군 ②: **확정 전** 취소 요청은 죽은 집이 아니다.

    거부될 수 있다. 여기서 죽었다고 말하면 살아 있는 청구가 화면에서 사라진다.
    """
    order = _naver_order()
    _link(order, order_no=_FIRST_NO, relation="NEW", amount=_FIRST_AMOUNT,
          claim_status="CANCEL_REQUEST")
    _link(order, order_no=_LIVE_REPAY_NO, relation="REPAY", amount=_LIVE_AMOUNT)

    payload = build_dock_payload(db_session, order)

    first = _fact(payload, _FIRST_NO)
    assert first["settled"] is False, "확정 전 취소 요청을 환불 확정으로 셌다"
    assert first["label"] == "이전 주문"


def test_a_partly_cancelled_household_is_not_dead(app):
    """★ 음성 대조군 ③: 집의 **일부만** 취소 확정이면 그 집은 살아 있다."""
    order = _naver_order()
    _link(order, order_no=_LIVE_REPAY_NO, relation="REPAY", amount=_LIVE_AMOUNT,
          claim_status="CANCEL_DONE")
    _link(order, order_no=_LIVE_REPAY_NO, relation="REPAY", amount=_LIVE_AMOUNT)
    _link(order, order_no=_FIRST_NO, relation="NEW", amount=_FIRST_AMOUNT)

    payload = build_dock_payload(db_session, order)

    assert _fact(payload, _LIVE_REPAY_NO)["settled"] is False
    assert _fact(payload, _LIVE_REPAY_NO)["label"] == "이번 주문(재결제)"


def test_an_addon_household_is_untouched(app):
    """★ 음성 대조군 ④: 추가결제 집은 옛 집이 살아 있다 — 라벨·금액 종전 그대로."""
    order = _naver_order()
    _link(order, order_no=_FIRST_NO, relation="NEW", amount=_FIRST_AMOUNT)
    _link(order, order_no=_LIVE_REPAY_NO, relation="ADDON", amount=_LIVE_AMOUNT)

    payload = build_dock_payload(db_session, order)

    assert _fact(payload, _FIRST_NO)["label"] == "원 주문"
    assert _fact(payload, _FIRST_NO)["superseded"] is False
    assert _fact(payload, _LIVE_REPAY_NO)["label"] == "추가결제분"
    assert payload["deposit_hint"]["live_total"] == _FIRST_AMOUNT + _LIVE_AMOUNT


def test_two_living_repays_name_only_the_latest_one(app):
    """살아 있는 재결제가 둘이면 **마지막 집만** `이번 주문` 이다(붙이기 실수 대비)."""
    order = _naver_order()
    _link(order, order_no=_FIRST_NO, relation="NEW", amount=_FIRST_AMOUNT)
    _link(order, order_no=_DEAD_REPAY_NO, relation="REPAY", amount=_DEAD_AMOUNT)
    _link(order, order_no=_LIVE_REPAY_NO, relation="REPAY", amount=_LIVE_AMOUNT)

    payload = build_dock_payload(db_session, order)

    assert _fact(payload, _DEAD_REPAY_NO)["label"] == "재결제분"
    assert _fact(payload, _LIVE_REPAY_NO)["label"] == "이번 주문(재결제)"
