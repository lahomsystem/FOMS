"""우리가 낸 취소는 긴급 알림으로 되돌아오지 않는다 (2026-08-24 감사).

판매자 직접취소(``fulfillment.cancel_order``)를 보내면 다음 5분 스윕이 그 결과를 클레임으로
목격한다. 예전에는 그대로 ``is_urgent=True`` 알림을 만들었고, 문안이 **"일정·생산이 잡혀
있으면 진행을 멈추고 네이버 판매자센터에서 확인하세요"** 였다. 방금 자기가 누른 일이 5분 뒤
"멈춰라" 경보로 돌아온다 — 진짜 고객 취소와 구분이 안 되니 경보 전체가 무뎌진다.

**막는 것은 알림뿐이다.** 스냅샷·발주상태·묶음키·``last_status`` 갱신은 그대로 한다.
사실은 사실이고, 화면의 '취소 완료' 표시는 그 갱신에서 나온다.
"""
from __future__ import annotations

import datetime

from db import db_session
from foms.services.integrations.naver_commerce.claim_watch import refresh_claims
from werkzeug.security import generate_password_hash

from models import ExternalOrderLink, Notification, User

_NOW = datetime.datetime(2026, 8, 24, 12, 0, 0)
_EXTERNAL_ID = "20260824990001"


class _Client:
    """상세 조회만 흉내 내는 가짜 클라이언트(네이버 HTTP 0회)."""

    def __init__(self, detail: dict):
        self._detail = detail
        self.calls: list[list[str]] = []

    def get_product_orders(self, ids):
        self.calls.append(list(ids))
        return [self._detail]


def _claimed_detail() -> dict:
    """취소가 도는 상세 응답."""
    return {
        "order": {"orderId": "N-SELF"},
        "productOrder": {
            "productOrderId": _EXTERNAL_ID,
            "productName": "취소된 상품",
            "claimStatus": "CANCEL_DONE",
            "placeOrderStatus": "OK",
            "shippingAddress": {"name": "신중섭", "tel1": "010-9000-0001",
                                "baseAddress": "서울 취소로 1", "detailedAddress": "101호"},
        },
    }


def _link(*, ours: bool) -> ExternalOrderLink:
    """수집 링크 1건. ``ours`` 면 우리가 낸 취소 표식을 남긴다."""
    state = {"fulfillment": {"canceled_at": _NOW.isoformat()}} if ours else None
    row = ExternalOrderLink(
        channel="NAVER", external_id=_EXTERNAL_ID, external_order_no="N-SELF",
        sync_status="LINKED", place_order_status="OK", triage_state=state,
        raw_snapshot={"order": {"orderId": "N-SELF"},
                      "productOrder": {"productOrderId": _EXTERNAL_ID}},
    )
    db_session.add(row)
    db_session.commit()
    return row


def _admin() -> User:
    """알림이 도달할 곳 — 담당자가 없으면 ADMIN 역할로 올라간다(_notify_targets)."""
    user = User(username="claimwatch_admin", password=generate_password_hash("pw"),
                role="ADMIN", team="CS", name="관리자", is_active=True)
    db_session.add(user)
    db_session.commit()
    return user


def _notifications() -> list[Notification]:
    return db_session.query(Notification).filter(
        Notification.notification_type == "NAVER_ORDER_CLAIMED").all()


def test_our_own_cancel_does_not_page_anyone(app):
    """우리 취소 표식이 있으면 알림을 만들지 않는다.

    **수신자를 반드시 만들어 둔다** — 대상이 없으면 억제가 없어도 알림이 0건이라
    이 테스트가 우연히 통과한다(2026-08-24 자기점검에서 실제로 그랬다).
    """
    _admin()
    _link(ours=True)
    client = _Client(_claimed_detail())

    stats = refresh_claims(db_session, client=client,
                           changed=[{"productOrderId": _EXTERNAL_ID}], now=_NOW)
    db_session.commit()

    assert stats["claimed"] == 1, "사실은 그대로 센다"
    assert stats["notified"] == 0, "우리가 누른 일이 경보로 돌아왔다"
    assert stats["self_canceled"] == 1, "억제도 세어야 나중에 확인할 수 있다"
    assert _notifications() == []


def test_a_real_customer_cancel_still_pages(app):
    """표식이 없으면(=고객이 취소) 예전처럼 알린다 — 억제가 진짜 사고까지 삼키면 안 된다."""
    _admin()
    _link(ours=False)
    client = _Client(_claimed_detail())

    stats = refresh_claims(db_session, client=client,
                           changed=[{"productOrderId": _EXTERNAL_ID}], now=_NOW)
    db_session.commit()

    assert stats["claimed"] == 1
    assert stats["notified"] >= 1, "고객 취소를 안 알리면 생산이 그대로 나간다"
    assert stats["self_canceled"] == 0
    assert _notifications(), "알림 row 가 없다"


def test_suppression_still_refreshes_the_facts(app):
    """알림만 막고 **상태 갱신은 그대로** 한다 — 화면의 '취소 완료'가 거기서 나온다."""
    _admin()
    link = _link(ours=True)
    link_id = int(link.id)
    client = _Client(_claimed_detail())

    refresh_claims(db_session, client=client,
                   changed=[{"productOrderId": _EXTERNAL_ID}], now=_NOW)
    db_session.commit()
    db_session.expire_all()

    fresh = db_session.get(ExternalOrderLink, link_id)
    assert fresh.raw_snapshot["productOrder"]["claimStatus"] == "CANCEL_DONE"
    assert fresh.place_order_status == "OK"
    assert fresh.triage_state["claim_sync"]["last_status"] == "CANCEL_DONE"
    # 우리 취소 표식은 그대로 남는다(다른 축이라 덮어쓰지 않는다).
    assert fresh.triage_state["fulfillment"]["canceled_at"]
