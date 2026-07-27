"""주소 변경 시 지오코드를 SIDEFX outbox 이벤트로 예약하는 producer (DATA-MEASUREMENT-01).

주소가 바뀌면 좌표를 다시 계산해야 한다. 예전 write 경로는 커밋 뒤 RQ enqueue 를 시도하고
실패하면 **동기 지오코드로 폴백**했다(postcommit 직접 지오코드) — 요청 스레드가 외부 API 를
붙잡고, 실패는 커밋 밖에서 조용히 사라졌다. 이 모듈은 그 폴백을 없애고, 지오코드를 business
transaction **안에서** typed side-effect outbox 행 1개로 원자 예약한다. 실제 지오코드 수행은
SIDEFX worker 몫이다(여기서는 producer 만).

anchor 는 ``ADDRESS_CHANGED`` :class:`~models.OrderEvent` 다 — REV-00 이 요구하는 event
parity 를 만족하고, ``source_domain=ORDER_EVENT`` one-of FK 매트릭스로 outbox 행을 orphan
없이 고정한다(신규 테이블 불요).
"""
from __future__ import annotations

import datetime
from typing import Any, Optional

from sqlalchemy.orm import Session

from foms.services.sidefx_outbox import enqueue_side_effect
from models import DomainSideEffectOutbox, OrderEvent

__all__ = ["GEOCODE_EFFECT_TYPE", "ADDRESS_CHANGED_EVENT", "enqueue_order_address_geocode"]

#: outbox effect_type — SIDEFX worker 의 GEOCODE handler 가 소비한다.
GEOCODE_EFFECT_TYPE = "GEOCODE"
#: 주소 변경 event parity 의 OrderEvent.event_type.
ADDRESS_CHANGED_EVENT = "ADDRESS_CHANGED"


def enqueue_order_address_geocode(
    session: Session,
    order: Any,
    *,
    address: str,
    actor_user_id: Optional[int],
    now: Optional[datetime.datetime] = None,
) -> DomainSideEffectOutbox:
    """주소 변경을 ``ADDRESS_CHANGED`` event 로 남기고 GEOCODE side-effect 를 예약한다.

    호출자의 REV-00 mutation transaction(row lock) 안에서 호출한다 — event/outbox insert 는
    business write 와 같은 tx 라 커밋/롤백을 함께한다. ``postcommit 직접 지오코드/폴백은
    수행하지 않는다``.

    Args:
        session: business transaction 세션(호출자 소유, 커밋 미수행).
        order: 주소가 바뀐 Order(이미 ``order.address`` 등이 갱신된 상태).
        address: 정규화된 새 주소 문자열(payload 기록용, 빈 문자열 가능).
        actor_user_id: 변경 주체 user id(event audit, None 가능).
        now: 테스트용 시각 주입(기본 outbox 기본값).

    Returns:
        flush 된 :class:`~models.DomainSideEffectOutbox` (GEOCODE, PENDING).
    """
    event = OrderEvent(
        order_id=order.id,
        event_type=ADDRESS_CHANGED_EVENT,
        payload={"address": address},
        created_by_user_id=actor_user_id,
    )
    session.add(event)
    session.flush()  # event.id 확보(outbox ORDER_EVENT FK 참조)

    return enqueue_side_effect(
        session,
        source_domain="ORDER_EVENT",
        source_id=event.id,
        effect_type=GEOCODE_EFFECT_TYPE,
        payload={"order_id": order.id, "address": address},
        dedupe_key=f"{GEOCODE_EFFECT_TYPE}:{event.id}",
        now=now,
    )
