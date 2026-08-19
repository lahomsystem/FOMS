"""NAVER-INGEST-02 T16-G: 발주확인·발송처리 계약 (스텁 클라이언트).

되돌릴 수 없는 조작이라 계약이 넷이다:
① 한 집은 통째로 ② 두 번 눌러도 네이버는 한 번만 ③ 발주확인 전 발송 금지
④ 실패는 사유를 남기고 조용히 넘어가지 않는다.
"""

from __future__ import annotations

import pytest

from db import db_session
from foms.services.integrations.naver_commerce.fulfillment import (
    DIRECT_DELIVERY,
    FulfillmentError,
    confirm_place_order,
    dispatch_order,
)
from models import ExternalOrderLink


class _StubClient:
    """네이버를 부르지 않는 스텁 — 호출 횟수와 payload 만 기록한다."""

    def __init__(self, *, fail: bool = False) -> None:
        self.confirm_calls: list[list[str]] = []
        self.dispatch_calls: list[list[dict]] = []
        self.fail = fail

    def confirm_place_orders(self, ids):
        if self.fail:
            raise RuntimeError("HTTP 400 처리권한이 없는 상품주문번호")
        self.confirm_calls.append(list(ids))
        return {"data": {"successProductOrderIds": list(ids)}}

    def dispatch_product_orders(self, rows):
        if self.fail:
            raise RuntimeError("HTTP 400 발송처리 실패")
        self.dispatch_calls.append(list(rows))
        return {"data": {"successProductOrderIds": [r["productOrderId"] for r in rows]}}


def _link(external_id: str, *, order_no: str = "N-FUL", place: str | None = None) -> int:
    link = ExternalOrderLink(
        channel="NAVER", external_id=external_id, external_order_no=order_no,
        sync_status="LINKED", place_order_status=place,
        raw_snapshot={"order": {"orderId": order_no},
                      "productOrder": {"productOrderId": external_id}},
    )
    db_session.add(link)
    db_session.commit()
    return int(link.id)


def _state(link_id: int) -> dict:
    db_session.expire_all()
    link = db_session.get(ExternalOrderLink, link_id)
    return (link.triage_state or {}).get("fulfillment") or {}


def test_confirm_covers_the_whole_group(app):
    """한 집의 상품주문 전부가 한 번의 호출로 발주확인된다."""
    first = _link("PO-F1", place="NOT_YET")
    second = _link("PO-F2", place="NOT_YET")
    client = _StubClient()

    result = confirm_place_order(db_session, client, link_id=first, actor_user_id=7)
    db_session.commit()

    assert client.confirm_calls == [["PO-F1", "PO-F2"]]
    assert set(result["confirmed"]) == {"PO-F1", "PO-F2"}
    assert _state(first)["place_confirmed_at"]
    assert db_session.get(ExternalOrderLink, second).place_order_status == "OK"


def test_confirm_twice_calls_naver_once(app):
    """두 번 눌러도 네이버는 한 번만 부른다(되돌릴 수 없는 조작)."""
    link_id = _link("PO-F-IDEM", order_no="N-FUL-IDEM", place="NOT_YET")
    client = _StubClient()

    confirm_place_order(db_session, client, link_id=link_id)
    db_session.commit()
    second = confirm_place_order(db_session, client, link_id=link_id)
    db_session.commit()

    assert len(client.confirm_calls) == 1
    assert second["confirmed"] == []
    assert second["skipped"] == ["PO-F-IDEM"]


def test_confirm_failure_records_reason_and_raises(app):
    """실패는 사유를 남기고 그대로 올린다 — 조용한 실패 금지."""
    link_id = _link("PO-F-ERR", order_no="N-FUL-ERR", place="NOT_YET")
    client = _StubClient(fail=True)

    with pytest.raises(FulfillmentError):
        confirm_place_order(db_session, client, link_id=link_id)
    db_session.commit()

    assert "처리권한" in _state(link_id)["last_error"]
    db_session.expire_all()
    assert db_session.get(ExternalOrderLink, link_id).place_order_status == "NOT_YET"


def test_dispatch_requires_place_confirmation_first(app):
    """발주확인 전에는 발송처리하지 않는다(네이버가 거절하기 전에 우리가 막는다)."""
    link_id = _link("PO-F-EARLY", order_no="N-FUL-EARLY", place="NOT_YET")
    client = _StubClient()

    with pytest.raises(FulfillmentError):
        dispatch_order(db_session, client, link_id=link_id)
    assert client.dispatch_calls == []


def test_dispatch_uses_direct_delivery_with_iso_timestamp(app):
    """자사 배송은 택배사·송장이 없다 — DIRECT_DELIVERY + ISO8601 발송일."""
    link_id = _link("PO-F-DISP", order_no="N-FUL-DISP", place="OK")
    client = _StubClient()

    dispatch_order(db_session, client, link_id=link_id, actor_user_id=7)
    db_session.commit()

    assert len(client.dispatch_calls) == 1
    row = client.dispatch_calls[0][0]
    assert row["productOrderId"] == "PO-F-DISP"
    assert row["deliveryMethod"] == DIRECT_DELIVERY
    assert row["dispatchDate"].endswith("+09:00")
    assert "." in row["dispatchDate"], "밀리초가 있어야 한다"
    assert _state(link_id)["dispatched_at"]


def test_dispatch_twice_calls_naver_once(app):
    """발송처리도 멱등이다 — 두 번 나가면 정산·구매확정이 꼬인다."""
    link_id = _link("PO-F-DISP2", order_no="N-FUL-DISP2", place="OK")
    client = _StubClient()

    dispatch_order(db_session, client, link_id=link_id)
    db_session.commit()
    dispatch_order(db_session, client, link_id=link_id)
    db_session.commit()

    assert len(client.dispatch_calls) == 1


def test_unknown_link_raises(app):
    """없는 링크는 조용히 성공하지 않는다."""
    with pytest.raises(FulfillmentError):
        confirm_place_order(db_session, _StubClient(), link_id=999999)


def test_route_enqueues_and_never_calls_naver_from_web(auth_client, monkeypatch):
    """web 은 큐에 넣기만 한다 — 네이버 HTTP 는 WORKER 몫(호출 IP 3슬롯 계약)."""
    calls = []

    def _fake_enqueue(link_id, action, actor_user_id=None):
        calls.append((link_id, action, actor_user_id))
        return True

    monkeypatch.setattr("foms.services.jobs.queue.enqueue_naver_fulfillment", _fake_enqueue)
    link_id = _link("PO-F-ROUTE", order_no="N-FUL-ROUTE", place="NOT_YET")

    response = auth_client.post(f"/admin/naver-ingest/{link_id}/fulfillment",
                                json={"action": "confirm"})
    assert response.status_code == 200
    assert response.get_json()["data"]["queued"] is True
    assert calls and calls[0][0] == link_id and calls[0][1] == "confirm"


def test_route_reports_when_queue_is_unavailable(auth_client, monkeypatch):
    """큐가 없으면 성공한 척하지 않는다 — 사람에게 판매자센터로 안내한다."""
    monkeypatch.setattr("foms.services.jobs.queue.enqueue_naver_fulfillment",
                        lambda *a, **k: False)
    link_id = _link("PO-F-NOQ", order_no="N-FUL-NOQ", place="NOT_YET")

    response = auth_client.post(f"/admin/naver-ingest/{link_id}/fulfillment",
                                json={"action": "confirm"})
    assert response.status_code == 503
    assert "판매자센터" in response.get_json()["error"]


def test_route_rejects_unknown_action(auth_client):
    """작업은 닫힌집합이다."""
    link_id = _link("PO-F-BAD", order_no="N-FUL-BAD", place="NOT_YET")
    response = auth_client.post(f"/admin/naver-ingest/{link_id}/fulfillment",
                                json={"action": "cancel_everything"})
    assert response.status_code == 400
