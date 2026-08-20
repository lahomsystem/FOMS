"""NAVER-INGEST-01 T14-F: 수집 이후 취소·반품 추적 계약 테스트 (SQLite 레인).

고정하는 계약:

* 변경 목록에 **이미 수집한** 상품주문이 떴을 때만 상세를 다시 부른다(추가 호출 최소화).
* 취소 판정 정본은 상세 응답의 ``claimStatus`` — 변경 목록의 상태 문자열이 아니다.
* 원본 스냅샷을 최신으로 갈아 끼워 화면(큐·트리아지·도크)이 자동으로 최신을 보게 한다.
* 알림은 **같은 상태로 두 번 보내지 않는다**(5분 폴링).
* 담당자가 없으면 ADMIN **역할** 알림 1건이다 — 관리자 수만큼 복제하지 않는다
  (NOTIF-ROLE-01, 수신자별 상태는 ``notification_user_states``).
* 주문 상태를 자동으로 바꾸지 않는다(사용자 확정 — 표시 + 알림까지).
"""

from __future__ import annotations

from db import db_session
from foms.services.integrations.naver_commerce.claim_watch import (
    NOTIFICATION_TYPE,
    STATE_KEY,
    changed_external_ids,
    refresh_claims,
)
from models import ExternalOrderLink, Notification, User

_SEQ = [0]


def _uid() -> str:
    _SEQ[0] += 1
    return str(_SEQ[0])


def _admin() -> User:
    user = User(username=f"claim_admin_{_uid()}", password="pw-not-committed",
                name="관리자", role="ADMIN", team="CS", is_active=True)
    db_session.add(user)
    db_session.commit()
    return user


def _detail(external_id: str, *, claim: str = "", amount: int = 500000) -> dict:
    product_order = {
        "productOrderId": external_id,
        "productOrderStatus": "PAYED",
        "productName": "붙박이장",
        "productOption": "색상: 화이트",
        "totalPaymentAmount": amount,
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


def _link(external_id: str) -> ExternalOrderLink:
    link = ExternalOrderLink(channel="NAVER", external_id=external_id,
                             sync_status="COLLECTED",
                             raw_snapshot=_detail(external_id))
    db_session.add(link)
    db_session.commit()
    return link


class FakeClient:
    """상세 조회만 흉내내고 호출 인자를 기록한다."""

    def __init__(self, details: list[dict]):
        self._details = details
        self.calls: list[list[str]] = []

    def get_product_orders(self, ids):
        self.calls.append(list(ids))
        wanted = set(ids)
        return [d for d in self._details
                if d["productOrder"]["productOrderId"] in wanted]


def _changed(external_id: str, status: str = "CANCELED") -> dict:
    return {"productOrderId": external_id, "productOrderStatus": status}


# --------------------------------------------------------------------------- #
# 대상 선정
# --------------------------------------------------------------------------- #

def test_changed_ids_are_not_filtered_by_status():
    """취소도 변경 이벤트로 온다 — 수집 후보와 달리 상태로 거르지 않는다."""
    ids = changed_external_ids([_changed("PO-1", "CANCELED"),
                                _changed("PO-2", "PAYED"),
                                _changed("PO-1", "CANCELED")])
    assert ids == ["PO-1", "PO-2"]


def test_no_existing_link_means_no_extra_api_call(app):
    """수집한 적 없는 상품주문만 바뀌었으면 상세를 부르지 않는다(호출 0회)."""
    client = FakeClient([_detail("PO-UNKNOWN", claim="CANCEL_REQUEST")])
    stats = refresh_claims(db_session, client=client, changed=[_changed("PO-UNKNOWN")])
    assert client.calls == []
    assert stats == {"refreshed": 0, "claimed": 0, "notified": 0}


def test_empty_change_list_short_circuits(app):
    """변경이 없으면 아무것도 하지 않는다."""
    client = FakeClient([])
    assert refresh_claims(db_session, client=client, changed=[])["refreshed"] == 0
    assert client.calls == []


# --------------------------------------------------------------------------- #
# 반영 + 알림
# --------------------------------------------------------------------------- #

def test_cancel_after_collection_is_detected_and_notified(app):
    """수집 뒤 취소되면 원본이 갱신되고 담당자(없으면 ADMIN 역할)에게 알린다."""
    _admin()
    link = _link(f"PO-{_uid()}")
    client = FakeClient([_detail(link.external_id, claim="CANCEL_REQUEST")])

    stats = refresh_claims(db_session, client=client,
                           changed=[_changed(link.external_id)])
    db_session.commit()

    assert stats["refreshed"] == 1 and stats["claimed"] == 1 and stats["notified"] == 1
    # 원본이 최신으로 갈렸다 — 화면은 전부 여기서 읽는다.
    assert link.raw_snapshot["productOrder"]["claimStatus"] == "CANCEL_REQUEST"
    assert link.triage_state[STATE_KEY]["last_status"] == "CANCEL_REQUEST"

    rows = (db_session.query(Notification)
            .filter(Notification.notification_type == NOTIFICATION_TYPE).all())
    assert len(rows) == 1
    # 담당자가 없으면 ADMIN '역할' 알림 1건 — 관리자 수만큼 복제하지 않는다(NOTIF-ROLE-01).
    assert rows[0].target_type == "ROLE" and rows[0].target_role == "ADMIN"
    assert rows[0].target_user_id is None
    assert "취소 요청" in rows[0].title


def test_same_claim_status_does_not_notify_twice(app):
    """5분 폴링이라 중복 방지가 필수다 — 같은 상태로는 한 번만 알린다."""
    _admin()
    link = _link(f"PO-{_uid()}")
    client = FakeClient([_detail(link.external_id, claim="CANCEL_REQUEST")])
    changed = [_changed(link.external_id)]

    refresh_claims(db_session, client=client, changed=changed)
    db_session.commit()
    second = refresh_claims(db_session, client=client, changed=changed)
    db_session.commit()

    assert second["refreshed"] == 1 and second["claimed"] == 1
    assert second["notified"] == 0
    rows = (db_session.query(Notification)
            .filter(Notification.notification_type == NOTIFICATION_TYPE).all())
    assert len(rows) == 1


def test_escalated_claim_status_notifies_again(app):
    """취소 요청 → 취소 완료처럼 상태가 바뀌면 다시 알린다(상태별 1회)."""
    _admin()
    link = _link(f"PO-{_uid()}")
    changed = [_changed(link.external_id)]
    refresh_claims(db_session, client=FakeClient([_detail(link.external_id, claim="CANCEL_REQUEST")]),
                   changed=changed)
    db_session.commit()
    refresh_claims(db_session, client=FakeClient([_detail(link.external_id, claim="CANCEL_DONE")]),
                   changed=changed)
    db_session.commit()

    rows = (db_session.query(Notification)
            .filter(Notification.notification_type == NOTIFICATION_TYPE).all())
    assert len(rows) == 2
    assert link.triage_state[STATE_KEY]["notified_status"] == "CANCEL_DONE"


def test_normal_change_refreshes_without_notifying(app):
    """취소가 아닌 변경(배송 등)은 원본만 갱신하고 알리지 않는다."""
    _admin()
    link = _link(f"PO-{_uid()}")
    client = FakeClient([_detail(link.external_id, amount=777000)])

    stats = refresh_claims(db_session, client=client, changed=[_changed(link.external_id)])
    db_session.commit()

    assert stats == {"refreshed": 1, "claimed": 0, "notified": 0}
    assert link.raw_snapshot["productOrder"]["totalPaymentAmount"] == 777000
    assert db_session.query(Notification).filter(
        Notification.notification_type == NOTIFICATION_TYPE).count() == 0


def test_claim_watch_type_is_registered_for_push():
    """P1 미등재면 enqueue 해도 push 가 조용히 no-op 된다(무음 알림의 유일한 기전)."""
    from foms.services.notifications.push_sender import _DEFAULT_P1_TYPES

    assert NOTIFICATION_TYPE in _DEFAULT_P1_TYPES
