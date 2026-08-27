# -*- coding: utf-8 -*-
"""T8-S1 판매자 반품 접수 — 불가역 호출의 가드·화이트리스트·멱등을 잠근다.

이 경로는 **되돌릴 수 없다**: 접수하면 구매자에게 반품 진행이 보이고, 커머스API 로는
수거 정보를 다시 못 바꾼다. 그래서 "네이버가 400 으로 막아 주겠지"에 기대지 않고
호출 **전에** 전부 막는다 — 발송처리·취소와 같은 규율이다.
"""
from __future__ import annotations

import pytest

from foms.services.integrations.naver_commerce.fulfillment import (
    FulfillmentError,
    RETURN_COLLECT_METHOD,
    RETURN_REASONS,
    CANCEL_REASONS,
    request_return,
)


class _Client:
    """호출을 기록하는 가짜 클라이언트. 기본은 전건 성공."""

    def __init__(self, *, fail: dict | None = None, raises: Exception | None = None):
        self.calls: list[dict] = []
        self._fail = fail or {}
        self._raises = raises

    def request_return_product_order(self, product_order_id, *, reason,
                                     collect_method, detail=None, quantity=None):
        self.calls.append({"pid": product_order_id, "reason": reason,
                           "collect_method": collect_method, "detail": detail})
        if self._raises is not None:
            raise self._raises
        if product_order_id in self._fail:
            return {"data": {"successProductOrderIds": [],
                             "failProductOrderInfos": [
                                 {"productOrderId": product_order_id,
                                  "message": self._fail[product_order_id]}]}}
        return {"data": {"successProductOrderIds": [product_order_id],
                         "failProductOrderInfos": []}}


# ------------------------------------------------------- 회수 방법 화이트리스트


def test_collect_method_is_a_single_frozen_value():
    """회수 방법은 **값 하나**다 — 목록에 두면 언젠가 누가 고른다.

    `RETURN_DESIGNATED`·`RETURN_DELIVERY` 를 보내면 API 값이 무시되고 상품정보의
    택배사가 **고객 집으로 자동 수거**를 간다(되돌릴 수 없다). 그래서 그 코드들은
    상수로도 존재시키지 않는다.
    """
    assert RETURN_COLLECT_METHOD == "RETURN_INDIVIDUAL"
    assert isinstance(RETURN_COLLECT_METHOD, str), "목록이면 고를 수 있게 된다"

    # 위험 코드를 **설명하는 문장**과 **보낼 수 있는 값**은 다르다. 주석·docstring 은
    # 오히려 있어야 하고, 막아야 할 것은 "문자열 상수로 존재해서 언젠가 body 에 실리는" 것이다.
    # 그래서 소스 문자열 검색이 아니라 AST 로 **정확히 그 값인 리터럴**만 찾는다.
    import ast
    import foms.services.integrations.naver_commerce.fulfillment as mod

    tree = ast.parse(open(mod.__file__, encoding="utf-8").read())
    literals = {node.value for node in ast.walk(tree)
                if isinstance(node, ast.Constant) and isinstance(node.value, str)}
    for forbidden in ("RETURN_DESIGNATED", "RETURN_DELIVERY"):
        assert forbidden not in literals, (
            f"{forbidden} 이 문자열 상수로 존재한다 — 언젠가 body 에 실린다")


def test_return_reasons_are_not_the_cancel_reasons():
    """반품 사유 목록은 취소와 **다른 목록**이다 — 재사용하면 네이버가 400 을 준다."""
    assert RETURN_REASONS != CANCEL_REASONS
    assert "WRONG_DELAYED_DELIVERY" in RETURN_REASONS
    assert "SOLD_OUT" not in RETURN_REASONS, "품절은 반품 사유가 아니다(취소 사유다)"


def test_unknown_reason_is_rejected_before_any_call():
    """목록 밖 사유는 **네이버를 부르기 전에** 막는다."""
    client = _Client()
    with pytest.raises(FulfillmentError) as err:
        request_return(session=None, client=client, link_id=1, reason="NOPE")
    assert "반품 사유 코드" in str(err.value)
    assert client.calls == [], "막아야 할 요청이 네이버로 나갔다"


def test_empty_reason_is_rejected_before_any_call():
    """빈 사유도 마찬가지다."""
    client = _Client()
    with pytest.raises(FulfillmentError):
        request_return(session=None, client=client, link_id=1, reason="")
    assert client.calls == []


# ------------------------------------------------------------------ 집 단위 가드

from db import db_session  # noqa: E402
from models import ExternalOrderLink  # noqa: E402


def _link(external_id: str, *, order_no: str = "N-RET", claim: str = "",
          dispatched: bool = False, returned: bool = False) -> int:
    """상품주문 1건. ``dispatched`` 면 우리 발송 표식을, ``returned`` 면 반품 표식을 남긴다."""
    from foms.services.integrations.naver_commerce.mapping import group_key_text

    product_order = {"productOrderId": external_id}
    if claim:
        product_order["claimStatus"] = claim
    snapshot = {"order": {"orderId": order_no}, "productOrder": product_order}
    state: dict = {}
    if dispatched:
        state["fulfillment"] = {"dispatched_at": "2026-08-27T00:00:00"}
    if returned:
        state["return"] = {"requested_at": "2026-08-27T00:00:00"}
    link = ExternalOrderLink(
        channel="NAVER", external_id=external_id, external_order_no=order_no,
        sync_status="LINKED", place_order_status="OK",
        raw_snapshot=snapshot, group_key=group_key_text(snapshot),
        triage_state=state or None,
    )
    db_session.add(link)
    db_session.commit()
    return int(link.id)


def test_not_dispatched_household_is_rejected(app):
    """**발송 전이면 반품이 아니라 취소다** — 안 나간 물건을 반품으로 접수하지 않는다."""
    client = _Client()
    lid = _link("PO-RET-A1", order_no="N-RET-A", dispatched=False)
    with pytest.raises(FulfillmentError) as err:
        request_return(db_session, client, link_id=lid, reason="COLOR_AND_SIZE")
    assert "발송처리가 안 된" in str(err.value)
    assert client.calls == [], "발송 전인데 네이버로 반품 요청이 나갔다"


def test_dispatched_household_is_accepted_and_marked(app):
    """발송된 집은 접수되고 **우리 표식**이 남는다(멱등의 근거)."""
    client = _Client()
    lid = _link("PO-RET-B1", order_no="N-RET-B", dispatched=True)
    out = request_return(db_session, client, link_id=lid, reason="COLOR_AND_SIZE",
                         detail="문짝 색상 상이")
    db_session.commit()
    assert out["returned"] == ["PO-RET-B1"]
    assert len(client.calls) == 1
    call = client.calls[0]
    assert call["reason"] == "COLOR_AND_SIZE"
    assert call["collect_method"] == RETURN_COLLECT_METHOD, "자사 회수가 아닌 값이 나갔다"
    db_session.expire_all()
    state = (db_session.get(ExternalOrderLink, lid).triage_state or {}).get("return") or {}
    assert state.get("requested_at"), "우리 표식이 안 남았다 — 두 번 눌리면 또 나간다"
    assert state.get("collect_method") == RETURN_COLLECT_METHOD


def test_second_press_does_not_call_naver_again(app):
    """두 번 눌러도 네이버는 **한 번만** — 불가역 경로의 멱등."""
    client = _Client()
    lid = _link("PO-RET-C1", order_no="N-RET-C", dispatched=True, returned=True)
    out = request_return(db_session, client, link_id=lid, reason="COLOR_AND_SIZE")
    assert out["returned"] == []
    assert client.calls == [], "이미 접수한 집에 두 번째 호출이 나갔다"


def test_claim_in_flight_blocks_return(app):
    """이미 클레임이 도는 집에는 반품을 또 걸지 않는다."""
    client = _Client()
    lid = _link("PO-RET-D1", order_no="N-RET-D", dispatched=True, claim="RETURN_REQUESTED")
    with pytest.raises(FulfillmentError):
        request_return(db_session, client, link_id=lid, reason="COLOR_AND_SIZE")
    assert client.calls == []


def test_failure_leaves_a_reason_and_raises(app):
    """실패는 조용히 넘어가지 않는다 — 사유를 남기고 올린다."""
    client = _Client(fail={"PO-RET-E1": "상품 주문 상태 확인 필요"})
    lid = _link("PO-RET-E1", order_no="N-RET-E", dispatched=True)
    with pytest.raises(FulfillmentError) as err:
        request_return(db_session, client, link_id=lid, reason="COLOR_AND_SIZE")
    assert "상품 주문 상태 확인 필요" in str(err.value)
    db_session.expire_all()
    state = (db_session.get(ExternalOrderLink, lid).triage_state or {}).get("fulfillment") or {}
    assert state.get("last_error"), "실패 사유가 화면에 남지 않는다"


def test_partially_dispatched_household_only_returns_dispatched_rows(app):
    """**부분 발송 집**에서 미발송 상품주문에 반품이 나가면 안 된다 (2026-08-27 CEO).

    집 단위 가드(`집 안에 하나라도 발송분이 있으면 통과`)만으로는 부족하다.
    실무에서 분할발송은 흔하고, 안 나간 물건에 반품을 접수하면 구매자에게
    **없는 배송이 되돌아오는 것**으로 보인다. 되돌릴 수 없다.
    """
    from foms.services.integrations.naver_commerce.mapping import group_key_text

    client = _Client()
    order_no = "N-RET-MIX"
    snapshot = {"order": {"orderId": order_no},
                "productOrder": {"productOrderId": "PO-MIX-1"}}
    gk = group_key_text(snapshot)
    ids = []
    for pid, dispatched in (("PO-MIX-1", True), ("PO-MIX-2", False)):
        snap = {"order": {"orderId": order_no}, "productOrder": {"productOrderId": pid}}
        link = ExternalOrderLink(
            channel="NAVER", external_id=pid, external_order_no=order_no,
            sync_status="LINKED", place_order_status="OK",
            raw_snapshot=snap, group_key=gk,
            triage_state=({"fulfillment": {"dispatched_at": "2026-08-27T00:00:00"}}
                          if dispatched else None),
        )
        db_session.add(link)
        ids.append(link)
    db_session.commit()

    request_return(db_session, client, link_id=int(ids[0].id), reason="COLOR_AND_SIZE")
    db_session.commit()
    sent = [c["pid"] for c in client.calls]
    assert sent == ["PO-MIX-1"], f"미발송 건에 반품이 나갔다: {sent}"
