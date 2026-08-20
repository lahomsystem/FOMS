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


def _collected_link(*, order_no: str, product: str, amount: int,
                    tel: str = "010-3333-4444", address: str = "서울 강남구 1",
                    detail: str = "101호", recipient: str = "이수취",
                    claim_status: str = "") -> ExternalOrderLink:
    """주문 없이 수집만 된 링크(COLLECTED) 1건 — 묶음 표시 테스트용."""
    link = ExternalOrderLink(
        channel="NAVER", external_id=f"PO-{_uid()}", sync_status="COLLECTED",
        external_order_no=order_no,
        raw_snapshot={
            "order": {"orderId": order_no, "ordererName": "김주문",
                      "ordererTel": "010-1111-2222"},
            "productOrder": {
                "productOrderId": f"PO-{_uid()}", "productName": product,
                "productOption": "", "totalPaymentAmount": amount,
                "claimStatus": claim_status or None,
                "shippingAddress": {"name": recipient, "tel1": tel,
                                    "baseAddress": address, "detailedAddress": detail},
            },
        },
    )
    db_session.add(link)
    db_session.commit()
    return link


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


def test_pane_shows_cs_two_steps_not_assignment(auth_client):
    """CS 흐름은 ① 주문 만들기 ② 규격 입력 두 단계다.

    담당자 지정은 접수 단계가 아니라 고객 통화 → 실측일 지정 → 실측 스케줄링 시점에 한다
    (2026-08-17 사용자 확정) — 화면이 그 순서를 강요하면 안 된다.
    """
    _ingested_order(_sales())
    body = auth_client.get("/admin/naver-ingest/triage").get_data(as_text=True)
    assert "주문 만들기" in body and "ERP 규격 입력" in body
    assert "담당자 지정은 실측 일정 잡을 때" in body
    # 규격이 비었으면 지금 할 일을 짚어 준다.
    assert "편집기에서 제품 규격을 채우세요" in body


def test_done_button_is_not_locked_by_missing_spec_or_assignee(auth_client):
    """규격·담당자가 비어도 '확인 완료'를 막지 않는다 — 경고만 띄운다."""
    _ingested_order(_sales())
    body = auth_client.get("/admin/naver-ingest/triage").get_data(as_text=True)
    done = body.split('id="triage-done"')[1].split(">")[0]
    assert "disabled" not in done
    assert "규격이 아직 비어 있습니다" in body


def test_spec_filled_order_shows_done_state(auth_client):
    """규격이 들어간 주문은 2단계까지 완료로 보이고 경고가 사라진다."""
    from db import db_session as sess
    from models import Order
    from sqlalchemy.orm.attributes import flag_modified
    import copy

    link = _ingested_order(_sales())
    order = sess.get(Order, int(link.order_id))
    data = copy.deepcopy(order.structured_data or {})
    data["items"] = [{"product_name": "붙박이장", "spec_rows": [{"w": 2400, "h": 2400}]}]
    order.structured_data = data
    flag_modified(order, "structured_data")
    sess.commit()

    body = auth_client.get(f"/admin/naver-ingest/triage?link_id={link.id}").get_data(as_text=True)
    assert "규격 입력됨" in body
    assert "규격이 아직 비어 있습니다" not in body


def test_queue_badge_shows_next_step(auth_client):
    """목록에서도 다음 할 일이 보인다(주문 만들기 / 규격 입력)."""
    _collected_link(order_no="N-300", product="아직 주문 전", amount=100000)
    _ingested_order(_sales())
    body = auth_client.get("/admin/naver-ingest/triage").get_data(as_text=True)
    assert '<span class="badge bg-primary">주문 만들기</span>' in body
    assert '<span class="badge bg-primary">규격 입력</span>' in body


def test_create_order_response_carries_edit_url(auth_client):
    """'주문 만들기' 응답에 편집 화면 주소가 실린다 — 화면이 새 탭으로 연다."""
    from foms.services.integrations.naver_commerce.constants import (
        ACTOR_USERNAME, OWNER_USERNAME,
    )
    from models import User

    db_session.add_all([
        User(username=ACTOR_USERNAME, password="pw-not-committed", name="봇",
             role="MANAGER", team="CS", is_active=True),
        User(username=OWNER_USERNAME, password="pw-not-committed", name="미배정",
             role="STAFF", team="SALES", is_active=True),
    ])
    db_session.commit()
    link = _collected_link(order_no="N-301", product="본품", amount=300000)

    response = auth_client.post(f"/admin/naver-ingest/{link.id}/create-order",
                                json={})
    payload = response.get_json()
    assert payload["success"] is True
    assert payload["data"]["edit_url"].endswith("open=erp-order")
    assert str(payload["data"]["order_id"]) in payload["data"]["edit_url"]


def test_cancelled_link_shows_badge_and_locks_create_button(auth_client):
    """취소 요청 건은 큐에 빨간 배지가 뜨고 '주문 만들기'가 잠긴다.

    productOrderStatus 는 PAYED 라 상태만 보면 정상 주문과 구분되지 않는다.
    """
    link = _collected_link(order_no="N-200", product="취소된 붙박이장", amount=500000,
                           claim_status="CANCEL_REQUEST")
    body = auth_client.get(f"/admin/naver-ingest/triage?link_id={link.id}").get_data(as_text=True)
    assert "취소 요청" in body
    assert "disabled" in body.split('id="triage-create-order"')[1].split(">")[0]


def test_normal_link_keeps_create_button_enabled(auth_client):
    """정상 건은 잠그지 않는다 — 경고가 남발되면 아무도 안 본다."""
    link = _collected_link(order_no="N-201", product="정상 붙박이장", amount=500000)
    body = auth_client.get(f"/admin/naver-ingest/triage?link_id={link.id}").get_data(as_text=True)
    button = body.split('id="triage-create-order"')[1].split(">")[0]
    assert "disabled" not in button


def test_queue_groups_one_household_into_one_row(auth_client):
    """T14-C: 같은 (주문번호·수취인 전화·주소)는 큐에서 한 줄이다.

    상품주문 1건 = 1행이면 같은 사람 이름이 3~4번 반복돼 몇 집이 밀렸는지 셀 수 없다.
    """
    _collected_link(order_no="N-100", product="붙박이장 본품", amount=800000)
    _collected_link(order_no="N-100", product="TYPE A (반옷장)", amount=30000)
    _collected_link(order_no="N-100", product="길이추가(1cm)", amount=0)
    body = auth_client.get("/admin/naver-ingest/triage").get_data(as_text=True)
    assert "외 2건" in body          # 대표 + 나머지 2건
    assert "1집" in body             # 묶음 수
    assert "상품주문 3건" in body     # 실제 링크 수


def test_queue_lead_is_the_expensive_main_product(auth_client):
    """대표는 금액 최대(본품)다 — 0원 구성이 제목이 되면 본품을 찾아 헤맨다."""
    _collected_link(order_no="N-101", product="길이추가(1cm)", amount=0)
    _collected_link(order_no="N-101", product="라홈 붙박이장 본품", amount=496000)
    body = auth_client.get("/admin/naver-ingest/triage").get_data(as_text=True)
    lead_pos = body.index("라홈 붙박이장 본품")
    addon_pos = body.index("길이추가(1cm)")
    assert lead_pos < addon_pos      # 대표가 먼저 나온다


def test_group_members_list_lead_first(auth_client):
    """펼침 목록도 대표(본품) 먼저 — 0원 구성이 첫 줄이면 본품을 찾아 헤맨다."""
    _collected_link(order_no="N-104", product="구성 옵션 A", amount=0)
    _collected_link(order_no="N-104", product="구성 옵션 B", amount=20000)
    _collected_link(order_no="N-104", product="대표 본품", amount=900000)
    body = auth_client.get("/admin/naver-ingest/triage").get_data(as_text=True)
    members = body.split('id="naver-grp-')[1]
    assert members.index("대표 본품") < members.index("구성 옵션 A")


def test_queue_splits_groups_by_address(auth_client):
    """주소가 다르면 분리한다 — 합치면 남의 집으로 시공을 나간다."""
    _collected_link(order_no="N-102", product="본품 A", amount=500000, detail="101호")
    _collected_link(order_no="N-102", product="본품 B", amount=400000, detail="202호")
    body = auth_client.get("/admin/naver-ingest/triage").get_data(as_text=True)
    assert "2집" in body
    assert "외 1건" not in body


def test_create_order_button_targets_the_group_lead(auth_client):
    """묶음당 버튼 1개: '주문 만들기'는 대표(본품) 링크로 부른다 — 형제는 서비스가 묶는다."""
    _collected_link(order_no="N-103", product="옵션", amount=10000)
    lead = _collected_link(order_no="N-103", product="본품", amount=700000)
    body = auth_client.get("/admin/naver-ingest/triage").get_data(as_text=True)
    assert f'data-link-id="{lead.id}"' in body


def test_done_button_carries_every_link_in_the_group(auth_client):
    """'확인 완료'는 구성 전체 id 를 싣는다 — 한 건이 남으면 같은 집이 큐에 다시 뜬다."""
    first = _ingested_order(_sales())
    second = ExternalOrderLink(
        channel="NAVER", external_id=f"PO-{_uid()}", order_id=first.order_id,
        sync_status="LINKED", raw_snapshot=first.raw_snapshot,
    )
    db_session.add(second)
    db_session.commit()
    first_id, second_id = first.id, second.id

    body = auth_client.get("/admin/naver-ingest/triage").get_data(as_text=True)
    marker = 'data-link-ids="'
    assert marker in body
    ids = set(body.split(marker)[1].split('"')[0].split(","))
    assert {str(first_id), str(second_id)} <= ids


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


# --------------------------------------------------------------------------- #
# 취소·반품 건의 큐 이탈 (03 감사 결함 #4)
# --------------------------------------------------------------------------- #

def test_cancelled_link_can_still_be_marked_done(auth_client):
    """취소·반품 건도 큐에서 뺄 수 있어야 한다(03 감사 결함 #4).

    이 건들은 주문을 만들 수 없다(서버가 400). 그런데 카드 footer 가
    ``{% if not selected.order_id %}`` 로 배타 분기라, 주문 없는 건은 '확인 완료'
    버튼을 아예 만나지 못했다. 결과: 취소·반품 집이 영원히 큐에 남는다.
    플레이오토의 최대 불만("쇼핑몰에서 직접 처리하세요")을 그대로 재현한 셈이다.
    """
    link = _collected_link(order_no="N-DONE-CANCEL", product="취소된 붙박이장",
                           amount=500000, claim_status="CANCEL_DONE")
    body = auth_client.get(
        f"/admin/naver-ingest/triage?link_id={link.id}").get_data(as_text=True)

    assert 'id="triage-done"' in body, "취소·반품 건에도 확인 완료 버튼이 있어야 한다"
    done = body.split('id="triage-done"')[1].split(">")[0]
    assert "disabled" not in done
    assert str(link.id) in body.split('data-link-ids="')[1].split('"')[0]
    # 주문 만들기는 여전히 잠겨 있어야 한다 — 큐에서 빼는 것과 만드는 것은 다른 일이다.
    assert "disabled" in body.split('id="triage-create-order"')[1].split(">")[0]


def test_collected_link_without_claim_also_has_done_button(auth_client):
    """정상 수집분도 마찬가지 — 주문을 안 만들고 닫아야 할 집이 있다(중복 수집 등)."""
    link = _collected_link(order_no="N-DONE-PLAIN", product="정상 붙박이장", amount=300000)
    body = auth_client.get(
        f"/admin/naver-ingest/triage?link_id={link.id}").get_data(as_text=True)

    assert 'id="triage-done"' in body
    assert "disabled" not in body.split('id="triage-create-order"')[1].split(">")[0]


def test_assignee_control_stays_on_the_order_side_only(auth_client):
    """담당자 지정은 주문이 있어야 의미가 있다 — 주문 없는 건에는 나오면 안 된다.

    footer 분기를 푸는 김에 담당자 select 까지 딸려 나오면, CS 가 '지금 지정해야 하나'
    로 읽는다. 담당자 지정은 실측 일정 단계 일이다(도메인 규칙 5).
    """
    link = _collected_link(order_no="N-NOASSIGN", product="붙박이장", amount=300000)
    body = auth_client.get(
        f"/admin/naver-ingest/triage?link_id={link.id}").get_data(as_text=True)
    assert 'id="triage-assignee"' not in body


def test_review_route_accepts_link_without_order(auth_client):
    """버튼이 있어도 서버가 안 받으면 큐에서 안 빠진다 — 라우트까지 확인한다.

    취소·반품 건은 주문이 영영 안 생긴다. review 는 '사람이 봤다' 축이라 주문과
    무관해야 한다.
    """
    link = _collected_link(order_no="N-REVIEW-NOORDER", product="취소된 붙박이장",
                           amount=500000, claim_status="CANCEL_DONE")
    link_id = link.id

    response = auth_client.post(f"/admin/naver-ingest/{link_id}/review", json={})
    assert response.status_code == 200, response.get_data(as_text=True)
    assert response.get_json()["success"] is True

    db_session.expire_all()
    assert db_session.get(ExternalOrderLink, link_id).reviewed_at is not None

    body = auth_client.get("/admin/naver-ingest/triage").get_data(as_text=True)
    assert "취소된 붙박이장" not in body
