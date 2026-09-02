# -*- coding: utf-8 -*-
"""NVCLAIM-ORDER-01 — 추가구성상품이 붙은 집의 **호출 순서** 계약.

네이버는 한 집(묶음) 안 상품주문의 호출 순서를 작업 종류별로 **반대로** 요구한다.
정본은 커머스API 공식 FAQ(author ``commerce-api-naver``):
https://github.com/commerce-api-naver/commerce-api/discussions/1321

    발송 처리(취소 철회)는 "본상품 → 추가구성상품" 순서로,
    클레임 요청/승인은 "추가구성상품 → 본상품" 순서로 호출해야 합니다.

2026-09-02 운영 사고가 이 계약이 없어서 났다 — 반품 4건 중 추가상품 3건만 환불되고
본품이 ``추가상품 반품진행 후, 본 상품 반품진행을 할 수 있습니다.`` 로 실패했는데
시스템은 **성공으로 끝났다**. 오류 문자열은 문서에 없고 실패 코드는 사유 불문 ``9999``
로만 오므로(#1457) 메시지 파싱이 아니라 **순서로 예방**하는 것이 유일하게 견고하다.

픽스처 규율 두 가지 — 없으면 이 파일은 동어반복이 된다:

* 발송 방향 테스트는 **추가상품 id 를 본품보다 작게** 만든다. 오늘 순서가 맞는 건
  ``_links_of_group`` 의 ``ORDER BY id ASC`` 가 수집 순서와 우연히 일치해서일 뿐이라,
  본품 id 가 작은 픽스처는 정렬이 없어도 통과한다.
* 다중 본품 집을 반드시 하나 둔다. 본품 1개 집만 쓰면 평면 정렬과 본품군별 인터리브가
  같은 답을 내서 회귀를 못 막는다.
"""
from __future__ import annotations

import pytest

from db import db_session
from models import ExternalOrderLink
from foms.services.integrations.naver_commerce.constants import ADDON_PRODUCT_CLASS
from foms.services.integrations.naver_commerce.fulfillment import (
    FulfillmentError,
    dispatch_order,
    request_return,
)


MAIN_PRODUCT_CLASS = "조합형옵션상품"


class _ReturnClient:
    """반품 접수 호출 **순서**를 기록하는 가짜 클라이언트."""

    def __init__(self, *, fail: dict | None = None):
        self.calls: list[str] = []
        self._fail = fail or {}

    def request_return_product_order(self, product_order_id, *, reason,
                                     collect_method, detail=None, quantity=None):
        self.calls.append(str(product_order_id))
        if product_order_id in self._fail:
            return {"data": {"successProductOrderIds": [],
                             "failProductOrderInfos": [
                                 {"productOrderId": product_order_id,
                                  "code": "9999",
                                  "message": self._fail[product_order_id]}]}}
        return {"data": {"successProductOrderIds": [product_order_id],
                         "failProductOrderInfos": []}}


class _DispatchClient:
    """발송처리 payload 의 **배열 순서**를 기록하는 가짜 클라이언트."""

    def __init__(self):
        self.order: list[str] = []

    def dispatch_product_orders(self, dispatches):
        self.order = [str(d["productOrderId"]) for d in dispatches]
        return {"data": {"successProductOrderIds": list(self.order),
                         "failProductOrderInfos": []}}


def _link(external_id: str, *, order_no: str, addon: bool,
          dispatched: bool = False, returned: bool = False,
          claim: str = "", claim_type: str = "") -> int:
    """상품주문 1건을 만든다. ``addon`` 이 ``productClass`` 를 가른다(판별 정본)."""
    from foms.services.integrations.naver_commerce.mapping import group_key_text

    product_order = {
        "productOrderId": external_id,
        "productClass": ADDON_PRODUCT_CLASS if addon else MAIN_PRODUCT_CLASS,
    }
    if claim:
        product_order["claimStatus"] = claim
    if claim_type:
        product_order["claimType"] = claim_type
    snapshot = {"order": {"orderId": order_no}, "productOrder": product_order}
    state: dict = {}
    if dispatched:
        state["fulfillment"] = {"dispatched_at": "2026-08-31T00:00:00"}
    if returned:
        state["return"] = {"requested_at": "2026-09-01T00:00:00"}
    link = ExternalOrderLink(
        channel="NAVER", external_id=external_id, external_order_no=order_no,
        sync_status="LINKED", place_order_status="OK",
        raw_snapshot=snapshot, group_key=group_key_text(snapshot),
        triage_state=state or None,
    )
    db_session.add(link)
    db_session.commit()
    return int(link.id)


# --------------------------------------------------- 클레임 = 추가상품 먼저


def test_return_calls_addons_before_the_main_product(app):
    """사고 재현 픽스처 — **본품이 먼저 삽입된 집**에서 반품이 추가상품부터 나가야 한다.

    운영 사고의 집(ERP 5026)이 정확히 이 모양이었다: 본품 link id 117 이 가장 작고
    추가상품 3건이 118~120. ``id.asc`` 를 그대로 쓰면 본품이 1번으로 나가고 네이버가
    거절한다.
    """
    order_no = "N-ORD-MIXED"
    main = _link("PO-MAIN", order_no=order_no, addon=False, dispatched=True)
    for pid in ("PO-ADD-1", "PO-ADD-2", "PO-ADD-3"):
        _link(pid, order_no=order_no, addon=True, dispatched=True)

    client = _ReturnClient()
    request_return(db_session, client, link_id=main, reason="COLOR_AND_SIZE")
    db_session.commit()

    assert client.calls[-1] == "PO-MAIN", (
        f"본품이 마지막이 아니다 — 네이버가 거절한다: {client.calls}")
    assert set(client.calls[:-1]) == {"PO-ADD-1", "PO-ADD-2", "PO-ADD-3"}


def test_return_order_holds_for_a_household_with_two_main_products(app):
    """**다중 본품 집** — 모든 본품이 자기 추가상품보다 뒤에 있어야 한다.

    평면 정렬 ``[추가상품 전부, 본품 전부]`` 는 임의의 본품 M 에 대해 그 추가상품이
    전부 접두부에 있으므로 per-main 선행조건의 상위집합이다. 본품군별 인터리브는
    불가역 호출 순서를 ``attribution.py`` 의 추정 휴리스틱에 묶으므로 채택하지 않는다.
    """
    order_no = "N-ORD-TWOMAIN"
    first = _link("PO-M1", order_no=order_no, addon=False, dispatched=True)
    _link("PO-M1-A1", order_no=order_no, addon=True, dispatched=True)
    _link("PO-M2", order_no=order_no, addon=False, dispatched=True)
    _link("PO-M2-A1", order_no=order_no, addon=True, dispatched=True)

    client = _ReturnClient()
    request_return(db_session, client, link_id=first, reason="COLOR_AND_SIZE")
    db_session.commit()

    pos = {pid: i for i, pid in enumerate(client.calls)}
    assert pos["PO-M1-A1"] < pos["PO-M1"], f"M1 이 자기 옵션보다 먼저다: {client.calls}"
    assert pos["PO-M2-A1"] < pos["PO-M2"], f"M2 이 자기 옵션보다 먼저다: {client.calls}"


# --------------------------------------------------- 발송 = 본품 먼저


def test_dispatch_calls_the_main_product_before_addons(app):
    """발송처리는 **반대 방향**이다 — 추가상품 id 가 더 작아도 본품이 먼저 나가야 한다.

    이 픽스처가 이 파일의 핵심이다. 추가상품을 먼저 삽입해 ``id.asc`` 가 추가상품을
    앞세우게 만든다 — 정렬이 코드로 강제돼 있지 않으면 여기서 빨강이 난다.
    """
    order_no = "N-ORD-DISPATCH"
    addon = _link("PO-D-ADDON", order_no=order_no, addon=True)
    main = _link("PO-D-MAIN", order_no=order_no, addon=False)
    assert addon < main, "픽스처 전제가 깨졌다 — 추가상품 id 가 더 작아야 한다"

    client = _DispatchClient()
    dispatch_order(db_session, client, link_id=addon)
    db_session.commit()

    assert client.order[0] == "PO-D-MAIN", (
        f"본품이 첫 번째가 아니다 — 발송 방향 위반: {client.order}")


# --------------------------------------------------- 부분 실패는 실패다


def test_partial_failure_raises_and_keeps_both_records(app):
    """성공 3 + 실패 1 → **예외가 오르고**, 성공 표식과 실패 사유가 둘 다 남는다.

    ``tasks.py`` 의 ``except FulfillmentError`` 는 rollback 하지 않고 commit 한 뒤
    다시 올린다 — 그래서 예외를 올려도 기록이 사라지지 않는다. RQ 에 재시도 설정이
    없으므로(``queue.py`` 에 ``Retry(`` 0건) 불가역 호출이 자동 재전송되지도 않는다.
    """
    order_no = "N-ORD-PARTIAL"
    main = _link("PO-P-MAIN", order_no=order_no, addon=False, dispatched=True)
    for pid in ("PO-P-A1", "PO-P-A2", "PO-P-A3"):
        _link(pid, order_no=order_no, addon=True, dispatched=True)

    reason_text = "추가상품 반품진행 후, 본 상품 반품진행을 할 수 있습니다."
    client = _ReturnClient(fail={"PO-P-MAIN": reason_text})
    with pytest.raises(FulfillmentError):
        request_return(db_session, client, link_id=main, reason="COLOR_AND_SIZE")
    db_session.commit()
    db_session.expire_all()

    failed = (db_session.get(ExternalOrderLink, main).triage_state or {})
    assert (failed.get("fulfillment") or {}).get("last_error"), "실패 사유가 안 남았다"
    ok_row = db_session.query(ExternalOrderLink).filter_by(external_id="PO-P-A1").first()
    assert ((ok_row.triage_state or {}).get("return") or {}).get("requested_at"), (
        "성공한 형제의 표식까지 사라졌다 — 다시 누르면 또 나간다")


# --------------------------------------------------- 가드 스코프


def test_remaining_main_can_still_be_sent_after_siblings_returned(app):
    """**사고 복구 경로** — 형제가 반품 완료여도 남은 본품은 접수할 수 있어야 한다.

    운영 사고의 집이 지금 이 상태다. 집 단위 all-or-nothing 가드가 부분 성공한 집을
    스스로 잠가, 담당자에게 판매자센터 수작업 말고는 길이 없었다. 네이버 쪽 선행조건은
    이미 충족돼 있다(추가상품 3건이 ``RETURN_DONE``).
    """
    order_no = "N-ORD-RECOVER"
    main = _link("PO-R-MAIN", order_no=order_no, addon=False, dispatched=True)
    for pid in ("PO-R-A1", "PO-R-A2"):
        _link(pid, order_no=order_no, addon=True, dispatched=True, returned=True,
              claim="RETURN_DONE", claim_type="RETURN")

    client = _ReturnClient()
    out = request_return(db_session, client, link_id=main, reason="COLOR_AND_SIZE")
    db_session.commit()

    assert client.calls == ["PO-R-MAIN"], (
        f"남은 본품만 나가야 한다(이미 반품된 형제는 제외): {client.calls}")
    assert out["returned"] == ["PO-R-MAIN"]


def test_a_blocked_sibling_does_not_stop_the_clean_line(app):
    """형제 한 건에 **고객 클레임**이 걸려도 멀쩡한 라인은 나간다 — 대신 시끄럽게.

    RC3 를 한 단계 아래에서 되살리지 않는 자리다. 라인 가드를 도입해 놓고 "대상 중 한
    건이 막혔으니 집 전체를 거절" 하면 담당자는 같은 막다른 길에 다시 서고, 화면은
    :func:`return_sendable` 로 버튼을 열어 뒀으니 **모순까지 난다.**

    조용히 빼지는 않는다: 뺀 라인에 사유를 남기고 ``FulfillmentError`` 를 올린다.
    빈 대상을 ``{"returned": []}`` 성공으로 돌려주는 것이 이번 사고의 결함 그 자체다.
    """
    order_no = "N-ORD-BLOCKEDSIB"
    clean = _link("PO-B-CLEAN", order_no=order_no, addon=False, dispatched=True)
    _link("PO-B-CLAIMED", order_no=order_no, addon=True, dispatched=True,
          claim="RETURN_REQUEST", claim_type="RETURN")

    client = _ReturnClient()
    with pytest.raises(FulfillmentError):
        request_return(db_session, client, link_id=clean, reason="COLOR_AND_SIZE")
    db_session.commit()
    db_session.expire_all()

    assert client.calls == ["PO-B-CLEAN"], (
        f"막힌 형제 때문에 멀쩡한 라인까지 안 나갔다: {client.calls}")
    blocked_row = (db_session.query(ExternalOrderLink)
                   .filter_by(external_id="PO-B-CLAIMED").first())
    state = (blocked_row.triage_state or {}).get("fulfillment") or {}
    assert state.get("last_error"), "왜 안 나갔는지가 화면에 안 남았다"


def test_exchange_in_flight_still_blocks_the_whole_household(app):
    """진행 중 **교환**은 라인 스코프의 예외 — 집 전체를 계속 막는다.

    분할발송 집에서 미발송 본품이 교환 중이고 그 추가상품만 발송된 경우, 라인 스코프만
    보면 추가상품에 불가역 반품 접수가 나간다. ``_claim_guard`` docstring 이 R-4
    (2026-08-28)로 못 박은 회귀라 예외 1종으로 남긴다.
    """
    order_no = "N-ORD-EXCHANGE"
    _link("PO-X-MAIN", order_no=order_no, addon=False, dispatched=False,
          claim="EXCHANGE_REQUEST", claim_type="EXCHANGE")
    addon = _link("PO-X-ADDON", order_no=order_no, addon=True, dispatched=True)

    client = _ReturnClient()
    with pytest.raises(FulfillmentError):
        request_return(db_session, client, link_id=addon, reason="COLOR_AND_SIZE")
    assert client.calls == [], "교환이 도는 집에 불가역 반품 접수가 나갔다"


# --------------------------------------------------- T3 실패 라인의 반품 축 기록


def test_a_failed_return_line_gets_its_own_record(app):
    """실패한 라인에도 **반품 축 기록**이 남는다 (NVCLAIM-ORDER-01 T3).

    이 기록이 없던 것이 RC5 였다: 성공분만 ``return`` 축을 받아서 실패한 라인은 축이
    비어 **"아직 안 보냄"과 구분되지 않았고**, 실패 띠를 ``확인함`` 으로 닫는 순간
    유일한 흔적이던 ``last_error`` 마저 사라졌다(황민철 집, ERP 5026).

    ``requested_at`` 은 안 생겨야 한다 — 실패는 접수가 아니고,
    :func:`is_return_pending` 이 그 키로 멱등을 판정한다. 실패한 라인은 **다시 보낼
    대상으로 남아야** 한다.
    """
    from foms.services.integrations.naver_commerce.fulfillment import (
        is_return_pending, return_failure,
    )

    order_no = "N-ORD-T3"
    main = _link("PO-T3-MAIN", order_no=order_no, addon=False, dispatched=True)
    _link("PO-T3-A1", order_no=order_no, addon=True, dispatched=True)

    reason_text = "추가상품 반품진행 후, 본 상품 반품진행을 할 수 있습니다."
    client = _ReturnClient(fail={"PO-T3-MAIN": reason_text})
    with pytest.raises(FulfillmentError):
        request_return(db_session, client, link_id=main, reason="COLOR_AND_SIZE")
    db_session.commit()
    db_session.expire_all()

    row = db_session.get(ExternalOrderLink, main)
    axis = (row.triage_state or {}).get("return") or {}
    assert axis.get("failed_at"), "실패 라인에 반품 축 기록이 없다 — 띠를 닫으면 흔적이 사라진다"
    assert reason_text in axis.get("failed_reason", "")
    assert not axis.get("requested_at"), "실패를 접수로 기록하면 다시 보낼 수 없게 된다"
    assert is_return_pending(row), "실패한 라인은 다시 보낼 대상으로 남아야 한다"
    assert return_failure(row)["failed_reason"], "공통 술어가 기록을 못 읽는다"


def test_the_failure_record_survives_clearing_the_banner(app):
    """``확인함`` 은 통지를 닫을 뿐 **사실을 지우지 않는다** — 잠금을 걷은 근거.

    ``clear_failure`` 는 ``fulfillment.last_error`` 축만 만진다. 반품 축의
    ``failed_at``/``failed_reason`` 이 남아야 담당자가 띠를 닫은 뒤에도 상품주문 표에서
    "이 본품은 접수가 실패한 채다"를 읽는다.
    """
    from foms.services.integrations.naver_commerce.fulfillment import (
        clear_failure, return_failure,
    )

    order_no = "N-ORD-T3CLEAR"
    main = _link("PO-T3C-MAIN", order_no=order_no, addon=False, dispatched=True)
    _link("PO-T3C-A1", order_no=order_no, addon=True, dispatched=True)

    client = _ReturnClient(fail={"PO-T3C-MAIN": "네이버가 거절했습니다"})
    with pytest.raises(FulfillmentError):
        request_return(db_session, client, link_id=main, reason="COLOR_AND_SIZE")
    db_session.commit()

    clear_failure(db_session, link_id=main)
    db_session.commit()
    db_session.expire_all()

    row = db_session.get(ExternalOrderLink, main)
    state = (row.triage_state or {}).get("fulfillment") or {}
    assert not state.get("last_error"), "띠가 안 닫혔다"
    assert return_failure(row)["failed_at"], "띠를 닫자 실패 사실까지 사라졌다 — RC5 재발"


def test_a_later_success_clears_the_failure_record(app):
    """다시 보내 성공하면 실패 기록을 지운다 — 안 지우면 영원히 '접수 실패'로 읽힌다."""
    from foms.services.integrations.naver_commerce.fulfillment import return_failure

    order_no = "N-ORD-T3RETRY"
    main = _link("PO-T3R-MAIN", order_no=order_no, addon=False, dispatched=True)

    with pytest.raises(FulfillmentError):
        request_return(db_session, _ReturnClient(fail={"PO-T3R-MAIN": "일시 오류"}),
                       link_id=main, reason="COLOR_AND_SIZE")
    db_session.commit()

    request_return(db_session, _ReturnClient(), link_id=main, reason="COLOR_AND_SIZE")
    db_session.commit()
    db_session.expire_all()

    row = db_session.get(ExternalOrderLink, main)
    assert not return_failure(row)["failed_at"], "접수됐는데 화면이 계속 실패라고 말한다"
    assert ((row.triage_state or {}).get("return") or {}).get("requested_at")
