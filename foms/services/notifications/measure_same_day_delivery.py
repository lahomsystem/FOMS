"""SIDEFX ``MEAS_SAME_DAY_ALERT`` handler — 당일 실측 긴급 추가를 채널톡 긴급방에 올린다.

예약은 :func:`foms.services.notifications.measure_same_day.reserve_measure_same_day_alert`
가 주문 저장과 같은 트랜잭션(savepoint)에서 한다. 화면 알림·웹 푸시는 웹 쪽(커밋 뒤 emit·RQ)이 보내므로
이 handler 는 **채널톡만** 보낸다(SIDEFX 에는 Flask 앱이 없어 emit 을 할 수 없다).

계약(:mod:`foms.services.alimtalk_delivery_handler` 와 같다):

* **세션 소유권**: 스스로 commit 하지 않는다. 이력 기록과 outbox ``DONE`` 은 worker 가 같은
  tx 로 commit 한다. 실패해도 worker 는 롤백하지 않고 commit 하므로 세션에 쓴 기록은 남는다.
* **당일 전용**: 예약 날짜가 오늘(KST)이 아니거나 지금 실측일에 오늘이 없으면 보내지 않고
  끝낸다(DONE). 몇 시간 뒤 재시도해 어제 일을 알리는 것은 해롭다.
* **재시도**: 벤더 실패(``success`` False 또는 예외)만 예외로 올린다. 그룹 끔·미설정은 DONE.
* **멱등**: 이력 ``structured_data.channeltalk_push_urgent_measure`` 에 같은 멱등키로
  ``message_id`` 가 있으면 다시 보내지 않는다.
"""

from __future__ import annotations

import copy
import logging
from typing import Any, Optional

from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from foms.services import channel_client
from foms.services.channel_policy import build_message_blocks, get_routing_group_id
from foms.services.datetime_kst import get_today_kst, now_utc_naive
from foms.services.notifications.measure_same_day import (
    EFFECT_TYPE,
    build_dedupe_key,
    build_measure_same_day_payload,
)
from foms.services.order_date_sync import collect_order_schedule_date_specs
from models import DomainSideEffectOutbox, Order

_LOGGER = logging.getLogger("sidefx_measure_same_day")

__all__ = [
    "BOT_NAME",
    "HISTORY_KEY",
    "MeasureSameDayDeliveryError",
    "handle_measure_same_day_alert",
]

#: 채널톡 봇 표시 이름.
BOT_NAME = "FOMS긴급"
#: 서버 소유 이력 키(폼 저장·주문 복사에서 보존/제외 등재됨).
HISTORY_KEY = "channeltalk_push_urgent_measure"
#: 이력 목록 최대 길이(오래된 것부터 버린다).
_HISTORY_LIMIT = 20

_EMPTY_GROUP_WARNED = False


class MeasureSameDayDeliveryError(RuntimeError):
    """채널톡 발송을 이번에 끝내지 못했다(worker 가 재시도/DEAD 처리)."""


def _payload(row: DomainSideEffectOutbox) -> dict:
    return row.payload if isinstance(row.payload, dict) else {}


def _int_or_none(raw: Any) -> Optional[int]:
    if raw is None or isinstance(raw, bool):
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def _history(order: Order) -> list:
    sd = order.structured_data if isinstance(order.structured_data, dict) else {}
    items = sd.get(HISTORY_KEY)
    return items if isinstance(items, list) else []


def _already_sent(order: Order, dedupe_key: str) -> bool:
    return any(
        isinstance(item, dict) and item.get("dedupe_key") == dedupe_key and item.get("message_id")
        for item in _history(order)
    )


def _append_history(
    session: Session,
    order: Order,
    *,
    dedupe_key: str,
    date: str,
    message_id: Any,
    error: Optional[str],
) -> None:
    """이력 항목 1개를 붙인다(재조회·잠금 → deepcopy → 수정 → 재대입 → flag_modified, 최대 20개).

    벤더 왕복 동안 사용자가 주문을 저장했을 수 있다. structured_data 를 통째로 되쓰는 구조라
    쓰기 직전에 행을 다시 읽고 잠가서 그 사이 저장본을 덮지 않는다(``kakao_alimtalk`` 선례).
    """
    session.refresh(order, with_for_update=True)
    next_sd = copy.deepcopy(order.structured_data) if isinstance(order.structured_data, dict) else {}
    items = next_sd.get(HISTORY_KEY)
    items = list(items) if isinstance(items, list) else []
    items.append(
        {
            "dedupe_key": dedupe_key,
            "date": date,
            "message_id": message_id,
            "sent_at": now_utc_naive().isoformat(),
            "error": error,
        }
    )
    next_sd[HISTORY_KEY] = items[-_HISTORY_LIMIT:]
    order.structured_data = next_sd
    flag_modified(order, "structured_data")


def _order_has_measurement_on(order: Order, date: str) -> bool:
    return any(
        spec.get("kind") == "measurement" and str(spec.get("date") or "") == date
        for spec in collect_order_schedule_date_specs(order)
    )


def _build_text(order: Order) -> str:
    """``[긴급 실측] 오늘 {시간} · {고객명} · {지역} · 담당 {담당}`` (서버 조립)."""
    view = build_measure_same_day_payload(order, notification_id=0, added_by="", added_at=None)
    return (
        f"[긴급 실측] 오늘 {view['time']} · {view['customer_name'] or '-'} · "
        f"{view['area'] or '-'} · 담당 {view['manager'] or '-'}"
    )


def _warn_empty_group_once() -> None:
    global _EMPTY_GROUP_WARNED
    if _EMPTY_GROUP_WARNED:
        return
    _EMPTY_GROUP_WARNED = True
    _LOGGER.warning(
        "[meas-same-day] CHANNEL_GROUP_URGENT_MEASURE 가 빈 문자열 — 채널톡 긴급방 발송을 끕니다"
    )


def handle_measure_same_day_alert(row: DomainSideEffectOutbox) -> None:
    """``MEAS_SAME_DAY_ALERT`` 행 1개를 처리한다(commit 은 worker 소유).

    Args:
        row: PROCESSING 으로 claim 된 outbox 행(worker 세션 attach).

    Raises:
        MeasureSameDayDeliveryError: 세션 미attach, 또는 벤더 발송 실패(재시도 대상).
    """
    session = Session.object_session(row)
    if session is None:
        raise MeasureSameDayDeliveryError(f"outbox row {row.id} is not attached to a session")

    payload = _payload(row)
    order_id = _int_or_none(payload.get("order_id"))
    date = str(payload.get("date") or "").strip()
    if order_id is None or not date:
        _LOGGER.info("[meas-same-day] payload 불완전(id=%s) — skip", row.id)
        return
    order = session.get(Order, order_id)
    if order is None:
        _LOGGER.info("[meas-same-day] order %s 없음(id=%s) — skip", order_id, row.id)
        return

    dedupe_key = row.dedupe_key or build_dedupe_key(order_id, date)
    if date != get_today_kst().isoformat():
        _append_history(
            session, order, dedupe_key=dedupe_key, date=date, message_id=None, error="stale"
        )
        _LOGGER.info("[meas-same-day] 날짜 지남 order=%s date=%s — skip", order_id, date)
        return
    if not _order_has_measurement_on(order, date):
        _append_history(
            session, order, dedupe_key=dedupe_key, date=date, message_id=None, error="no_longer_today"
        )
        _LOGGER.info("[meas-same-day] 실측일에서 오늘이 빠짐 order=%s — skip", order_id)
        return
    if _already_sent(order, dedupe_key):
        _LOGGER.info("[meas-same-day] 이미 보냄 %s — skip", dedupe_key)
        return

    group_id = get_routing_group_id("manual", {"push_kind": "urgent_measure"})
    if not str(group_id or "").strip():
        _warn_empty_group_once()
        return
    if not channel_client.is_configured():
        _LOGGER.error(
            "[meas-same-day] 채널톡 미설정(CHANNEL_APP_SECRET/CHANNEL_ID) — 발송 불가 order=%s",
            order_id,
        )
        _append_history(
            session, order, dedupe_key=dedupe_key, date=date, message_id=None, error="not_configured"
        )
        return

    text = _build_text(order)
    blocks = build_message_blocks("manual", {"order_id": order_id, "text": text})
    result = channel_client.send_group_message(
        str(group_id), text, blocks=blocks, bot_name=BOT_NAME
    )
    if not isinstance(result, dict) or not result.get("success"):
        raise MeasureSameDayDeliveryError(
            f"channeltalk send failed (order={order_id}, effect={EFFECT_TYPE})"
        )
    _append_history(
        session,
        order,
        dedupe_key=dedupe_key,
        date=date,
        message_id=result.get("message_id") or "sent",
        error=None,
    )
