"""D3: 도크가 **예약금(선금)에 넣을 금액**을 말하는지 (2026-08-27).

결함(사용자 실화면): 도크는 네이버 결제액을 그대로 보여 주지만 그 숫자가 ERP 의
``#erp-deposit-amount`` 와 맞는지는 아무도 말하지 않았다. 붙인 뒤 며칠 지난 화면이라
사람은 자기가 예전에 넣은 값이 지금도 맞는지 알 수 없었고, 재결제 집이 섞이면 환불된
옛 집 금액까지 더해 읽었다.

여기서 못박는 것:

* ``target`` 은 **절대값**(살아 있는 집들의 상품주문 결제액 합)이다 — 재결제 카드의
  상대값(``현재값 + 새 금액``)을 며칠 뒤 화면에 그대로 쓰면 이미 고쳐 놓은 값에 한 번 더
  더하게 된다. 재결제로 대체된 집(``superseded``)은 합계에서 **빠진다**.
* 문장은 **서버가** 만들고 :func:`repay_reconcile.deposit_guidance` 에 위임한다 —
  재결제 화면과 같은 말을 써야 두 화면이 같은 규칙으로 읽힌다.
  대체된 집이 있으면 ``REPAY``(대신 바꾸기), 없으면 ``ADDON``(차액 더하기).
* 금액을 못 읽은 상품주문은 **0 으로 더하지 않고 센다**. 조용히 작아진 합계는
  ``잔금 = 출고가 − 예약금`` 을 타고 고객 과다 청구가 된다.
* ``copy_value`` 는 쉼표·단위 없는 정수 문자열이고, 복사할 정답이 없는
  ``over``·``unknown`` 에서는 빈 문자열이다. **자동 기입은 없다** — 복사까지가 끝이다.
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

def test_match_state_confirms_without_asking_for_a_change(app):
    """예약금이 네이버 결제액과 같으면 ``match`` — 고치라고 말하지 않는다.

    보통 주문에 상시 카드를 세우면 잡음이 되고, 정말 틀린 날에 아무도 안 읽는다.
    """
    payload = _two_households(deposit=824200, relation="ADDON",
                              old_amount=704200, new_amount=120000)

    hint = payload["deposit_hint"]
    assert hint["state"] == "match"
    assert hint["current"] == 824200
    assert hint["target"] == 824200
    assert hint["diff"] == 0
    assert "같습니다" in hint["sentence"]
    # 고치라는 동사가 없어야 한다 — 맞는 값에 손대게 만들면 안 된다.
    assert "고치세요" not in hint["sentence"]
    assert "바꾸세요" not in hint["sentence"]


# --------------------------------------------------------------------------- #
# (2) 추가결제 — 차액을 "더해"
# --------------------------------------------------------------------------- #

def test_differs_addon_says_add_the_gap(app):
    """대체된 집이 없으면 ``ADDON`` 위임 — 옛 결제가 살아 있으니 차액을 **더한다**.

    문장은 :func:`repay_reconcile.deposit_guidance` 가 만든다. 도크가 따로 쓰면 재결제
    화면과 다른 말을 하게 되고, 사람은 어느 쪽을 믿을지 알 수 없다.
    """
    payload = _two_households(deposit=500000, relation="ADDON",
                              old_amount=500000, new_amount=120000)

    hint = payload["deposit_hint"]
    assert hint["state"] == "differs"
    assert hint["current"] == 500000
    # 두 집 모두 살아 있다 — 합계는 둘 다 든다.
    assert hint["target"] == 620000
    assert hint["diff"] == 120000
    assert "120,000원을 더해" in hint["sentence"]
    assert "620,000원" in hint["sentence"]
    assert hint["copy_value"] == "620000"
    # 대체된 집이 없으므로 "환불된 이전 주문" 단서가 붙으면 거짓말이다.
    assert "환불된 이전 주문" not in hint["note"]


# --------------------------------------------------------------------------- #
# (3) 재결제 — 옛 집을 빼고 "대신" + 단서
# --------------------------------------------------------------------------- #

def test_differs_repay_excludes_superseded_and_notes_it(app):
    """재결제 집이 있으면 ``REPAY`` 위임 — 옛 집 금액은 합계에서 **빠지고** 단서가 붙는다.

    합치면 이중 계상이다: 옛 결제는 이미 환불됐다(``repay_reconcile`` 모듈 머리말).
    """
    payload = _two_households(deposit=500000, relation="REPAY",
                              old_amount=500000, new_amount=704200)

    hint = payload["deposit_hint"]
    assert hint["state"] == "differs"
    # 대체된 옛 집(500,000)은 빠진다 — 1,204,200 이 아니다.
    assert hint["target"] == 704200
    assert hint["diff"] == 204200
    assert "704,200원으로 바꾸세요" in hint["sentence"]
    assert "대신" in hint["sentence"]
    assert hint["note"] == "환불된 이전 주문은 뺀 금액입니다"
    assert hint["copy_value"] == "704200"


# --------------------------------------------------------------------------- #
# (4) 금액을 못 읽은 행 — 0 으로 더하지 않고 센다
# --------------------------------------------------------------------------- #

def test_unknown_amount_is_counted_never_summed_as_zero(app):
    """``totalPaymentAmount`` 가 int 가 아니면 **모름 1건**이지 0 원이 아니다.

    0 으로 더하면 합계가 조용히 작아지고, 그 숫자를 예약금에 넣은 사람이
    ``잔금 = 출고가 − 예약금`` 을 타고 고객에게 과다 청구한다. 숫자를 못 내는 날에는
    숫자를 말하지 않는다.
    """
    order = _naver_order(deposit=100000)
    _link(order, _snapshot(amount=100000, order_no=_OLD_NO), order_no=_OLD_NO)
    _link(order, _snapshot(amount=None, order_no=_OLD_NO, product_name="길이추가 1cm",
                           product_class="추가구성상품"), order_no=_OLD_NO)

    payload = build_dock_payload(db_session, order)

    house = payload["households"][0]
    assert house["amount_total"] == 100000
    assert house["amount_unknown"] == 1
    hint = payload["deposit_hint"]
    assert hint["state"] == "unknown"
    assert hint["unknown_count"] == 1
    assert hint["target"] is None
    assert hint["diff"] is None
    # 복사할 정답이 없다 — 빈 값이라 복사 버튼이 붙지 않는다.
    assert hint["copy_value"] == ""
    assert "1건" in hint["sentence"]
    assert hint["current"] == 100000


# --------------------------------------------------------------------------- #
# (5) 예약금이 더 큰 경우 — 경고만, "낮추라"고 말하지 않는다
# --------------------------------------------------------------------------- #

def test_over_state_warns_without_telling_anyone_to_lower_it(app):
    """예약금이 네이버 결제액보다 크면 ``over`` — 내리라고 지시하지 않는다.

    네이버 밖 입금(계좌이체 선금 등)이 정당할 수 있고, 그 지시는
    ``잔금 = 출고가 − 예약금`` 을 타고 고객 청구로 나간다.
    """
    payload = _single(deposit=900000, amount=704200)

    hint = payload["deposit_hint"]
    assert hint["state"] == "over"
    assert hint["current"] == 900000
    assert hint["target"] == 704200
    assert hint["diff"] == -195800
    assert "195,800원 많습니다" in hint["sentence"]
    for forbidden in ("낮추", "내리", "줄이"):
        assert forbidden not in hint["sentence"], hint["sentence"]
    # 틀렸다고 단정할 수 없으니 복사할 값도 없다.
    assert hint["copy_value"] == ""


# --------------------------------------------------------------------------- #
# (6) 클레임 — 환불액 미반영을 고지한다
# --------------------------------------------------------------------------- #

def test_claim_adds_note_that_refund_is_not_deducted_yet(app):
    """취소·반품이 걸린 주문은 합계가 **환불 전** 금액임을 말한다.

    ``totalPaymentAmount`` 는 결제 시점 값이라 클레임 환불이 아직 안 빠져 있다. 그걸
    말하지 않으면 사람이 환불된 돈까지 예약금에 넣는다.
    """
    payload = _single(deposit=100000, amount=704200, claim_status="CANCEL_REQUEST")

    assert payload["claim_label"] == "취소 요청"
    note = payload["deposit_hint"]["note"]
    assert "취소 요청" in note
    assert "환불액" in note


# --------------------------------------------------------------------------- #
# (7) 복사값 형식 — 쉼표·단위 없는 정수 문자열
# --------------------------------------------------------------------------- #

def test_copy_value_is_a_bare_integer_string(app):
    """``copy_value`` 는 ``"1234567"`` — 쉼표·``원`` 이 붙으면 붙여넣기가 깨진다.

    사람은 이 값을 ``#erp-deposit-amount`` 에 **직접** 붙여넣는다(자동 기입 금지 —
    명문 규약). 문장 쪽은 사람이 읽는 자리라 쉼표를 유지한다.
    """
    payload = _single(deposit=0, amount=1234567)

    hint = payload["deposit_hint"]
    assert hint["copy_value"] == "1234567"
    assert "," not in hint["copy_value"]
    assert "원" not in hint["copy_value"]
    assert int(hint["copy_value"]) == hint["target"]
    # 읽는 문장에는 쉼표가 그대로 있어야 한다(같은 값을 두 축으로 낸다).
    assert "1,234,567원" in hint["sentence"]


# --------------------------------------------------------------------------- #
# (8) 집 단위 금액 키 — 화면이 그룹 합계를 검산할 근거
# --------------------------------------------------------------------------- #

def test_every_household_carries_its_own_amount_totals(app):
    """``households[]`` 마다 ``amount_total``·``amount_unknown`` 이 실린다.

    집이 둘인 주문에서 화면이 집별 합계를 직접 세면 예약금 안내와 어긋난다 —
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
    # 예약금 target 은 살아 있는 집만 더한 값과 같다.
    assert payload["deposit_hint"]["target"] == by_no[_NEW_NO]["amount_total"]
