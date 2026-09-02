"""NAVER-INGEST-BACKFILL: 과거 주문 소급 수집 계약 테스트 (SQLite 레인).

고정하는 계약:

* **워터마크를 건드리지 않는다** — 백필이 정상 수집의 전진 기록을 되돌리면 안 된다.
* 구간을 하루 단위 창으로 나눠 순회하고, 창마다 커밋해 진척(``done_through``)을 남긴다.
* 중복 수집 0 — 같은 상품주문이 두 번 들어오지 않는다(사전 조회 + UNIQUE).
* 과거 클레임은 **반영하되 알림 0건**(사용자 결정 2026-09-01).
* 구간 규칙 위반(빈 구간·미래·90일 초과)은 **네이버 호출 0회**로 거절한다.
* 한 창이 실패해도 앞 창의 성과는 남고, 실패 사유가 상태에 기록된다.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from db import db_session
from foms.services.integrations.naver_commerce import backfill as backfill_mod
from foms.services.integrations.naver_commerce import watermark as wm
from foms.services.integrations.naver_commerce.backfill import (
    BackfillRangeError,
    MAX_RANGE,
    read_state,
    run_backfill,
    validate_range,
)
from foms.services.integrations.naver_commerce.client import KST
from models import ExternalOrderLink, Notification, User

_SEQ = [0]


def _uid() -> str:
    _SEQ[0] += 1
    return str(_SEQ[0])


def _detail(product_order_id: str, *, claim: str = "") -> dict:
    """상세 응답 1건(값은 가상)."""
    product_order = {
        "productOrderId": product_order_id,
        "productOrderStatus": "PAYED",
        "productName": "붙박이장 세트",
        "productOption": "색상: 화이트 / 폭: 2400",
        "quantity": 1,
        "totalPaymentAmount": 1250000,
        "shippingAddress": {
            "name": "이수취",
            "tel1": "010-3333-4444",
            "baseAddress": "서울특별시 강남구 테헤란로 1",
            "detailedAddress": "101동 1001호",
        },
    }
    if claim:
        product_order["claimStatus"] = claim
    detail = {
        "order": {
            "orderId": f"ORD-{product_order_id}",
            "ordererName": "김주문",
            "ordererTel": "010-1111-2222",
            "orderDate": "2026-06-12T14:23:11.000+09:00",
        },
        "productOrder": product_order,
    }
    if claim:
        detail["cancel"] = {"cancelReason": "SIMPLE_INTENT_CHANGED"}
    return detail


def _changed(product_order_id: str, status: str = "PAYED") -> dict:
    return {"productOrderId": product_order_id, "productOrderStatus": status,
            "lastChangedDate": "2026-06-12T14:24:00.000+09:00"}


class WindowClient:
    """창(start)별로 서로 다른 변경 목록을 돌려주는 가짜 클라이언트."""

    def __init__(self, per_window: list[list[dict]], details: list[dict]):
        self._per_window = per_window
        self._details = details
        self.windows: list[tuple[datetime, datetime]] = []
        self.detail_calls: list[list[str]] = []

    def get_last_changed_statuses(self, start, end):
        index = len(self.windows)
        self.windows.append((start, end))
        if index < len(self._per_window):
            return list(self._per_window[index])
        return []

    def get_product_orders(self, ids):
        self.detail_calls.append(list(ids))
        wanted = set(ids)
        return [d for d in self._details
                if d["productOrder"]["productOrderId"] in wanted]


class ExplodingClient(WindowClient):
    """두 번째 창에서 터지는 클라이언트(부분 실패 계약용)."""

    def get_last_changed_statuses(self, start, end):
        if len(self.windows) == 1:
            self.windows.append((start, end))
            raise RuntimeError("네이버 500")
        return super().get_last_changed_statuses(start, end)


NOW = datetime(2026, 9, 1, 12, 0, tzinfo=KST)


def _run(client, *, days: int = 2, **kwargs):
    """``days`` 일 구간을 백필한다(실대기 없음)."""
    end = NOW - timedelta(days=1)
    start = end - timedelta(days=days)
    return run_backfill(db_session, client=client, start=start, end=end,
                        now=NOW, sleep=lambda _seconds: None, **kwargs)


# --------------------------------------------------------------------------- #
# 구간 규칙 — 호출 전에 거절한다
# --------------------------------------------------------------------------- #

def test_reversed_range_is_rejected_without_any_call(app):
    """시작이 끝보다 뒤면 네이버를 부르지 않는다."""
    client = WindowClient([], [])
    with pytest.raises(BackfillRangeError):
        run_backfill(db_session, client=client, start=NOW, end=NOW - timedelta(days=1),
                     now=NOW, sleep=lambda _s: None)
    assert client.windows == []


def test_future_end_is_rejected(app):
    """아직 오지 않은 구간은 긁을 수 없다."""
    with pytest.raises(BackfillRangeError):
        validate_range(NOW - timedelta(days=1), NOW + timedelta(hours=1), now=NOW)


def test_range_over_limit_is_rejected_not_silently_trimmed(app):
    """90일을 넘기면 조용히 자르지 않고 거절한다("다 긁었다"로 읽히면 안 된다)."""
    with pytest.raises(BackfillRangeError):
        validate_range(NOW - MAX_RANGE - timedelta(days=1), NOW, now=NOW)
    # 상한과 정확히 같은 길이는 통과한다.
    begin, finish = validate_range(NOW - MAX_RANGE, NOW, now=NOW)
    assert finish - begin == MAX_RANGE


def test_naive_datetimes_are_read_as_kst(app):
    """naive 입력은 KST 로 간주한다(운영 화면이 날짜만 보낸다)."""
    begin, finish = validate_range(datetime(2026, 8, 1), datetime(2026, 8, 2), now=NOW)
    assert begin.tzinfo is not None and finish.tzinfo is not None


# --------------------------------------------------------------------------- #
# 창 순회 · 수집
# --------------------------------------------------------------------------- #

def test_range_is_split_into_daily_windows(app):
    """이틀 구간은 하루 단위 창 두 개 이상으로 나뉜다(API 24시간 상한)."""
    client = WindowClient([], [])
    payload = _run(client, days=2)
    assert len(client.windows) >= 2
    assert payload["windows"] == len(client.windows)
    # 마지막 창의 끝은 요청 구간의 끝이다(끝을 넘겨 조회하지 않는다).
    assert client.windows[-1][1] == datetime.fromisoformat(payload["window"]["to"])


def test_backfill_collects_links_for_past_orders(app):
    """과거 구간의 결제완료 건이 링크로 보관된다."""
    external_id = f"PO-BF-{_uid()}"
    client = WindowClient([[_changed(external_id)]], [_detail(external_id)])
    payload = _run(client, days=1)
    assert payload["collected"] == 1
    link = (db_session.query(ExternalOrderLink)
            .filter(ExternalOrderLink.external_id == external_id).one())
    assert link.sync_status == "COLLECTED"
    assert link.order_id is None      # 백필은 주문을 만들지 않는다
    assert link.group_key             # 집 묶기 사본은 정상 수집과 같은 경로로 채워진다


def test_second_run_collects_nothing_new(app):
    """같은 구간을 다시 돌려도 중복 수집 0 (멱등)."""
    external_id = f"PO-BF-{_uid()}"
    details = [_detail(external_id)]
    first = _run(WindowClient([[_changed(external_id)]], details), days=1)
    second = _run(WindowClient([[_changed(external_id)]], details), days=1)
    assert first["collected"] == 1
    assert second["collected"] == 0
    assert second["skipped"] >= 1
    assert (db_session.query(ExternalOrderLink)
            .filter(ExternalOrderLink.external_id == external_id).count()) == 1


def test_watermark_is_not_touched(app):
    """백필은 워터마크를 앞으로도 뒤로도 움직이지 않는다."""
    wm.advance(db_session, success_to=NOW - timedelta(hours=2), now=NOW)
    db_session.commit()
    before = wm.read_watermark(db_session)
    assert before is not None
    external_id = f"PO-BF-{_uid()}"
    _run(WindowClient([[_changed(external_id)]], [_detail(external_id)]), days=1)
    assert wm.read_watermark(db_session) == before


def test_dry_run_makes_nothing(app):
    """dry-run 은 조회까지만 한다 — 링크도 상태 요약도 만들지 않는다."""
    external_id = f"PO-BF-{_uid()}"
    payload = _run(WindowClient([[_changed(external_id)]], [_detail(external_id)]),
                   days=1, dry_run=True)
    assert payload["collected"] == 0
    assert (db_session.query(ExternalOrderLink)
            .filter(ExternalOrderLink.external_id == external_id).count()) == 0


# --------------------------------------------------------------------------- #
# 알림 억제
# --------------------------------------------------------------------------- #

def test_past_claims_are_applied_without_notifications(app):
    """과거 취소는 상태로 반영하되 알림을 만들지 않는다(사용자 결정 2026-09-01)."""
    external_id = f"PO-BF-{_uid()}"
    # 1창: 결제완료로 수집 → 2창: 같은 건이 취소로 다시 변경 이벤트
    client = WindowClient(
        [[_changed(external_id)], [_changed(external_id, "CANCELED")]],
        [_detail(external_id, claim="CANCEL_REQUEST")],
    )
    # 알림이 갈 **자리가 있는** 상태로 잰다 — 받을 사람이 없으면 억제를 반증할 수 없다.
    db_session.add(User(username=f"bf_admin_{_uid()}", password="pw-not-committed",
                        name="관리자", role="ADMIN", team="CS", is_active=True))
    db_session.commit()
    before = db_session.query(Notification).count()
    payload = _run(client, days=2)
    assert payload["claims_refreshed"] >= 1
    assert db_session.query(Notification).count() == before


# --------------------------------------------------------------------------- #
# 진행 상태 · 부분 실패
# --------------------------------------------------------------------------- #

def test_progress_state_records_done_through(app):
    """창마다 진척을 남긴다 — 끊겨도 어디까지 했는지 안다."""
    _run(WindowClient([], []), days=2)
    state = read_state(db_session)
    assert state["running"] is False
    assert state["done_through"] == state["requested_to"]
    assert state["last_summary"]["windows"] >= 2


def test_failed_window_keeps_earlier_progress_and_records_error(app):
    """두 번째 창이 터져도 첫 창의 수집은 남고, 사유가 상태에 적힌다."""
    external_id = f"PO-BF-{_uid()}"
    client = ExplodingClient([[_changed(external_id)]], [_detail(external_id)])
    payload = _run(client, days=2)
    assert "failed" in payload
    assert payload["collected"] == 1
    assert (db_session.query(ExternalOrderLink)
            .filter(ExternalOrderLink.external_id == external_id).count()) == 1
    state = read_state(db_session)
    assert state["running"] is False
    assert "네이버 500" in state["last_error"]


def test_calls_are_spaced_between_windows(app):
    """창 사이에 간격을 둔다 — 2 RPS 한도를 넘기지 않기 위한 유일한 방벽."""
    slept: list[float] = []
    end = NOW - timedelta(days=1)
    run_backfill(db_session, client=WindowClient([], []), start=end - timedelta(days=3),
                 end=end, now=NOW, sleep=slept.append)
    assert slept and all(value == backfill_mod.CALL_INTERVAL_SECONDS for value in slept)


# --------------------------------------------------------------------------- #
# 상태 필터 — 과거는 결제완료로 안 걸린다
# --------------------------------------------------------------------------- #

def test_backfill_collects_orders_that_are_no_longer_payed(app):
    """오래된 주문은 이미 배송완료·구매확정이다 — 결제완료 필터로 거르면 0건이 된다.

    스테이징 실측(2026-09-01): 06-04~08-16 변경 이벤트 1,300건 중 PAYED 0건.
    변경 피드의 ``productOrderStatus`` 가 이벤트 당시가 아니라 현재 상태이기 때문이다.
    """
    external_id = f"PO-BF-{_uid()}"
    detail = _detail(external_id)
    detail["productOrder"]["productOrderStatus"] = "DELIVERED"
    client = WindowClient([[_changed(external_id, "DELIVERED")]], [detail])
    payload = _run(client, days=1)
    assert payload["collected"] == 1
    assert (db_session.query(ExternalOrderLink)
            .filter(ExternalOrderLink.external_id == external_id).count()) == 1


def test_normal_sweep_filters_known_non_payed(app):
    """정상 스윕은 **이미 아는** 상품주문의 비결제완료 변경을 후보로 삼지 않는다.

    2026-09-02 이후 처음 보는 번호는 상태와 무관하게 받는다(D1) — 그래서 대조군은
    링크가 이미 있는 건이어야 한다. 백필과 스윕의 차이는 이 축뿐이다.
    """
    from foms.services.integrations.naver_commerce.ingest import sync_naver_orders

    external_id = f"PO-BF-{_uid()}"
    detail = _detail(external_id)
    detail["productOrder"]["productOrderStatus"] = "DELIVERED"
    db_session.add(ExternalOrderLink(channel="NAVER", external_id=external_id,
                                     sync_status="COLLECTED", raw_snapshot=detail))
    db_session.commit()
    client = WindowClient([[_changed(external_id, "DELIVERED")]], [detail])
    result = sync_naver_orders(db_session, client=client, start=NOW - timedelta(hours=6),
                               end=NOW, now=NOW)
    db_session.commit()
    assert result.candidates == 0
    assert result.collected == 0
    assert result.dropped_by_status == {"DELIVERED": 1}


# --------------------------------------------------------------------------- #
# 처리 큐 보호 — 백필은 "지금 할 일"이 아니다
# --------------------------------------------------------------------------- #

def test_backfilled_links_are_marked_reviewed_and_stay_out_of_the_queue(app):
    """백필 링크는 확인 완료로 들어온다 — 안 그러면 90일치가 처리 탭을 덮는다.

    스테이징 실측(2026-09-01): 표식 없이 돌린 백필이 링크 1,560건 = 798집을 큐에 밀어넣었다.
    """
    external_id = f"PO-BF-{_uid()}"
    _run(WindowClient([[_changed(external_id)]], [_detail(external_id)]), days=1)
    link = (db_session.query(ExternalOrderLink)
            .filter(ExternalOrderLink.external_id == external_id).one())
    assert link.reviewed_at is not None
    # 시각만 남기면 사람이 확인한 것과 구분이 안 된다 — 소급분 표식을 함께 남긴다.
    assert (link.triage_state or {}).get("backfill")


def test_normal_sweep_links_still_enter_the_queue(app):
    """정상 스윕은 그대로다 — 새 주문은 사람이 봐야 한다."""
    from foms.services.integrations.naver_commerce.ingest import sync_naver_orders

    external_id = f"PO-BF-{_uid()}"
    client = WindowClient([[_changed(external_id)]], [_detail(external_id)])
    sync_naver_orders(db_session, client=client, start=NOW - timedelta(hours=6),
                      end=NOW, now=NOW)
    db_session.commit()
    link = (db_session.query(ExternalOrderLink)
            .filter(ExternalOrderLink.external_id == external_id).one())
    assert link.reviewed_at is None
