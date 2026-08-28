"""NAVER-INGEST-02 T16-E: 기존 주문에 붙이기(attach)·되돌리기(detach) 계약.

붙이기는 **돈이 남의 집에 섞일 수 있는** 조작이다. 그래서 계약이 셋이다:
① 묶음 전체가 함께 움직인다 ② 취소 건은 추가결제로 못 붙인다 ③ 되돌릴 수 있다.

요청은 자기 세션에서 커밋하므로, 검증은 항상 **id 로 다시 읽어서** 한다
(``db_session.refresh`` 는 요청 뒤 detach 된 인스턴스에서 죽는다).
"""

from __future__ import annotations

from db import db_session
from models import ExternalOrderLink, Order, SecurityLog


def _fresh(link_id: int) -> ExternalOrderLink:
    """요청 뒤 DB 상태를 다시 읽는다."""
    db_session.expire_all()
    return db_session.get(ExternalOrderLink, link_id)


def _order(name: str = "김고객", phone: str = "010-1111-2222") -> int:
    order = Order(received_date="2026-08-01", customer_name=name, phone=phone,
                  address="서울시 강남구 테헤란로 152", product="붙박이장", status="RECEIVED")
    db_session.add(order)
    db_session.commit()
    return int(order.id)


def _link(external_id: str, *, order_no: str = "N-ATT", claim: str = "",
          status: str = "COLLECTED", address: str = "", tel: str = "") -> int:
    """수집 링크 1건. ``address``/``tel`` 을 주면 분할배송(같은 주문번호·다른 집)이 된다."""
    product_order = {"productOrderId": external_id, "productName": "로라 무몰딩 1cm"}
    if claim:
        product_order["claimStatus"] = claim
    if address or tel:
        product_order["shippingAddress"] = {"name": "이수취", "tel1": tel,
                                            "baseAddress": address, "detailedAddress": ""}
    link = ExternalOrderLink(
        channel="NAVER", external_id=external_id, external_order_no=order_no,
        sync_status=status,
        raw_snapshot={"order": {"orderId": order_no}, "productOrder": product_order},
    )
    db_session.add(link)
    db_session.commit()
    return int(link.id)


def test_attach_puts_the_whole_group_on_the_existing_order(auth_client):
    """한 집은 통째로 움직인다 — 한 건만 붙으면 나머지가 미아가 된다."""
    order_id = _order()
    first_id = _link("PO-A1")
    second_id = _link("PO-A2")

    response = auth_client.post(f"/admin/naver-ingest/{first_id}/attach",
                                json={"order_id": order_id, "relation": "ADDON"})
    assert response.status_code == 200
    assert response.get_json()["success"] is True

    first, second = _fresh(first_id), _fresh(second_id)
    assert first.order_id == order_id and second.order_id == order_id
    assert first.relation == "ADDON" and second.relation == "ADDON"
    assert first.sync_status == "LINKED"


def test_attach_is_idempotent(auth_client):
    """두 번 눌러도 결과가 같다(새로고침 재전송 방어)."""
    order_id = _order()
    link_id = _link("PO-IDEM", order_no="N-IDEM")
    url = f"/admin/naver-ingest/{link_id}/attach"
    body = {"order_id": order_id, "relation": "ADDON"}

    assert auth_client.post(url, json=body).status_code == 200
    assert auth_client.post(url, json=body).status_code == 200
    assert _fresh(link_id).order_id == order_id


def test_attach_rejects_cancelled_group_as_addon(auth_client):
    """취소·반품 건은 추가결제로 붙일 수 없다(서버가 정본 가드)."""
    order_id = _order()
    link_id = _link("PO-CANCEL", order_no="N-CANCEL", claim="CANCEL_DONE")

    response = auth_client.post(f"/admin/naver-ingest/{link_id}/attach",
                                json={"order_id": order_id, "relation": "ADDON"})
    assert response.status_code == 400
    assert "취소" in response.get_json()["error"]
    assert _fresh(link_id).order_id is None


def test_repay_is_allowed_on_cancelled_group(auth_client):
    """재결제는 원 주문이 취소된 경우라 허용한다."""
    order_id = _order()
    link_id = _link("PO-REPAY", order_no="N-REPAY", claim="CANCEL_DONE")

    response = auth_client.post(f"/admin/naver-ingest/{link_id}/attach",
                                json={"order_id": order_id, "relation": "REPAY"})
    assert response.status_code == 200
    assert _fresh(link_id).relation == "REPAY"


def test_attach_rejects_unknown_relation(auth_client):
    """관계값은 닫힌집합이다 — NEW 는 붙이기가 아니라 주문 생성 경로다."""
    order_id = _order()
    link_id = _link("PO-BADREL", order_no="N-BADREL")
    for relation in ("NEW", "", "WHATEVER"):
        response = auth_client.post(f"/admin/naver-ingest/{link_id}/attach",
                                    json={"order_id": order_id, "relation": relation})
        assert response.status_code == 400


def test_attach_rejects_deleted_order(auth_client):
    """휴지통 주문에는 붙이지 않는다."""
    order_id = _order()
    order = db_session.get(Order, order_id)
    order.deleted_at = "2026-08-10"
    db_session.commit()
    link_id = _link("PO-DELORD", order_no="N-DELORD")

    response = auth_client.post(f"/admin/naver-ingest/{link_id}/attach",
                                json={"order_id": order_id, "relation": "ADDON"})
    assert response.status_code == 400


def test_attach_refuses_when_already_on_another_order(auth_client):
    """이미 다른 주문에 붙어 있으면 조용히 옮기지 않는다 — 되돌린 뒤 다시 붙인다."""
    first_order_id = _order()
    other_order_id = _order(name="다른고객", phone="010-3333-4444")
    link_id = _link("PO-MOVE", order_no="N-MOVE")
    auth_client.post(f"/admin/naver-ingest/{link_id}/attach",
                     json={"order_id": first_order_id, "relation": "ADDON"})

    response = auth_client.post(f"/admin/naver-ingest/{link_id}/attach",
                                json={"order_id": other_order_id, "relation": "ADDON"})
    assert response.status_code == 400
    assert _fresh(link_id).order_id == first_order_id


def test_detach_restores_collected_state(auth_client):
    """되돌리면 수집 직후 상태로 온전히 돌아간다."""
    order_id = _order()
    link_id = _link("PO-UNDO", order_no="N-UNDO")
    auth_client.post(f"/admin/naver-ingest/{link_id}/attach",
                     json={"order_id": order_id, "relation": "ADDON"})

    response = auth_client.post(f"/admin/naver-ingest/{link_id}/detach")
    assert response.status_code == 200
    after = _fresh(link_id)
    assert after.order_id is None
    assert after.relation == "NEW"
    assert after.sync_status == "COLLECTED"


def test_detach_refuses_promoted_links(auth_client):
    """주문 생성분(NEW)은 되돌리지 않는다 — 그건 주문 삭제 문제다."""
    order_id = _order()
    link_id = _link("PO-PROMOTED", order_no="N-PROMOTED", status="LINKED")
    link = db_session.get(ExternalOrderLink, link_id)
    link.order_id = order_id
    db_session.commit()

    response = auth_client.post(f"/admin/naver-ingest/{link_id}/detach")
    assert response.status_code == 400
    assert _fresh(link_id).order_id == order_id


def test_attach_is_audited(auth_client):
    """누가 어느 주문에 무엇을 붙였는지 남는다."""
    order_id = _order()
    link_id = _link("PO-AUDIT", order_no="N-AUDIT")
    auth_client.post(f"/admin/naver-ingest/{link_id}/attach",
                     json={"order_id": order_id, "relation": "ADDON"})

    logs = db_session.query(SecurityLog).filter(
        SecurityLog.action == "NAVER_INGEST_ATTACH_ORDER").all()
    assert logs, "붙이기 감사 로그가 없다"


def test_attach_requires_login(client):
    """비로그인 차단."""
    response = client.post("/admin/naver-ingest/1/attach",
                           json={"order_id": 1, "relation": "ADDON"})
    assert response.status_code in (301, 302, 401, 403)


def test_triage_pane_offers_existing_order_candidates(auth_client):
    """확인 화면이 기존 주문 후보와 붙이기 버튼을 보여준다 (T16-D)."""
    order = Order(received_date="2026-08-01", customer_name="후보고객",
                  phone="010-2222-3333", erp_phone_digits="01022223333",
                  address="서울시 송파구 올림픽로 300", product="붙박이장", status="RECEIVED")
    db_session.add(order)
    db_session.commit()
    order_id = int(order.id)

    link = ExternalOrderLink(
        channel="NAVER", external_id="PO-UI-CAND", external_order_no="N-UI-CAND",
        sync_status="COLLECTED",
        raw_snapshot={"order": {"orderId": "N-UI-CAND", "ordererTel": "010-2222-3333"},
                      "productOrder": {"productOrderId": "PO-UI-CAND",
                                       "productName": "로라 무몰딩 1cm",
                                       "shippingAddress": {"name": "후보고객",
                                                           "tel1": "010-2222-3333",
                                                           "baseAddress": "서울시 송파구 올림픽로 300",
                                                           "detailedAddress": ""}}},
    )
    db_session.add(link)
    db_session.commit()

    body = auth_client.get(f"/admin/naver-ingest/triage?link_id={link.id}").get_data(as_text=True)
    assert "이 고객의 기존 주문" in body
    assert "추가결제로 붙이기" in body
    assert f'data-order-id="{order_id}"' in body


def test_attached_link_shows_undo_control(auth_client):
    """붙인 뒤에는 무엇에 붙었는지와 되돌리기가 보인다."""
    order_id = _order(name="되돌림고객", phone="010-4444-5555")
    link_id = _link("PO-UI-UNDO", order_no="N-UI-UNDO")
    auth_client.post(f"/admin/naver-ingest/{link_id}/attach",
                     json={"order_id": order_id, "relation": "ADDON"})

    body = auth_client.get(f"/admin/naver-ingest/triage?link_id={link_id}").get_data(as_text=True)
    assert "되돌리기" in body
    assert f"주문 #{order_id}" in body


def test_persistent_pane_alerts_opt_out_of_autodismiss(auth_client):
    """확인 화면의 상시 안내는 5초 자동 닫힘에서 빠져야 한다.

    ``static/js/runtime/script.js`` 가 로드 5초 뒤 모든 ``.alert`` 를 닫는다. 후보·붙임 상태·
    발주 상태·취소 경고는 사용자가 보고 판단해야 하는 정보라 사라지면 안 된다
    (2026-08-19 스테이징 실측: 후보 블록이 통째로 증발했다).
    """
    order_id = _order(name="상시안내", phone="010-8888-7777")
    link_id = _link("PO-PERSIST", order_no="N-PERSIST")
    auth_client.post(f"/admin/naver-ingest/{link_id}/attach",
                     json={"order_id": order_id, "relation": "ADDON"})

    body = auth_client.get(f"/admin/naver-ingest/triage?link_id={link_id}").get_data(as_text=True)
    pane = body[body.index("붙어 있습니다") - 800:body.index("붙어 있습니다")]
    assert "data-foms-no-autodismiss" in pane


def _pricing(order_id: int) -> dict:
    db_session.expire_all()
    data = db_session.get(Order, order_id).structured_data or {}
    return data.get("pricing") or {}


def test_attach_records_payment_without_touching_totals(auth_client):
    """추가결제는 **기록만** 한다 — 출고가·잔금·계약금을 자동으로 바꾸지 않는다 (T16-F)."""
    order_id = _order(name="기록고객", phone="010-6666-1111")
    order = db_session.get(Order, order_id)
    order.structured_data = {"pricing": {"deposit": 100000, "balance": 400000},
                             "totals": {"items_total": 500000}}
    db_session.commit()

    link_id = _link("PO-PAY-REC", order_no="N-PAY-REC")
    link = db_session.get(ExternalOrderLink, link_id)
    link.raw_snapshot = {
        "order": {"orderId": "N-PAY-REC", "paymentDate": "2026-08-19T10:16:00.000+09:00"},
        "productOrder": {"productOrderId": "PO-PAY-REC", "productName": "로라 1cm",
                         "totalPaymentAmount": 94900},
    }
    db_session.commit()

    auth_client.post(f"/admin/naver-ingest/{link_id}/attach",
                     json={"order_id": order_id, "relation": "ADDON"})

    pricing = _pricing(order_id)
    assert pricing["deposit"] == 100000, "계약금이 바뀌면 안 된다"
    assert pricing["balance"] == 400000, "잔금이 바뀌면 안 된다"
    entries = pricing["extra_payments"]
    assert len(entries) == 1
    assert entries[0]["amount"] == 94900
    assert entries[0]["relation"] == "ADDON"
    assert entries[0]["external_id"] == "PO-PAY-REC"


def test_attach_twice_does_not_double_record(auth_client):
    """두 번 눌러도 금액이 두 번 쌓이면 안 된다."""
    order_id = _order(name="멱등고객", phone="010-6666-2222")
    link_id = _link("PO-PAY-IDEM", order_no="N-PAY-IDEM")
    body = {"order_id": order_id, "relation": "ADDON"}
    auth_client.post(f"/admin/naver-ingest/{link_id}/attach", json=body)
    auth_client.post(f"/admin/naver-ingest/{link_id}/attach", json=body)

    assert len(_pricing(order_id)["extra_payments"]) == 1


def test_detach_removes_the_payment_record(auth_client):
    """되돌리면 기록도 걷어낸다 — 안 지우면 되돌린 금액이 주문에 남는다."""
    order_id = _order(name="되돌림기록", phone="010-6666-3333")
    link_id = _link("PO-PAY-UNDO", order_no="N-PAY-UNDO")
    auth_client.post(f"/admin/naver-ingest/{link_id}/attach",
                     json={"order_id": order_id, "relation": "ADDON"})
    assert _pricing(order_id)["extra_payments"]

    auth_client.post(f"/admin/naver-ingest/{link_id}/detach")
    assert _pricing(order_id)["extra_payments"] == []


def test_attach_stays_inside_the_household_on_split_shipment(auth_client):
    """분할배송에서 A집을 붙여도 B집은 그대로 남는다.

    주문번호로만 묶으면 B집 링크까지 남의 주문으로 넘어가고 큐에서 사라진다 —
    발주확인에서 고친 것과 같은 결함이 붙이기 경로에 남아 있었다.
    """
    order_id = _order()
    a_first = _link("PO-SPA-1", order_no="N-ATT-SPLIT",
                    address="서울 강남구 1", tel="010-1111-1111")
    a_second = _link("PO-SPA-2", order_no="N-ATT-SPLIT",
                     address="서울 강남구 1", tel="010-1111-1111")
    b_only = _link("PO-SPB-1", order_no="N-ATT-SPLIT",
                   address="부산 해운대구 9", tel="010-2222-2222")

    response = auth_client.post(f"/admin/naver-ingest/{a_first}/attach",
                                json={"order_id": order_id, "relation": "ADDON"})

    assert response.status_code == 200, response.get_data(as_text=True)
    assert _fresh(a_first).order_id == order_id
    assert _fresh(a_second).order_id == order_id
    assert _fresh(b_only).order_id is None, "옆 집이 남의 주문으로 넘어갔다"
    assert _fresh(b_only).sync_status == "COLLECTED"


def _order_sd(order_id: int) -> dict:
    """요청 뒤 주문의 structured_data 를 다시 읽는다."""
    db_session.expire_all()
    return db_session.get(Order, order_id).structured_data or {}


def test_attach_opens_the_dock_gate(auth_client):
    """붙이면 도크 렌더 게이트가 켜진다 — 없으면 결과를 볼 자리가 없다.

    주문 편집 화면은 게이트가 참일 때만 네이버 원본 도크를 렌더하고
    (``foms/web/orders/edit.py``), 붙이기가 기록한 추가결제를 읽는 코드는 그 도크
    하나뿐이다. 게이트가 없으면 붙이기는 성공했는데 화면은 빈손이다 —
    2026-08-24 스테이징 실사례(주문 4485: REPAY 6건·1,610,780원 기록, 화면 아무것도 없음).

    2026-08-28 이전에는 이 자리가 출처 키(``source``)를 찍었다. 출처와 게이트를 가른
    뒤로는 ``naver_linked`` 가 그 몫이다(설계서 §7, NVREPAY-06 은
    ``test_naver_origin_marker_split.py``).
    """
    order_id = _order()
    assert "naver_linked" not in _order_sd(order_id), "사전 조건: 게이트 꺼진 주문"
    link_id = _link("PO-SRC-1")

    response = auth_client.post(f"/admin/naver-ingest/{link_id}/attach",
                                json={"order_id": order_id, "relation": "REPAY"})

    assert response.status_code == 200, response.get_data(as_text=True)
    assert _order_sd(order_id).get("naver_linked") is True


def test_attach_records_money_where_the_screen_can_read_it(auth_client):
    """게이트와 금액 기록이 **같은 저장에서** 함께 남는다(한쪽만 남으면 또 빈손이다)."""
    order_id = _order()
    link_id = _link("PO-SRC-2")

    auth_client.post(f"/admin/naver-ingest/{link_id}/attach",
                     json={"order_id": order_id, "relation": "REPAY"})

    data = _order_sd(order_id)
    assert data.get("naver_linked") is True
    assert isinstance(data.get("pricing", {}).get("extra_payments"), list)
    assert data["pricing"]["extra_payments"], "붙였는데 결제 기록이 비었다"


def test_attach_never_touches_an_existing_source(auth_client):
    """다른 채널 표식은 건드리지 않는다 — 덮으면 그 주문의 출처가 거짓이 된다.

    붙이기는 이제 출처 키를 **아예 쓰지 않으므로** 값이 무엇이든 그대로 남는다.
    켜지는 것은 게이트뿐이다.
    """
    order_id = _order()
    order = db_session.get(Order, order_id)
    order.structured_data = {"source": "OTHER_CHANNEL"}
    db_session.commit()
    link_id = _link("PO-SRC-3")

    auth_client.post(f"/admin/naver-ingest/{link_id}/attach",
                     json={"order_id": order_id, "relation": "ADDON"})

    data = _order_sd(order_id)
    assert data.get("source") == "OTHER_CHANNEL"
    assert data.get("naver_linked") is True
