# -*- coding: utf-8 -*-
"""NVCLAIM-PARTIAL-01 — 취소·반품을 **상품주문 일부만 골라** 보내는 계약(서비스 층).

스펙 ``docs/specs/2026-09-11-naver-partial-claim_SPEC.md``, 계약 §0~§6(CEO 확정 2026-09-11).
기준 사례는 운영 #2354(브리프 §2-1): 본품 1 + 추가구성 7, 그중 4건은 판매자센터에서 이미
``CANCEL_DONE``. 사용자는 남은 라인 일부만 골라 취소·반품하고 싶다.

이 파일은 서비스 층(``plan_claim_scope``·``cancel_order``·``request_return``)만 본다. 나머지
층은 형제 파일이 같은 규율로 잠근다 — 부분 취소 뒤 발주확인·발송과 벌크 pre-check 는
``test_naver_partial_claim_dispatch``, 큐·워커·라우트·미리보기(``claim-plan``)·감사는
``test_naver_partial_claim_routes``, 화면(pane)은 ``test_naver_partial_claim_ui``.
픽스처·헬퍼는 ``naver_partial_claim_helpers`` 한 벌을 공유한다.

**네이버 클레임은 불가역이다.** 어떤 테스트도 실제 ``NaverCommerceClient`` 로 네트워크를
타지 않는다: 서비스는 :class:`_StubClient`, 라우트는 ``enqueue_*`` monkeypatch, claim-plan 은
클라이언트 생성 자체를 raise 로 막아 0회를 증명한다.

``product_order_ids`` 의 뜻 3종(계약 §0)이 전 계층에서 같다:

* **None(키 부재)** = 집 전체(오늘 동작 그대로 — ★ 음성 대조군이 지킨다)
* **[]** = 거절(라우트 400, 서비스 ``FulfillmentError``, 네이버 0회)
* **[id…]** = 그 라인만 + 서버가 붙이는 자동 동반(본품을 고르면 남은 추가구성상품)

새 이름(``plan_claim_scope``·``cancel_sendable``·``CANCEL_SCOPE_*`` 등)은 **각 테스트 안에서
지역 import** 한다 — 구현이 아직 없어도 ``--collect-only`` 가 통과해야 워커 A·B·C 와 나란히
쓸 수 있다. ★ 표시 테스트는 구현 전에도 green 이어야 하는 음성 대조군이다.
"""
from __future__ import annotations

import pytest

from db import db_session

from tests.services.integrations.naver_partial_claim_helpers import (
    _StubClient,
    _ext,
    _household_2354,
    _link,
    _links,
    _pids,
    _state,
)

# --------------------------------------------------------------------------- #
# 서비스 — 취소 (계약 §1)
# --------------------------------------------------------------------------- #

def test_cancel_subset_calls_only_the_chosen_rows_in_claim_order(app):
    """고른 라인만 나간다 — 본품을 고르면 남은 추가구성상품이 **자동 동반**되고 순서는 추가구성 먼저.

    M+A1+A2 집에서 [M, A1] 을 고르면 A2 가 자동으로 붙어(결정 3) ``[A1, A2, M]`` 순으로
    나가고, 세 라인 모두 ``cancel_scope == "partial"`` 표식을 받는다(결정 5).
    """
    from foms.services.integrations.naver_commerce.fulfillment import (
        CANCEL_SCOPE_PARTIAL, cancel_order,
    )

    order_no = "N-PC-SUB"
    main = _link("PO-PC-SUB-M", order_no=order_no, addon=False)
    a1 = _link("PO-PC-SUB-A1", order_no=order_no, addon=True)
    a2 = _link("PO-PC-SUB-A2", order_no=order_no, addon=True)
    client = _StubClient()

    result = cancel_order(db_session, client, link_id=main, reason="INTENT_CHANGED",
                          product_order_ids=["PO-PC-SUB-M", "PO-PC-SUB-A1"])
    db_session.commit()

    assert _pids(client) == ["PO-PC-SUB-A1", "PO-PC-SUB-A2", "PO-PC-SUB-M"]
    assert result["auto_added"] == ["PO-PC-SUB-A2"]
    assert result["scope"] == "partial"
    for lid in (main, a1, a2):
        assert _state(lid)["canceled_at"]
        assert _state(lid)["cancel_scope"] == CANCEL_SCOPE_PARTIAL == "partial"


def test_cancel_without_the_key_covers_the_household(app):
    """★ 음성 대조군 — **키 부재**(``product_order_ids`` 를 안 넘김)는 오늘처럼 집 전체다.

    test_naver_cancel.py:83 과 같은 기대. 구현 전에도 통과해야 하고, 구현 뒤에도 그대로여야
    한다(옛 탭·옛 JS 의 하위호환 경로). ``scope`` 키 단언은 별도 테스트에 둔다.
    """
    from foms.services.integrations.naver_commerce.fulfillment import cancel_order

    order_no = "N-PC-HH"
    main = _link("PO-PC-HH-M", order_no=order_no, addon=False)
    _link("PO-PC-HH-A1", order_no=order_no, addon=True)
    client = _StubClient()

    result = cancel_order(db_session, client, link_id=main, reason="INTENT_CHANGED")
    db_session.commit()

    assert sorted(_pids(client)) == ["PO-PC-HH-A1", "PO-PC-HH-M"]
    assert sorted(result["canceled"]) == ["PO-PC-HH-A1", "PO-PC-HH-M"]


def test_household_cancel_marks_scope_household(app):
    """키 부재 취소의 성공 표식은 ``cancel_scope == "household"`` 다(계약 §5)."""
    from foms.services.integrations.naver_commerce.fulfillment import (
        CANCEL_SCOPE_HOUSEHOLD, cancel_order,
    )

    main = _link("PO-PC-HHS-M", order_no="N-PC-HHS", addon=False)
    a1 = _link("PO-PC-HHS-A1", order_no="N-PC-HHS", addon=True)

    result = cancel_order(db_session, _StubClient(), link_id=main, reason="INTENT_CHANGED")
    db_session.commit()

    assert result["scope"] == "household"
    for lid in (main, a1):
        assert _state(lid)["cancel_scope"] == CANCEL_SCOPE_HOUSEHOLD == "household"


def test_cancel_with_an_empty_list_is_refused_without_calls(app):
    """``[]`` 는 "전체" 가 아니라 **거절**이다(C2) — 호출 0회, 표식도 없다."""
    from foms.services.integrations.naver_commerce.fulfillment import (
        FulfillmentError, cancel_order,
    )

    main = _link("PO-PC-EMP-M", order_no="N-PC-EMP", addon=False)
    a1 = _link("PO-PC-EMP-A1", order_no="N-PC-EMP", addon=True)
    client = _StubClient()

    with pytest.raises(FulfillmentError) as err:
        cancel_order(db_session, client, link_id=main, reason="INTENT_CHANGED",
                     product_order_ids=[])
    db_session.commit()

    assert "대상 상품주문을 고르세요" in str(err.value)
    assert client.calls == []
    for lid in (main, a1):
        assert not _state(lid).get("last_error"), "빈 목록 거절이 라인에 실패를 남겼다"


def test_cancel_with_an_id_outside_the_household_is_refused(app):
    """집 밖 상품주문번호가 섞이면 한 건도 보내지 않고 그 id 를 말한다(C2)."""
    from foms.services.integrations.naver_commerce.fulfillment import (
        FulfillmentError, cancel_order,
    )

    main = _link("PO-PC-OUT-M", order_no="N-PC-OUT", addon=False)
    client = _StubClient()

    with pytest.raises(FulfillmentError) as err:
        cancel_order(db_session, client, link_id=main, reason="INTENT_CHANGED",
                     product_order_ids=["PO-NOPE"])

    assert "PO-NOPE" in str(err.value)
    assert client.calls == []


def test_main_only_selection_pulls_the_uncovered_addons_and_skips_covered_ones(app):
    """기준 사례 #2354 — 본품만 고르면 **남은** 추가구성 3건이 붙고, 이미 취소된 4건은 안 간다.

    ``addon_return_covered`` 가 CANCEL_DONE 형제를 충족으로 읽으므로 C1~C4 는 자동 동반
    대상이 아니고(보낼 수도 없다), A1~A3 만 붙어 ``[A1, A2, A3, M]`` 으로 나간다.
    """
    from foms.services.integrations.naver_commerce.fulfillment import cancel_order

    order_no = "N-PC-2354"
    ids = _household_2354(order_no)
    client = _StubClient()

    result = cancel_order(db_session, client, link_id=ids["M"], reason="INTENT_CHANGED",
                          product_order_ids=[_ext(order_no, "M")])
    db_session.commit()

    assert _pids(client) == [_ext(order_no, n) for n in ("A1", "A2", "A3", "M")]
    assert result["auto_added"] == [_ext(order_no, n) for n in ("A1", "A2", "A3")]
    for name in ("C1", "C2", "C3", "C4"):
        assert "canceled_at" not in _state(ids[name]), f"{name} 은 이미 취소된 건이다"


def test_cancel_scope_gap_sends_nothing_when_an_addon_cannot_go(app):
    """결정 4 — 취소 축에도 FAQ 3880 범위 규격. 함께 갈 추가구성상품이 못 가면 **0건 전송**.

    A1 은 이미 발송돼 취소를 보낼 수 없다(``cancel_sendable`` 거짓). 본품만 골라도 자동
    동반이 안 되니 gap 이고, 본품에 사유를 남기고 한 건도 보내지 않는다.
    """
    from foms.services.integrations.naver_commerce.fulfillment import (
        FulfillmentError, cancel_order,
    )

    order_no = "N-PC-GAP"
    main = _link("PO-PC-GAP-M", order_no=order_no, addon=False)
    _link("PO-PC-GAP-A1", order_no=order_no, addon=True, dispatched=True)
    client = _StubClient()

    with pytest.raises(FulfillmentError) as err:
        cancel_order(db_session, client, link_id=main, reason="INTENT_CHANGED",
                     product_order_ids=["PO-PC-GAP-M"])
    db_session.commit()

    assert "추가구성상품" in str(err.value)
    assert client.calls == [], "gap 인데 일부가 나갔다 — 2026-09-01 사고의 모양"
    assert _state(main)["last_error_action"] == "cancel"


def test_addon_only_cancel_is_not_blocked_by_the_scope_rule(app):
    """음성 대조군(test_naver_addon_claim_order.py:435 의 취소 축 거울) — 추가구성만 고르면 규격은 침묵한다."""
    from foms.services.integrations.naver_commerce.fulfillment import cancel_order

    order_no = "N-PC-ADDONLY"
    main = _link("PO-PC-AO-M", order_no=order_no, addon=False)
    _link("PO-PC-AO-A1", order_no=order_no, addon=True)
    client = _StubClient()

    result = cancel_order(db_session, client, link_id=main, reason="INTENT_CHANGED",
                          product_order_ids=["PO-PC-AO-A1"])
    db_session.commit()

    assert _pids(client) == ["PO-PC-AO-A1"]
    assert result["canceled"] == ["PO-PC-AO-A1"]
    assert "canceled_at" not in _state(main)


def test_addon_only_household_cancel_is_not_blocked_by_the_scope_rule(app):
    """★ 음성 대조군(키 부재 변형) — 추가구성상품만 있는 집의 집 전체 취소는 규격에 안 걸린다.

    구현 전에도 통과해야 한다: 취소 축에 범위 검사를 붙여도(결정 4) 대상에 본품이 없으면
    ``addon_return_gap`` 은 빈 목록이다.
    """
    from foms.services.integrations.naver_commerce.fulfillment import cancel_order

    a1 = _link("PO-PC-AOH-A1", order_no="N-PC-AOH", addon=True)
    client = _StubClient()

    result = cancel_order(db_session, client, link_id=a1, reason="INTENT_CHANGED")
    db_session.commit()

    assert _pids(client) == ["PO-PC-AOH-A1"]
    assert result["canceled"] == ["PO-PC-AOH-A1"]


def test_same_subset_twice_calls_naver_once(app):
    """C5 멱등 — 같은 부분집합을 두 번 보내면 두 번째는 조용히 빈다(예외 없음, 호출 0회)."""
    from foms.services.integrations.naver_commerce.fulfillment import cancel_order

    order_no = "N-PC-IDEM"
    main = _link("PO-PC-IDEM-M", order_no=order_no, addon=False)
    _link("PO-PC-IDEM-A1", order_no=order_no, addon=True)
    client = _StubClient()

    first = cancel_order(db_session, client, link_id=main, reason="INTENT_CHANGED",
                         product_order_ids=["PO-PC-IDEM-A1"])
    db_session.commit()
    second = cancel_order(db_session, client, link_id=main, reason="INTENT_CHANGED",
                          product_order_ids=["PO-PC-IDEM-A1"])
    db_session.commit()

    assert first["canceled"] == ["PO-PC-IDEM-A1"]
    assert second["canceled"] == []
    assert len(client.calls) == 1


def test_a_selected_row_that_is_not_sendable_sends_nothing(app):
    """C3/C4 — 고른 라인 중 보낼 수 없는 것이 있으면 조용히 빼지 않고 **0건 전송 + 그 라인 실패**.

    A1 에 고객 반품 요청이 걸려 있다. [A1, A2] 를 고르면 A2 만 보내는 것이 아니라 전부
    멈추고 A1 에만 사유를 남긴다 — 체크된 것과 나간 것이 다르면 재진술이 거짓이 된다.
    """
    from foms.services.integrations.naver_commerce.fulfillment import (
        FulfillmentError, cancel_order,
    )

    order_no = "N-PC-BLK"
    main = _link("PO-PC-BLK-M", order_no=order_no, addon=False)
    a1 = _link("PO-PC-BLK-A1", order_no=order_no, addon=True,
               claim="RETURN_REQUEST", claim_type="RETURN")
    a2 = _link("PO-PC-BLK-A2", order_no=order_no, addon=True)
    client = _StubClient()

    with pytest.raises(FulfillmentError):
        cancel_order(db_session, client, link_id=main, reason="INTENT_CHANGED",
                     product_order_ids=["PO-PC-BLK-A1", "PO-PC-BLK-A2"])
    db_session.commit()

    assert client.calls == []
    assert _state(a1)["last_error_action"] == "cancel"
    assert not _state(a2).get("last_error") and "canceled_at" not in _state(a2)


def test_cancel_never_passes_quantity(app):
    """결정 7 — 수량 일부 취소는 범위 밖. 집 전체·부분 어느 경로도 ``quantity`` 를 넘기지 않는다."""
    from foms.services.integrations.naver_commerce.fulfillment import cancel_order

    whole = _link("PO-PC-QW-M", order_no="N-PC-QW", addon=False)
    _link("PO-PC-QW-A1", order_no="N-PC-QW", addon=True)
    part = _link("PO-PC-QP-M", order_no="N-PC-QP", addon=False)
    _link("PO-PC-QP-A1", order_no="N-PC-QP", addon=True)
    client = _StubClient()

    cancel_order(db_session, client, link_id=whole, reason="INTENT_CHANGED")
    db_session.commit()
    cancel_order(db_session, client, link_id=part, reason="INTENT_CHANGED",
                 product_order_ids=["PO-PC-QP-A1"])
    db_session.commit()

    assert len(client.calls) == 3
    for call in client.calls:
        assert "quantity" not in call["kwargs"], call
        assert "cancelQuantity" not in call["kwargs"], call


def test_plan_restates_exactly_what_the_server_sends(app):
    """C1 — 미리보기(``plan_claim_scope``)의 ``todo`` 가 실제 호출 순서와 **한 글자도** 다르지 않다."""
    from foms.services.integrations.naver_commerce.fulfillment import (
        cancel_order, plan_claim_scope,
    )

    order_no = "N-PC-PLAN"
    ids = _household_2354(order_no)
    plan = plan_claim_scope(_links(ids["M"]), action="cancel",
                            product_order_ids=[_ext(order_no, "M")])
    assert plan["ok"] is True, plan["message"]

    client = _StubClient()
    cancel_order(db_session, client, link_id=ids["M"], reason="INTENT_CHANGED",
                 product_order_ids=[_ext(order_no, "M")])
    db_session.commit()

    assert plan["todo"] == _pids(client)
    assert plan["selected"] == [_ext(order_no, "M")]
    assert plan["auto_added"] == [_ext(order_no, n) for n in ("A1", "A2", "A3")]


# --------------------------------------------------------------------------- #
# 서비스 — 반품 (계약 §1, 반품 축)
# --------------------------------------------------------------------------- #

def test_return_subset_calls_only_the_chosen_rows(app):
    """반품도 같은 규율 — 고른 추가구성 1건만 나가고 사유·회수방법이 그대로 실린다."""
    from foms.services.integrations.naver_commerce.fulfillment import (
        RETURN_COLLECT_METHOD, request_return,
    )

    order_no = "N-PC-RSUB"
    main = _link("PO-PC-RSUB-M", order_no=order_no, addon=False, dispatched=True)
    _link("PO-PC-RSUB-A1", order_no=order_no, addon=True, dispatched=True)
    _link("PO-PC-RSUB-A2", order_no=order_no, addon=True, dispatched=True)
    client = _StubClient()

    result = request_return(db_session, client, link_id=main, reason="COLOR_AND_SIZE",
                            product_order_ids=["PO-PC-RSUB-A1"])
    db_session.commit()

    assert _pids(client) == ["PO-PC-RSUB-A1"]
    assert client.calls[0]["kwargs"]["reason"] == "COLOR_AND_SIZE"
    assert client.calls[0]["kwargs"]["collect_method"] == RETURN_COLLECT_METHOD
    assert "quantity" not in client.calls[0]["kwargs"]
    assert result["returned"] == ["PO-PC-RSUB-A1"]
    assert result["scope"] == "partial"


def test_return_main_only_pulls_the_uncovered_addons(app):
    """본품만 고른 반품 — 남은 추가구성상품이 자동 동반돼 ``[A1, A2, M]`` 으로 나간다."""
    from foms.services.integrations.naver_commerce.fulfillment import request_return

    order_no = "N-PC-RMAIN"
    main = _link("PO-PC-RMAIN-M", order_no=order_no, addon=False, dispatched=True)
    _link("PO-PC-RMAIN-A1", order_no=order_no, addon=True, dispatched=True)
    _link("PO-PC-RMAIN-A2", order_no=order_no, addon=True, dispatched=True)
    client = _StubClient()

    result = request_return(db_session, client, link_id=main, reason="COLOR_AND_SIZE",
                            product_order_ids=["PO-PC-RMAIN-M"])
    db_session.commit()

    assert _pids(client) == ["PO-PC-RMAIN-A1", "PO-PC-RMAIN-A2", "PO-PC-RMAIN-M"]
    assert result["auto_added"] == ["PO-PC-RMAIN-A1", "PO-PC-RMAIN-A2"]


def test_return_with_an_empty_list_is_refused(app):
    """반품 ``[]`` 도 거절 — 호출 0회."""
    from foms.services.integrations.naver_commerce.fulfillment import (
        FulfillmentError, request_return,
    )

    main = _link("PO-PC-REMP-M", order_no="N-PC-REMP", addon=False, dispatched=True)
    client = _StubClient()

    with pytest.raises(FulfillmentError) as err:
        request_return(db_session, client, link_id=main, reason="COLOR_AND_SIZE",
                       product_order_ids=[])
    assert "대상 상품주문을 고르세요" in str(err.value)
    assert client.calls == []


def test_return_with_an_unknown_id_is_refused(app):
    """반품에 집 밖 id — 호출 0회, 그 id 를 말한다."""
    from foms.services.integrations.naver_commerce.fulfillment import (
        FulfillmentError, request_return,
    )

    main = _link("PO-PC-RUNK-M", order_no="N-PC-RUNK", addon=False, dispatched=True)
    client = _StubClient()

    with pytest.raises(FulfillmentError) as err:
        request_return(db_session, client, link_id=main, reason="COLOR_AND_SIZE",
                       product_order_ids=["PO-NOPE-R"])
    assert "PO-NOPE-R" in str(err.value)
    assert client.calls == []


def test_return_without_the_key_is_unchanged(app):
    """★ 음성 대조군 — 키 부재 반품은 오늘과 같다: 발송된 2건 전부, 추가구성 먼저."""
    from foms.services.integrations.naver_commerce.fulfillment import request_return

    order_no = "N-PC-RHH"
    main = _link("PO-PC-RHH-M", order_no=order_no, addon=False, dispatched=True)
    _link("PO-PC-RHH-A1", order_no=order_no, addon=True, dispatched=True)
    client = _StubClient()

    result = request_return(db_session, client, link_id=main, reason="COLOR_AND_SIZE")
    db_session.commit()

    assert _pids(client) == ["PO-PC-RHH-A1", "PO-PC-RHH-M"]
    assert sorted(result["returned"]) == ["PO-PC-RHH-A1", "PO-PC-RHH-M"]
