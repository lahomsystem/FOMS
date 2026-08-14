"""NAVER-INGEST-01 T12: 수집분 → 주문 생성 계약 (SQLite 레인).

수집(자동)과 생성(사람 판단)을 분리했다. 여기서 고정하는 계약:

* 버튼 1회 = 주문 1건. **두 번 눌러도 1건**(멱등 — 링크에 order_id 가 박힌다).
* 생성은 ``create_order()`` 경유 — owner 배정·mutation_version·GEOCODE outbox 가 따라온다.
* 매핑이 깨진 원본은 주문 대신 ``PENDING_REVIEW`` 로 남고 사유를 돌려준다.
* 원본이 없으면 만들지 않는다(빈 주문 방지).
* 라우트는 ADMIN 전용이고 감사 로그를 남긴다.
"""

from __future__ import annotations

import copy

import pytest
from werkzeug.security import generate_password_hash

from db import db_session
from foms.services.integrations.naver_commerce.accounts import resolve_ingest_account_ids
from foms.services.integrations.naver_commerce.constants import (
    ACTOR_USERNAME,
    OWNER_USERNAME,
)
from foms.services.integrations.naver_commerce.promotion import (
    PromotionError,
    promote_link_to_order,
    summarize_snapshot,
)
from models import (
    DomainSideEffectOutbox,
    ExternalOrderLink,
    Order,
    OrderAssignment,
    User,
)

DETAIL = {
    "order": {"orderId": "2026081412345", "ordererName": "김주문",
              "ordererTel": "010-1111-2222", "orderDate": "2026-08-14T10:00:00.000+09:00"},
    "productOrder": {
        "productOrderId": "PO-P1", "productOrderStatus": "PAYED",
        "productName": "붙박이장 세트", "productOption": "색상: 화이트 / 폭: 2400",
        "quantity": 2, "totalPaymentAmount": 1250000,
        "sellerProductCode": "LAHOM-BIB-2400",
        "shippingAddress": {"name": "이수취", "tel1": "010-3333-4444",
                            "baseAddress": "서울특별시 강남구 테헤란로 1",
                            "detailedAddress": "101동 1001호", "zipCode": "06232"},
    },
}


def _accounts() -> tuple[User, User]:
    actor = User(username=ACTOR_USERNAME, password="pw-not-committed", name="네이버 수집봇",
                 role="MANAGER", team="CS", is_active=True)
    owner = User(username=OWNER_USERNAME, password="pw-not-committed", name="미배정",
                 role="STAFF", team="SALES", is_active=True)
    db_session.add_all([actor, owner])
    db_session.commit()
    return (actor, owner)


def _link(detail: dict | None = DETAIL, *, status: str = "COLLECTED",
          external_id: str = "PO-P1") -> ExternalOrderLink:
    link = ExternalOrderLink(channel="NAVER", external_id=external_id,
                             raw_snapshot=copy.deepcopy(detail) if detail else None,
                             sync_status=status)
    db_session.add(link)
    db_session.commit()
    return link


def test_promotion_creates_exactly_one_order(app):
    """수집분 1건 → 주문 1건, 링크가 LINKED 로 바뀐다."""
    actor, owner = _accounts()
    link = _link()

    order_id, created = promote_link_to_order(
        db_session, link_id=link.id, actor_user_id=actor.id, owner_user_id=owner.id)
    db_session.commit()

    assert created is True
    order = db_session.query(Order).one()
    assert order.id == order_id
    assert order.customer_name == "이수취"
    assert order.status == "RECEIVED"
    assert order.is_erp_order is True
    assert order.mutation_version == 1
    db_session.refresh(link)
    assert (link.sync_status, link.order_id) == ("LINKED", order.id)


def test_second_click_does_not_create_a_duplicate(app):
    """버튼 두 번 = 주문 하나. 두 번째 호출은 created=False."""
    actor, owner = _accounts()
    link = _link()

    first_id, first_created = promote_link_to_order(
        db_session, link_id=link.id, actor_user_id=actor.id, owner_user_id=owner.id)
    db_session.commit()
    second_id, second_created = promote_link_to_order(
        db_session, link_id=link.id, actor_user_id=actor.id, owner_user_id=owner.id)
    db_session.commit()

    assert (first_id, second_id) == (first_id, first_id)
    assert first_created is True and second_created is False
    assert db_session.query(Order).count() == 1


def test_owner_and_geocode_follow_the_canonical_path(app):
    """create_order 경유라 보류함 owner 배정과 GEOCODE 예약이 함께 붙는다."""
    actor, owner = _accounts()
    link = _link()

    promote_link_to_order(db_session, link_id=link.id,
                          actor_user_id=actor.id, owner_user_id=owner.id)
    db_session.commit()

    order = db_session.query(Order).one()
    assignment = (db_session.query(OrderAssignment)
                  .filter(OrderAssignment.order_id == order.id,
                          OrderAssignment.domain == "SALES").one())
    assert assignment.user_id == owner.id
    assert assignment.assigned_by_user_id == actor.id
    assert order.lat is None and order.lng is None, "네이버 좌표를 주입하면 안 된다"
    assert db_session.query(DomainSideEffectOutbox).count() == 1


def test_broken_snapshot_becomes_pending_review_without_order(app):
    """매핑이 깨지면 주문 대신 보류로 남고 사유가 돌아온다."""
    actor, owner = _accounts()
    broken = copy.deepcopy(DETAIL)
    broken["productOrder"]["shippingAddress"]["baseAddress"] = ""
    broken["productOrder"]["shippingAddress"]["detailedAddress"] = ""
    link = _link(broken)

    with pytest.raises(PromotionError):
        promote_link_to_order(db_session, link_id=link.id,
                              actor_user_id=actor.id, owner_user_id=owner.id)
    db_session.commit()

    assert db_session.query(Order).count() == 0
    db_session.refresh(link)
    assert link.sync_status == "PENDING_REVIEW"
    assert link.failure_reason


def test_missing_snapshot_is_refused(app):
    """원본이 없으면 빈 주문을 만들지 않는다."""
    actor, owner = _accounts()
    link = _link(None)

    with pytest.raises(PromotionError):
        promote_link_to_order(db_session, link_id=link.id,
                              actor_user_id=actor.id, owner_user_id=owner.id)
    assert db_session.query(Order).count() == 0


def test_summary_reads_display_values_from_snapshot(app):
    """주문이 없어도 목록에 보여줄 값이 원본에서 나온다."""
    summary = summarize_snapshot(DETAIL)

    assert summary["customer_name"] == "이수취"
    assert summary["product"] == "붙박이장 세트"
    assert summary["options"] == "색상: 화이트 / 폭: 2400"
    assert summary["quantity"] == 2
    assert summary["amount"] == 1250000
    assert summary["order_date"] == "2026-08-14"


def test_summary_never_explodes_on_garbage(app):
    """깨진 원본 하나가 목록 전체를 죽이면 안 된다."""
    for garbage in (None, {}, [], "문자열", {"productOrder": "잘못된 타입"}):
        summary = summarize_snapshot(garbage)
        assert isinstance(summary, dict)
        assert set(summary) >= {"customer_name", "product", "options"}


def test_account_contract_is_checked_before_creating(app):
    """보류함 계정이 비활성이면 주문을 만들지 않는다(owner 계약)."""
    actor, owner = _accounts()
    owner.is_active = False
    db_session.commit()

    with pytest.raises(Exception):
        resolve_ingest_account_ids(db_session)


def _login_admin(client) -> User:
    admin = User(username="promo_admin", password=generate_password_hash("pw"),
                 role="ADMIN", team="CS", name="관리자", is_active=True)
    db_session.add(admin)
    db_session.commit()
    with client.session_transaction() as sess:
        sess["user_id"] = admin.id
        sess["username"] = admin.username
        sess["role"] = admin.role
    return admin


def test_route_creates_order_and_is_idempotent(client):
    """라우트 1회 = 주문 1건, 재요청해도 같은 주문 id."""
    _login_admin(client)
    _accounts()
    link_id = _link().id  # 요청 후 세션이 닫히므로 id 를 먼저 잡아 둔다.

    first = client.post(f"/admin/naver-ingest/{link_id}/create-order")
    second = client.post(f"/admin/naver-ingest/{link_id}/create-order")

    assert first.status_code == 200 and first.get_json()["success"] is True
    assert second.get_json()["data"]["order_id"] == first.get_json()["data"]["order_id"]
    assert second.get_json()["data"]["created"] is False
    assert db_session.query(Order).count() == 1


def test_route_requires_admin(client):
    """STAFF 는 주문을 만들 수 없다."""
    staff = User(username="promo_staff", password=generate_password_hash("pw"),
                 role="STAFF", team="SALES", name="영업", is_active=True)
    db_session.add(staff)
    db_session.commit()
    with client.session_transaction() as sess:
        sess["user_id"] = staff.id
        sess["username"] = staff.username
        sess["role"] = staff.role
    _accounts()
    link_id = _link().id

    response = client.post(f"/admin/naver-ingest/{link_id}/create-order")

    assert response.status_code in (302, 403)
    assert db_session.query(Order).count() == 0


def test_route_reports_missing_accounts_instead_of_500(client):
    """T0 계정이 없으면 500 이 아니라 사유가 담긴 400 이다."""
    _login_admin(client)
    link_id = _link().id

    response = client.post(f"/admin/naver-ingest/{link_id}/create-order")

    assert response.status_code == 400
    assert "계정" in response.get_json()["error"]
