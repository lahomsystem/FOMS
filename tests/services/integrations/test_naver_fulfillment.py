"""NAVER-INGEST-02 T16-G: 발주확인·발송처리 계약 (스텁 클라이언트).

되돌릴 수 없는 조작이라 계약이 넷이다:
① 한 집은 통째로 ② 두 번 눌러도 네이버는 한 번만 ③ 발주확인 전 발송 금지
④ 실패는 사유를 남기고 조용히 넘어가지 않는다.
"""

from __future__ import annotations

from typing import Any

import pytest

from db import db_session
from foms.services.integrations.naver_commerce.fulfillment import (
    DIRECT_DELIVERY,
    FulfillmentError,
    clear_failure,
    confirm_place_order,
    dispatch_order,
)
from models import ExternalOrderLink


class _StubClient:
    """네이버를 부르지 않는 스텁 — 호출 횟수와 payload 만 기록한다.

    ``partial`` 을 주면 그 상품주문만 **HTTP 200 안에서** 실패로 돌려준다
    (커머스API 는 건별 실패를 body 의 ``failProductOrderInfos`` 로 준다).
    ``payload_override`` 는 모양이 다른 응답(옛 필드·빈 body)을 흉내낸다.
    """

    def __init__(self, *, fail: bool = False, partial: dict[str, str] | None = None,
                 payload_override: Any = None) -> None:
        self.confirm_calls: list[list[str]] = []
        self.dispatch_calls: list[list[dict]] = []
        self.fail = fail
        self.partial = dict(partial or {})
        self.payload_override = payload_override

    def _payload(self, ids: list[str]) -> dict:
        if self.payload_override is not None:
            return self.payload_override
        ok = [x for x in ids if x not in self.partial]
        data: dict[str, Any] = {"successProductOrderIds": ok}
        if self.partial:
            data["failProductOrderInfos"] = [
                {"productOrderId": pid, "message": reason}
                for pid, reason in self.partial.items() if pid in ids
            ]
        return {"data": data}

    def confirm_place_orders(self, ids):
        if self.fail:
            raise RuntimeError("HTTP 400 처리권한이 없는 상품주문번호")
        self.confirm_calls.append(list(ids))
        return self._payload([str(x) for x in ids])

    def dispatch_product_orders(self, rows):
        if self.fail:
            raise RuntimeError("HTTP 400 발송처리 실패")
        self.dispatch_calls.append(list(rows))
        return self._payload([str(r["productOrderId"]) for r in rows])


def _link(external_id: str, *, order_no: str = "N-FUL", place: str | None = None,
          address: str = "", tel: str = "", relation: str = "") -> int:
    """수집분 링크 1건. ``address``/``tel`` 을 주면 **분할배송**(같은 주문번호·다른 집)이 된다."""
    from foms.services.integrations.naver_commerce.mapping import group_key_text

    snapshot = {"order": {"orderId": order_no},
                "productOrder": {"productOrderId": external_id}}
    if address or tel:
        snapshot["productOrder"]["shippingAddress"] = {
            "name": "이수취", "tel1": tel, "baseAddress": address, "detailedAddress": "",
        }
    link = ExternalOrderLink(
        channel="NAVER", external_id=external_id, external_order_no=order_no,
        sync_status="LINKED", place_order_status=place, relation=relation or None,
        raw_snapshot=snapshot, group_key=group_key_text(snapshot),
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


def test_dispatch_lets_an_addon_close_before_place_confirmation(app):
    """추가결제는 발주확인 전에도 닫는다 (D1) — 물건이 따로 나가지 않는다.

    네이버 발송관리 화면도 발주확인 없이 발송처리를 받는다. 우리가 먼저 막으면 사람이
    두 번 눌러야 하고, 안 눌러도 되는 발주확인을 배우게 된다.
    """
    link_id = _link("PO-F-ADDON", order_no="N-FUL-ADDON", place="NOT_YET", relation="ADDON")
    client = _StubClient()

    dispatch_order(db_session, client, link_id=link_id)
    db_session.commit()

    assert len(client.dispatch_calls) == 1
    assert _state(link_id)["dispatched_at"]


def test_dispatch_blocks_a_repay_before_place_confirmation(app):
    """재결제는 발주확인 전에 닫지 **않는다** (D1 개정 2026-08-24).

    옛 D1(2026-08-22)은 ADDON 논리("물건이 따로 나가지 않는다")를 REPAY 로 확장했는데
    그 문장은 재결제에 거짓이다 — 재결제는 원 주문을 취소하고 그 물건값을 다시 낸 것이라
    **원 주문의 물건이 나중에 한 번 나간다**. 출고 전에 닫으면 구매자에게 "배송 시작"이
    먼저 뜨고 구매확정·정산 시계가 돌며, dispatched_any 가 되어 취소 버튼까지 사라진다.
    2026-08-19 스펙 §3 원안(REPAY = 신규와 같게)으로 되돌린 결정이다.

    거절 사유가 **링크에 남는지**까지 본다: web 은 enqueue 뒤 이미 "요청했습니다"로
    답했으므로, 이 기록이 사람에게 닿는 유일한 통지 경로다.
    """
    link_id = _link("PO-F-REPAY", order_no="N-FUL-REPAY", place="NOT_YET", relation="REPAY")
    client = _StubClient()

    with pytest.raises(FulfillmentError) as caught:
        dispatch_order(db_session, client, link_id=link_id)
    db_session.commit()

    assert client.dispatch_calls == [], "재결제 집이 발주확인 없이 네이버로 나갔다"
    assert "발주확인이 먼저입니다" in str(caught.value)
    state = _state(link_id)
    assert "발주확인이 먼저입니다" in state["last_error"], "거절 사유가 링크에 없다"
    assert state["last_error_action"] == "dispatch"


def test_a_repay_dispatches_after_place_confirmation(app):
    """재결제도 **막다른 길이 아니다** — 발주확인을 마치면 발송처리가 그대로 나간다.

    D1 개정의 비용은 클릭 1회여야 한다. 발주확인 뒤에도 막히면 그건 개정이 아니라
    재결제 집을 화면에서 처리할 수 없게 만든 것이다.
    """
    link_id = _link("PO-F-REPAY-OK", order_no="N-FUL-REPAY-OK", place="NOT_YET",
                    relation="REPAY")
    client = _StubClient()

    confirm_place_order(db_session, client, link_id=link_id)
    db_session.commit()
    dispatch_order(db_session, client, link_id=link_id)
    db_session.commit()

    assert len(client.dispatch_calls) == 1
    assert _state(link_id)["dispatched_at"]
    assert not _state(link_id)["last_error"]


def test_a_mixed_household_still_needs_place_confirmation_first(app):
    """관계가 섞인 집은 **발주확인이 먼저**다 (2026-08-23 리뷰 F7).

    붙이기는 집 전체에 관계를 쓰지만, attach 이후 수집된 형제는 server_default 'NEW' 로
    들어온다. 한 건만 ADDON 이라고 집을 열면 그 NEW 형제까지 발주확인 없이 발송된다.
    """
    link_id = _link("PO-F-MIX1", order_no="N-FUL-MIX", place="NOT_YET", relation="ADDON")
    _link("PO-F-MIX2", order_no="N-FUL-MIX", place="NOT_YET")
    client = _StubClient()

    with pytest.raises(FulfillmentError):
        dispatch_order(db_session, client, link_id=link_id)
    assert client.dispatch_calls == []


def test_a_fully_addon_household_closes_together(app):
    """집 전체가 추가결제면 형제까지 함께 닫는다 — 한 집은 통째로."""
    link_id = _link("PO-F-ALL1", order_no="N-FUL-ALL", place="NOT_YET", relation="ADDON")
    _link("PO-F-ALL2", order_no="N-FUL-ALL", place="NOT_YET", relation="ADDON")
    client = _StubClient()

    dispatch_order(db_session, client, link_id=link_id)
    db_session.commit()

    assert sorted(r["productOrderId"] for r in client.dispatch_calls[0]) == ["PO-F-ALL1", "PO-F-ALL2"]


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


# --------------------------------------------------------------------------- #
# 분할배송 — 화면이 가른 집과 워커가 처리하는 대상이 같아야 한다 (리뷰 지적 P2)
#
# 화면은 group_key(주문번호+수취인 전화+주소)로 집을 가르는데 워커가 주문번호로만 묶으면,
# A집만 체크해도 B집까지 발주확인이 나간다. 네이버로 나간 호출은 되돌릴 수 없다.
# --------------------------------------------------------------------------- #

def test_confirm_stays_inside_the_selected_household(app):
    """A집만 골랐으면 B집 상품주문은 건드리지 않는다."""
    a_first = _link("PO-SP-A1", order_no="N-SPLIT", place="NOT_YET",
                    address="서울 강남구 1", tel="010-1111-1111")
    _link("PO-SP-A2", order_no="N-SPLIT", place="NOT_YET",
          address="서울 강남구 1", tel="010-1111-1111")
    b_only = _link("PO-SP-B1", order_no="N-SPLIT", place="NOT_YET",
                   address="부산 해운대구 9", tel="010-2222-2222")
    client = _StubClient()

    result = confirm_place_order(db_session, client, link_id=a_first)
    db_session.commit()

    assert client.confirm_calls == [["PO-SP-A1", "PO-SP-A2"]], client.confirm_calls
    assert set(result["confirmed"]) == {"PO-SP-A1", "PO-SP-A2"}
    assert _state(b_only) == {}, "옆 집은 상태도 바뀌면 안 된다"
    db_session.expire_all()
    assert db_session.get(ExternalOrderLink, b_only).place_order_status == "NOT_YET"


def test_dispatch_stays_inside_the_selected_household(app):
    """발송처리도 마찬가지 — 옆 집이 발주확인 전이라고 A집 발송이 막히지도 않는다."""
    a_first = _link("PO-SPD-A1", order_no="N-SPLITD", place="OK",
                    address="서울 강남구 1", tel="010-1111-1111")
    b_only = _link("PO-SPD-B1", order_no="N-SPLITD", place="NOT_YET",
                   address="부산 해운대구 9", tel="010-2222-2222")
    client = _StubClient()

    result = dispatch_order(db_session, client, link_id=a_first)
    db_session.commit()

    assert [row["productOrderId"] for row in client.dispatch_calls[0]] == ["PO-SPD-A1"]
    assert result["dispatched"] == ["PO-SPD-A1"]
    assert _state(b_only) == {}


# --------------------------------------------------------------------------- #
# HTTP 200 안의 건별 실패 (리뷰 지적 P4)
#
# 커머스API 는 200 을 주면서 body 에 실패 목록을 담는다. 그걸 안 보면 실패한 상품주문에도
# 성공 도장이 찍히고, 멱등 규칙 때문에 **다시는 보내지지 않는다** — 조용한 미발송이 된다.
# --------------------------------------------------------------------------- #

def test_partial_failure_stamps_only_the_successful_ones(app):
    """200 안의 실패 건은 성공 표식을 받지 않고 사유를 남긴다."""
    first = _link("PO-PF-1", order_no="N-PF", place="NOT_YET")
    second = _link("PO-PF-2", order_no="N-PF", place="NOT_YET")
    client = _StubClient(partial={"PO-PF-2": "판매자 확인이 필요한 상품주문입니다"})

    with pytest.raises(FulfillmentError) as caught:
        confirm_place_order(db_session, client, link_id=first)
    db_session.commit()

    assert "판매자 확인이 필요한 상품주문입니다" in str(caught.value)
    assert _state(first)["place_confirmed_at"], "성공한 건은 그대로 확정된다"
    assert not _state(second).get("place_confirmed_at"), "실패한 건에 도장을 찍으면 안 된다"
    assert "판매자 확인이 필요한 상품주문입니다" in _state(second)["last_error"]
    db_session.expire_all()
    assert db_session.get(ExternalOrderLink, second).place_order_status == "NOT_YET"


def test_retry_after_partial_failure_sends_only_the_failed_one(app):
    """다시 시도하면 실패한 상품주문만 나간다 — 성공분을 두 번 부르지 않는다."""
    first = _link("PO-PF-R1", order_no="N-PFR", place="NOT_YET")
    _link("PO-PF-R2", order_no="N-PFR", place="NOT_YET")
    client = _StubClient(partial={"PO-PF-R2": "일시 오류"})
    with pytest.raises(FulfillmentError):
        confirm_place_order(db_session, client, link_id=first)
    db_session.commit()

    client.partial = {}
    confirm_place_order(db_session, client, link_id=first)
    db_session.commit()

    assert client.confirm_calls == [["PO-PF-R1", "PO-PF-R2"], ["PO-PF-R2"]], client.confirm_calls


def test_unknown_response_shape_is_still_treated_as_success(app):
    """성공 목록 키가 없는 응답은 예전처럼 전부 성공으로 본다(판단 근거가 없다)."""
    link_id = _link("PO-PF-SHAPE", order_no="N-PFS", place="NOT_YET")
    client = _StubClient(payload_override={"traceId": "abc"})

    result = confirm_place_order(db_session, client, link_id=link_id)
    db_session.commit()

    assert result["confirmed"] == ["PO-PF-SHAPE"]
    assert _state(link_id)["place_confirmed_at"]


def test_dispatch_partial_failure_keeps_the_failed_one_open(app):
    """발송처리도 같다 — 실패 건은 발송 표식 없이 남아 다시 보낼 수 있다."""
    first = _link("PO-PFD-1", order_no="N-PFD", place="OK")
    second = _link("PO-PFD-2", order_no="N-PFD", place="OK")
    client = _StubClient(partial={"PO-PFD-2": "발송 가능 상태가 아닙니다"})

    with pytest.raises(FulfillmentError):
        dispatch_order(db_session, client, link_id=first)
    db_session.commit()

    assert _state(first)["dispatched_at"]
    assert not _state(second).get("dispatched_at")
    assert "발송 가능 상태가 아닙니다" in _state(second)["last_error"]


def test_failure_records_which_action_failed(app):
    """실패 사유에 **어느 작업**이 실패했는지 함께 남는다 — 화면 재시도가 그걸 보고 고른다."""
    confirm_link = _link("PO-ACT-1", order_no="N-ACT1", place="NOT_YET")
    with pytest.raises(FulfillmentError):
        confirm_place_order(db_session, _StubClient(fail=True), link_id=confirm_link)
    db_session.commit()

    dispatch_link = _link("PO-ACT-2", order_no="N-ACT2", place="OK")
    with pytest.raises(FulfillmentError):
        dispatch_order(db_session, _StubClient(fail=True), link_id=dispatch_link)
    db_session.commit()

    assert _state(confirm_link)["last_error_action"] == "confirm"
    assert _state(dispatch_link)["last_error_action"] == "dispatch"


# --------------------------------------------------------------------------- #
# 실패 기록 지우기 (2차 리뷰)
#
# 판매자센터에서 손으로 해결하면 우리 쪽 last_error 는 영원히 남아 빨간 띠가 고정된다.
# 사람이 "확인했다"고 말할 수 있어야 한다. 성공 표식은 건드리지 않는다.
# --------------------------------------------------------------------------- #

def test_clear_failure_clears_every_sibling_that_failed_the_same_action(app):
    """**같은 작업으로 실패한** 형제를 함께 지운다 — 하나만 남으면 띠가 다시 뜬다.

    이름이 한때 ``..._wipes_the_whole_household`` 였는데 그건 과장이다(2026-09-02).
    ``clear_failure`` 의 범위는 집 전체가 아니라 **기준 링크와 같은 작업으로 실패한
    형제들**이다(NVCLAIM-ORDER-01 RC5 2차) — 다른 작업의 실패는 남는다. 여기서 둘 다
    지워지는 것은 둘이 **같은 발주확인**에서 실패했기 때문이지 집이라서가 아니다.
    아래 ``kept`` 단언이 그 축을 붙든다.
    """
    first = _link("PO-CLR-1", order_no="N-CLR", place="NOT_YET")
    second = _link("PO-CLR-2", order_no="N-CLR", place="NOT_YET")
    with pytest.raises(FulfillmentError):
        confirm_place_order(db_session, _StubClient(fail=True), link_id=first)
    db_session.commit()

    result = clear_failure(db_session, link_id=first, actor_user_id=7)
    db_session.commit()

    assert result["cleared"] == 2
    assert result["kept"] == 0, "같은 작업으로 실패했으므로 남길 것이 없다"
    assert result["action"] == "confirm", "무슨 작업을 지웠는지가 범위의 축이다"
    assert not _state(first).get("last_error")
    assert not _state(second).get("last_error")
    assert _state(first)["failure_cleared_by"] == 7


def test_clear_failure_keeps_the_success_marks(app):
    """지우는 건 실패 사유뿐이다 — 발주확인·발송처리 표식을 지우면 멱등이 깨진다."""
    link_id = _link("PO-CLR-KEEP", order_no="N-CLR-K", place="NOT_YET")
    confirm_place_order(db_session, _StubClient(), link_id=link_id)
    db_session.commit()
    from foms.services.integrations.naver_commerce.fulfillment import _write_state
    from models import ExternalOrderLink as _L

    _write_state(db_session.get(_L, link_id), {"last_error": "판매자센터에서 처리함",
                                               "last_error_action": "dispatch"})
    db_session.commit()

    clear_failure(db_session, link_id=link_id)
    db_session.commit()

    assert not _state(link_id).get("last_error")
    assert _state(link_id)["place_confirmed_at"], "성공 표식은 남아야 한다"


def test_clear_failure_does_not_touch_other_households(app):
    """옆 집 실패는 그대로 둔다."""
    mine = _link("PO-CLR-A", order_no="N-CLR-A", place="NOT_YET")
    other = _link("PO-CLR-B", order_no="N-CLR-B", place="NOT_YET")
    for link_id in (mine, other):
        with pytest.raises(FulfillmentError):
            confirm_place_order(db_session, _StubClient(fail=True), link_id=link_id)
        db_session.commit()

    clear_failure(db_session, link_id=mine)
    db_session.commit()

    assert not _state(mine).get("last_error")
    assert _state(other)["last_error"], "옆 집 실패까지 지우면 사고를 덮는다"


# --------------------------------------------------------------------------- #
# 3차 리뷰 — 클레임 집 발송 금지 / 상품주문번호 없는 실패 항목
# --------------------------------------------------------------------------- #

def _claimed(link_id: int, status: str = "CANCEL_REQUEST") -> None:
    """그 링크의 원본에 클레임 표식을 심는다(네이버 취소·반품 진행 중)."""
    import copy

    from sqlalchemy.orm.attributes import flag_modified

    link = db_session.get(ExternalOrderLink, link_id)
    snapshot = copy.deepcopy(link.raw_snapshot or {})
    snapshot.setdefault("productOrder", {})["claimStatus"] = status
    link.raw_snapshot = snapshot
    flag_modified(link, "raw_snapshot")
    db_session.commit()


def test_dispatch_refuses_a_household_with_a_claim(app):
    """형제가 취소·반품 중이면 발송처리를 서버가 막는다 — 되돌릴 수 없는 호출이다."""
    first = _link("PO-CLM-1", order_no="N-CLM", place="OK")
    second = _link("PO-CLM-2", order_no="N-CLM", place="OK")
    _claimed(second)
    client = _StubClient()

    with pytest.raises(FulfillmentError) as caught:
        dispatch_order(db_session, client, link_id=first)

    assert "취소" in str(caught.value) or "반품" in str(caught.value), str(caught.value)
    assert client.dispatch_calls == [], "네이버를 부르면 안 된다"


def test_confirm_refuses_a_household_with_a_claim(app):
    """발주확인도 같다 — 취소가 걸린 집은 화면에서도 서버에서도 손대지 않는다."""
    first = _link("PO-CLM-C1", order_no="N-CLM-C", place="NOT_YET")
    _claimed(_link("PO-CLM-C2", order_no="N-CLM-C", place="NOT_YET"))
    client = _StubClient()

    with pytest.raises(FulfillmentError):
        confirm_place_order(db_session, client, link_id=first)

    assert client.confirm_calls == []


def test_failure_without_product_order_id_is_not_treated_as_success(app):
    """상품주문번호가 없는 실패 항목이 와도 성공 도장을 찍지 않는다.

    버리고 넘어가면 '성공 목록도 실패 목록도 없다' 경로로 떨어져 전부 성공이 되고,
    멱등 규칙 때문에 영영 재발송되지 않는다 — 이 함수가 막으려던 조용한 미발송이다.
    """
    link_id = _link("PO-NOID", order_no="N-NOID", place="NOT_YET")
    client = _StubClient(payload_override={
        "data": {"failProductOrderInfos": [{"message": "처리할 수 없는 요청입니다"}]}})

    with pytest.raises(FulfillmentError):
        confirm_place_order(db_session, client, link_id=link_id)
    db_session.commit()

    assert not _state(link_id).get("place_confirmed_at")
    assert _state(link_id)["last_error"]


# --------------------------------------------------------------------------- #
# 4차 리뷰 — 거절도 보여야 한다 / 사유를 잃지 않는다
# --------------------------------------------------------------------------- #

def test_claim_refusal_is_written_where_the_screen_can_see_it(app):
    """서버가 막았다는 사실이 화면에 닿아야 한다.

    web 은 enqueue 만 하고 즉시 "요청했습니다"로 답한다. 워커가 조용히 거절하면 사람은
    보냈다고 믿는다 — 실패 사유를 상태에 남기는 것이 유일한 통로다.
    """
    first = _link("PO-CLMV-1", order_no="N-CLMV", place="OK")
    _claimed(_link("PO-CLMV-2", order_no="N-CLMV", place="OK"))

    with pytest.raises(FulfillmentError):
        dispatch_order(db_session, _StubClient(), link_id=first)
    db_session.commit()

    state = _state(first)
    assert "취소" in state["last_error"] or "반품" in state["last_error"], state
    assert state["last_error_action"] == "dispatch"


def test_unattributed_reason_survives_when_a_success_list_exists(app):
    """상품주문번호 없는 실패 사유도 화면까지 간다 — 진단이 사라지면 못 고친다."""
    first = _link("PO-UNATTR-1", order_no="N-UNATTR", place="NOT_YET")
    _link("PO-UNATTR-2", order_no="N-UNATTR", place="NOT_YET")
    client = _StubClient(payload_override={"data": {
        "successProductOrderIds": ["PO-UNATTR-1"],
        "failProductOrderInfos": [{"message": "판매자 확인이 필요합니다"}],
    }})

    with pytest.raises(FulfillmentError):
        confirm_place_order(db_session, client, link_id=first)
    db_session.commit()

    second_state = [r for r in db_session.query(ExternalOrderLink)
                    .filter(ExternalOrderLink.external_id == "PO-UNATTR-2").all()][0]
    reason = (second_state.triage_state or {})["fulfillment"]["last_error"]
    assert "판매자 확인이 필요합니다" in reason, reason


# --------------------------------------------------------------------------- #
# 5차 리뷰 — 거절 가시화(발주확인 전) / 컬럼으로 확인된 형제
# --------------------------------------------------------------------------- #

def test_dispatch_before_place_confirm_leaves_a_reason(app):
    """'발주확인이 먼저입니다' 도 화면에 닿아야 한다 — web 은 이미 성공으로 답했다."""
    first = _link("PO-ORD-1", order_no="N-ORDER", place="OK")
    blocked = _link("PO-ORD-2", order_no="N-ORDER", place="NOT_YET")

    with pytest.raises(FulfillmentError):
        dispatch_order(db_session, _StubClient(), link_id=first)
    db_session.commit()

    # 사유는 막힌 건에만 남는다 — 이미 발주확인이 끝난 형제까지 빨갛게 만들면 안 된다.
    state = _state(blocked)
    assert "발주확인" in state["last_error"], state
    assert state["last_error_action"] == "dispatch"
    assert not _state(first).get("last_error")


def test_confirm_skips_a_sibling_already_confirmed_in_the_column(app):
    """판매자센터에서 손으로 발주확인한 형제는 다시 보내지 않는다.

    컬럼(place_order_status='OK')을 무시하면 네이버가 그 건을 실패로 돌려주고,
    실제로는 정상인데 빨간 실패 띠가 남는다(발송처리는 이미 컬럼을 본다).
    """
    first = _link("PO-COL-1", order_no="N-COL", place="NOT_YET")
    _link("PO-COL-2", order_no="N-COL", place="OK")
    client = _StubClient()

    confirm_place_order(db_session, client, link_id=first)
    db_session.commit()

    assert client.confirm_calls == [["PO-COL-1"]], client.confirm_calls


# --------------------------------------------------------------------------- #
# 6차 리뷰 — 거절 사유는 해당 건에만 / 컬럼 확인분도 자가치유
# --------------------------------------------------------------------------- #

def test_dispatch_refusal_marks_only_the_unconfirmed_ones(app):
    """'발주확인이 먼저' 사유를 집 전체에 찍으면, 이미 확인된 건까지 실패로 집힌다."""
    confirmed = _link("PO-MIX-1", order_no="N-MIX", place="OK")
    pending = _link("PO-MIX-2", order_no="N-MIX", place="NOT_YET")

    with pytest.raises(FulfillmentError):
        dispatch_order(db_session, _StubClient(), link_id=confirmed)
    db_session.commit()

    assert not _state(confirmed).get("last_error"), "발주확인이 끝난 건에 실패가 찍혔다"
    assert "발주확인" in _state(pending)["last_error"]


def test_confirm_clears_a_stale_error_for_column_confirmed_links(app):
    """판매자센터에서 손으로 발주확인한 집도 실패 띠에서 풀린다.

    컬럼만 OK 가 된 링크는 todo 에서 빠지는데, 그때 사유를 안 지우면 재전송으로 낫던
    자가치유 경로가 사라져 빨간 띠가 영구히 남는다.
    """
    link_id = _link("PO-STALE", order_no="N-STALE", place="NOT_YET")
    with pytest.raises(FulfillmentError):
        confirm_place_order(db_session, _StubClient(fail=True), link_id=link_id)
    db_session.commit()
    # 사람이 판매자센터에서 처리 → 다음 스윕이 컬럼을 OK 로 올린다.
    db_session.get(ExternalOrderLink, link_id).place_order_status = "OK"
    db_session.commit()

    result = confirm_place_order(db_session, _StubClient(), link_id=link_id)
    db_session.commit()

    assert result["confirmed"] == []
    assert not _state(link_id).get("last_error"), "낡은 실패 사유가 그대로 남았다"


def test_confirm_refuses_a_household_with_a_broken_collection(app):
    """수집이 실패·보류된 형제가 있으면 발주확인을 네이버로 보내지 않는다 (리뷰 H-B).

    화면(`_place_groups`)이 FAILED/PENDING_REVIEW 를 목록에서 빼지만 그건 화면일 뿐이다.
    `_links_of_group` 은 상태를 안 보고, 이력 탭 '워크벤치' 링크는 PENDING_REVIEW
    링크를 그대로 열어 준다 — 그 집에서 발주확인 버튼이 열렸다. 발주확인은 되돌릴 수
    없으므로 마지막 문은 서버가 닫는다.
    """
    first = _link("PO-BRK-1", order_no="N-BRK", place="NOT_YET")
    broken = _link("PO-BRK-2", order_no="N-BRK", place="NOT_YET")
    db_session.get(ExternalOrderLink, broken).sync_status = "PENDING_REVIEW"
    db_session.commit()
    client = _StubClient()

    with pytest.raises(FulfillmentError) as err:
        confirm_place_order(db_session, client, link_id=first)

    assert "수집이 완료되지 않은" in str(err.value)
    assert client.confirm_calls == [], "네이버 호출이 나갔다 — 가드가 뚫렸다"


def test_confirm_still_runs_for_a_healthy_household(app):
    """정상 수집분만 있는 집은 그대로 나간다 — 가드가 과잉 차단하면 안 된다."""
    link_id = _link("PO-OK-1", order_no="N-OKH", place="NOT_YET")
    client = _StubClient()

    confirm_place_order(db_session, client, link_id=link_id)
    db_session.commit()

    assert client.confirm_calls, "정상 집인데 호출이 안 나갔다"


# --------------------------------------------------------------------------- #
# ④ 의 마지막 한 겹 — 사유를 못 남길 때도 조용하지 않다
# --------------------------------------------------------------------------- #

def test_record_task_failure_is_not_silent_when_the_group_is_gone(app, caplog):
    """집을 못 찾아 사유를 못 남기면 **못 남겼다는 것을 로그로 남긴다**.

    `record_task_failure` 는 워커가 서비스 바깥에서 죽었을 때의 **마지막 통지 경로**다
    (docstring 이 스스로 "실패해도 조용하지 않게 한다"고 적어 뒀다). 그런데 링크 조회가
    `FulfillmentError` 면 아무 말 없이 돌아섰다 — 화면은 "요청했습니다"로 멈춰 있고
    취소는 재시도 버튼도 없으니, 그 조합이면 실패가 어디에도 안 남는다.
    """
    import logging

    from foms.services.integrations.naver_commerce.fulfillment import record_task_failure

    with caplog.at_level(logging.WARNING):
        record_task_failure(db_session, link_id=99999999,
                            action="cancel", reason="인증 만료")

    assert any("실패 사유 기록 실패" in record.getMessage()
               for record in caplog.records), "집을 못 찾은 것을 조용히 넘겼다"
