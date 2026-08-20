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


def _order_row(name: str = "처리고객") -> int:
    from models import Order

    order = Order(received_date="2026-08-01", customer_name=name, phone="010-1212-3434",
                  address="서울시 강남구 테헤란로 152", product="붙박이장", status="RECEIVED")
    db_session.add(order)
    db_session.commit()
    return int(order.id)


def _attach_link(link_id: int, order_id: int, relation: str) -> None:
    link = db_session.get(ExternalOrderLink, link_id)
    link.order_id = order_id
    link.relation = relation
    link.sync_status = "LINKED"
    db_session.commit()


def test_confirm_button_shows_for_new_order_before_place_confirm(auth_client):
    """신규는 주문을 만든 뒤 발주확인 버튼이 뜬다 (T16-H)."""
    order_id = _order_row()
    link_id = _link("PO-H-NEW", order_no="N-H-NEW", place="NOT_YET")
    _attach_link(link_id, order_id, "NEW")

    body = auth_client.get(f"/admin/naver-ingest/triage?link_id={link_id}").get_data(as_text=True)
    assert 'data-action="confirm"' in body
    assert 'data-action="dispatch"' not in body


def test_confirm_button_hidden_once_confirmed(auth_client):
    """발주확인이 끝났으면 버튼 대신 완료 표시만 남는다(중복 호출 차단)."""
    order_id = _order_row("확인끝")
    link_id = _link("PO-H-DONE", order_no="N-H-DONE", place="OK")
    _attach_link(link_id, order_id, "NEW")

    body = auth_client.get(f"/admin/naver-ingest/triage?link_id={link_id}").get_data(as_text=True)
    assert 'data-action="confirm"' not in body
    assert "발주확인 완료" in body


def test_addon_dispatch_button_appears_only_after_place_confirm(auth_client):
    """추가결제는 **발주확인 뒤** 발송처리 버튼이 뜬다(네이버가 그 순서를 강제한다)."""
    order_id = _order_row("추가결제")
    link_id = _link("PO-H-ADDON", order_no="N-H-ADDON", place="NOT_YET")
    _attach_link(link_id, order_id, "ADDON")

    body = auth_client.get(f"/admin/naver-ingest/triage?link_id={link_id}").get_data(as_text=True)
    assert 'data-action="confirm"' in body
    assert 'data-action="dispatch"' not in body

    link = db_session.get(ExternalOrderLink, link_id)
    link.place_order_status = "OK"
    db_session.commit()

    body = auth_client.get(f"/admin/naver-ingest/triage?link_id={link_id}").get_data(as_text=True)
    assert 'data-action="dispatch"' in body


def test_new_order_does_not_get_a_dispatch_button(auth_client):
    """신규 주문의 발송처리는 실제 출고·시공 시점 일이라 여기서 누르지 않는다."""
    order_id = _order_row("신규발송")
    link_id = _link("PO-H-NEWDISP", order_no="N-H-NEWDISP", place="OK")
    _attach_link(link_id, order_id, "NEW")

    body = auth_client.get(f"/admin/naver-ingest/triage?link_id={link_id}").get_data(as_text=True)
    assert 'data-action="dispatch"' not in body
    assert "실제 출고·시공 시점" in body


def test_last_error_is_shown_not_swallowed(auth_client):
    """실패 사유는 화면에 그대로 남는다."""
    order_id = _order_row("실패표시")
    link_id = _link("PO-H-ERR", order_no="N-H-ERR", place="NOT_YET")
    _attach_link(link_id, order_id, "NEW")
    link = db_session.get(ExternalOrderLink, link_id)
    link.triage_state = {"fulfillment": {"last_error": "HTTP 400 처리권한 없음"}}
    db_session.commit()

    body = auth_client.get(f"/admin/naver-ingest/triage?link_id={link_id}").get_data(as_text=True)
    assert "HTTP 400 처리권한 없음" in body


def test_reviewed_link_pane_is_still_reachable(auth_client):
    """확인 완료된 건도 link_id 로 대조 pane 을 열 수 있어야 한다.

    큐에서는 빠지지만 발주확인·발송처리 버튼이 그 화면에 있다 — 열 수 없으면 처리 경로가
    사라진다(2026-08-20 스테이징에서 실제로 막혔다).
    """
    from foms.services.datetime_kst import now_utc_naive

    order_id = _order_row("확인끝난건")
    link_id = _link("PO-H-REVIEWED", order_no="N-H-REVIEWED", place="NOT_YET")
    _attach_link(link_id, order_id, "NEW")
    link = db_session.get(ExternalOrderLink, link_id)
    link.reviewed_at = now_utc_naive()
    db_session.commit()

    body = auth_client.get(f"/admin/naver-ingest/triage?link_id={link_id}").get_data(as_text=True)
    assert "PO-H-REVIEWED" in body
    assert 'data-action="confirm"' in body


def test_worker_keeps_the_failure_reason_instead_of_rolling_it_back(app, monkeypatch):
    """워커가 실패해도 **사유는 남아야 한다**.

    서비스는 사유를 일부러 기록하고 올린다(`fulfillment.py` 의 except 절). 그런데 워커가
    모든 예외에 db.rollback() 을 걸어 그 기록까지 지워 왔다 — 실패가 DB 어디에도 안 남고
    로그·RQ 에만 있었다. 화면이 "성공 n · 실패 m · 사유" 를 보여주려면 이 기록이 정본이다.

    성공분까지 함께 커밋되면 안 된다 — 그건 아래 별도 테스트가 지킨다.
    """
    from foms.services.integrations.naver_commerce import client as client_mod
    from foms.services.jobs import tasks as tasks_mod

    link_id = _link("PO-F-WORKER", order_no="N-FUL-WORKER", place="NOT_YET")
    # 태스크가 함수 안에서 import 하므로 원본 모듈 속성을 갈아 끼운다.
    monkeypatch.setattr(client_mod, "NaverCommerceClient", lambda: _StubClient(fail=True))

    with pytest.raises(Exception):
        tasks_mod.run_naver_fulfillment_task(link_id, "confirm", None)

    db_session.expire_all()
    link = db_session.get(ExternalOrderLink, link_id)
    assert link is not None
    state = (link.triage_state or {}).get("fulfillment") or {}
    assert "처리권한" in (state.get("last_error") or ""), state
    assert state.get("last_error_at"), state
    # 실패인데 성공 표식이 붙으면 안 된다.
    assert not state.get("place_confirmed_at"), state
    assert link.place_order_status == "NOT_YET"


def test_worker_failure_commit_does_not_leak_success_marks(app, monkeypatch):
    """실패 경로 커밋이 '처리됐다' 표식까지 남기면 안 된다.

    사유를 살리려고 커밋을 열었으니, 그 커밋이 성공 표식을 데려오지 않는지 반대편도 고정한다.
    네이버 호출이 실패하면 place_confirmed_at·place_order_status 는 그대로여야 하고,
    다음 시도가 정상적으로 다시 나가야 한다.
    """
    from foms.services.integrations.naver_commerce import client as client_mod
    from foms.services.jobs import tasks as tasks_mod

    link_id = _link("PO-F-NOLEAK", order_no="N-FUL-NOLEAK", place="NOT_YET")

    monkeypatch.setattr(client_mod, "NaverCommerceClient", lambda: _StubClient(fail=True))
    with pytest.raises(Exception):
        tasks_mod.run_naver_fulfillment_task(link_id, "confirm", None)

    db_session.expire_all()
    state = (db_session.get(ExternalOrderLink, link_id).triage_state or {}).get("fulfillment") or {}
    assert not state.get("place_confirmed_at"), state

    # 다시 시도하면 네이버로 실제로 나간다(실패가 '이미 처리됨'으로 굳지 않는다).
    ok_client = _StubClient()
    monkeypatch.setattr(client_mod, "NaverCommerceClient", lambda: ok_client)
    tasks_mod.run_naver_fulfillment_task(link_id, "confirm", None)

    assert ok_client.confirm_calls, "재시도가 네이버를 부르지 않았다"
    db_session.expire_all()
    link = db_session.get(ExternalOrderLink, link_id)
    state = (link.triage_state or {}).get("fulfillment") or {}
    assert state.get("place_confirmed_at")
    # 성공하면 사유는 지워진다 — 낡은 실패 문구가 화면에 남으면 안 된다.
    assert not state.get("last_error")
    assert link.place_order_status == "OK"
