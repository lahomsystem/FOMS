"""R3 (스펙 2026-08-24 §6): 붙이기·되돌리기가 **주문 변경 이력**에 남는지.

2026-08-19 스펙 §7 Q3("재결제 시 원 주문의 취소를 어떻게 남기나")의 답이 안 B 다 —
주문 상태는 한 글자도 바꾸지 않고 ``OrderEvent`` 1건만 남긴다. 08-19 §3.3 이 이미
약속했는데 ``log_access`` 만 구현되고 ``OrderEvent`` 는 빠져 있었다.

**이 파일의 부정 단언이 본체다.** ``translate_event_type_to_korean`` 의 기본값이
``"기타 변경"``(``foms/services/order_event_display.py``)이라, 라벨 사전 등재를 빼먹으면
화면에는 영문 코드가 아니라 **한글 "기타 변경"** 이 뜬다 — "한글로 보인다" 류 완료 기준으로는
절대 못 잡는다. 그래서 긍정 단언 옆에 항상 ``"기타 변경" not in ...`` 을 함께 건다.

주문·링크는 실제 행으로 만든다(999999 류 금지 — 로컬 SQLite 는 FK 미강제, CI 는 강제).
"""

from __future__ import annotations

from db import db_session
from models import ExternalOrderLink, Order, OrderEvent

ATTACH_LABEL = "네이버 수집분 연결"
DETACH_LABEL = "네이버 수집분 연결 해제"
FALLBACK_LABEL = "기타 변경"


def _order(name: str, phone: str) -> int:
    """이력을 붙일 실제 FOMS 주문 1건."""
    order = Order(received_date="2026-08-01", customer_name=name, phone=phone,
                  address="서울시 강남구 테헤란로 152", product="붙박이장", status="RECEIVED")
    db_session.add(order)
    db_session.commit()
    return int(order.id)


def _link(external_id: str, *, order_no: str, amount: int = 0) -> int:
    """수집 링크 1건(금액은 ``totalPaymentAmount`` 원문으로 넣는다)."""
    product_order = {"productOrderId": external_id, "productName": "로라 무몰딩 1cm"}
    if amount:
        product_order["totalPaymentAmount"] = amount
    link = ExternalOrderLink(
        channel="NAVER", external_id=external_id, external_order_no=order_no,
        sync_status="COLLECTED",
        raw_snapshot={"order": {"orderId": order_no}, "productOrder": product_order},
    )
    db_session.add(link)
    db_session.commit()
    return int(link.id)


def _events(order_id: int) -> list[OrderEvent]:
    """그 주문의 이벤트를 시간순으로 다시 읽는다(요청이 자기 세션에서 커밋한다)."""
    db_session.expire_all()
    return (db_session.query(OrderEvent)
            .filter(OrderEvent.order_id == order_id)
            .order_by(OrderEvent.id.asc()).all())


def _change_log_labels(auth_client, order_id: int) -> list[str]:
    """관리자 `변경 로그` 가 실제로 그리는 라벨(``what_label``) 목록."""
    response = auth_client.get(f"/api/orders/{order_id}/change-events")
    assert response.status_code == 200
    body = response.get_json()
    assert body["success"] is True
    return [row["what_label"] for row in body["events"]]


def test_attach_leaves_one_order_event(auth_client):
    """붙이면 이력 1건 — 무엇이 얼마 붙었는지가 payload 에 있다."""
    order_id = _order("이력붙임", "010-7777-1111")
    link_id = _link("PO-EVT-A1", order_no="N-EVT-A", amount=94900)

    response = auth_client.post(f"/admin/naver-ingest/{link_id}/attach",
                                json={"order_id": order_id, "relation": "REPAY"})
    assert response.status_code == 200, response.get_data(as_text=True)

    events = _events(order_id)
    assert len(events) == 1, f"붙이기 이력이 1건이 아니다: {[e.event_type for e in events]}"
    event = events[0]
    assert event.event_type == "NAVER_ORDER_ATTACHED"
    assert event.payload["relation"] == "REPAY"
    assert event.payload["external_order_no"] == "N-EVT-A"
    assert event.payload["product_order_count"] == 1
    assert event.payload["amount_total"] == 94900

    # /api/orders/<N>/events 로도 같은 1건이 보인다.
    stream = auth_client.get(f"/api/orders/{order_id}/events")
    assert stream.status_code == 200
    types = [row["event_type"] for row in stream.get_json()["events"]]
    assert types == ["NAVER_ORDER_ATTACHED"]


def test_attach_event_reads_as_korean_label_not_fallback(auth_client):
    """관리자 `변경 로그` 에 정확히 `네이버 수집분 연결` 로 뜬다.

    부정 단언이 핵심이다 — 라벨 사전에서 타입을 빼면 이 테스트가 `기타 변경` 때문에 red 가
    된다(빼먹은 걸 눈으로는 못 잡는다).
    """
    order_id = _order("라벨확인", "010-7777-2222")
    link_id = _link("PO-EVT-L1", order_no="N-EVT-L", amount=12000)
    auth_client.post(f"/admin/naver-ingest/{link_id}/attach",
                     json={"order_id": order_id, "relation": "ADDON"})

    labels = _change_log_labels(auth_client, order_id)
    assert labels == [ATTACH_LABEL], f"변경 로그 라벨이 다르다: {labels}"
    assert FALLBACK_LABEL not in labels, (
        f"라벨 사전 미등재로 '{FALLBACK_LABEL}' 로 뭉개졌다: {labels}")

    # 관리자 `변경 로그` 화면이 실제로 부르는 엔드포인트(templates/admin/change_logs.html).
    mine = auth_client.get("/api/me/change-events?limit=200")
    assert mine.status_code == 200
    rows = [row for row in mine.get_json()["events"] if row["order_id"] == order_id]
    screen_labels = [row["what_label"] for row in rows]
    assert screen_labels == [ATTACH_LABEL], f"변경 로그 화면 라벨이 다르다: {screen_labels}"
    assert FALLBACK_LABEL not in screen_labels, (
        f"라벨 사전 미등재로 '{FALLBACK_LABEL}' 로 뭉개졌다: {screen_labels}")
    # 08-19 §3.3 이 약속한 "무엇이 얼마" 문장.
    assert "네이버 추가결제" in rows[0]["how_text"]
    assert "12,000원" in rows[0]["how_text"]


def test_detach_appends_and_keeps_the_attach_event(auth_client):
    """되돌려도 붙임 이력은 살아 있다 — append-only(금액 기록만 걷어낸다)."""
    order_id = _order("이력되돌림", "010-7777-3333")
    link_id = _link("PO-EVT-D1", order_no="N-EVT-D", amount=55000)
    auth_client.post(f"/admin/naver-ingest/{link_id}/attach",
                     json={"order_id": order_id, "relation": "REPAY"})

    response = auth_client.post(f"/admin/naver-ingest/{link_id}/detach")
    assert response.status_code == 200, response.get_data(as_text=True)

    events = _events(order_id)
    assert [e.event_type for e in events] == ["NAVER_ORDER_ATTACHED",
                                              "NAVER_ORDER_DETACHED"], (
        "붙임 이벤트가 사라졌거나 해제 이벤트가 없다")
    detached = events[1]
    assert detached.payload["relation"] == "REPAY"
    assert detached.payload["external_order_no"] == "N-EVT-D"
    assert detached.payload["product_order_count"] == 1
    assert detached.payload["amount_total"] == 55000
    # 금액 기록은 걷어냈지만 이력은 남는다.
    pricing = (db_session.get(Order, order_id).structured_data or {}).get("pricing") or {}
    assert pricing.get("extra_payments") == []

    labels = _change_log_labels(auth_client, order_id)
    assert sorted(labels) == sorted([ATTACH_LABEL, DETACH_LABEL]), f"라벨이 다르다: {labels}"
    assert FALLBACK_LABEL not in labels, (
        f"라벨 사전 미등재로 '{FALLBACK_LABEL}' 로 뭉개졌다: {labels}")


def test_attach_history_counts_the_whole_household(auth_client):
    """집이 통째로 붙으므로 건수·금액도 집 전체다 — 한 건만 세면 이력이 거짓말을 한다."""
    order_id = _order("집전체", "010-7777-4444")
    first_id = _link("PO-EVT-H1", order_no="N-EVT-H", amount=100000)
    _link("PO-EVT-H2", order_no="N-EVT-H", amount=23500)

    auth_client.post(f"/admin/naver-ingest/{first_id}/attach",
                     json={"order_id": order_id, "relation": "ADDON"})

    payload = _events(order_id)[0].payload
    assert payload["product_order_count"] == 2
    assert payload["amount_total"] == 123500
