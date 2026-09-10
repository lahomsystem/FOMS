"""도크 네이버 결제 금액 카드의 재료 — ``deposit_hint`` 는 낱말·돈 표기·합계·모름 건수만 싣는다.

2026-08-27(D3)~2026-09-10 사이에는 예약금(선금) 목표액·대조 상태·"지금 값에 더해 고치세요" 문장·
복사값·환불 단서까지 실었다. 2026-09-10 사용자 지시로 화면(ERP 도크)이 그 설명문을 전부 걷고
**낱말 + 금액 한 줄**만 그리게 되자 읽는 곳이 0 이 됐고, 2026-09-11 에 키·헬퍼를 함께 걷어냈다.
예약금 목표액 셈은 워크벤치 정리 카드의 :func:`repay_reconcile.deposit_guidance` 에만 남아 있다.

여기서 못박는 것:

* ``live_total`` 은 **살아 있는 집**(재결제로 대체되지 않은 집)들의 상품주문 결제액 합이다 —
  대체된 옛 집은 빠진다. 재결제 카드의 상대값을 쓰지 않는다.
* 금액을 못 읽은 상품주문은 **0 으로 더하지 않고 센다**(``unknown_count``). 그 날은
  ``live_total_display`` 를 비운다 — 조용히 작아진 합계는 ``잔금 = 출고가 − 예약금`` 을 타고
  고객 과다 청구가 된다.
* 낱말(``relation_label``)과 돈 표기(``live_total_display``)는 **서버가** 만든다 — 화면이 다시
  포맷하면 두 자리가 조용히 갈린다.
"""

from __future__ import annotations

import copy

from sqlalchemy.orm.attributes import flag_modified
from werkzeug.security import generate_password_hash

from db import db_session
from foms.services.integrations.naver_commerce.dock import build_dock_payload
from foms.services.orders.order_create import create_order
from models import ExternalOrderLink, Order, User

_OLD_NO = "2026082545684381"
_NEW_NO = "2026082615627581"

_SEQ = [0]


def _uid() -> str:
    _SEQ[0] += 1
    return f"dep{_SEQ[0]}"


def _owner() -> User:
    user = User(username=f"dock_dep_{_uid()}", password=generate_password_hash("pw"),
                role="STAFF", team="CS", name="접수 담당", is_active=True)
    db_session.add(user)
    db_session.commit()
    return user


def _snapshot(*, amount, order_no: str = _OLD_NO, product_name: str = "붙박이장 로라",
              product_class: str = "조합형옵션상품",
              claim_status: str = "") -> dict:
    """상품주문 상세 한 건. ``amount`` 에 int 가 아닌 값을 주면 '금액 모름' 행이 된다."""
    return {
        "order": {"orderId": order_no, "ordererName": "이수취",
                  "ordererTel": "010-1111-2222"},
        "productOrder": {
            "productOrderId": f"PO-{_uid()}",
            "productName": product_name,
            "productOption": "사이즈: 3000 / 색상: 화이트",
            "productClass": product_class,
            "totalPaymentAmount": amount,
            "quantity": 1,
            "claimStatus": claim_status or None,
            "shippingAddress": {"name": "이수취", "tel1": "010-3333-4444",
                                "baseAddress": "서울 강남구 1", "detailedAddress": "101호"},
        },
    }


def _naver_order(*, deposit) -> Order:
    """네이버 수집 주문 하나 — 예약금(선금)은 생성 뒤 직접 찍는다.

    ``create_order`` 는 ``recompute_totals`` 를 거치므로, 이 테스트가 보려는 값
    (``payment.deposit``)을 생성 인자로 넘기면 무엇이 살아남는지가 그 함수에 매인다.
    읽는 자리(``erp_deposit_amount_from_structured``)와 같은 키를 직접 쓴다.
    """
    order = create_order(
        db_session,
        actor_user_id=_owner().id, owner_user_id=_owner().id,
        order_fields=dict(received_date="2026-08-25", customer_name="이수취",
                          phone="010-3333-4444", address="서울 강남구 1 101호",
                          product="붙박이장", options="색상: 화이트", status="RECEIVED"),
        structured_data={"source": "NAVER_SMARTSTORE"},
        is_erp_order=True,
    )
    db_session.flush()
    sd = copy.deepcopy(order.structured_data or {})
    sd.setdefault("payment", {})["deposit"] = deposit
    order.structured_data = sd
    flag_modified(order, "structured_data")
    db_session.commit()
    return order


def _link(order: Order, snapshot: dict, *, order_no: str,
          relation: str = "NEW") -> ExternalOrderLink:
    link = ExternalOrderLink(
        channel="NAVER",
        external_id=snapshot["productOrder"]["productOrderId"],
        order_id=order.id,
        external_order_no=order_no,
        sync_status="LINKED",
        relation=relation,
        raw_snapshot=snapshot,
    )
    db_session.add(link)
    db_session.commit()
    return link


def _single(*, deposit, amount, claim_status: str = "") -> dict:
    """집 하나 · 상품주문 하나짜리 주문의 도크 payload."""
    order = _naver_order(deposit=deposit)
    _link(order, _snapshot(amount=amount, order_no=_OLD_NO, claim_status=claim_status),
          order_no=_OLD_NO)
    return build_dock_payload(db_session, order)


def _two_households(*, deposit, relation: str, old_amount: int, new_amount: int) -> dict:
    """원 주문 집(``NEW``) + 나중에 붙은 집(``relation``)의 도크 payload."""
    order = _naver_order(deposit=deposit)
    _link(order, _snapshot(amount=old_amount, order_no=_OLD_NO),
          order_no=_OLD_NO, relation="NEW")
    _link(order, _snapshot(amount=new_amount, order_no=_NEW_NO),
          order_no=_NEW_NO, relation=relation)
    return build_dock_payload(db_session, order)


# --------------------------------------------------------------------------- #
# (1) 값이 맞는 보통 주문 — 한 줄 확인
# --------------------------------------------------------------------------- #

# --------------------------------------------------------------------------- #
# (2) 추가결제 — 차액을 "더해"
# --------------------------------------------------------------------------- #

# --------------------------------------------------------------------------- #
# (3) 재결제 — 옛 집을 빼고 "대신" + 단서
# --------------------------------------------------------------------------- #

# --------------------------------------------------------------------------- #
# (4) 금액을 못 읽은 행 — 0 으로 더하지 않고 센다
# --------------------------------------------------------------------------- #

# --------------------------------------------------------------------------- #
# (5) 예약금이 더 큰 경우 — 경고만, "낮추라"고 말하지 않는다
# --------------------------------------------------------------------------- #

# --------------------------------------------------------------------------- #
# (6) 클레임 — 환불액 미반영을 고지한다
# --------------------------------------------------------------------------- #

# --------------------------------------------------------------------------- #
# (7) 복사값 형식 — 쉼표·단위 없는 정수 문자열
# --------------------------------------------------------------------------- #

# --------------------------------------------------------------------------- #
# (8) 집 단위 금액 키 — 화면이 그룹 합계를 검산할 근거
# --------------------------------------------------------------------------- #

def test_every_household_carries_its_own_amount_totals(app):
    """``households[]`` 마다 ``amount_total``·``amount_unknown`` 이 실린다.

    집이 둘인 주문에서 화면이 집별 합계를 직접 세면 카드 합계와 어긋난다 —
    같은 자리에서 낸 값을 함께 싣는다.
    """
    payload = _two_households(deposit=0, relation="REPAY",
                              old_amount=500000, new_amount=704200)

    by_no = {house["order_no"]: house for house in payload["households"]}
    assert by_no[_OLD_NO]["amount_total"] == 500000
    assert by_no[_OLD_NO]["amount_unknown"] == 0
    assert by_no[_OLD_NO]["superseded"] is True
    assert by_no[_NEW_NO]["amount_total"] == 704200
    assert by_no[_NEW_NO]["amount_unknown"] == 0
    assert by_no[_NEW_NO]["superseded"] is False
    # 카드의 합계(live_total)는 살아 있는 집만 더한 값과 같다.
    assert payload["deposit_hint"]["live_total"] == by_no[_NEW_NO]["amount_total"]


# --------------------------------------------------------------------------- #
# (9) 카드 한 줄 키 — 낱말·돈 표기는 서버가 만든다 (2026-09-10 사용자 지시)
# --------------------------------------------------------------------------- #

def test_pure_addon_household_says_addon_and_the_naver_amount_alone(app):
    """주문 #5206 모양: ERP 주문에 추가결제 집 하나 — `추가 결제` + `1,290,850원`.

    목표액(바닥값 포함 1,390,850)은 카드에 안 쓴다 — 사용자가 지운 설명문의 숫자다.
    기존 키(``target_display``)는 그대로 산다(CEO 계약 2026-09-10 — 런타임 소비처 없음, 후속 정리 후보).
    """
    order = _naver_order(deposit=100000)
    _link(order, _snapshot(amount=1290850, order_no=_NEW_NO), order_no=_NEW_NO, relation="ADDON")

    hint = build_dock_payload(db_session, order)["deposit_hint"]

    assert hint["relation_label"] == "추가 결제"
    assert hint["live_total_display"] == "1,290,850원"


def test_pure_repay_household_says_repay_and_excludes_the_superseded_house(app):
    """재결제로 대체된 옛 집은 낱말·돈 둘 다에서 빠진다 — 살아 있는 집이 전부 REPAY 면 `재결제`."""
    payload = _two_households(deposit=0, relation="REPAY", old_amount=500000, new_amount=704200)

    assert payload["deposit_hint"]["relation_label"] == "재결제"
    assert payload["deposit_hint"]["live_total_display"] == "704,200원"


def test_mixed_live_households_say_naver_payment_with_the_live_total(app):
    """원 주문 집(NEW)이 살아 있고 추가결제 집이 붙으면 `네이버 결제` + 두 집 합계."""
    payload = _two_households(deposit=0, relation="ADDON", old_amount=500000, new_amount=120000)

    assert payload["deposit_hint"]["relation_label"] == "네이버 결제"
    assert payload["deposit_hint"]["live_total_display"] == "620,000원"


def test_plain_new_order_has_no_relation_word_so_no_card(app):
    """보통 주문(집 하나·NEW)은 낱말이 빈 문자열 — 돈 표기는 있어도 카드는 서지 않는다."""
    hint = _single(deposit=0, amount=704200)["deposit_hint"]

    assert hint["relation_label"] == ""
    assert hint["live_total_display"] == "704,200원"


def test_unknown_amount_leaves_the_display_blank(app):
    """금액 모름이면 돈 표기를 비운다 — 숫자를 못 내는 날엔 숫자를 말하지 않는다((4) 와 같은 픽스처)."""
    order = _naver_order(deposit=100000)
    _link(order, _snapshot(amount=100000, order_no=_OLD_NO), order_no=_OLD_NO, relation="ADDON")
    _link(order, _snapshot(amount=None, order_no=_OLD_NO, product_name="길이추가 1cm",
                           product_class="추가구성상품"), order_no=_OLD_NO, relation="ADDON")

    hint = build_dock_payload(db_session, order)["deposit_hint"]

    assert hint["unknown_count"] == 1
    assert hint["live_total_display"] == ""
    assert hint["live_total"] == 100000, "못 읽은 건은 0 으로 더하지 않고 센다 — 읽은 건 합만 남는다"
