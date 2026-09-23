"""당일 실측 긴급 알림 — SIDEFX ``MEAS_SAME_DAY_ALERT`` 채널톡 handler 계약.

* 성공이면 긴급방(기본 209989)에 봇 ``FOMS긴급`` 으로 1회 보내고 이력을 남긴다.
* 같은 멱등키로 다시 돌면 보내지 않는다(worker 재배달·수동 재처리).
* 그룹 끔(빈 문자열)·채널톡 미설정·날짜 지남·실측일에서 오늘이 빠짐은 보내지 않고 정상 반환
  (worker 가 DONE 으로 닫는다 — 당일 알림을 몇 시간 뒤 재시도하는 것은 해롭다).
* 벤더 실패만 예외로 올려 재시도시킨다.

채널톡은 실제로 부르지 않는다(``send_group_message`` 가짜).
"""

from __future__ import annotations

import datetime as _dt
import uuid
from typing import Any

import pytest

from db import db_session, engine
from foms.services import channel_client
from foms.services.notifications import measure_same_day as msd
from foms.services.notifications import measure_same_day_delivery as delivery
from foms.services.sidefx_outbox import enqueue_side_effect
from foms.services.sidefx_worker import run_delivery_once
from models import DomainSideEffectOutbox, Order, OrderEvent

TODAY = "2026-09-23"


@pytest.fixture
def fixed_today(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(delivery, "get_today_kst", lambda: _dt.date.fromisoformat(TODAY))
    # 이 스위트는 handler 만 본다 — 주문 생성이 진짜 예약을 만들지 않게 막는다.
    monkeypatch.setattr(msd, "reserve_measure_same_day_alert", lambda *_a, **_k: None)


@pytest.fixture
def channel(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """채널톡 설정됨 + 가짜 발송기(호출 인자 기록)."""
    state: dict[str, Any] = {"calls": [], "result": {"success": True, "message_id": "m-1"}}

    def _send(group_id, plain_text, blocks=None, files=None, bot_name="FOMS", raise_on_error=False):
        state["calls"].append(
            {"group_id": group_id, "text": plain_text, "blocks": blocks, "bot_name": bot_name}
        )
        result = state["result"]
        if isinstance(result, Exception):
            raise result
        return result

    monkeypatch.setattr(channel_client, "send_group_message", _send)
    monkeypatch.setattr(channel_client, "is_configured", lambda: True)
    monkeypatch.delenv("CHANNEL_GROUP_URGENT_MEASURE", raising=False)
    return state


def _order(measure_date: str = TODAY) -> Order:
    order = Order(
        received_date="2026-09-01",
        customer_name="채널 고객",
        phone="010-1111-2222",
        address="서울 송파구 올림픽로 300",
        product="붙박이장",
        status="RECEIVED",
        manager_name="박담당",
        is_erp_order=True,
        erp_stage_code="RECEIVED",
        structured_data={
            "workflow": {"stage": "RECEIVED"},
            "parties": {"customer": {"name": "채널 고객"}, "manager": {"name": "박담당"}},
            "site": {"address_full": "서울 송파구 올림픽로 300"},
            "items": [{"product_name": "붙박이장"}],
            "schedule": {"measurement": {"date": measure_date, "time": "15시 30분"}},
        },
    )
    db_session.add(order)
    db_session.commit()
    return order


def _row(order: Order, date: str = TODAY) -> DomainSideEffectOutbox:
    event = OrderEvent(order_id=order.id, event_type=msd.EVENT_TYPE, payload={"date": date})
    db_session.add(event)
    db_session.flush()
    key = msd.build_dedupe_key(order.id, date)
    row = enqueue_side_effect(
        db_session,
        source_domain="ORDER_EVENT",
        source_id=event.id,
        effect_type=msd.EFFECT_TYPE,
        payload={"order_id": order.id, "date": date, "notification_id": None},
        dedupe_key=key,
        provider_idempotency_key=key,
    )
    db_session.commit()
    return row


def _history(order_id: int) -> list:
    db_session.expire_all()
    return (db_session.get(Order, order_id).structured_data or {}).get(delivery.HISTORY_KEY) or []


def _run(row: DomainSideEffectOutbox) -> None:
    delivery.handle_measure_same_day_alert(row)
    db_session.commit()


def test_success_sends_once_and_records_history(app, fixed_today, channel):
    order = _order()
    row = _row(order)
    _run(row)

    assert len(channel["calls"]) == 1
    call = channel["calls"][0]
    assert call["group_id"] == "209989"
    assert call["bot_name"] == "FOMS긴급"
    assert call["text"] == "[긴급 실측] 오늘 15시 30분 · 채널 고객 · 서울 송파구 · 담당 박담당"
    assert any("주문 보기" in b.get("value", "") for b in call["blocks"])
    history = _history(order.id)
    assert len(history) == 1
    assert history[0]["dedupe_key"] == f"meas_same_day:{order.id}:{TODAY}"
    assert history[0]["message_id"] == "m-1"
    assert history[0]["error"] is None


def test_same_dedupe_key_rerun_does_not_send_again(app, fixed_today, channel):
    order = _order()
    row = _row(order)
    _run(row)
    _run(db_session.get(DomainSideEffectOutbox, row.id))
    assert len(channel["calls"]) == 1


def test_env_group_override(app, fixed_today, channel, monkeypatch):
    monkeypatch.setenv("CHANNEL_GROUP_URGENT_MEASURE", "777")
    order = _order()
    _run(_row(order))
    assert channel["calls"][0]["group_id"] == "777"


def test_empty_group_skips_without_error(app, fixed_today, channel, monkeypatch):
    monkeypatch.setenv("CHANNEL_GROUP_URGENT_MEASURE", "")
    order = _order()
    _run(_row(order))
    assert channel["calls"] == []


def test_not_configured_skips_and_records(app, fixed_today, channel, monkeypatch):
    monkeypatch.setattr(channel_client, "is_configured", lambda: False)
    order = _order()
    _run(_row(order))
    assert channel["calls"] == []
    assert [h["error"] for h in _history(order.id)] == ["not_configured"]


def test_vendor_failure_raises_for_retry(app, fixed_today, channel):
    channel["result"] = {"success": False, "message_id": None}
    order = _order()
    row = _row(order)
    with pytest.raises(delivery.MeasureSameDayDeliveryError):
        delivery.handle_measure_same_day_alert(row)


def test_stale_date_does_not_send(app, fixed_today, channel):
    order = _order("2026-09-22")
    _run(_row(order, date="2026-09-22"))
    assert channel["calls"] == []
    assert [h["error"] for h in _history(order.id)] == ["stale"]


def test_no_longer_today_does_not_send(app, fixed_today, channel):
    order = _order("2026-09-25")  # 예약 뒤 실측일이 다른 날로 옮겨졌다
    _run(_row(order, date=TODAY))
    assert channel["calls"] == []
    assert [h["error"] for h in _history(order.id)] == ["no_longer_today"]


def test_history_is_capped_at_twenty(app, fixed_today, channel):
    order = _order()
    sd = dict(order.structured_data)
    sd[delivery.HISTORY_KEY] = [{"dedupe_key": f"old:{i}", "message_id": f"x{i}"} for i in range(25)]
    order.structured_data = sd
    db_session.commit()
    _run(_row(order))
    history = _history(order.id)
    assert len(history) == 20
    assert history[-1]["message_id"] == "m-1"


# --------------------------------------------------------------------------- #
# 실제 worker 경로(claim → dispatch → finalize → commit)
# --------------------------------------------------------------------------- #
def _deliver() -> dict:
    return run_delivery_once(
        engine,
        owner_hash="m" * 64,
        lease_token_fn=lambda: str(uuid.uuid4()),
        dispatch_fn=delivery.handle_measure_same_day_alert,
    )


def test_worker_marks_done_on_success(app, fixed_today, channel):
    order = _order()
    order_id = order.id
    row_id = _row(order).id
    db_session.remove()
    result = _deliver()
    assert result["done"] == 1 and result["retried"] == 0
    db_session.expire_all()
    assert db_session.get(DomainSideEffectOutbox, row_id).status == "DONE"
    assert _history(order_id)[0]["message_id"] == "m-1"


def test_worker_retries_on_vendor_failure(app, fixed_today, channel):
    channel["result"] = RuntimeError("vendor down")
    order = _order()
    row_id = _row(order).id
    db_session.remove()
    result = _deliver()
    assert result["retried"] == 1 and result["done"] == 0
    db_session.expire_all()
    assert db_session.get(DomainSideEffectOutbox, row_id).status == "PENDING"


def test_worker_marks_done_when_group_disabled(app, fixed_today, channel, monkeypatch):
    monkeypatch.setenv("CHANNEL_GROUP_URGENT_MEASURE", "")
    order = _order()
    row_id = _row(order).id
    db_session.remove()
    assert _deliver()["done"] == 1
    db_session.expire_all()
    assert db_session.get(DomainSideEffectOutbox, row_id).status == "DONE"
    assert channel["calls"] == []


def test_worker_marks_dead_when_vendor_keeps_failing(app, fixed_today, channel):
    """채널톡 오류가 attempts 한도까지 이어지면 DEAD 로 닫는다(무한 재시도 없음)."""
    channel["result"] = RuntimeError("vendor down")
    order = _order()
    row_id = _row(order).id
    db_session.remove()
    result = run_delivery_once(
        engine,
        owner_hash="m" * 64,
        lease_token_fn=lambda: str(uuid.uuid4()),
        dispatch_fn=delivery.handle_measure_same_day_alert,
        max_attempts=1,
    )
    assert result["dead"] == 1 and result["done"] == 0
    db_session.expire_all()
    assert db_session.get(DomainSideEffectOutbox, row_id).status == "DEAD"


def test_history_write_keeps_concurrent_order_save(app, fixed_today, channel, monkeypatch):
    """벤더 왕복 중 다른 세션이 저장한 structured_data 필드를 이력 기록이 덮지 않는다."""
    from sqlalchemy.orm import Session as _Session

    order = _order()
    order_id = order.id
    row = _row(order)
    sent = {"result": {"success": True, "message_id": "m-2"}}

    def _send_and_save_elsewhere(group_id, plain_text, blocks=None, files=None,
                                 bot_name="FOMS", raise_on_error=False):
        other = _Session(bind=engine)
        try:
            other_order = other.get(Order, order_id)
            sd = dict(other_order.structured_data or {})
            sd["memo_concurrent"] = "다른 창에서 저장"
            other_order.structured_data = sd
            other.commit()
        finally:
            other.close()
        return sent["result"]

    monkeypatch.setattr(channel_client, "send_group_message", _send_and_save_elsewhere)
    _run(row)

    db_session.expire_all()
    sd = db_session.get(Order, order_id).structured_data or {}
    assert sd.get("memo_concurrent") == "다른 창에서 저장"
    assert sd[delivery.HISTORY_KEY][-1]["message_id"] == "m-2"
