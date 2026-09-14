"""GAP-01: 네이버 수집분 ↔ ERP 주문 대조 계약.

고정하는 것:

* 버킷 5개가 각각 어떤 입력에서 나오는지(음성 대조군 포함). ``CANCEL_REQUEST``
  는 종결이 **아니다** — 확정만 종결이다. 이 음성 대조군이 없으면 나머지
  단언은 아무것도 증명하지 않는다.
* ``relation`` 은 추가·재결제 축이 아니다. ``relation='NEW'`` 인데 상품명이
  ``추가결제`` 면 부가 라인이다.
* ``raw_snapshot`` 은 중첩·평평 두 모양으로 온다. 한 모양만 읽으면 조용히
  0건이 된다.
* ``claimStatus`` 가 **빈 문자열**이어도 뒤 후보(triage_state)를 본다.
  ``nullif`` 없이 ``coalesce`` 하면 빈 문자열이 이겨서 여기서 red 다.
* 행이 조용히 사라지지 않는다 — 버킷 count 합 == total == scanned.
* 행 dict 에 전화·주소가 없다. 이름은 마스킹된 것만 나간다.
* 이 모듈은 네이버 HTTP 를 내지 않는다(WORKER 단일 출구 계약).

운영 실측치(93 / 227 / 1,080 / 444)는 **다른 술어**로 센 값이라 여기 박지
않는다. 테스트는 분기가 의도대로 갈리는지와 합이 맞는지만 못박는다.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from db import db_session
from foms.services.integrations.naver_commerce.claim_watch import STATE_KEY
from foms.services.integrations.naver_commerce.constants import (
    ADDON_PRODUCT_CLASS,
    CHANNEL,
)
from foms.services.integrations.naver_commerce.order_gap import (
    GAP_ATTACHABLE,
    GAP_BUCKETS,
    GAP_CLOSED,
    GAP_EXTRA,
    GAP_LABELS,
    GAP_MISSING,
    GAP_ROW_KEYS,
    GAP_UNDECIDED,
    build_order_gap_view,
    classify_gap_row,
    list_order_gap,
    mask_name,
    summarize_order_gap,
)
from models import ExternalOrderLink, Order

ROOT = Path(__file__).resolve().parents[2]

GAP_PANE = "templates/admin/partials/naver_gap_pane.html"

#: 화면이 절대 말하면 안 되는 단정. 전화 대조는 휴리스틱이라 양쪽으로 틀린다.
FORBIDDEN_WORDS = ("빠진 주문", "누락", "확정된 미생성", "반드시")

#: 상단 안내 한 줄. 글자까지 계약이다.
REQUIRED_NOTICE = "전화 대조로 짚은 후보입니다 — 확정된 수가 아닙니다."

_SEQ = [0]


@pytest.fixture
def db(app):
    yield db_session
    db_session.rollback()


def _uid() -> str:
    _SEQ[0] += 1
    return f"gap-{_SEQ[0]}"


# --------------------------------------------------------------------------- #
# 헬퍼
# --------------------------------------------------------------------------- #

def _fields(**over) -> dict:
    """살아있는 본품 한 벌(=GAP_MISSING/ATTACHABLE 후보)을 기본값으로."""
    base = {
        "product_class": "조합형옵션상품",
        "product_name": "붙박이장",
        "order_status": "PURCHASE_DECIDED",
        "claim_status": "",
        "amount": 500000,
        "relation": "NEW",
        "phone_digits": "01033334444",
    }
    base.update(over)
    return base


def _snapshot(*, nested: bool, product_class: str, product_name: str,
              order_status: str, claim_status: str | None, amount,
              external_id: str) -> dict:
    product_order = {
        "productOrderId": external_id,
        "productClass": product_class,
        "productName": product_name,
        "productOrderStatus": order_status,
        "totalPaymentAmount": amount,
    }
    if claim_status is not None:
        product_order["claimStatus"] = claim_status
    if not nested:
        # 평평한 모양 — 배치 조회에서 이렇게 온다(mapping.unwrap_detail).
        flat = dict(product_order)
        flat["orderId"] = "N-" + external_id
        return flat
    return {"order": {"orderId": "N-" + external_id, "ordererName": "김주문"},
            "productOrder": product_order}


def _link(*, nested: bool = True,
          product_class: str = "조합형옵션상품",
          product_name: str = "붙박이장",
          order_status: str = "PURCHASE_DECIDED",
          claim_status: str | None = None,
          amount=500000,
          relation: str = "NEW",
          recipient_name: str = "이수취",
          phone: str | None = "01033334444",
          triage_state: dict | None = None,
          order: Order | None = None) -> ExternalOrderLink:
    external_id = f"PO-{_uid()}"
    link = ExternalOrderLink(
        channel=CHANNEL,
        external_id=external_id,
        sync_status="COLLECTED",
        relation=relation,
        order_id=order.id if order is not None else None,
        recipient_name=recipient_name,
        recipient_phone_digits=phone,
        triage_state=triage_state,
        raw_snapshot=_snapshot(nested=nested, product_class=product_class,
                               product_name=product_name,
                               order_status=order_status,
                               claim_status=claim_status, amount=amount,
                               external_id=external_id),
    )
    db_session.add(link)
    db_session.commit()
    return link


def _order(*, phone_digits: str, trashed: bool = False) -> Order:
    order = Order(customer_name="테스트고객", phone="010-3333-4444", address="서울",
                  product="붙박이장", options="", received_date="2026-09-01",
                  status="DELETED" if trashed else "RECEIVED",
                  is_erp_order=False, structured_data={},
                  erp_phone_digits=phone_digits)
    if trashed:
        import datetime

        order.deleted_at = datetime.datetime(2026, 9, 2, 0, 0, 0)
    db_session.add(order)
    db_session.commit()
    return order


def _bucket_of(link_ids) -> dict[int, str]:
    """link_id → 버킷. 칸마다 목록을 받아 뒤집는다(전수 확인용)."""
    wanted = set(link_ids)
    found: dict[int, str] = {}
    for name in GAP_BUCKETS:
        for row in list_order_gap(db_session, bucket=name, limit=1000):
            if row["link_id"] in wanted:
                found[row["link_id"]] = row["bucket"]
    return found


# --------------------------------------------------------------------------- #
# 1. 분류 분기 전수 (순수 함수)
# --------------------------------------------------------------------------- #

def test_classify_closed_by_order_status():
    """네이버 주문 상태가 CANCELED/RETURNED 면 종결이다."""
    assert classify_gap_row(_fields(order_status="CANCELED"),
                            has_erp_order=False) == GAP_CLOSED
    assert classify_gap_row(_fields(order_status="RETURNED"),
                            has_erp_order=True) == GAP_CLOSED


def test_classify_closed_only_when_claim_phase_done():
    """종결은 CLAIM_PHASES 가 done 이라고 말할 때만이다."""
    assert classify_gap_row(_fields(order_status="PAYED",
                                    claim_status="CANCEL_DONE"),
                            has_erp_order=False) == GAP_CLOSED
    assert classify_gap_row(_fields(order_status="PAYED",
                                    claim_status="RETURN_DONE"),
                            has_erp_order=False) == GAP_CLOSED


def test_classify_claim_request_is_not_closed():
    """음성 대조군 — 요청 단계는 종결이 아니다.

    "claimStatus 가 비어 있지 않은가" 한 비트 판정을 쓰면 여기서 red 다
    (2026-08-28 운영 사고 link 79 / 주문 #4998 의 재료).
    """
    assert classify_gap_row(_fields(order_status="PAYED",
                                    claim_status="CANCEL_REQUEST"),
                            has_erp_order=False) == GAP_UNDECIDED


def test_classify_claim_reject_is_not_closed():
    """거부된 클레임은 주문이 살아 있다 — 종결도 아니고 본품 확정도 아니다."""
    assert classify_gap_row(_fields(claim_status="CANCEL_REJECT"),
                            has_erp_order=True) == GAP_UNDECIDED


def test_classify_extra_by_product_class():
    assert classify_gap_row(_fields(product_class=ADDON_PRODUCT_CLASS),
                            has_erp_order=False) == GAP_EXTRA


def test_classify_extra_by_relation():
    for relation in ("ADDON", "REPAY"):
        assert classify_gap_row(_fields(relation=relation),
                                has_erp_order=False) == GAP_EXTRA


def test_classify_extra_wins_over_relation_new():
    """오용 차단 — relation 은 추가·재결제 축이 아니다.

    운영에는 상품명이 그대로 ``추가결제`` 인데 relation 이 ``NEW`` 인 행이
    있다. relation 만 보면 그 행이 "주문 없음" 으로 새어 나온다.
    """
    assert classify_gap_row(_fields(product_name="추가결제", relation="NEW"),
                            has_erp_order=False) == GAP_EXTRA
    # 앞뒤 공백이 있어도 같다.
    assert classify_gap_row(_fields(product_name="  추가결제  ", relation="NEW"),
                            has_erp_order=False) == GAP_EXTRA


def test_classify_live_main_splits_on_erp_order():
    assert classify_gap_row(_fields(), has_erp_order=False) == GAP_MISSING
    assert classify_gap_row(_fields(), has_erp_order=True) == GAP_ATTACHABLE


def test_classify_empty_phone_is_missing_not_attachable():
    """짚을 축이 없으면 '주문 없음' 이다. 조용히 attachable 로 보내면 거짓말이다."""
    assert classify_gap_row(_fields(phone_digits=""),
                            has_erp_order=True) == GAP_MISSING
    assert classify_gap_row(_fields(phone_digits=None),
                            has_erp_order=True) == GAP_MISSING


def test_classify_zero_amount_is_undecided():
    assert classify_gap_row(_fields(amount=0), has_erp_order=True) == GAP_UNDECIDED


def test_classify_unknown_product_class_is_undecided():
    assert classify_gap_row(_fields(product_class="알수없는구분"),
                            has_erp_order=True) == GAP_UNDECIDED


def test_classify_in_flight_status_is_undecided():
    """배송 중은 네 칸 어디도 아니다 — 다섯 번째 칸이 없으면 행이 사라진다."""
    assert classify_gap_row(_fields(order_status="DELIVERING"),
                            has_erp_order=True) == GAP_UNDECIDED


def test_classify_returns_only_known_buckets():
    for fields in (_fields(), _fields(order_status="CANCELED"),
                   _fields(relation="ADDON"), _fields(amount=0),
                   _fields(claim_status="CANCEL_DONE")):
        assert classify_gap_row(fields, has_erp_order=False) in GAP_BUCKETS


# --------------------------------------------------------------------------- #
# 2. mask_name
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("raw,masked", [
    (None, ""),
    ("", ""),
    ("   ", ""),
    ("홍", "*"),
    ("홍길", "홍*"),
    ("홍길동", "홍*동"),
    ("남궁민수", "남**수"),
])
def test_mask_name(raw, masked):
    assert mask_name(raw) == masked
