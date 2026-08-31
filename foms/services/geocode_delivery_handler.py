"""공용 ``GEOCODE`` side-effect handler (SIDEFX delivery — DATA-MEASUREMENT-01 소비단).

:mod:`foms.services.order_geocode_outbox` 가 주소 변경 tx 안에서 예약한 ``GEOCODE`` outbox
행을 소비한다. 이 handler 가 없으면 그 행들은 :class:`~foms.services.sidefx_worker.NoHandlerError`
로 10회 재시도 뒤 DEAD 로 쌓인다(운영에 PENDING 이 고여 있던 원인).

계약(:mod:`foms.services.storage_delete_handler` 와 동일):

* **세션 소유권**: handler 는 자기 commit 을 하지 않는다. worker 세션에 attach 된 Order 를
  수정만 하고, outbox ``DONE`` 전이와 **같은 tx** 로
  :func:`foms.services.sidefx_worker.run_delivery_once` 가 commit 한다(원자성).
* **재시도 의미론**: 예외를 올리면 worker 가 attempts++/backoff/DEAD 로 처리한다. 반대로
  "더 할 일이 없는" 상황(주문 삭제됨·payload 에 order_id 없음·주소 빈 값·이미 좌표 있음)은
  **정상 반환**해 DONE 으로 끝낸다 — 재시도해도 결과가 바뀌지 않는 일을 DEAD 로 쌓지 않는다.
* **변환 실패**: 카카오 변환기가 좌표를 못 찾는 경우는 예외가 아니라 데이터 문제다. RQ 경로와
  똑같이 ``geocode_status='failed'`` 를 기록하고 성공 반환한다(같은 주소로 10회 재호출하면
  카카오 쿼터만 태운다). 네트워크/DB 장애 같은 진짜 실패는 예외로 올라가 재시도된다.
* **멱등**: 같은 행이 재전달돼도 ``address_hash`` + 좌표 일치면 외부 호출 없이 즉시 반환한다
  (판정은 :func:`foms.services.geocode_helpers.apply_geocode_to_order` SSOT).

Order row 를 ``FOR UPDATE`` 로 잠그지 않는다 — 외부 HTTP 호출 구간 내내 주문 row lock 을
쥐면 실 사용자 write 를 막는다. 지오코드 결과는 주소로부터 결정되므로 동시 delivery 가
겹쳐도 같은 값을 쓴다(last-write-wins 안전).
"""
from __future__ import annotations

import logging
from typing import Optional

from sqlalchemy.orm import Session

from foms.services.geocode_helpers import (
    GEOCODE_OUTCOME_FAILED,
    GEOCODE_OUTCOME_NO_ADDRESS,
    apply_geocode_to_order,
)
from models import DomainSideEffectOutbox, Order

_LOGGER = logging.getLogger("sidefx_geocode")

#: outbox effect_type(producer 정본은 foms.services.order_geocode_outbox.GEOCODE_EFFECT_TYPE).
GEOCODE_EFFECT_TYPE = "GEOCODE"


class GeocodeDeliveryError(RuntimeError):
    """GEOCODE 배달을 진행할 수 없다(세션 미attach 등 방어 — worker 가 재시도/DEAD 처리)."""


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


def handle_geocode(row: DomainSideEffectOutbox) -> None:
    """``GEOCODE`` outbox 행 1개를 처리한다(주문 좌표 갱신, commit 은 worker 소유).

    Args:
        row: PROCESSING 으로 claim 된 ``effect_type=GEOCODE`` outbox 행(worker 세션 attach).
            성공하면 정상 반환, 재시도가 필요한 실패는 예외를 올린다.

    Raises:
        GeocodeDeliveryError: 행이 세션에 attach 되지 않음(방어적 fail-closed).
        Exception: 주소 변환기/DB 의 예기치 못한 실패는 그대로 전파(worker 가 재시도).
    """
    session = Session.object_session(row)
    if session is None:  # dispatch 는 항상 attach 된 row 를 준다 — 방어적 fail-closed.
        raise GeocodeDeliveryError(f"outbox row {row.id} is not attached to a session")

    order_id = _order_id(row)
    if order_id is None:
        _LOGGER.info(
            "[geocode] no order_id in payload (domain=%s id=%s) — safe skip",
            row.source_domain, row.id)
        return

    order = session.get(Order, order_id)
    if order is None:  # 주문이 삭제됨 — 재시도해도 돌아오지 않는다(DEAD 로 쌓지 않음).
        _LOGGER.info("[geocode] order %s already gone (id=%s) — skip", order_id, row.id)
        return

    outcome = apply_geocode_to_order(order)
    if outcome == GEOCODE_OUTCOME_NO_ADDRESS:
        _LOGGER.info(
            "[geocode] order %s has no address (id=%s) — marked failed, no retry",
            order_id, row.id)
    elif outcome == GEOCODE_OUTCOME_FAILED:
        _LOGGER.warning(
            "[geocode] order %s address conversion failed (id=%s) — marked failed, no retry",
            order_id, row.id)
