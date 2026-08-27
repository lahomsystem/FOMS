"""클레임 **상태 이력** 계약 테스트 (SQLite 레인).

배경: 지금 코드는 스윕마다 ``raw_snapshot`` 을 통째로 덮어쓰고
(``claim_watch._refresh_link``), ``triage_state['claim_sync']`` 에 남기는 것은
``last_status`` **하나**(최신값)뿐이다. 그래서 클레임이
``RETURN_REQUEST`` → 수거중 → 수거완료 를 지나가면 **지나간 상태와 그때의 값이
사라진다.** 반품 승인 분기에 필요한 ``holdbackStatus``(보류)·
``claimDeliveryFeePayMethod``(반품 배송비 귀책)는 스테이징 실데이터에 0건이라
**실물 반품 1건이 유일한 관측 기회**인데, 그 1건이 와도 증거가 안 남았다.

고정하는 계약:

1. 모양이 **바뀔 때만** ``claim_sync['history']`` 에 1건 쌓인다. 모양은
   ``(claimStatus, holdbackStatus, claimDeliveryFeePayMethod)`` 셋이다 — 상태 하나로
   막으면 상태가 멈춘 채 보류·귀책만 움직이는 전이가 통째로 버려진다(CEO 검수 2026-08-27).
2. 같은 모양으로 다시 스윕하면 쌓이지 않는다(5분 폴링이라 안 막으면 JSONB 가 무한히 큰다).
3. 캡 20건 — 넘치면 오래된 쪽을 버리되 **첫 행 1건은 고정 보존**한다(처음 관측 시점).
   값의 **출처 블록**(``holdback_block``·``fee_block``)도 함께 남긴다.
   배포 전부터 진행 중이던 클레임의 첫 행은 ``backfilled: True`` 로 표시한다 —
   그 행의 ``at`` 은 전이 시각이 아니라 배포 후 첫 스윕 시각이다.
4. ``holdbackStatus``·``claimDeliveryFeePayMethod`` 가 상세에 있으면 그 값이 잡힌다.
5. 그 필드가 **아예 없어도 예외 없이** ``None`` 으로 기록된다 — 값이 없다고 스윕이
   터지면 관측 기회 자체가 사라져 이 기능의 존재 이유를 스스로 부순다.
6. 이력을 남긴다고 ``last_status``·알림 동작이 바뀌지 않는다(알림 회귀 방어).
"""

from __future__ import annotations

from datetime import datetime

from db import db_session
from foms.services.integrations.naver_commerce.claim_watch import (
    NOTIFICATION_TYPE,
    STATE_KEY,
    _HISTORY_MAX,
    refresh_claims,
)
from models import ExternalOrderLink, Notification, User

_SEQ = [0]


def _uid() -> str:
    _SEQ[0] += 1
    return str(_SEQ[0])


def _admin() -> User:
    user = User(username=f"hist_admin_{_uid()}", password="pw-not-committed",
                name="관리자", role="ADMIN", team="CS", is_active=True)
    db_session.add(user)
    db_session.commit()
    return user


def _detail(external_id: str, *, claim: str = "", reason: str = "SIMPLE_INTENT_CHANGED",
            return_block: dict | None = None) -> dict:
    """상품주문 상세 1건. ``return_block`` 을 주면 ``returnInfo`` 블록으로 싣는다."""
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
        detail["cancel"] = {"cancelReason": reason}
    if return_block is not None:
        detail["returnInfo"] = dict(return_block)
    return detail


def _link(external_id: str) -> ExternalOrderLink:
    link = ExternalOrderLink(channel="NAVER", external_id=external_id,
                             sync_status="COLLECTED",
                             raw_snapshot=_detail(external_id))
    db_session.add(link)
    db_session.commit()
    return link


class FakeClient:
    """상세 조회만 흉내낸다(claim_watch 계약 테스트와 같은 관습)."""

    def __init__(self, details: list[dict]):
        self._details = details
        self.calls: list[list[str]] = []

    def get_product_orders(self, ids):
        self.calls.append(list(ids))
        wanted = set(ids)
        return [d for d in self._details
                if d["productOrder"]["productOrderId"] in wanted]


def _changed(external_id: str) -> dict:
    return {"productOrderId": external_id, "productOrderStatus": "CHANGED"}


def _sweep(link: ExternalOrderLink, detail: dict) -> dict:
    """스윕 1회 — 상세 1건을 넣고 커밋한 뒤 집계를 준다."""
    stats = refresh_claims(db_session, client=FakeClient([detail]),
                           changed=[_changed(link.external_id)])
    db_session.commit()
    return stats


def _history(link: ExternalOrderLink) -> list[dict]:
    return list((link.triage_state or {}).get(STATE_KEY, {}).get("history") or [])


# --------------------------------------------------------------------------- #
# 1~3. 쌓이는 규칙
# --------------------------------------------------------------------------- #

def test_two_status_changes_leave_two_history_rows(app):
    """상태가 두 번 바뀌면 이력 2건 — 지나간 상태가 사라지지 않는다."""
    _admin()
    link = _link(f"PO-{_uid()}")
    _sweep(link, _detail(link.external_id, claim="RETURN_REQUEST"))
    _sweep(link, _detail(link.external_id, claim="COLLECT_DONE"))

    rows = _history(link)
    assert [row["status"] for row in rows] == ["RETURN_REQUEST", "COLLECT_DONE"]
    assert rows[0]["reason"] == "SIMPLE_INTENT_CHANGED"
    # naive=UTC 규약 — tz 가 붙어 있으면 다른 시각 축이 섞인 것이다.
    assert datetime.fromisoformat(rows[0]["at"]).tzinfo is None


def test_same_status_sweep_does_not_append(app):
    """같은 상태로 다시 스윕하면 안 쌓인다 — 5분 폴링이 JSONB 를 무한히 키운다."""
    _admin()
    link = _link(f"PO-{_uid()}")
    detail = _detail(link.external_id, claim="RETURN_REQUEST")
    _sweep(link, detail)
    _sweep(link, detail)
    _sweep(link, detail)

    assert [row["status"] for row in _history(link)] == ["RETURN_REQUEST"]


def test_history_is_capped_but_keeps_the_first_row(app):
    """21번째 상태 변화가 와도 길이는 20이고 **첫 행은 살아남는다**.

    2026-08-27 CEO 검수: 캡이 오래된 쪽부터 버리면 상태가 진동할 때 **그 클레임이 처음
    관측된 시점**이 사라진다 — "증거를 남긴다"는 목적과 방향이 반대다. 첫 행 1건은
    고정 보존하고 그 다음부터 링버퍼로 돈다.
    """
    _admin()
    link = _link(f"PO-{_uid()}")
    statuses = [f"STEP_{index:02d}" for index in range(1, _HISTORY_MAX + 2)]
    for status in statuses:
        _sweep(link, _detail(link.external_id, claim=status))

    rows = _history(link)
    assert len(rows) == _HISTORY_MAX
    assert rows[0]["status"] == "STEP_01", "처음 관측 시점이 잘려나갔다"
    assert rows[-1]["status"] == statuses[-1]
    # 가운데에서 밀려나는 것은 두 번째 행(STEP_02)이다.
    assert [row["status"] for row in rows] == [statuses[0]] + statuses[2:]


def test_holdback_change_is_recorded_even_when_claim_status_is_frozen(app):
    """`claimStatus` 가 안 바뀌어도 **보류·귀책이 바뀌면** 기록한다.

    2026-08-27 CEO 검수(치명): 중복억제 키가 `status` 하나였을 때, 실물 반품에서
    `RETURN_REQUEST` 에 머문 채 `holdbackStatus` 만 움직이는 전이가 통째로 버려졌다.
    그런데 그 축이 이 기능이 존재하는 **유일한 이유**다(승인 분기의 입력이고, 보류를
    풀면 반품비가 0원으로 초기화된다 — 원장 B1). `raw_snapshot` 은 매 스윕 덮어써지니
    한 번 놓치면 그 조합은 영구히 사라진다.
    """
    _admin()
    link = _link(f"PO-{_uid()}")
    for holdback, fee in ((None, None),
                          ("HOLDBACK_REQUEST", "RETURN_DELIVERY_FEE_DEDUCTION"),
                          ("HOLDBACK_RELEASE", "RETURN_DELIVERY_FEE_FREE")):
        block = {"claimStatus": "RETURN_REQUEST"}
        if holdback:
            block["holdbackStatus"] = holdback
            block["claimDeliveryFeePayMethod"] = fee
        _sweep(link, _detail(link.external_id, claim="RETURN_REQUEST", return_block=block))

    rows = _history(link)
    assert [row["holdback_status"] for row in rows] == [
        None, "HOLDBACK_REQUEST", "HOLDBACK_RELEASE"]
    assert rows[1]["fee_pay_method"] == "RETURN_DELIVERY_FEE_DEDUCTION"
    assert {row["status"] for row in rows} == {"RETURN_REQUEST"}, "상태는 내내 같았다"


def test_history_records_which_block_the_value_came_from(app):
    """값의 **출처 블록**을 함께 남긴다 — 그게 이 관측의 답이다.

    2026-08-27 CEO 검수(치명): 기록 축은 `cancel` 블록까지 훑는데(표시 축과 달리 좁히지
    않는다) 출처를 안 남기면 취소 블록 값이 반품 보류로 기록돼도 사후에 구분할 수 없다.
    애초에 "어느 블록에 실려 오는지조차 모른다"가 관측 목표라 출처가 곧 답이다.
    """
    _admin()
    link = _link(f"PO-{_uid()}")
    _sweep(link, _detail(link.external_id, claim="RETURN_REQUEST",
                         return_block={"claimStatus": "RETURN_REQUEST",
                                       "holdbackStatus": "HOLDBACK_REQUEST",
                                       "claimDeliveryFeePayMethod": "RETURN_DELIVERY_FEE_FREE"}))

    row = _history(link)[-1]
    assert row["holdback_block"] == "returnInfo"
    assert row["fee_block"] == "returnInfo"


def test_pre_existing_claim_first_row_is_marked_backfilled(app):
    """배포 **전부터** 진행 중이던 클레임의 첫 행은 `backfilled` 로 표시한다.

    2026-08-27 CEO 검수: 그 행의 `at` 은 전이 시각이 아니라 배포 후 첫 스윕 시각이다.
    표식이 없으면 나중에 "이 반품 언제 요청됐나"에 틀린 날짜로 답한다.
    """
    _admin()
    link = _link(f"PO-{_uid()}")
    state = dict(link.triage_state or {})
    state[STATE_KEY] = {"last_status": "RETURN_REQUEST"}
    link.triage_state = state
    db_session.commit()

    _sweep(link, _detail(link.external_id, claim="RETURN_DONE"))
    rows = _history(link)
    assert rows[0].get("backfilled") is True

    # 그 뒤 실제로 관측한 전이에는 표식이 붙지 않는다.
    _sweep(link, _detail(link.external_id, claim="RETURN_REJECT"))
    assert "backfilled" not in _history(link)[-1]


# --------------------------------------------------------------------------- #
# 4~5. 관측 대상 두 필드 (우리 코드에 grep 히트 0 — 모양을 본 적이 없다)
# --------------------------------------------------------------------------- #

def test_holdback_and_fee_pay_method_are_captured(app):
    """상세에 보류·배송비 귀책이 있으면 그 값이 이력에 잡힌다(블록 탐색)."""
    _admin()
    link = _link(f"PO-{_uid()}")
    _sweep(link, _detail(
        link.external_id, claim="RETURN_REQUEST",
        return_block={"returnReason": "BROKEN",
                      "holdbackStatus": "HOLDBACK_REQUEST",
                      "claimDeliveryFeePayMethod": "RETURN_DELIVERY_FEE_PAY_BY_SELLER"},
    ))

    row = _history(link)[-1]
    assert row["holdback_status"] == "HOLDBACK_REQUEST"
    assert row["fee_pay_method"] == "RETURN_DELIVERY_FEE_PAY_BY_SELLER"


def test_missing_holdback_fields_record_none_without_error(app):
    """두 필드가 아예 없어도 예외 없이 ``None`` 으로 기록된다.

    스테이징 392행에 0건인 필드라 '없는 게 정상'이다. 여기서 터지면 실물 반품 1건이
    들어온 그 스윕이 통째로 실패해 관측 기회 자체가 사라진다.
    """
    _admin()
    link = _link(f"PO-{_uid()}")
    stats = _sweep(link, _detail(link.external_id, claim="RETURN_REQUEST"))

    assert stats["refreshed"] == 1
    row = _history(link)[-1]
    assert row["holdback_status"] is None
    assert row["fee_pay_method"] is None


# --------------------------------------------------------------------------- #
# 6. 알림 회귀 방어 — 이 작업의 최대 위험
# --------------------------------------------------------------------------- #

def test_history_does_not_change_last_status_or_notifications(app):
    """이력을 남겨도 ``last_status``·알림 횟수는 그대로다(중복 억제가 그 값에 의존)."""
    _admin()
    link = _link(f"PO-{_uid()}")
    detail = _detail(link.external_id, claim="CANCEL_REQUEST")
    first = _sweep(link, detail)
    second = _sweep(link, detail)

    assert first["notified"] == 1 and second["notified"] == 0
    sync = link.triage_state[STATE_KEY]
    assert sync["last_status"] == "CANCEL_REQUEST"
    assert sync["notified_status"] == "CANCEL_REQUEST"
    assert db_session.query(Notification).filter(
        Notification.notification_type == NOTIFICATION_TYPE).count() == 1


def test_clean_link_first_sweep_leaves_no_history(app):
    """클레임이 없는 건의 첫 스윕은 빈 항목을 심지 않는다(지나간 상태가 없다)."""
    _admin()
    link = _link(f"PO-{_uid()}")
    _sweep(link, _detail(link.external_id))

    assert _history(link) == []
    assert link.triage_state[STATE_KEY]["last_status"] == ""
