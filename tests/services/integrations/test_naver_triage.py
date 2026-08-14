"""NAVER-INGEST-01 T9·T10: 트리아지 작업대 + 담당자 지정 계약 테스트.

고정하는 것:

* 큐에는 **확인 대기(`reviewed_at IS NULL`)한 `LINKED` 건만** 뜬다.
* "확인 완료"는 사람이 누른 사실만 기록한다 — 시스템이 "다 채웠는지" 추측하지 않는다.
* 담당자 지정은 `set_sales_assignee()` 경유라 owner 교체·이벤트가 따라온다
  (`OrderAssignment` 직접 생성 금지).
"""

from __future__ import annotations

from db import db_session
from foms.services.orders.order_create import create_order
from models import ExternalOrderLink, SecurityLog, User

_SEQ = [0]


def _uid() -> str:
    _SEQ[0] += 1
    return str(_SEQ[0])


def _sales(name: str = "영업") -> User:
    user = User(username=f"sales_{_uid()}", password="pw-not-committed", name=name,
                role="STAFF", team="SALES", is_active=True)
    db_session.add(user)
    db_session.commit()
    return user


def _ingested_order(owner: User, *, reviewed: bool = False,
                    memo: str = "") -> ExternalOrderLink:
    """수집 주문 1건 + 링크를 만든다(수집 파이프라인이 만드는 모양)."""
    order = create_order(
        db_session,
        actor_user_id=owner.id, owner_user_id=owner.id,
        order_fields=dict(received_date="2026-08-13", customer_name="이수취",
                          phone="010-3333-4444", address="서울 강남구 1 101호",
                          product="붙박이장", options="색상: 화이트 / 폭: 2400",
                          status="RECEIVED"),
        structured_data={"source": "NAVER_SMARTSTORE"},
        is_erp_order=True,
    )
    db_session.flush()
    link = ExternalOrderLink(
        channel="NAVER", external_id=f"PO-{_uid()}", order_id=order.id,
        sync_status="LINKED",
        raw_snapshot={
            "order": {"orderId": "1", "ordererName": "김주문", "ordererTel": "010-1111-2222"},
            "productOrder": {
                "productOrderId": "PO-1", "productName": "붙박이장",
                "productOption": "색상: 화이트 / 폭: 2400", "totalPaymentAmount": 1250000,
                "sellerProductCode": "LAHOM-1", "shippingDueDate": "2026-08-20",
                "shippingMemo": memo,
                "shippingAddress": {"name": "이수취", "tel1": "010-3333-4444",
                                    "baseAddress": "서울 강남구 1", "detailedAddress": "101호"},
            },
        },
    )
    if reviewed:
        from foms.services.datetime_kst import now_utc_naive

        link.reviewed_at = now_utc_naive()
    db_session.add(link)
    db_session.commit()
    return link


# --------------------------------------------------------------------------- #
# 큐 (T9)
# --------------------------------------------------------------------------- #

def test_triage_requires_admin(app, client):
    """원본에 실번호·주소가 있어 비로그인은 접근 불가."""
    assert client.get("/admin/naver-ingest/triage").status_code in (301, 302, 401, 403)


def test_queue_shows_only_unreviewed_linked_rows(auth_client):
    """확인 완료분과 보류/실패 건은 큐에 뜨지 않는다."""
    owner = _sales()
    pending = _ingested_order(owner)
    done = _ingested_order(owner, reviewed=True)
    db_session.add(ExternalOrderLink(channel="NAVER", external_id="PO-HOLD",
                                     sync_status="PENDING_REVIEW"))
    db_session.commit()

    pending_id, done_id = pending.external_id, done.external_id
    body = auth_client.get("/admin/naver-ingest/triage").get_data(as_text=True)
    assert pending_id in body
    assert done_id not in body
    assert "PO-HOLD" not in body


def test_option_text_is_shown_prominently(auth_client):
    """옵션 원문이 이 화면의 존재 이유다 — v1 은 규격을 파싱하지 않는다."""
    _ingested_order(_sales())
    body = auth_client.get("/admin/naver-ingest/triage").get_data(as_text=True)
    assert "색상: 화이트 / 폭: 2400" in body
    assert "네이버 옵션 원문" in body


def test_pane_compares_naver_original_with_foms_values(auth_client):
    """원본과 FOMS 현재 값을 나란히 보여줘야 무엇이 어긋났는지 사람이 판단한다."""
    _ingested_order(_sales())
    body = auth_client.get("/admin/naver-ingest/triage").get_data(as_text=True)
    assert "네이버 원본" in body and "FOMS 현재 값" in body
    assert "김주문" in body  # 주문자(수취인과 다름)도 보여야 한다
    assert "LAHOM-1" in body


def test_pane_shows_shipping_memo_from_product_order(auth_client):
    """배송메모는 productOrder.shippingMemo 에 있다 — 원본에서 읽으므로 과거 수집분도
    재처리 없이 그대로 보인다(2026-08-14 실필드 확인)."""
    _ingested_order(_sales(), memo="문 앞에 놓아주세요")
    body = auth_client.get("/admin/naver-ingest/triage").get_data(as_text=True)
    assert "배송 메모" in body and "문 앞에 놓아주세요" in body


def test_pane_links_to_the_order_editor_not_a_second_spec_form(auth_client):
    """규격 입력은 편집기가 SSOT — 작업대는 링크만 준다(계산 규칙 이중화 방지)."""
    link = _ingested_order(_sales())
    body = auth_client.get("/admin/naver-ingest/triage").get_data(as_text=True)
    assert f"/edit_order/{link.order_id}" in body or f"order_id={link.order_id}" in body \
        or f"/{link.order_id}" in body
    assert "주문 열어서 규격 채우기" in body


def test_empty_queue_is_explicit(auth_client):
    """빈 화면이 아니라 '확인할 주문이 없습니다'로 말해야 한다."""
    body = auth_client.get("/admin/naver-ingest/triage").get_data(as_text=True)
    assert "확인할 주문이 없습니다" in body


# --------------------------------------------------------------------------- #
# 확인 완료 (T9)
# --------------------------------------------------------------------------- #

def test_mark_reviewed_removes_row_from_queue(auth_client):
    """확인 완료를 누르면 큐에서 빠진다."""
    link = _ingested_order(_sales())
    link_id, external_id = link.id, link.external_id
    response = auth_client.post(f"/admin/naver-ingest/{link_id}/review", json={})
    assert response.status_code == 200 and response.get_json()["success"] is True

    db_session.expire_all()
    assert db_session.get(ExternalOrderLink, link_id).reviewed_at is not None
    body = auth_client.get("/admin/naver-ingest/triage").get_data(as_text=True)
    assert external_id not in body


def test_mark_reviewed_records_who_did_it(auth_client):
    """누가 확인했는지 남아야 나중에 물어볼 수 있다."""
    link_id = _ingested_order(_sales()).id
    auth_client.post(f"/admin/naver-ingest/{link_id}/review", json={})
    db_session.expire_all()
    assert db_session.get(ExternalOrderLink, link_id).reviewed_by_user_id is not None


def test_second_review_does_not_overwrite_the_first(auth_client):
    """첫 확인 시각이 기록이다 — 재요청이 시각을 덮으면 이력이 사라진다."""
    link_id = _ingested_order(_sales()).id
    auth_client.post(f"/admin/naver-ingest/{link_id}/review", json={})
    db_session.expire_all()
    first = db_session.get(ExternalOrderLink, link_id).reviewed_at
    auth_client.post(f"/admin/naver-ingest/{link_id}/review", json={})
    db_session.expire_all()
    assert db_session.get(ExternalOrderLink, link_id).reviewed_at == first


def test_mark_reviewed_is_audited(auth_client):
    """쓰기 라우트는 감사 원장에 남는다."""
    link_id = _ingested_order(_sales()).id
    auth_client.post(f"/admin/naver-ingest/{link_id}/review", json={})
    actions = [row.action for row in db_session.query(SecurityLog).all()]
    assert "NAVER_INGEST_MARK_REVIEWED" in actions


def test_review_404_for_unknown_link(auth_client):
    """없는 이력은 조용히 성공하지 않는다."""
    assert auth_client.post("/admin/naver-ingest/999999/review", json={}).status_code == 404


def test_staff_can_mark_reviewed(app, client):
    """T14-A: 규격을 실제로 입력하는 STAFF 가 확인 완료를 직접 누를 수 있다."""
    from werkzeug.security import generate_password_hash

    staff = User(username=f"triage_staff_{_uid()}", password=generate_password_hash("pw"),
                 role="STAFF", team="CS", name="접수 담당", is_active=True)
    db_session.add(staff)
    db_session.commit()
    staff_id = staff.id
    with client.session_transaction() as sess:
        sess["user_id"] = staff_id
        sess["username"] = staff.username
        sess["role"] = staff.role

    link_id = _ingested_order(_sales()).id
    response = client.post(f"/admin/naver-ingest/{link_id}/review", json={})

    assert response.status_code == 200 and response.get_json()["success"] is True
    db_session.expire_all()
    assert db_session.get(ExternalOrderLink, link_id).reviewed_by_user_id == staff_id


# --------------------------------------------------------------------------- #
# 담당자 지정 (T10)
# --------------------------------------------------------------------------- #

def test_assignee_route_wiring_calls_canonical_service_and_audits(auth_client, monkeypatch):
    """라우트는 canonical 서비스를 부르고 감사 기록을 남긴다.

    **owner 교체 자체는 PG 레인 계약**이다(``tests/postgres/test_naver_triage_assignment.py``) —
    SALES active-owner 유일성은 ``postgresql_where`` 부분 유니크라 SQLite 레인에서는
    전체 유니크가 되어 교체가 성립하지 않는다. 여기서는 라우트 배선만 고정한다.
    """
    order_id = _ingested_order(_sales("미배정")).order_id
    real_id = _sales("실제담당").id
    seen: dict = {}

    def _fake(session, **kwargs):
        seen.update(kwargs)
        return None

    monkeypatch.setattr("foms.services.orders.assignment.set_sales_assignee", _fake)
    response = auth_client.post(f"/admin/naver-ingest/{order_id}/assignee",
                                json={"user_id": real_id})
    assert response.status_code == 200 and response.get_json()["success"] is True
    assert seen["order_id"] == order_id and seen["user_id"] == real_id
    # 보류함에서 실제 담당자로 옮기는 것은 교체라 사유가 필수다 — 화면이 안 보내므로 서버가 채운다.
    assert seen["reason"]
    assert seen["scope_hash"] and seen["request_hash"]
    actions = [row.action for row in db_session.query(SecurityLog).all()]
    assert "NAVER_INGEST_SET_ASSIGNEE" in actions


def test_assignee_rejects_missing_user_id(auth_client):
    """담당자 없이 부르면 400 — 조용히 아무 일도 안 하지 않는다."""
    link = _ingested_order(_sales())
    response = auth_client.post(f"/admin/naver-ingest/{link.order_id}/assignee", json={})
    assert response.status_code == 400
    assert response.get_json()["success"] is False


def test_assignee_rejects_non_sales_user(auth_client):
    """SALES 가 아닌 사람은 담당자가 될 수 없다(배정 계약)."""
    link = _ingested_order(_sales())
    drawing = User(username=f"draw_{_uid()}", password="pw-not-committed", name="도면",
                   role="STAFF", team="DRAWING", is_active=True)
    db_session.add(drawing)
    db_session.commit()
    response = auth_client.post(f"/admin/naver-ingest/{link.order_id}/assignee",
                                json={"user_id": drawing.id})
    assert response.status_code >= 400
    assert response.get_json()["success"] is False


def test_holding_account_is_not_offered_as_an_assignee(auth_client):
    """보류함 계정을 담당자로 고를 수 있으면 미배정이 해소되지 않는다."""
    from foms.services.integrations.naver_commerce.ingest import OWNER_USERNAME

    db_session.add(User(username=OWNER_USERNAME, password="pw-not-committed",
                        name="미배정 (네이버 수집)", role="STAFF", team="SALES",
                        is_active=True))
    db_session.commit()
    _ingested_order(_sales("진짜영업"))
    body = auth_client.get("/admin/naver-ingest/triage").get_data(as_text=True)
    assert "진짜영업" in body
    assert "미배정 (네이버 수집)" not in body
