"""SAFE 주문에 UUID AS cycle 발급 + enforcement 게이트 (AS-BACKFILL-00, §5.2).

:func:`~foms.services.orders.audit_as_cycles.audit_as_cycles` 가 ``SAFE`` 로 분류한 주문에만
UUID :class:`~models.OrderASCycle` 을 발급하고(열린 entry=current ``IN_PROGRESS``, 닫힌
entry=``COMPLETED`` 이력), flat ``as_info`` entry 의 transition/schedule/completion/
classification 을 cycle 컬럼으로 **복제**한다. flat ``structured_data`` 는 **절대 삭제/재작성
하지 않는다**(inferred stage rewrite 금지 — 전이 활성화는 하류 STATE-AS-01 소관). ambiguous
주문은 손대지 않는다(자동 매핑 0).

멱등/resume: 이미 발급된 cycle(같은 ``order_id`` + ``legacy_as_id``)은 다시 발급하지 않는다
(부분 실패 후 재실행이 아직 없는 cycle 만 이어서 발급). ``uq_order_as_cycle_legacy``
partial-unique 가 DB 레벨에서도 중복 발급을 막고, ``uq_order_as_cycle_current`` 가 한 주문
current cycle 을 1개로 강제한다 — runs.py 의 lease/checkpoint 대신 이 **자원 idempotency** 가
resume 을 보장한다.

:func:`can_enforce` 는 전이(STATE-AS-01)를 켤 수 있는지 판정한다: ambiguous 0건이고
**모든** in-flight AS 주문이 current cycle 을 가질 때만 True(§ "in-flight AS current 100%").
그 전에는 command flag 를 켜지 않는다.

ponytail: 형제 ``backfill_production_runs`` / ``backfill_order_item_identities`` 와 동일 lite
패턴 — 암호화 run state machine(``runs.py``)을 끌어오지 않는다. 대량/재개가 필요해지면 그때 감싼다.
"""
from __future__ import annotations

import datetime
import uuid
from dataclasses import dataclass
from typing import List, Optional

from sqlalchemy.orm import Session

from foms.services.orders.audit_as_cycles import (
    ASCycleAudit,
    audit_as_cycles,
)


@dataclass(frozen=True)
class BackfillResult:
    """backfill 적용 결과 요약.

    Attributes:
        cycles_minted: 새로 발급된 AS cycle 수.
        already_present: 이미 발급돼 건너뛴 cycle 수(재실행 멱등 증거).
        ambiguous_skipped: 손대지 않은 ambiguous 주문 수(자동 매핑 0 증거).
    """

    cycles_minted: int
    already_present: int
    ambiguous_skipped: int


def _parse_dt(iso: Optional[str]) -> Optional[datetime.datetime]:
    """legacy ISO 문자열을 naive datetime 으로(파싱 불가 시 None — provenance 유실 허용)."""
    if not iso:
        return None
    try:
        parsed = datetime.datetime.fromisoformat(iso)
    except (ValueError, TypeError):
        return None
    return parsed.replace(tzinfo=None) if parsed.tzinfo is not None else parsed


def _cycle_exists(session: Session, order_id: int, legacy_as_id: int) -> bool:
    """주문의 해당 legacy as_info entry cycle 이 이미 발급됐는가(멱등 판정)."""
    from models import OrderASCycle

    return (
        session.query(OrderASCycle.id)
        .filter(
            OrderASCycle.order_id == order_id,
            OrderASCycle.legacy_as_id == legacy_as_id,
        )
        .first()
        is not None
    )


def apply_safe_backfill(
    session: Session, audit: Optional[ASCycleAudit] = None
) -> BackfillResult:
    """SAFE 주문에만 AS cycle 을 발급한다(ambiguous 무접근·멱등·flat 보존).

    이미 발급된 (order_id, legacy_as_id) cycle 은 건너뛴다(재실행 멱등). flat structured_data
    는 읽기만 하고 수정하지 않는다 — transition/schedule/completion/classification 은 cycle
    컬럼에 **복제**된다. 커밋은 호출자 몫이다.

    Args:
        session: DB 세션.
        audit: 미리 계산한 audit(없으면 내부에서 :func:`audit_as_cycles` 호출).

    Returns:
        :class:`BackfillResult`.
    """
    from models import OrderASCycle

    if audit is None:
        audit = audit_as_cycles(session)

    minted = 0
    already = 0
    new_cycles: List[OrderASCycle] = []
    for plan in audit.safe:
        for cycle in plan.cycles:
            if _cycle_exists(session, plan.order_id, cycle.legacy_as_id):
                already += 1
                continue
            new_cycles.append(OrderASCycle(
                id=str(uuid.uuid4()),
                order_id=plan.order_id,
                status=cycle.status,
                legacy_as_id=cycle.legacy_as_id,
                started_at=_parse_dt(cycle.started_at),
                started_by=cycle.started_by,
                reason=cycle.reason,
                description=cycle.description,
                visit_date=cycle.visit_date,
                visit_time=cycle.visit_time,
                completed_at=_parse_dt(cycle.completed_at),
                completed_by=cycle.completed_by,
                completion_note=cycle.completion_note,
                is_current=cycle.is_current,
            ))
            minted += 1

    session.add_all(new_cycles)
    session.flush()
    return BackfillResult(
        cycles_minted=minted,
        already_present=already,
        ambiguous_skipped=len(audit.ambiguous),
    )


def can_enforce(session: Session) -> bool:
    """전이(STATE-AS-01) 활성화 게이트: ambiguous 0 AND in-flight AS current 100%.

    ambiguous 주문이 하나라도 있거나, flat AS 축이 열린(``RECEIVED``/``IN_PROGRESS``) 주문
    중 current cycle(``is_current``)이 없는 주문이 하나라도 있으면 False.

    Args:
        session: DB 세션.

    Returns:
        enforcement 적용 가능하면 True.
    """
    from models import OrderASCycle

    audit = audit_as_cycles(session)
    if audit.ambiguous:
        return False
    for order_id in audit.in_flight_ids:
        current = (
            session.query(OrderASCycle.id)
            .filter(
                OrderASCycle.order_id == order_id,
                OrderASCycle.is_current.is_(True),
            )
            .first()
        )
        if current is None:
            return False
    return True


__all__ = [
    "BackfillResult",
    "apply_safe_backfill",
    "can_enforce",
]
