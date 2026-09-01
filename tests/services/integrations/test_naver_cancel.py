"""판매자 직접취소 계약 (스텁 클라이언트) — 스펙 §3.4.

되돌릴 수 없고 정산에 바로 닿는 조작이라 계약이 다섯이다:
① 한 집은 통째로 ② 두 번 눌러도 네이버는 한 번만 ③ 이미 발송처리한 집은 못 건드린다
④ 사유 코드는 네이버가 아는 값만 ⑤ 실패는 사유를 남기고 조용히 넘어가지 않는다.

네이버 취소는 **상품주문 1건씩** 부른다(발주확인·발송처리와 달리 배치가 아니다).
"""

from __future__ import annotations

import pytest

from db import db_session
from foms.services.integrations.naver_commerce.fulfillment import (
    CANCEL_REASONS,
    FulfillmentError,
    cancel_order,
    dispatch_order,
)
from models import ExternalOrderLink


class _StubClient:
    """취소 호출만 기록하는 스텁. ``fail`` 로 건별 실패를 흉내낸다."""

    def __init__(self, *, fail_ids: set[str] | None = None) -> None:
        self.cancel_calls: list[dict] = []
        self.dispatch_calls: list[list[dict]] = []
        self.fail_ids = set(fail_ids or ())

    def request_cancel_product_order(self, product_order_id, *, reason,
                                     detail=None, quantity=None):
        pid = str(product_order_id)
        self.cancel_calls.append({"productOrderId": pid, "cancelReason": reason,
                                  "cancelDetailedReason": detail, "cancelQuantity": quantity})
        if pid in self.fail_ids:
            return {"data": {"failProductOrderInfos": [
                {"productOrderId": pid, "code": "104442", "message": "상품 주문 상태 확인 필요"}]}}
        return {"data": {"successProductOrderIds": [pid]}}

    def dispatch_product_orders(self, rows):
        self.dispatch_calls.append(list(rows))
        return {"data": {"successProductOrderIds": [str(r["productOrderId"]) for r in rows]}}


def _link(external_id: str, *, order_no: str = "N-CXL", place: str | None = "OK",
          claim: str = "") -> int:
    from foms.services.integrations.naver_commerce.mapping import group_key_text

    product_order = {"productOrderId": external_id}
    if claim:
        product_order["claimStatus"] = claim
    snapshot = {"order": {"orderId": order_no}, "productOrder": product_order}
    link = ExternalOrderLink(
        channel="NAVER", external_id=external_id, external_order_no=order_no,
        sync_status="LINKED", place_order_status=place,
        raw_snapshot=snapshot, group_key=group_key_text(snapshot),
    )
    db_session.add(link)
    db_session.commit()
    return int(link.id)


@pytest.fixture()
def workbench_on(monkeypatch):
    """취소는 워크벤치 전용 기능이다 — 게이트가 켜져야 라우트가 열린다."""
    monkeypatch.setenv("FOMS_NAVER_WORKBENCH_ENABLED", "1")
    monkeypatch.setenv("FOMS_NAVER_WORKBENCH_COHORT", "all")
    yield


def _state(link_id: int) -> dict:
    db_session.expire_all()
    link = db_session.get(ExternalOrderLink, link_id)
    return (link.triage_state or {}).get("fulfillment") or {}


# --------------------------------------------------------------------------- #
# 대상 범위 · 멱등
# --------------------------------------------------------------------------- #

def test_cancel_covers_the_whole_household_one_call_each(app):
    """한 집은 통째로 취소한다 — 형제가 남으면 반쪽 취소가 된다.

    네이버 취소 API 는 상품주문 1건씩이라 집 크기만큼 호출한다.
    """
    first = _link("PO-C1", order_no="N-CXL-1")
    _link("PO-C2", order_no="N-CXL-1")
    client = _StubClient()

    result = cancel_order(db_session, client, link_id=first, reason="INTENT_CHANGED")
    db_session.commit()

    assert sorted(c["productOrderId"] for c in client.cancel_calls) == ["PO-C1", "PO-C2"]
    assert sorted(result["canceled"]) == ["PO-C1", "PO-C2"]


def test_cancel_twice_calls_naver_once(app):
    """두 번 눌러도 네이버는 한 번만 — 되돌릴 수 없는 조작의 기본 계약."""
    link_id = _link("PO-C-IDEM", order_no="N-CXL-IDEM")
    client = _StubClient()

    cancel_order(db_session, client, link_id=link_id, reason="INTENT_CHANGED")
    db_session.commit()
    cancel_order(db_session, client, link_id=link_id, reason="INTENT_CHANGED")
    db_session.commit()

    assert len(client.cancel_calls) == 1
    assert _state(link_id)["canceled_at"]


def test_cancel_records_who_and_why(app):
    """누가 어떤 사유로 취소했는지 남긴다 — 정산 문의가 오면 이 기록이 근거다."""
    link_id = _link("PO-C-WHY", order_no="N-CXL-WHY")
    client = _StubClient()

    cancel_order(db_session, client, link_id=link_id, reason="INTENT_CHANGED",
                 detail="고객 변심 — 전화 확인", actor_user_id=11)
    db_session.commit()

    state = _state(link_id)
    assert state["cancel_reason"] == "INTENT_CHANGED"
    assert state["canceled_by"] == 11
    assert client.cancel_calls[0]["cancelDetailedReason"] == "고객 변심 — 전화 확인"


# --------------------------------------------------------------------------- #
# 가드
# --------------------------------------------------------------------------- #

def test_cancel_refuses_an_unknown_reason(app):
    """네이버가 모르는 사유 코드는 우리 쪽에서 먼저 막는다(호출 낭비·400 방지)."""
    link_id = _link("PO-C-BADREASON", order_no="N-CXL-BAD")
    client = _StubClient()

    with pytest.raises(FulfillmentError):
        cancel_order(db_session, client, link_id=link_id, reason="JUST_BECAUSE")
    assert client.cancel_calls == []


def test_sold_out_can_never_be_sent(app):
    """`SOLD_OUT` 은 **절대 보내지 않는다** (사용자 지시 2026-09-01).

    공식 #2823: 이 사유로 취소하면 대상 상품·옵션 조합의 재고가 **품절 처리**되고 판매관리
    프로그램 패널티가 붙는다. 우리 스토어는 시공 제품이라 품절 취소가 업무에 없다 —
    얻는 것 없이 제재만 남는다.

    화면에서 빼는 것으로는 부족하다: 라우트와 서비스가 화이트리스트로 검사하므로 **목록에서
    지워야** 열린 탭·북마크·직접 호출로도 못 나간다. 2026-08-28 에는 "정당한 용례"라며
    삭제를 기각했었고, 이 테스트가 그 되돌림을 막는다.
    """
    from foms.services.integrations.naver_commerce.fulfillment import (
        BANNED_CLAIM_REASONS,
        RETURN_REASONS,
    )

    assert "SOLD_OUT" in BANNED_CLAIM_REASONS
    for banned in BANNED_CLAIM_REASONS:
        assert banned not in CANCEL_REASONS, f"취소 사유에 {banned} 가 살아 있다"
        assert banned not in RETURN_REASONS, f"반품 사유에 {banned} 가 살아 있다"

    # 서비스가 실제로 거절하는지 — 상수만 보면 우회 경로를 못 잡는다.
    link_id = _link("PO-C-SOLDOUT", order_no="N-CXL-SOLDOUT")
    client = _StubClient()
    with pytest.raises(FulfillmentError):
        cancel_order(db_session, client, link_id=link_id, reason="SOLD_OUT")
    assert client.cancel_calls == [], "금지 사유가 네이버로 나갔다"


def test_cancel_refuses_a_dispatched_household(app):
    """이미 발송처리한 집은 취소가 아니라 반품 흐름이다 — 여기서 막는다."""
    link_id = _link("PO-C-SENT", order_no="N-CXL-SENT")
    client = _StubClient()
    dispatch_order(db_session, client, link_id=link_id)
    db_session.commit()

    with pytest.raises(FulfillmentError):
        cancel_order(db_session, client, link_id=link_id, reason="INTENT_CHANGED")
    assert client.cancel_calls == []
    assert "발송처리" in _state(link_id)["last_error"]


def test_cancel_refuses_a_household_already_in_a_claim(app):
    """이미 취소·반품이 도는 집은 손대지 않는다(판매자센터가 정본)."""
    link_id = _link("PO-C-CLAIM", order_no="N-CXL-CLAIM", claim="CANCEL_REQUEST")
    client = _StubClient()

    with pytest.raises(FulfillmentError):
        cancel_order(db_session, client, link_id=link_id, reason="INTENT_CHANGED")
    assert client.cancel_calls == []


# --------------------------------------------------------------------------- #
# 실패 기록
# --------------------------------------------------------------------------- #

def test_cancel_partial_failure_keeps_the_failed_one_open(app):
    """건별 실패는 그 건에만 사유를 남기고, 성공분에는 도장을 찍는다."""
    first = _link("PO-C-OK", order_no="N-CXL-PART")
    second = _link("PO-C-NG", order_no="N-CXL-PART")
    client = _StubClient(fail_ids={"PO-C-NG"})

    with pytest.raises(FulfillmentError):
        cancel_order(db_session, client, link_id=first, reason="INTENT_CHANGED")
    db_session.commit()

    assert _state(first)["canceled_at"]
    assert "canceled_at" not in _state(second)
    assert "상품 주문 상태" in _state(second)["last_error"]
    assert _state(second)["last_error_action"] == "cancel"


def test_cancel_http_failure_records_the_reason(app):
    """네트워크·HTTP 실패도 사유를 남긴다 — 조용한 실패 금지."""
    link_id = _link("PO-C-HTTP", order_no="N-CXL-HTTP")

    class _Boom(_StubClient):
        def request_cancel_product_order(self, product_order_id, **kwargs):
            raise RuntimeError("HTTP 400 처리권한이 없는 상품주문번호")

    with pytest.raises(FulfillmentError):
        cancel_order(db_session, _Boom(), link_id=link_id, reason="INTENT_CHANGED")
    db_session.commit()

    assert "처리권한" in _state(link_id)["last_error"]


# --------------------------------------------------------------------------- #
# 라우트 — web 은 큐에 넣기만 한다 (호출 IP 3슬롯 계약)
# --------------------------------------------------------------------------- #

def test_route_enqueues_and_never_calls_naver_from_web(auth_client, monkeypatch, workbench_on):
    """취소도 WORKER 단일 출구다 — web 에서 네이버로 나가면 IP 가 막힌다."""
    calls = []

    def _fake_enqueue(link_id, reason, detail=None, actor_user_id=None):
        calls.append((link_id, reason, detail, actor_user_id))
        return True

    monkeypatch.setattr("foms.services.jobs.queue.enqueue_naver_cancel", _fake_enqueue)
    link_id = _link("PO-C-ROUTE", order_no="N-CXL-ROUTE")

    response = auth_client.post(f"/admin/naver-ingest/{link_id}/cancel",
                                json={"reason": "INTENT_CHANGED", "detail": "고객과 통화로 재결제 합의"})

    assert response.status_code == 200
    assert response.get_json()["success"] is True
    assert calls == [(link_id, "INTENT_CHANGED", "고객과 통화로 재결제 합의",
                  calls[0][3])]


def test_route_rejects_an_unknown_reason(auth_client, workbench_on):
    """사유 코드는 서버가 정본으로 검사한다 — 화면 select 만 믿지 않는다."""
    link_id = _link("PO-C-ROUTE-BAD", order_no="N-CXL-ROUTE-BAD")

    response = auth_client.post(f"/admin/naver-ingest/{link_id}/cancel",
                                json={"reason": "WHATEVER"})

    assert response.status_code == 400
    assert response.get_json()["success"] is False


def test_route_reports_when_queue_is_unavailable(auth_client, monkeypatch, workbench_on):
    """큐가 없으면 성공한 척하지 않는다 — 판매자센터로 가라고 말한다."""
    monkeypatch.setattr("foms.services.jobs.queue.enqueue_naver_cancel",
                        lambda *a, **k: False)
    link_id = _link("PO-C-ROUTE-NOQ", order_no="N-CXL-ROUTE-NOQ")

    response = auth_client.post(f"/admin/naver-ingest/{link_id}/cancel",
                                json={"reason": "INTENT_CHANGED"})

    assert response.status_code == 503
    assert "판매자센터" in response.get_json()["error"]


def test_route_writes_an_audit_trail(auth_client, monkeypatch, workbench_on):
    """되돌릴 수 없는 조작은 누가 눌렀는지 감사 로그에 남는다."""
    from models import SecurityLog

    monkeypatch.setattr("foms.services.jobs.queue.enqueue_naver_cancel",
                        lambda *a, **k: True)
    link_id = _link("PO-C-AUDIT", order_no="N-CXL-AUDIT")

    auth_client.post(f"/admin/naver-ingest/{link_id}/cancel", json={"reason": "INTENT_CHANGED"})

    db_session.expire_all()
    logged = (db_session.query(SecurityLog)
              .filter(SecurityLog.action == "NAVER_INGEST_CANCEL_ENQUEUE").all())
    assert logged, "감사 로그가 남아야 한다"


def test_worker_runs_cancel_with_the_reason(app, monkeypatch):
    """WORKER 작업이 사유를 그대로 서비스로 넘긴다."""
    from foms.services.jobs import tasks

    seen = {}

    def _fake_cancel(session, client, *, link_id, reason, detail=None, actor_user_id=None):
        seen.update({"link_id": link_id, "reason": reason, "detail": detail,
                     "actor": actor_user_id})
        return {"canceled": ["PO-C-WORKER"], "skipped": []}

    monkeypatch.setattr(
        "foms.services.integrations.naver_commerce.fulfillment.cancel_order", _fake_cancel)
    monkeypatch.setattr(
        "foms.services.integrations.naver_commerce.client.NaverCommerceClient",
        lambda *a, **k: _StubClient())
    link_id = _link("PO-C-WORKER", order_no="N-CXL-WORKER")

    tasks.run_naver_fulfillment_task(link_id, "cancel", 5, reason="INTENT_CHANGED",
                                     detail="고객과 통화로 재결제 합의")

    assert seen == {"link_id": link_id, "reason": "INTENT_CHANGED",
                    "detail": "고객과 통화로 재결제 합의", "actor": 5}


# --------------------------------------------------------------------------- #
# 취소한 집은 더 이상 손대지 않는다 (푸시 전 리뷰 [치명])
# --------------------------------------------------------------------------- #

def test_dispatch_refuses_a_cancelled_household(app):
    """취소한 집에 발송처리가 나가면 안 된다.

    ``_claim_guard`` 는 raw_snapshot 만 본다 — **우리가 방금 보낸 취소는 다음 수집 스윕
    전까지 스냅샷에 없다**. 그래서 취소 표식을 따로 봐야 한다.
    """
    from foms.services.integrations.naver_commerce.fulfillment import dispatch_order

    link_id = _link("PO-C-THEN-DISP", order_no="N-CXL-THEN-DISP")
    client = _StubClient()
    cancel_order(db_session, client, link_id=link_id, reason="INTENT_CHANGED")
    db_session.commit()

    with pytest.raises(FulfillmentError):
        dispatch_order(db_session, client, link_id=link_id)
    assert client.dispatch_calls == []


def test_confirm_refuses_a_cancelled_household(app):
    """발주확인도 마찬가지다 — 취소한 집은 '발주확인 전' 목록에서도 빠져야 한다."""
    from foms.services.integrations.naver_commerce.fulfillment import confirm_place_order

    link_id = _link("PO-C-THEN-CONF", order_no="N-CXL-THEN-CONF", place="NOT_YET")
    client = _StubClient()
    client.confirm_place_orders = lambda ids: {"data": {"successProductOrderIds": list(ids)}}
    cancel_order(db_session, client, link_id=link_id, reason="INTENT_CHANGED")
    db_session.commit()

    with pytest.raises(FulfillmentError):
        confirm_place_order(db_session, client, link_id=link_id)


def test_a_partly_cancelled_household_is_not_dispatched_either(app):
    """형제 하나만 취소돼도 그 집은 손대지 않는다 — 반쪽 발송은 되돌릴 수 없다."""
    from foms.services.integrations.naver_commerce.fulfillment import dispatch_order

    first = _link("PO-C-HALF1", order_no="N-CXL-HALF")
    second = _link("PO-C-HALF2", order_no="N-CXL-HALF")
    client = _StubClient(fail_ids={"PO-C-HALF2"})
    with pytest.raises(FulfillmentError):
        cancel_order(db_session, client, link_id=first, reason="INTENT_CHANGED")
    db_session.commit()

    with pytest.raises(FulfillmentError):
        dispatch_order(db_session, client, link_id=second)
    assert client.dispatch_calls == []


def test_cancel_route_is_closed_when_the_gate_is_off(auth_client, monkeypatch):
    """게이트 off = 이 기능의 롤백 경로다 — 열린 탭·북마크로 우회되면 안 된다."""
    monkeypatch.delenv("FOMS_NAVER_WORKBENCH_ENABLED", raising=False)
    monkeypatch.delenv("FOMS_NAVER_WORKBENCH_COHORT", raising=False)
    link_id = _link("PO-C-GATEOFF", order_no="N-CXL-GATEOFF")

    response = auth_client.post(f"/admin/naver-ingest/{link_id}/cancel",
                                json={"reason": "INTENT_CHANGED"})

    assert response.status_code == 403
