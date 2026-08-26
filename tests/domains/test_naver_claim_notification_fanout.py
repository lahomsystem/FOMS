"""NOTIF-ROLE-01: 네이버 클레임 알림은 사건 1건 = Notification 1건이다.

회귀 배경: 담당자가 없는 클레임은 활성 ADMIN **전원에게 개별 Notification row** 로
복제됐다(관리자 4명이면 같은 사건이 4 row). 알림 SSOT 는 공유 Notification 1건 +
수신자별 ``notification_user_states`` 다.

고정하는 계약:

1. 담당자 없는 클레임 → Notification **1건**, ``target_type='ROLE'`` ·
   ``target_role='ADMIN'`` (관리자 수와 무관하게 1건).
2. 담당자 있는 클레임 → ``target_type='USER'`` 1건 **+ 관리자용 ROLE 1건**
   (2026-08-26 사용자 확정: 취소는 담당자와 관리자가 같이 본다). 관리자가 몇 명이든
   ROLE 은 여전히 1건이다.
3. 대상이 아무도 없으면 알림 0건이고 ``notified_status`` 도 남기지 않는다
   (다음 스윕에서 다시 시도해야 하므로).
4. ``refresh_claims`` 의 ``notified`` 집계는 **수신자 수**다 — ROLE 로 바뀌었다고
   관리자 3명이 1로 줄어들면 호출부 카운터 의미가 깨진다.

``recipients.py`` 의 ROLE 해석(state 물질화)은 병행 작업이라, state 수 단언은 배선이
끝났을 때만 한다(미배선이면 skip). Notification row 계약은 무조건 단언한다.
"""

from __future__ import annotations

import pytest

from db import db_session
from foms.services.integrations.naver_commerce.claim_watch import (
    NOTIFICATION_TYPE,
    STATE_KEY,
    refresh_claims,
)
from foms.services.integrations.naver_commerce.constants import OWNER_USERNAME
from models import (
    ExternalOrderLink,
    Notification,
    NotificationRecipientSource,
    NotificationUserState,
    Order,
    OrderAssignment,
    User,
)

_SEQ = [0]


@pytest.fixture
def db(app):
    yield db_session
    db_session.rollback()


def _uid() -> str:
    _SEQ[0] += 1
    return f"role-{_SEQ[0]}"


def _user(username: str, *, role: str, name: str = "사람") -> User:
    user = User(username=username, password="pw-not-committed", name=name,
                role=role, team="CS", is_active=True)
    db_session.add(user)
    db_session.commit()
    return user


def _admins(count: int) -> list[User]:
    return [_user(f"admin-{_uid()}", role="ADMIN", name=f"관리자{i}")
            for i in range(count)]


def _detail(external_id: str, *, claim: str = "CANCEL_REQUEST") -> dict:
    product_order = {
        "productOrderId": external_id,
        "productOrderStatus": "PAYED",
        "productName": "붙박이장",
        "productOption": "색상: 화이트",
        "totalPaymentAmount": 500000,
        "shippingAddress": {"name": "이수취", "tel1": "010-3333-4444",
                            "baseAddress": "서울 강남구 1", "detailedAddress": "101호"},
    }
    if claim:
        product_order["claimStatus"] = claim
    detail = {"order": {"orderId": "N-1", "ordererName": "김주문"},
              "productOrder": product_order}
    if claim:
        detail["cancel"] = {"cancelReason": "SIMPLE_INTENT_CHANGED"}
    return detail


def _order_with_owner(owner: User | None) -> Order:
    """주문 1건 + (있으면) active SALES 배정 1행."""
    order = Order(customer_name="테스트고객", phone="010-0000-0000", address="서울",
                  product="붙박이장", options="", received_date="2026-08-20",
                  status="RECEIVED", is_erp_order=True, structured_data={})
    db_session.add(order)
    db_session.commit()
    if owner is not None:
        db_session.add(OrderAssignment(order_id=order.id, domain="SALES",
                                       user_id=owner.id, source="INITIAL_OWNER",
                                       active=True, assigned_by_user_id=owner.id))
        db_session.commit()
    return order


def _link(*, order: Order | None = None) -> ExternalOrderLink:
    external_id = f"PO-{_uid()}"
    link = ExternalOrderLink(channel="NAVER", external_id=external_id,
                             sync_status="COLLECTED",
                             order_id=order.id if order is not None else None,
                             raw_snapshot=_detail(external_id, claim=""))
    db_session.add(link)
    db_session.commit()
    return link


class FakeClient:
    """상세 조회만 흉내낸다(네이버로 나가는 HTTP 0회)."""

    def __init__(self, details: list[dict]):
        self._details = details

    def get_product_orders(self, ids):
        wanted = set(ids)
        return [d for d in self._details
                if d["productOrder"]["productOrderId"] in wanted]


def _run_claim(link: ExternalOrderLink) -> dict[str, int]:
    """해당 링크에 취소 요청 클레임을 흘려보내고 집계를 돌려준다."""
    client = FakeClient([_detail(link.external_id)])
    changed = [{"productOrderId": link.external_id, "productOrderStatus": "CANCELED"}]
    stats = refresh_claims(db_session, client=client, changed=changed)
    db_session.commit()
    return stats


def _claim_notifications() -> list[Notification]:
    return (db_session.query(Notification)
            .filter(Notification.notification_type == NOTIFICATION_TYPE)
            .all())


def _role_fanout_wired(notification: Notification) -> bool:
    """``recipients.py`` 가 ``target_role`` 을 수신자로 해석하는지(병행 작업 감지)."""
    from foms.services.notifications.recipients import (
        resolve_recipients_for_notification,
    )

    return bool(resolve_recipients_for_notification(db_session, notification))


# --------------------------------------------------------------------------- #
# 1. 담당자 없음 → ROLE 알림 1건
# --------------------------------------------------------------------------- #

def test_unassigned_claim_creates_single_role_notification(db):
    """관리자가 3명이어도 Notification 은 1건 — 과거엔 관리자 수만큼 만들었다."""
    admins = _admins(3)
    link = _link()

    stats = _run_claim(link)

    rows = _claim_notifications()
    assert len(rows) == 1, "관리자 수만큼 알림이 복제됐다(NOTIF-ROLE-01 회귀)"
    row = rows[0]
    assert row.target_type == "ROLE"
    assert row.target_role == "ADMIN"
    assert row.target_user_id is None
    # 카운터는 여전히 '사람 수' 다 — row 수(1)로 줄어들면 호출부 집계 의미가 깨진다.
    assert stats["notified"] == len(admins)
    assert link.triage_state[STATE_KEY]["notified_status"] == "CANCEL_REQUEST"

    if not _role_fanout_wired(row):
        pytest.skip("recipients.py 의 ROLE 해석 미배선 — state 수 단언은 보류")
    states = (db_session.query(NotificationUserState)
              .filter(NotificationUserState.notification_id == row.id).all())
    assert {s.user_id for s in states} == {a.id for a in admins}
    assert {s.recipient_source for s in states} == {
        NotificationRecipientSource.TARGET_ROLE
    }


def test_holding_account_owner_still_falls_back_to_role(db):
    """보류함(``naver_unassigned``)이 owner 면 사람이 아니므로 ADMIN 역할 알림만 남는다."""
    _admins(2)
    holding = _user(OWNER_USERNAME, role="STAFF", name="미배정")
    link = _link(order=_order_with_owner(holding))

    _run_claim(link)

    rows = _claim_notifications()
    assert len(rows) == 1
    assert rows[0].target_type == "ROLE" and rows[0].target_role == "ADMIN"


# --------------------------------------------------------------------------- #
# 2. 담당자 있음 → USER 알림 (회귀 가드)
# --------------------------------------------------------------------------- #

def test_assigned_claim_notifies_owner_and_admins(db):
    """담당자가 있으면 담당자 USER 1건 + 관리자 ROLE 1건 — 둘 다 받는다."""
    admins = _admins(3)
    sales = _user(f"sales-{_uid()}", role="STAFF", name="박영업")
    link = _link(order=_order_with_owner(sales))

    stats = _run_claim(link)

    rows = _claim_notifications()
    assert len(rows) == 2, "담당자·관리자 알림이 각각 1건씩 나와야 한다"
    user_row = next(row for row in rows if row.target_type == "USER")
    role_row = next(row for row in rows if row.target_type == "ROLE")
    assert user_row.target_user_id == sales.id and user_row.target_role is None
    # 관리자가 3명이어도 ROLE row 는 1건이다(NOTIF-ROLE-01).
    assert role_row.target_role == "ADMIN" and role_row.target_user_id is None
    assert stats["notified"] == 1 + len(admins)

    states = (db_session.query(NotificationUserState)
              .filter(NotificationUserState.notification_id == user_row.id).all())
    assert [s.user_id for s in states] == [sales.id]


def test_admin_owner_is_not_notified_twice(db):
    """담당자가 관리자면 ROLE 로 이미 받는다 — 같은 사건에 USER 알림을 겹쳐 만들지 않는다."""
    admin_owner = _user(f"admin-{_uid()}", role="ADMIN", name="관리영업")
    link = _link(order=_order_with_owner(admin_owner))

    stats = _run_claim(link)

    rows = _claim_notifications()
    assert len(rows) == 1
    assert rows[0].target_type == "ROLE" and rows[0].target_role == "ADMIN"
    assert stats["notified"] == 1


# --------------------------------------------------------------------------- #
# 3. 대상 0명
# --------------------------------------------------------------------------- #

def test_no_target_creates_no_notification(db):
    """담당자도 활성 관리자도 없으면 알림 0건이고 중복 억제 표식도 남기지 않는다."""
    link = _link()

    stats = _run_claim(link)

    assert _claim_notifications() == []
    assert stats["claimed"] == 1 and stats["notified"] == 0
    # 다음 스윕에서 다시 시도해야 하므로 notified_status 를 남기면 안 된다.
    assert "notified_status" not in link.triage_state[STATE_KEY]


def test_inactive_admin_is_not_a_target(db):
    """비활성 관리자만 있으면 대상 0명이다(활성 사용자만 수신자)."""
    admin = _admins(1)[0]
    admin.is_active = False
    db_session.commit()
    link = _link()

    stats = _run_claim(link)

    assert _claim_notifications() == []
    assert stats["notified"] == 0
