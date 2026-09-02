"""NAVER-AUTODISPATCH-01: 발송처리 자동 실행 계약 테스트 (SQLite 레인).

되돌릴 수 없는 조작을 무인으로 돌리는 자리라, 고정하는 것이 전부 "안 나가는 조건"이다:

* 스위치가 꺼져 있으면 **큐 호출 0회**(force 로도 못 넘는다).
* 주말·공휴일에는 대상을 세지도 않는다.
* 같은 날 두 번 불러도 한 번만 나간다.
* 보낼 집이 0이면 조용히 지나간다 — 알림도 감사도 만들지 않는다(사람이 이미 보낸 날).
* 막힌 집은 안 나가고, 그 수를 알림이 말한다.
* 큐가 죽으면 오늘을 닫지 않는다(다음 창에서 다시 시도해야 한다).
"""

from __future__ import annotations

from datetime import datetime, timezone, timedelta

import pytest

from db import db_session
from foms.services.integrations.naver_commerce import auto_dispatch as auto
from models import ExternalOrderLink, Notification, Order, OrderScheduleDate, SecurityLog

KST = timezone(timedelta(hours=9))

#: 2026-09-02 는 수요일(영업일), 2026-09-05 는 토요일.
WEEKDAY = datetime(2026, 9, 2, 16, 50, tzinfo=KST)
SATURDAY = datetime(2026, 9, 5, 16, 50, tzinfo=KST)

_SEQ = [0]


def _uid() -> str:
    _SEQ[0] += 1
    return str(_SEQ[0])


@pytest.fixture(autouse=True)
def _flags_on(monkeypatch):
    """기본은 켜진 상태로 잰다(꺼짐 계약은 개별 테스트가 따로 끈다)."""
    monkeypatch.setenv("FOMS_NAVER_BULK_DISPATCH_ENABLED", "1")
    monkeypatch.setenv("FOMS_NAVER_AUTO_DISPATCH_ENABLED", "1")


@pytest.fixture()
def queue_calls(monkeypatch):
    """큐 호출을 가로채 인자를 모은다(네이버로 나가지 않는다)."""
    calls: list[tuple] = []
    monkeypatch.setattr(
        "foms.services.jobs.queue.enqueue_naver_fulfillment",
        lambda link_id, action, actor=None: calls.append((link_id, action, actor)) or True,
    )
    return calls


def _detail(external_id: str, *, order_no: str) -> dict:
    return {
        "order": {"orderId": order_no, "ordererName": "김주문",
                  "ordererTel": "010-1111-2222"},
        "productOrder": {
            "productOrderId": external_id,
            "productOrderStatus": "PAYED",
            "placeOrderStatus": "OK",
            "productName": "붙박이장",
            "totalPaymentAmount": 1000000,
            "shippingAddress": {"name": "이수취", "tel1": "010-3333-4444",
                                "baseAddress": "서울 강남구 1", "detailedAddress": "101호"},
        },
    }


def _sendable_house(day: str, *, place_ok: bool = True) -> Order:
    """그날 실측 일정이 잡힌 주문 + 붙은 네이버 링크 1행."""
    order = Order(received_date=day, customer_name=f"자동{_uid()}", phone="010-5555-6666",
                  address="서울 강남구 테헤란로 1", product="붙박이장", status="MEASURE",
                  is_erp_order=True, measurement_date=day, erp_measurement_date=day,
                  structured_data={"schedule": {"measurement": {"date": day}}})
    db_session.add(order)
    db_session.commit()
    db_session.add(OrderScheduleDate(order_id=int(order.id), kind="measurement",
                                     date=day, source="beta_schedule"))
    external_id = f"PO-AUTO-{_uid()}"
    order_no = f"N-AUTO-{_uid()}"
    detail = _detail(external_id, order_no=order_no)
    if not place_ok:
        detail["productOrder"]["placeOrderStatus"] = "NOT_YET"
    db_session.add(ExternalOrderLink(
        channel="NAVER", external_id=external_id, order_id=int(order.id),
        external_order_no=order_no, sync_status="LINKED", raw_snapshot=detail,
        place_order_status=detail["productOrder"]["placeOrderStatus"],
        group_key=order_no,
    ))
    db_session.commit()
    return order


def _run(now: datetime = WEEKDAY, **kwargs):
    return auto.run_auto_dispatch(db_session, now=now, **kwargs)


# --------------------------------------------------------------------------- #
# 안 나가는 조건
# --------------------------------------------------------------------------- #

def test_disabled_switch_makes_no_call(app, queue_calls, monkeypatch):
    """자동 스위치가 꺼져 있으면 큐를 부르지 않는다."""
    monkeypatch.setenv("FOMS_NAVER_AUTO_DISPATCH_ENABLED", "0")
    _sendable_house("2026-09-02")
    assert _run()["outcome"] == "disabled"
    assert queue_calls == []


def test_feature_kill_switch_also_stops_auto(app, queue_calls, monkeypatch):
    """기능 킬스위치가 꺼져 있으면 자동만 켜도 안 나간다(손잡이가 갈리면 안 된다)."""
    monkeypatch.setenv("FOMS_NAVER_BULK_DISPATCH_ENABLED", "0")
    _sendable_house("2026-09-02")
    assert _run()["outcome"] == "disabled"
    assert queue_calls == []


def test_force_cannot_override_the_switch(app, queue_calls, monkeypatch):
    """force 는 영업일·하루1회만 넘는다 — 기능 스위치는 못 넘는다."""
    monkeypatch.setenv("FOMS_NAVER_AUTO_DISPATCH_ENABLED", "0")
    _sendable_house("2026-09-02")
    assert _run(force=True)["outcome"] == "disabled"
    assert queue_calls == []


def test_weekend_is_skipped_without_counting(app, queue_calls):
    """주말에는 대상을 세지도 않는다."""
    _sendable_house("2026-09-05")
    result = _run(SATURDAY)
    assert result["outcome"] == "holiday"
    assert result["total"] == 0
    assert queue_calls == []


def test_korean_holiday_is_skipped(app, queue_calls):
    """공휴일에도 안 보낸다(달력은 business_calendar 를 그대로 쓴다)."""
    from foms.services.common.business_calendar import get_holidays_kr

    holidays = sorted(get_holidays_kr(2026))
    assert holidays, "2026 공휴일 목록이 비어 있으면 이 계약을 잴 수 없다"
    holiday = holidays[0]
    _sendable_house(holiday)
    stamp = datetime.fromisoformat(holiday + "T16:50:00+09:00")
    assert _run(stamp)["outcome"] == "holiday"
    assert queue_calls == []


def test_second_run_on_the_same_day_does_nothing(app, queue_calls):
    """같은 날 두 번 불러도 한 번만 나간다(워커 재시작·replica 방어)."""
    _sendable_house("2026-09-02")
    first = _run()
    second = _run()
    assert first["outcome"] == "sent" and first["queued"] == 1
    assert second["outcome"] == "already_ran"
    assert len(queue_calls) == 1


def test_no_target_day_is_quiet(app, queue_calls):
    """보낼 집이 0이면 조용히 지나간다 — 알림도 감사도 만들지 않는다."""
    notifications = db_session.query(Notification).count()
    logs = db_session.query(SecurityLog).count()
    result = _run()
    assert result["outcome"] == "no_target"
    assert queue_calls == []
    assert db_session.query(Notification).count() == notifications
    assert db_session.query(SecurityLog).count() == logs


def test_blocked_house_is_not_sent_but_counted(app, queue_calls):
    """발주확인 전인 집은 안 보내고, 그 수를 결과가 말한다."""
    _sendable_house("2026-09-02", place_ok=False)
    result = _run()
    assert queue_calls == []
    assert result["outcome"] == "no_target"
    assert result["blocked"] == 1


# --------------------------------------------------------------------------- #
# 나가는 경로
# --------------------------------------------------------------------------- #

def test_sends_todays_houses_with_audit_and_notification(app, queue_calls):
    """보낼 집이 있으면 큐에 넣고, 감사 원장과 관리자 알림을 남긴다."""
    _sendable_house("2026-09-02")
    _sendable_house("2026-09-02")
    result = _run()
    assert result["outcome"] == "sent"
    assert result["queued"] == 2
    assert [call[1] for call in queue_calls] == ["dispatch", "dispatch"]

    logs = [row for row in db_session.query(SecurityLog).all()
            if row.action == auto.AUDIT_ACTION]
    assert len(logs) == 1
    # 사람이 아니라 스케줄이 한 일이다 — 행위자를 지어내지 않는다.
    assert logs[0].user_id is None
    assert logs[0].detail["date"] == "2026-09-02"

    rows = [row for row in db_session.query(Notification).all()
            if row.notification_type == auto.NOTIFICATION_TYPE]
    assert len(rows) == 1, "관리자 수만큼 복제하지 않는다(ROLE 알림 1건)"
    assert rows[0].target_type == "ROLE" and rows[0].target_role == "ADMIN"
    assert "2집" in rows[0].title


def test_state_records_the_run(app, queue_calls):
    """실행 기록이 남아야 하루 1회 계약이 성립한다."""
    _sendable_house("2026-09-02")
    _run()
    state = auto.read_state(db_session)
    assert state["last_run_date"] == "2026-09-02"
    assert state["last_outcome"] == "sent"
    assert state["last_summary"]["queued"] == 1


def test_queue_failure_keeps_the_day_open(app, monkeypatch):
    """큐가 죽으면 오늘을 닫지 않는다 — 살아난 뒤 다시 시도해야 한다."""
    monkeypatch.setattr("foms.services.jobs.queue.enqueue_naver_fulfillment",
                        lambda *a, **kw: False)
    _sendable_house("2026-09-02")
    result = _run()
    assert result["outcome"] == "queue_failed"
    assert "last_run_date" not in auto.read_state(db_session)


def test_force_runs_outside_business_day(app, queue_calls):
    """운영자가 직접 부르면(force) 주말에도 돈다 — 사람이 지금 그러기로 한 것이다."""
    _sendable_house("2026-09-05")
    result = _run(SATURDAY, force=True)
    assert result["outcome"] == "sent"
    assert len(queue_calls) == 1
