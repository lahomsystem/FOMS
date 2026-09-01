"""SIDEFX ``ALIMTALK_SEND`` handler — 실측 예약 알림톡 자동 발송 소비단.

저장 경로(:func:`foms.services.kakao_alimtalk.maybe_send_measure_alimtalk`)가 예약한
outbox 행을 소비한다. 수동 발송은 확인 모달이 결과를 기다리므로 이 handler 를 타지 않는다.

계약(:mod:`foms.services.geocode_delivery_handler` 와 동일):

* **세션 소유권**: handler 는 자기 commit 을 하지 않는다. 이력 기록과 outbox ``DONE`` 은
  worker 가 같은 tx 로 commit 한다.
* **재시도**: 네트워크·잔액·미설정 등 :func:`is_alimtalk_retryable_error` 는 예외로 올려
  PENDING backoff. 템플릿 불일치처럼 재시도해도 같은 결과는 정상 반환(DONE).
* **멱등**: 같은 멱등키로 이미 성공 이력이 있으면 Solapi 를 다시 부르지 않는다.
"""
from __future__ import annotations

import logging
from typing import Optional

from sqlalchemy.orm import Session

from foms.services.kakao_alimtalk import (
    is_alimtalk_retryable_error,
    send_alimtalk_in_session,
)
from models import DomainSideEffectOutbox, Order

_LOGGER = logging.getLogger("sidefx_alimtalk")

ALIMTALK_EFFECT_TYPE = "ALIMTALK_SEND"


class AlimtalkDeliveryError(RuntimeError):
    """알림톡 배달을 이번에 끝내지 못한다(워커가 재시도/DEAD 처리)."""


def _order_id(row: DomainSideEffectOutbox) -> Optional[int]:
    """outbox payload 에서 ``order_id`` 를 꺼낸다(없거나 정수가 아니면 None)."""
    payload = row.payload if isinstance(row.payload, dict) else {}
    raw = payload.get("order_id")
    if isinstance(raw, bool) or raw is None:
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def handle_alimtalk_send(row: DomainSideEffectOutbox) -> None:
    """``ALIMTALK_SEND`` 행 1개를 처리한다(이력 기록, commit 은 worker 소유).

    Args:
        row: PROCESSING 으로 claim 된 outbox 행(worker 세션 attach).

    Raises:
        AlimtalkDeliveryError: 세션 미attach, 또는 재시도할 발송 오류.
    """
    session = Session.object_session(row)
    if session is None:
        raise AlimtalkDeliveryError(f"outbox row {row.id} is not attached to a session")

    order_id = _order_id(row)
    if order_id is None:
        _LOGGER.info("[alimtalk] no order_id in payload (id=%s) — skip", row.id)
        return

    order = session.get(Order, order_id)
    if order is None:
        _LOGGER.info("[alimtalk] order %s already gone (id=%s) — skip", order_id, row.id)
        return

    result = send_alimtalk_in_session(
        session, order, dedupe_key=row.dedupe_key, event_id=row.order_event_id,
    )
    if result.get("sent"):
        return
    error = result.get("error")
    if is_alimtalk_retryable_error(error):
        raise AlimtalkDeliveryError(f"retryable alimtalk error {error!r} (order={order_id})")
    _LOGGER.warning(
        "[alimtalk] permanent skip order=%s error=%s id=%s", order_id, error, row.id)
