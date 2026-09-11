# -*- coding: utf-8 -*-
"""NVCLAIM-PARTIAL-01 — 부분 취소 뒤 남은 라인의 발주확인·발송(결정 5).

부분 취소 표식(``cancel_scope="partial"``)은 집을 잠그지 않고 **그 라인만** 대상에서 뺀다 —
household 표식이나 취소 실패가 남은 집은 그대로 잠긴다. 벌크 발송 pre-check
(``bulk_dispatch._blocking_reason``)가 같은 판정을 거울처럼 다시 하는지도 여기서 본다
(스펙 §11 결정 9).

서비스 계약(``plan_claim_scope``·``cancel_order``·``request_return``)은
``test_naver_partial_claim``, 큐·워커·라우트는 ``test_naver_partial_claim_routes``,
화면은 ``test_naver_partial_claim_ui`` 가 본다.
픽스처·헬퍼는 ``naver_partial_claim_helpers`` 한 벌을 공유한다.
"""
from __future__ import annotations

import copy

import pytest
from sqlalchemy.orm.attributes import flag_modified

from db import db_session
from models import ExternalOrderLink

from tests.services.integrations.naver_partial_claim_helpers import (
    _StubClient,
    _link,
    _links,
)

# --------------------------------------------------------------------------- #
# 결정 5 — 부분 취소 뒤 남은 라인의 발주확인·발송
# --------------------------------------------------------------------------- #

def test_partial_cancel_leaves_the_rest_dispatchable(app):
    """부분 취소 표식(``cancel_scope="partial"``)은 집을 잠그지 않고 **그 라인만 대상에서 뺀다**.

    발송처리(M+A1 집, A1 취소 → M 만 발송)와 발주확인(M2+A4 집, A4 취소 → M2 만 발주확인)
    둘 다 — ``_cancel_guard`` 가 제외 목록을 돌려주는 계약 §1.
    """
    from foms.services.integrations.naver_commerce.fulfillment import (
        cancel_order, confirm_place_order, dispatch_order,
    )

    main = _link("PO-PC-D5-M", order_no="N-PC-D5", addon=False)
    _link("PO-PC-D5-A1", order_no="N-PC-D5", addon=True)
    main2 = _link("PO-PC-D5C-M", order_no="N-PC-D5C", addon=False, place="NOT_YET")
    _link("PO-PC-D5C-A4", order_no="N-PC-D5C", addon=True, place="NOT_YET")
    client = _StubClient()

    cancel_order(db_session, client, link_id=main, reason="INTENT_CHANGED",
                 product_order_ids=["PO-PC-D5-A1"])
    db_session.commit()
    dispatched = dispatch_order(db_session, client, link_id=main)
    db_session.commit()

    assert dispatched["dispatched"] == ["PO-PC-D5-M"]
    assert [str(r["productOrderId"]) for r in client.dispatch_calls[-1]] == ["PO-PC-D5-M"]

    cancel_order(db_session, client, link_id=main2, reason="INTENT_CHANGED",
                 product_order_ids=["PO-PC-D5C-A4"])
    db_session.commit()
    confirmed = confirm_place_order(db_session, client, link_id=main2)
    db_session.commit()

    assert confirmed["confirmed"] == ["PO-PC-D5C-M"]
    assert client.confirm_calls[-1] == ["PO-PC-D5C-M"]


def test_partial_cancel_survives_the_next_refresh(app):
    """다음 수집이 A1 스냅샷을 ``CANCEL_DONE`` 으로 바꿔도 남은 본품 발송은 열려 있다.

    집 단위 ``_claim_guard`` 가 partial 표식 라인을 판정에서 빼 주지 않으면, 우리가 낸
    부분 취소가 재수집 뒤 형제 클레임으로 읽혀 집 전체를 다시 잠근다(결정 5 의 두 번째 절반).
    """
    from foms.services.integrations.naver_commerce.fulfillment import (
        cancel_order, dispatch_order,
    )

    main = _link("PO-PC-RF-M", order_no="N-PC-RF", addon=False)
    a1 = _link("PO-PC-RF-A1", order_no="N-PC-RF", addon=True)
    client = _StubClient()
    cancel_order(db_session, client, link_id=main, reason="INTENT_CHANGED",
                 product_order_ids=["PO-PC-RF-A1"])
    db_session.commit()

    row = db_session.get(ExternalOrderLink, a1)
    snapshot = copy.deepcopy(row.raw_snapshot)
    snapshot["productOrder"]["claimStatus"] = "CANCEL_DONE"
    snapshot["productOrder"]["claimType"] = "CANCEL"
    row.raw_snapshot = snapshot
    flag_modified(row, "raw_snapshot")
    db_session.commit()

    dispatched = dispatch_order(db_session, client, link_id=main)
    db_session.commit()

    assert dispatched["dispatched"] == ["PO-PC-RF-M"]
    assert [str(r["productOrderId"]) for r in client.dispatch_calls[-1]] == ["PO-PC-RF-M"]


def test_household_cancel_still_blocks_dispatch(app):
    """★ 음성 대조군(test_naver_cancel.py:325 거울) — 집 전체 취소 뒤 발송처리는 여전히 거절.

    결정 5 는 partial 표식만 연다. household(또는 옛 키 없는) 표식은 오늘처럼 집을 잠근다.
    """
    from foms.services.integrations.naver_commerce.fulfillment import (
        FulfillmentError, cancel_order, dispatch_order,
    )

    main = _link("PO-PC-HB-M", order_no="N-PC-HB", addon=False)
    _link("PO-PC-HB-A1", order_no="N-PC-HB", addon=True)
    client = _StubClient()
    cancel_order(db_session, client, link_id=main, reason="INTENT_CHANGED")
    db_session.commit()

    with pytest.raises(FulfillmentError):
        dispatch_order(db_session, client, link_id=main)
    assert client.dispatch_calls == []


def test_a_failed_cancel_line_still_blocks_dispatch(app):
    """취소 **실패**가 남은 라인(``last_error_action == "cancel"``)이 있으면 집 전체 차단(결정 5 단서)."""
    from foms.services.integrations.naver_commerce.fulfillment import (
        FulfillmentError, cancel_order, dispatch_order,
    )

    main = _link("PO-PC-FL-M", order_no="N-PC-FL", addon=False)
    _link("PO-PC-FL-A1", order_no="N-PC-FL", addon=True)
    client = _StubClient(fail_ids={"PO-PC-FL-A1"})

    with pytest.raises(FulfillmentError):
        cancel_order(db_session, client, link_id=main, reason="INTENT_CHANGED",
                     product_order_ids=["PO-PC-FL-A1"])
    db_session.commit()

    with pytest.raises(FulfillmentError) as err:
        dispatch_order(db_session, client, link_id=main)
    assert "취소" in str(err.value)
    assert client.dispatch_calls == []


# --------------------------------------------------------------------------- #
# 벌크 발송 pre-check — `_cancel_guard` 거울 (결정 5, 스펙 §11 결정 9)
# --------------------------------------------------------------------------- #

def test_bulk_blocking_reason_mirrors_the_cancel_guard(app):
    """``bulk_dispatch._blocking_reason`` 은 순수 함수다 — 네이버 0회, ``_StubClient`` 조차 없다.

    partial 표식 + 재수집 ``CANCEL_DONE`` 형제 집은 ``""``(보낼 수 있다), household 표식 집은
    '취소한 주문입니다', 취소 실패가 남은(``last_error_action == "cancel"``) 집은
    '취소가 실패한 상품주문이 있습니다' — ``fulfillment._cancel_guard`` 와 같은 갈래·순서.
    """
    from foms.services.integrations.naver_commerce.bulk_dispatch import _blocking_reason

    open_main = _link("PO-PC-BK-M", order_no="N-PC-BK", addon=False)
    _link("PO-PC-BK-A1", order_no="N-PC-BK", addon=True, canceled=True,
          cancel_scope="partial", claim="CANCEL_DONE", claim_type="CANCEL")
    lock_main = _link("PO-PC-BKH-M", order_no="N-PC-BKH", addon=False)
    _link("PO-PC-BKH-A1", order_no="N-PC-BKH", addon=True, canceled=True,
          cancel_scope="household")
    fail_main = _link("PO-PC-BKF-M", order_no="N-PC-BKF", addon=False)
    fail_a1 = _link("PO-PC-BKF-A1", order_no="N-PC-BKF", addon=True)
    row = db_session.get(ExternalOrderLink, fail_a1)
    row.triage_state = {"fulfillment": {"last_error": "상품 주문 상태 확인 필요",
                                        "last_error_action": "cancel"}}
    flag_modified(row, "triage_state")
    db_session.commit()

    assert _blocking_reason(_links(open_main)) == ""
    assert _blocking_reason(_links(lock_main)).startswith("취소한 주문입니다")
    assert "1건" in _blocking_reason(_links(lock_main))
    assert _blocking_reason(_links(fail_main)).startswith("취소가 실패한 상품주문이 있습니다")
