"""도크 머리말의 취소·반품 낱말은 **첫 라벨이 아니라 집계**다 (NVCLAIM-ORDER-01 A-7).

사고: 황민철 집(ERP 주문 5026, 네이버 ``2026082772909971``)은 상품주문 4건 반품 중
추가구성상품 3건만 ``RETURN_DONE`` 이 되고 본품 ``2026082754601551`` 은
``추가상품 반품진행 후, 본 상품 반품진행을 할 수 있습니다.`` 로 실패해 ``DELIVERING``
인 채 **운영에 미환불로 남았다**. 그런데 ERP 주문 상세의 네이버 도크는
``dock.py`` 의 first-non-empty-wins 때문에 머리말에 **``반품 완료``** 를 적었다 —
담당자가 집을 끝난 것으로 읽은 직접 원인이다.

트리아지 집 배지는 555cfe8d7 에서 같은 결함을 고쳤고(:func:`order_candidates.aggregate_claim`
공용), 도크는 그 배에서 **의도적으로 이월**된 마지막 표면이다.

여기서 못박는 것:

* 살아 있는 본품이 하나라도 남은 집은 ``반품 완료`` 라고 말하지 않는다 → ``일부 반품``.
* **음성 대조군** — 집 전체가 같은 단계면 라인 라벨을 그대로 쓴다(`수거중`처럼 단계까지
  말해 집계 낱말보다 정확하다). 바꾸는 것은 부분 상태 하나뿐이다.
* 교환은 취소·반품으로 세지 않는다(R-2) — 대체품을 기다리는 집이 `일부 취소` 가 되면 안 된다.
* 판정 축은 ``claim_code`` 다. 한국어 낱말을 ``==`` 로 비교하다 데인 적이 있다.
* 라벨과 ``claim_money_back`` 은 **짝으로** 바뀐다 — 예약금(선금) 단서가 그 짝을 쓴다.
"""

from __future__ import annotations

from db import db_session
from foms.services.integrations.naver_commerce.dock import build_dock_payload
from foms.services.orders.order_create import create_order
from models import ExternalOrderLink, Order, User
from werkzeug.security import generate_password_hash

#: 사고 원본의 집 번호(네이버 주문번호).
_ORDER_NO = "2026082772909971"

_SEQ = [0]


def _uid() -> str:
    _SEQ[0] += 1
    return f"hc{_SEQ[0]}"


def _owner() -> User:
    user = User(username=f"dock_claim_{_uid()}", password=generate_password_hash("pw"),
                role="STAFF", team="CS", name="접수 담당", is_active=True)
    db_session.add(user)
    db_session.commit()
    return user


def _snapshot(*, product_name: str, product_class: str = "조합형옵션상품",
              amount: int = 100000, claim_status: str = "",
              claim_type: str = "") -> dict:
    product_order = {
        "productOrderId": f"PO-{_uid()}",
        "productName": product_name,
        "productOption": "사이즈: 3000 / 색상: 화이트",
        "productClass": product_class,
        "totalPaymentAmount": amount,
        "quantity": 1,
        "claimStatus": claim_status or None,
        "shippingAddress": {"name": "황민철", "tel1": "010-3333-4444",
                            "baseAddress": "서울 강남구 1", "detailedAddress": "101호"},
    }
    if claim_type:
        product_order["claimType"] = claim_type
    return {"order": {"orderId": _ORDER_NO, "ordererName": "황민철",
                      "ordererTel": "010-1111-2222"},
            "productOrder": product_order}


def _naver_order() -> Order:
    owner = _owner()
    order = create_order(
        db_session,
        actor_user_id=owner.id, owner_user_id=owner.id,
        order_fields=dict(received_date="2026-08-27", customer_name="황민철",
                          phone="010-3333-4444", address="서울 강남구 1 101호",
                          product="붙박이장", options="색상: 화이트", status="MEASURE"),
        structured_data={"source": "NAVER_SMARTSTORE"},
        is_erp_order=True,
    )
    db_session.flush()
    return order


def _link(order: Order, snapshot: dict) -> ExternalOrderLink:
    link = ExternalOrderLink(
        channel="NAVER",
        external_id=snapshot["productOrder"]["productOrderId"],
        order_id=order.id,
        external_order_no=_ORDER_NO,
        sync_status="LINKED",
        relation="NEW",
        raw_snapshot=snapshot,
    )
    db_session.add(link)
    db_session.commit()
    return link


def _incident_household(*, main_claim: str = "") -> dict:
    """사고와 같은 모양 — 본품 1 + 추가구성상품 3. 본품은 기본으로 클레임이 없다.

    링크 id 는 삽입 순서(본품 먼저)라 **첫 라벨은 추가상품에서 온다** — 수정 전 코드가
    ``반품 완료`` 를 내놓던 바로 그 경로다.
    """
    order = _naver_order()
    _link(order, _snapshot(product_name="루나 슬라이딩 3000", amount=800000,
                           claim_status=main_claim))
    for index in range(3):
        _link(order, _snapshot(product_name=f"길이추가({index + 1}cm)",
                               product_class="추가구성상품", amount=33200,
                               claim_status="RETURN_DONE"))
    return build_dock_payload(db_session, order)


# --------------------------------------------------------------------------- #
# 사고 재현 — 본품이 살아 있는 집은 `반품 완료` 가 아니다
# --------------------------------------------------------------------------- #

def test_partial_return_household_does_not_say_return_done(app):
    """추가상품 3건만 반품된 집을 ``반품 완료`` 라고 말하지 않는다 (사고 재현)."""
    payload = _incident_household()

    assert payload["claim_label"] != "반품 완료"
    assert payload["claim_label"] == "일부 반품"
    # 판정 축은 낱말이 아니라 코드다.
    assert payload["claim_code"] == "partial"


def test_partial_return_household_keeps_the_money_back_flag(app):
    """라벨과 환불 판정은 **짝으로** 바뀐다 — ⚠ 와 예약금 단서가 그 짝을 쓴다."""
    payload = _incident_household()

    assert payload["claim_money_back"] is True
    note = payload["deposit_hint"]["note"]
    assert "일부 반품" in note and "환불액" in note


# --------------------------------------------------------------------------- #
# 음성 대조군 — 바꾸는 것은 부분 상태 하나뿐이다
# --------------------------------------------------------------------------- #

def test_fully_returned_household_keeps_the_line_label(app):
    """집 전체가 반품 완료면 라인 라벨 ``반품 완료`` 를 그대로 쓴다."""
    payload = _incident_household(main_claim="RETURN_DONE")

    assert payload["claim_label"] == "반품 완료"
    assert payload["claim_code"] == "all_done"
    assert payload["claim_money_back"] is True


def test_household_in_one_stage_keeps_the_more_precise_line_label(app):
    """집 전체가 수거중이면 집계 낱말이 아니라 ``수거중`` 이라고 말한다.

    집계 낱말은 단계를 못 말한다 — 전부 같은 단계인 집에서는 라인 라벨이 더 정확하다.
    """
    order = _naver_order()
    for index in range(2):
        _link(order, _snapshot(product_name=f"본품 {index + 1}",
                               claim_status="COLLECTING", claim_type="RETURN"))
    payload = build_dock_payload(db_session, order)

    assert payload["claim_label"] == "수거중"
    assert payload["claim_code"] == "all_pending"


def test_normal_household_says_nothing(app):
    """**음성 대조군** — 클레임이 없는 집에 낱말을 만들지 않는다(신호가 죽는다)."""
    order = _naver_order()
    _link(order, _snapshot(product_name="본품", amount=500000))
    payload = build_dock_payload(db_session, order)

    assert payload["claim_label"] == ""
    assert payload["claim_code"] == "alive"
    assert payload["claim_money_back"] is False


def test_exchange_in_flight_is_not_counted_as_a_cancel(app):
    """교환은 돈이 되돌아가지 않는다 — 대체품을 기다리는 집이 `일부 취소` 가 되면 안 된다(R-2)."""
    order = _naver_order()
    _link(order, _snapshot(product_name="본품", amount=500000))
    _link(order, _snapshot(product_name="길이추가(1cm)", product_class="추가구성상품",
                           amount=33200, claim_status="EXCHANGE_REQUEST",
                           claim_type="EXCHANGE"))
    payload = build_dock_payload(db_session, order)

    assert payload["claim_code"] == "alive"
    # 라벨은 사실이라 그대로 보여준다 — 바뀌는 것은 그것을 취소로 **세는 것**뿐이다.
    assert payload["claim_label"] == "교환 요청"
    assert payload["claim_money_back"] is False


def test_rejected_sibling_does_not_hide_a_real_refund(app):
    """첫 라벨이 ``반품 거부``(환불 없음)여도 형제의 진짜 반품이 집계에 남는다.

    이 집이 부분 반품인 것은 사실이므로 라벨과 환불 판정이 **함께** 집계 쪽으로 간다 —
    짝을 안 맞추면 화면이 `일부 반품` 이라 적으면서 ⚠ 를 뗀다.
    """
    order = _naver_order()
    _link(order, _snapshot(product_name="본품", amount=500000,
                           claim_status="RETURN_REJECT", claim_type="RETURN"))
    _link(order, _snapshot(product_name="길이추가(1cm)", product_class="추가구성상품",
                           amount=33200, claim_status="RETURN_DONE"))
    payload = build_dock_payload(db_session, order)

    assert payload["claim_code"] == "partial"
    assert payload["claim_label"] == "일부 반품"
    assert payload["claim_money_back"] is True
