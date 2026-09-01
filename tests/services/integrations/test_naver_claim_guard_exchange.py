"""불가역 동작 앞의 클레임 게이트 — 교환도 막는다 (R-4, 2026-08-28).

`_claim_guard` 는 `claim["blocking"]` 을 봤는데 `BLOCKING_CLAIM_STATUSES` 에 `EXCHANGE_*` 가
없다. 그래서 `request_return` 이 자기 주석에 **"이미 클레임(취소·반품·교환)이 도는 집에
반품을 또 걸지 않는다"** 고 적어 놓고 교환은 안 막았다 — 교환이 도는 상품주문에 **불가역
반품 접수**가 그대로 나간다. 같은 구멍이 발주확인·발송처리·취소에도 있었다.

두 축을 가른다:

* `blocking` = **주문을 만들면 안 되는가**. 돈이 되돌아간 클레임(취소·반품)만이다 —
  교환은 고객이 대체품을 받으므로 ERP 주문이 있어야 한다.
* :func:`mapping.blocks_irreversible` = **네이버로 불가역 호출을 보내도 되는가**.
  진행 중인 클레임은 종류 불문 막고, 끝난 클레임은 돈이 되돌아간 종류만 막는다.
  교환 완료는 대체품 발송이 남아 있을 수 있어 막지 않는다.
"""

from __future__ import annotations

import pytest

from db import db_session
from foms.services.integrations.naver_commerce.fulfillment import (
    FulfillmentError,
    cancel_order,
    confirm_place_order,
    request_return,
)
from foms.services.integrations.naver_commerce.mapping import (
    blocks_irreversible,
    extract_claim,
)
from models import ExternalOrderLink

_SEQ = [0]


def _uid() -> str:
    _SEQ[0] += 1
    return f"{_SEQ[0]:03d}"


class _StubClient:
    """네이버 호출을 기록만 하는 스텁 — 한 건이라도 기록되면 게이트가 샌 것이다."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def confirm_place_orders(self, ids):
        self.calls.append(("confirm", ",".join(map(str, ids))))
        return {"data": {"successProductOrderIds": [str(i) for i in ids]}}

    def request_cancel_product_order(self, product_order_id, **kwargs):
        self.calls.append(("cancel", str(product_order_id)))
        return {"data": {"successProductOrderIds": [str(product_order_id)]}}

    def request_return_product_order(self, product_order_id, **kwargs):
        self.calls.append(("return", str(product_order_id)))
        return {"data": {"successProductOrderIds": [str(product_order_id)]}}

    def dispatch_product_orders(self, rows):
        self.calls.append(("dispatch", ",".join(str(r["productOrderId"]) for r in rows)))
        return {"data": {"successProductOrderIds": [str(r["productOrderId"]) for r in rows]}}


def _link(*, claim: str, place: str | None = "OK", dispatched: bool = False) -> int:
    from foms.services.integrations.naver_commerce.mapping import group_key_text

    external_id = f"PO-GX-{_uid()}"
    order_no = f"N-GX-{_uid()}"
    product_order = {"productOrderId": external_id, "claimStatus": claim}
    snapshot = {"order": {"orderId": order_no}, "productOrder": product_order}
    if dispatched:
        snapshot["delivery"] = {"sendDate": "2026-08-20T10:00:00.000+09:00"}
    link = ExternalOrderLink(
        channel="NAVER", external_id=external_id, external_order_no=order_no,
        sync_status="LINKED", place_order_status=place,
        raw_snapshot=snapshot, group_key=group_key_text(snapshot),
    )
    db_session.add(link)
    db_session.commit()
    return int(link.id)


def _claim(status: str, claim_type: str = "") -> dict:
    product_order = {"productOrderId": "PO-X", "claimStatus": status}
    if claim_type:
        product_order["claimType"] = claim_type
    return extract_claim({"productOrder": product_order})


# ── 술어 자체 ────────────────────────────────────────────────────────────────

def test_in_flight_exchange_blocks_irreversible_calls():
    """진행 중인 교환은 종류 불문 막는다 — 불가역 호출 앞에서는 안전한 쪽으로 튼다."""
    assert blocks_irreversible(_claim("EXCHANGE_REQUEST", "EXCHANGE")) is True


def test_finished_exchange_does_not_block():
    """**음성 대조군** — 교환 완료는 주문이 살아 있다(대체품 발송이 남아 있을 수 있다)."""
    assert blocks_irreversible(_claim("EXCHANGE_DONE", "EXCHANGE")) is False


def test_money_back_claims_block_exactly_as_before():
    """**음성 대조군** — 기존 9종 판정이 한 개도 안 바뀐다(게이트가 느슨해지면 사고다)."""
    from foms.services.integrations.naver_commerce.mapping import BLOCKING_CLAIM_STATUSES

    for status in sorted(BLOCKING_CLAIM_STATUSES):
        assert blocks_irreversible(_claim(status)) is True, status


def test_rejected_and_unknown_never_block():
    """**음성 대조군** — 거부는 주문이 살아 있고, 모르는 상태는 원래도 안 막았다."""
    for status in ("CANCEL_REJECT", "RETURN_REJECT", "EXCHANGE_REJECT",
                   "PURCHASE_DECISION_HOLDBACK", "SOME_NEW_NAVER_STATUS", ""):
        assert blocks_irreversible(_claim(status)) is False, status


# ── 실제 경로 4종 ────────────────────────────────────────────────────────────

def test_return_request_refuses_a_household_in_exchange(app):
    """교환이 도는 집에 **불가역 반품 접수**를 보내지 않는다 — 주석이 약속한 동작이다."""
    link_id = _link(claim="EXCHANGE_REQUEST", dispatched=True)
    client = _StubClient()

    with pytest.raises(FulfillmentError):
        request_return(db_session, client, link_id=link_id, reason="INTENT_CHANGED")
    assert client.calls == [], "교환 중인데 반품이 나갔다"


def test_cancel_refuses_a_household_in_exchange(app):
    """취소도 같다."""
    link_id = _link(claim="EXCHANGE_REQUEST")
    client = _StubClient()

    # 사유는 **유효한 코드**여야 이 테스트가 클레임 가드를 시험한다 — 목록 밖 코드를 쓰면
    # 사유 검사에서 먼저 걸려 가드를 안 지나고도 초록이 된다(`SOLD_OUT` 삭제 2026-09-01).
    with pytest.raises(FulfillmentError):
        cancel_order(db_session, client, link_id=link_id, reason="INTENT_CHANGED")
    assert client.calls == []


def test_confirm_refuses_a_household_in_exchange(app):
    """발주확인도 같다."""
    link_id = _link(claim="EXCHANGE_REQUEST", place="NOT_YET")
    client = _StubClient()

    with pytest.raises(FulfillmentError):
        confirm_place_order(db_session, client, link_id=link_id)
    assert client.calls == []


def test_plain_order_still_passes_the_gate(app):
    """**음성 대조군** — 클레임 없는 집은 예전처럼 통과한다(게이트가 다 막으면 업무가 선다)."""
    link_id = _link(claim="", place="NOT_YET")
    client = _StubClient()

    confirm_place_order(db_session, client, link_id=link_id)

    assert [name for name, _ in client.calls] == ["confirm"]
