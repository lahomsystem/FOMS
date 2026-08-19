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
          status: str = "COLLECTED") -> int:
    product_order = {"productOrderId": external_id, "productName": "로라 무몰딩 1cm"}
    if claim:
        product_order["claimStatus"] = claim
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
