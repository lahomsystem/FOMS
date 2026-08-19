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

from sqlalchemy.orm.attributes import flag_modified

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


def test_cancelled_link_cannot_become_an_order(app):
    """네이버에서 취소·반품 진행 중이면 주문을 만들지 않는다.

    수집 필터는 ``productOrderStatus == PAYED`` 하나뿐이라 **취소 요청 건도 PAYED 로
    수집된다**(2026-08-14 스테이징 실물 1건). 화면 버튼만 잠그면 API 직접 호출로 뚫리므로
    서비스에서 막는다.
    """
    actor, owner = _accounts()
    detail = copy.deepcopy(DETAIL)
    detail["productOrder"]["claimStatus"] = "CANCEL_REQUEST"
    detail["cancel"] = {"cancelReason": "SIMPLE_INTENT_CHANGED"}
    link = _link(detail, external_id="PO-CANCEL")

    before = db_session.query(Order).count()
    with pytest.raises(PromotionError) as exc:
        promote_link_to_order(db_session, link_id=link.id,
                              actor_user_id=actor.id, owner_user_id=owner.id)
    assert "취소" in str(exc.value)
    assert db_session.query(Order).count() == before  # 주문이 만들어지지 않았다
    assert link.order_id is None


def test_cancel_reject_still_creates_order(app):
    """취소 '거부'는 정상 진행 건이다 — 막으면 진짜 주문을 못 만든다."""
    actor, owner = _accounts()
    detail = copy.deepcopy(DETAIL)
    detail["productOrder"]["claimStatus"] = "CANCEL_REJECT"
    link = _link(detail, external_id="PO-REJECT")
    order_id, created = promote_link_to_order(
        db_session, link_id=link.id, actor_user_id=actor.id, owner_user_id=owner.id)
    db_session.commit()
    assert created is True and order_id


def test_summary_exposes_claim_label(app):
    """목록 요약도 취소 표식을 싣는다(큐에서 알아볼 수 있어야 한다)."""
    detail = copy.deepcopy(DETAIL)
    detail["productOrder"]["claimStatus"] = "CANCEL_REQUEST"
    summary = summarize_snapshot(detail)
    assert summary["claim_label"] == "취소 요청" and summary["claim_blocking"] is True
    assert summarize_snapshot(DETAIL)["claim_label"] == ""


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


def test_route_allows_staff_and_blocks_viewer(client):
    """T14-A 권한 개방: STAFF 는 주문을 만들 수 있고, VIEWER 는 여전히 차단된다."""
    staff = User(username="promo_staff", password=generate_password_hash("pw"),
                 role="STAFF", team="SALES", name="영업", is_active=True)
    viewer = User(username="promo_viewer", password=generate_password_hash("pw"),
                  role="VIEWER", team="CS", name="뷰어", is_active=True)
    db_session.add_all([staff, viewer])
    db_session.commit()
    staff_id, viewer_id = staff.id, viewer.id
    _accounts()
    link_id = _link().id

    with client.session_transaction() as sess:
        sess["user_id"] = viewer_id
        sess["username"] = "promo_viewer"
        sess["role"] = "VIEWER"
    denied = client.post(f"/admin/naver-ingest/{link_id}/create-order")
    assert denied.status_code in (302, 403)
    assert db_session.query(Order).count() == 0

    with client.session_transaction() as sess:
        sess["user_id"] = staff_id
        sess["username"] = "promo_staff"
        sess["role"] = "STAFF"
    allowed = client.post(f"/admin/naver-ingest/{link_id}/create-order")
    assert allowed.status_code == 200 and allowed.get_json()["success"] is True
    assert db_session.query(Order).count() == 1


def test_route_reports_missing_accounts_instead_of_500(client):
    """T0 계정이 없으면 500 이 아니라 사유가 담긴 400 이다."""
    _login_admin(client)
    link_id = _link().id

    response = client.post(f"/admin/naver-ingest/{link_id}/create-order")

    assert response.status_code == 400
    assert "계정" in response.get_json()["error"]


# --------------------------------------------------------------------------- #
# T13: 같은 네이버 주문번호는 한 FOMS 주문으로 묶는다
# --------------------------------------------------------------------------- #

def _sibling(product_order_id: str, *, order_no: str = "2026081412345",
             name: str = "구성 옵션", amount: int = 0, quantity: int = 1,
             tel: str = "010-3333-4444", base: str = "서울특별시 강남구 테헤란로 1",
             detail_addr: str = "101동 1001호") -> ExternalOrderLink:
    """같은 묶음(또는 다른 묶음)의 상품주문 링크 1건."""
    payload = copy.deepcopy(DETAIL)
    payload["order"]["orderId"] = order_no
    po = payload["productOrder"]
    po["productOrderId"] = product_order_id
    po["productName"] = name
    po["totalPaymentAmount"] = amount
    po["quantity"] = quantity
    po["shippingAddress"]["tel1"] = tel
    po["shippingAddress"]["baseAddress"] = base
    po["shippingAddress"]["detailedAddress"] = detail_addr
    link = ExternalOrderLink(channel="NAVER", external_id=product_order_id,
                             external_order_no=order_no, raw_snapshot=payload,
                             sync_status="COLLECTED")
    db_session.add(link)
    db_session.commit()
    return link


def test_same_naver_order_becomes_one_foms_order(app):
    """본품 + 0원 구성 2건 = 주문 1건, 품목 3행, 금액은 합계."""
    actor, owner = _accounts()
    main = _sibling("PO-G1", name="붙박이장 본품", amount=1200000, quantity=5)
    _sibling("PO-G2", name="TYPE A (반옷장)", amount=0, quantity=2)
    _sibling("PO-G3", name="TYPE I (긴옷장)", amount=50000, quantity=1)

    order_id, created = promote_link_to_order(
        db_session, link_id=main.id, actor_user_id=actor.id, owner_user_id=owner.id)
    db_session.commit()

    assert created is True
    assert db_session.query(Order).count() == 1, "상품주문마다 주문이 생기면 안 된다"
    order = db_session.get(Order, order_id)
    assert order.payment_amount == 1250000, "묶음 합계여야 한다"
    assert "외 2건" in order.product
    items = (order.structured_data or {}).get("items") or []
    assert len(items) == 3
    assert {i["price"] for i in items} == {1200000, 0, 50000}
    links = db_session.query(ExternalOrderLink).all()
    assert {l.order_id for l in links} == {order_id}
    assert {l.sync_status for l in links} == {"LINKED"}


def test_split_delivery_is_not_merged(app):
    """같은 주문번호라도 수취인 주소가 다르면 묶지 않는다(분할배송)."""
    actor, owner = _accounts()
    here = _sibling("PO-S1", name="붙박이장", amount=900000)
    _sibling("PO-S2", name="붙박이장", amount=800000,
             tel="010-9999-8888", base="부산광역시 해운대구 2", detail_addr="202호")

    order_id, _ = promote_link_to_order(
        db_session, link_id=here.id, actor_user_id=actor.id, owner_user_id=owner.id)
    db_session.commit()

    order = db_session.get(Order, order_id)
    assert len(order.structured_data["items"]) == 1
    other = db_session.query(ExternalOrderLink).filter(
        ExternalOrderLink.external_id == "PO-S2").one()
    assert other.order_id is None, "다른 주소 건은 남의 주문에 들어가면 안 된다"


def test_already_promoted_sibling_is_not_pulled_in_twice(app):
    """이미 주문이 붙은 형제는 다시 묶지 않는다."""
    actor, owner = _accounts()
    first = _sibling("PO-D1", name="붙박이장", amount=1000000)
    second = _sibling("PO-D2", name="구성", amount=0)
    second_id = second.id

    promote_link_to_order(db_session, link_id=first.id,
                          actor_user_id=actor.id, owner_user_id=owner.id)
    db_session.commit()
    # 형제가 이미 첫 주문에 들어갔으므로 두 번째 호출은 그 주문을 그대로 돌려준다.
    order_id, created = promote_link_to_order(
        db_session, link_id=second_id, actor_user_id=actor.id, owner_user_id=owner.id)
    db_session.commit()

    assert created is False
    assert db_session.query(Order).count() == 1
    assert order_id == db_session.get(ExternalOrderLink, second_id).order_id


def test_lead_is_the_highest_amount_item(app):
    """대표(고객·주소·제품명)는 금액이 가장 큰 상품주문이다 — 0원 구성이 대표가 되면 안 된다."""
    actor, owner = _accounts()
    cheap = _sibling("PO-L1", name="TYPE A (반옷장)", amount=0)
    _sibling("PO-L2", name="라홈 붙박이장 본품", amount=1500000)

    order_id, _ = promote_link_to_order(
        db_session, link_id=cheap.id, actor_user_id=actor.id, owner_user_id=owner.id)
    db_session.commit()

    order = db_session.get(Order, order_id)
    assert order.product.startswith("라홈 붙박이장 본품")

def test_promotion_keeps_collection_order_for_attribution(app):
    """어느 형제를 눌러 만들어도 **수집 순서**가 유지돼야 귀속이 맞는다.

    2026-08-19 스테이징 실사고: 기준 링크를 앞으로 끌어내던 탓에 본품 2개짜리 집이
    ``M M a a`` 로 보여 추가옵션 12건이 한 본품에 몰렸다.
    """
    actor, owner = _accounts()
    first_main = _sibling("PO-ORD1", name="붙박이장 180cm", amount=1_115_800)
    addon = _sibling("PO-ORD2", name="TYPE C", amount=60_000)
    addon.raw_snapshot["productOrder"]["productClass"] = "추가구성상품"
    flag_modified(addon, "raw_snapshot")
    second_main = _sibling("PO-ORD3", name="붙박이장 30cm", amount=1_314_600)
    db_session.commit()

    # 대표(금액 최대)인 두 번째 본품을 눌러 만든다 — 옛 코드는 이 링크를 맨 앞으로 옮겼다.
    order_id, _ = promote_link_to_order(
        db_session, link_id=second_main.id, actor_user_id=actor.id, owner_user_id=owner.id)
    db_session.commit()

    order = db_session.get(Order, order_id)
    ids = [item["naver_product_order_id"] for item in order.structured_data["items"]]
    assert ids == ["PO-ORD3", "PO-ORD1"], "대표가 1번, 본품만 항목"
    assert order.payment_amount == 1_115_800 + 60_000 + 1_314_600
    assert {l.order_id for l in db_session.query(ExternalOrderLink).all()} == {order_id}
