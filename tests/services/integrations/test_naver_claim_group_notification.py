"""네이버 클레임 알림의 단위는 **집(주문)** 이다 — 세부옵션 수만큼 보내지 않는다.

회귀 배경(2026-08-25 운영): 한 고객이 주문 1건을 취소했는데 알림함에 같은 문장이 4건
쌓였다. 네이버는 주문 1건을 세부옵션마다 다른 상품주문번호로 쪼개 주고
(…111391 / …111401 / …111411 / …111421 — ``group_key`` 동일), 클레임 추적이 링크마다
알림을 만들었기 때문이다. 화면(확인 큐·이력)은 이미 집 단위로 묶여 있었는데 알림만
링크 단위로 남아 있었다.

고정하는 계약:

1. 같은 집·같은 상태로 바뀐 링크 N건 → Notification **1건**, 본문에 "외 N-1건".
2. 집이 다르면 알림도 따로 간다(묶어서 뭉개지 않는다).
3. 같은 집이라도 **담당자가 다르면** 따로 간다 — 남의 주문 소식을 받으면 안 된다.
4. 묶어 보낸 뒤 그 집의 **모든 링크**에 ``notified_status`` 가 남는다. 한 링크에만
   남기면 다음 스윕이 나머지 링크로 같은 알림을 다시 만든다(중복 억제 무력화).
"""

from __future__ import annotations

from db import db_session
from foms.services.integrations.naver_commerce.claim_watch import (
    NOTIFICATION_TYPE,
    STATE_KEY,
    refresh_claims,
)
from models import (
    ExternalOrderLink,
    Notification,
    Order,
    OrderAssignment,
    User,
)

_SEQ = [0]


def _uid() -> str:
    _SEQ[0] += 1
    return str(_SEQ[0])


def _user(role: str = "ADMIN") -> User:
    user = User(username=f"grp_{role.lower()}_{_uid()}", password="pw-not-committed",
                name="사람", role=role, team="CS", is_active=True)
    db_session.add(user)
    db_session.commit()
    return user


def _detail(external_id: str, *, order_no: str, claim: str = "",
            tel: str = "010-3333-4444") -> dict:
    """상품주문 상세 1건 — ``order_no``·``tel`` 이 같으면 같은 집이다."""
    product_order = {
        "productOrderId": external_id,
        "productOrderStatus": "PAYED",
        "productName": "붙박이장",
        "productOption": "색상: 화이트",
        "totalPaymentAmount": 500000,
        "shippingAddress": {"name": "이수취", "tel1": tel,
                            "baseAddress": "서울 강남구 1", "detailedAddress": "101호"},
    }
    if claim:
        product_order["claimStatus"] = claim
    detail = {"order": {"orderId": order_no, "ordererName": "김주문"},
              "productOrder": product_order}
    if claim:
        detail["cancel"] = {"cancelReason": "SIMPLE_INTENT_CHANGED"}
    return detail


def _order_with_owner(owner: User) -> Order:
    order = Order(customer_name="테스트고객", phone="010-0000-0000", address="서울",
                  product="붙박이장", options="", received_date="2026-08-25",
                  status="RECEIVED", is_erp_order=True, structured_data={})
    db_session.add(order)
    db_session.commit()
    db_session.add(OrderAssignment(order_id=order.id, domain="SALES",
                                   user_id=owner.id, source="INITIAL_OWNER",
                                   active=True, assigned_by_user_id=owner.id))
    db_session.commit()
    return order


def _link(*, order_no: str, order: Order | None = None) -> ExternalOrderLink:
    external_id = f"PO-{_uid()}"
    link = ExternalOrderLink(channel="NAVER", external_id=external_id,
                             sync_status="COLLECTED",
                             order_id=order.id if order is not None else None,
                             raw_snapshot=_detail(external_id, order_no=order_no))
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


def _sweep(links: list[ExternalOrderLink], *, order_nos: list[str],
           claim: str = "CANCEL_DONE") -> dict[str, int]:
    """링크들에 클레임을 한 스윕으로 흘려보낸다(운영과 같은 경로)."""
    details = [_detail(link.external_id, order_no=order_no, claim=claim)
               for link, order_no in zip(links, order_nos)]
    changed = [{"productOrderId": link.external_id, "productOrderStatus": "CANCELED"}
               for link in links]
    stats = refresh_claims(db_session, client=FakeClient(details), changed=changed)
    db_session.commit()
    return stats


def _claims() -> list[Notification]:
    return (db_session.query(Notification)
            .filter(Notification.notification_type == NOTIFICATION_TYPE)
            .order_by(Notification.id).all())


# --------------------------------------------------------------------------- #
# 1. 집 1건 = 알림 1건
# --------------------------------------------------------------------------- #

def test_one_household_with_many_options_creates_one_notification(app):
    """세부옵션 3건이 한 번에 취소돼도 알림은 1건이다(운영 4건 사고의 계약)."""
    _user("ADMIN")
    order_no = f"N-{_uid()}"
    links = [_link(order_no=order_no) for _ in range(3)]

    stats = _sweep(links, order_nos=[order_no] * 3)

    assert stats["refreshed"] == 3 and stats["claimed"] == 3
    rows = _claims()
    assert len(rows) == 1, "세부옵션 수만큼 알림이 생겼다(집 묶음 회귀)"
    assert rows[0].target_type == "ROLE" and rows[0].target_role == "ADMIN"
    # 대표 번호 1개 + 나머지 건수 — 사람이 집 하나로 읽어야 한다.
    assert f"상품주문번호 {links[0].external_id} 외 2건" in rows[0].message
    # 억제 표식은 집의 모든 링크에 남아야 다음 스윕이 조용하다.
    for link in links:
        assert link.triage_state[STATE_KEY]["notified_status"] == "CANCEL_DONE"


def test_repeat_sweep_of_same_household_is_silent(app):
    """같은 집·같은 상태로는 다시 알리지 않는다(5분 폴링)."""
    _user("ADMIN")
    order_no = f"N-{_uid()}"
    links = [_link(order_no=order_no) for _ in range(3)]

    _sweep(links, order_nos=[order_no] * 3)
    stats = _sweep(links, order_nos=[order_no] * 3)

    assert stats["notified"] == 0
    assert len(_claims()) == 1


# --------------------------------------------------------------------------- #
# 2. 묶지 말아야 할 것은 묶지 않는다
# --------------------------------------------------------------------------- #

def test_different_households_notify_separately(app):
    """집이 다르면 알림도 따로 — 묶음이 서로 다른 주문을 뭉개면 안 된다."""
    _user("ADMIN")
    first, second = f"N-{_uid()}", f"N-{_uid()}"
    links = [_link(order_no=first), _link(order_no=second)]

    _sweep(links, order_nos=[first, second])

    rows = _claims()
    assert len(rows) == 2
    assert {row.message.count("외 ") for row in rows} == {0}


def test_same_household_split_by_owner(app):
    """같은 집이라도 담당자가 다르면 따로 간다 — 남의 주문 소식을 받으면 안 된다."""
    _user("ADMIN")
    sales_a, sales_b = _user("SALES"), _user("SALES")
    order_no = f"N-{_uid()}"
    links = [_link(order_no=order_no, order=_order_with_owner(sales_a)),
             _link(order_no=order_no, order=_order_with_owner(sales_b))]

    _sweep(links, order_nos=[order_no] * 2)

    rows = _claims()
    assert len(rows) == 2
    assert {row.target_type for row in rows} == {"USER"}
    assert {row.target_user_id for row in rows} == {sales_a.id, sales_b.id}
