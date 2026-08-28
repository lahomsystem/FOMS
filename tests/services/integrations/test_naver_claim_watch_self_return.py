"""우리가 낸 **반품 접수**도 긴급 알림으로 되돌아오지 않는다 (R-3, 2026-08-28).

취소는 2026-08-24 감사에서 막았는데 **반품 복사본이 없었다**. 표식이 다른 자리에 남기
때문이다 — 취소는 ``triage_state['fulfillment']['canceled_at']``, 반품은
``triage_state['return']['requested_at']``. 억제 판정이 앞쪽만 읽어서, 담당자가 반품
접수 버튼을 누르면 5분 뒤 **"일정·생산이 잡혀 있으면 진행을 멈추세요"** 경보가 자기에게
돌아온다. 반품 버튼은 운영에 살아 있고(PR #171) 아직 아무도 안 눌렀을 뿐이다.

억제는 **클레임 종류가 맞을 때만** 한다 — 반품 표식이 진짜 고객 취소를 삼키면 안 된다.
"""
from __future__ import annotations

import datetime

from db import db_session
from foms.services.integrations.naver_commerce.claim_watch import refresh_claims
from werkzeug.security import generate_password_hash

from models import ExternalOrderLink, Notification, User

_NOW = datetime.datetime(2026, 8, 28, 12, 0, 0)
_EXTERNAL_ID = "20260828990001"


class _Client:
    """상세 조회만 흉내 내는 가짜 클라이언트(네이버 HTTP 0회)."""

    def __init__(self, detail: dict):
        self._detail = detail

    def get_product_orders(self, ids):
        return [self._detail]


def _detail(status: str, claim_type: str) -> dict:
    """클레임이 도는 상세 응답 1건."""
    return {
        "order": {"orderId": "N-SELFRET"},
        "productOrder": {
            "productOrderId": _EXTERNAL_ID,
            "productName": "반품 접수한 상품",
            "claimStatus": status,
            "claimType": claim_type,
            "placeOrderStatus": "OK",
            "shippingAddress": {"name": "신중섭", "tel1": "010-9000-0002",
                                "baseAddress": "서울 반품로 1", "detailedAddress": "101호"},
        },
    }


def _link(state: dict | None) -> ExternalOrderLink:
    """수집 링크 1건 — ``state`` 가 우리 표식이다(없으면 고객이 낸 클레임)."""
    row = ExternalOrderLink(
        channel="NAVER", external_id=_EXTERNAL_ID, external_order_no="N-SELFRET",
        sync_status="LINKED", place_order_status="OK", triage_state=state,
        raw_snapshot={"order": {"orderId": "N-SELFRET"},
                      "productOrder": {"productOrderId": _EXTERNAL_ID}},
    )
    db_session.add(row)
    db_session.commit()
    return row


def _ours_return() -> dict:
    return {"return": {"requested_at": _NOW.isoformat(), "requested_by": 1,
                       "reason": "INTENT_CHANGED", "collect_method": "RETURN_INDIVIDUAL"}}


def _ours_cancel() -> dict:
    return {"fulfillment": {"canceled_at": _NOW.isoformat()}}


def _admin() -> User:
    """알림이 도달할 곳 — 대상이 없으면 억제가 없어도 알림 0건이라 테스트가 우연히 통과한다."""
    user = User(username="claimwatch_ret_admin", password=generate_password_hash("pw"),
                role="ADMIN", team="CS", name="관리자", is_active=True)
    db_session.add(user)
    db_session.commit()
    return user


def _run(detail: dict) -> dict:
    stats = refresh_claims(db_session, client=_Client(detail),
                           changed=[{"productOrderId": _EXTERNAL_ID}], now=_NOW)
    db_session.commit()
    return stats


def _notifications() -> list[Notification]:
    return db_session.query(Notification).filter(
        Notification.notification_type == "NAVER_ORDER_CLAIMED").all()


def test_our_own_return_does_not_page_anyone(app):
    """우리가 낸 반품 접수는 경보로 돌아오지 않는다 — R-3 의 본체."""
    _admin()
    _link(_ours_return())

    stats = _run(_detail("RETURN_REQUEST", "RETURN"))

    assert stats["claimed"] == 1, "사실은 그대로 센다"
    assert stats["notified"] == 0, "방금 자기가 누른 일이 경보로 돌아왔다"
    assert stats["self_claimed"] == 1, "억제도 세어야 나중에 확인할 수 있다"
    assert _notifications() == []


def test_our_return_stays_quiet_through_the_whole_chain(app):
    """수거·완료까지 조용하다 — 우리 반품이 단계를 넘을 때마다 경보가 울리면 같은 사고다."""
    _admin()
    _link(_ours_return())

    stats = _run(_detail("COLLECT_DONE", "RETURN"))

    assert stats["notified"] == 0
    assert stats["self_claimed"] == 1


def test_a_real_customer_return_still_pages(app):
    """**음성 대조군** — 표식이 없으면(=고객이 낸 반품) 예전처럼 알린다."""
    _admin()
    _link(None)

    stats = _run(_detail("RETURN_REQUEST", "RETURN"))

    assert stats["claimed"] == 1
    assert stats["notified"] >= 1, "고객 반품을 안 알리면 생산이 그대로 나간다"
    assert stats["self_claimed"] == 0
    assert _notifications(), "알림 row 가 없다"


def test_our_return_marker_does_not_swallow_a_real_cancel(app):
    """**음성 대조군** — 반품 표식이 고객 **취소**까지 삼키면 안 된다.

    억제는 종류가 맞을 때만 한다. 표식 하나가 모든 클레임을 덮으면, 반품을 한 번 접수한
    링크는 그 뒤 어떤 진짜 사고가 나도 영영 조용해진다.
    """
    _admin()
    _link(_ours_return())

    stats = _run(_detail("CANCEL_DONE", "CANCEL"))

    assert stats["notified"] >= 1
    assert stats["self_claimed"] == 0
    assert _notifications(), "취소 알림 row 가 없다"


def test_our_cancel_marker_does_not_swallow_a_real_return(app):
    """**음성 대조군** — 반대 방향도 같다(취소 표식이 반품을 덮지 않는다)."""
    _admin()
    _link(_ours_cancel())

    stats = _run(_detail("RETURN_REQUEST", "RETURN"))

    assert stats["notified"] >= 1
    assert stats["self_claimed"] == 0


def test_suppression_still_refreshes_the_facts(app):
    """알림만 막고 상태 갱신은 그대로 한다 — 화면의 '반품 요청' 표시가 거기서 나온다."""
    _admin()
    link = _link(_ours_return())
    link_id = int(link.id)

    _run(_detail("RETURN_REQUEST", "RETURN"))

    row = db_session.get(ExternalOrderLink, link_id)
    assert (row.triage_state or {}).get("claim_sync", {}).get("last_status") == "RETURN_REQUEST"
