"""SAFE 주문에 current IN_PROGRESS run 발급 + enforcement 게이트 (PRODUCTION-BACKFILL-00, §5.2).

:func:`~foms.services.orders.audit_production_runs.audit_production_runs` 가 ``SAFE`` 로
분류한 주문에만 UUID :class:`~models.ProductionRun` (status ``IN_PROGRESS``, ``is_current``)
을 발급하고, flat ``production.steps``/``defects`` 를 그 run 의 scope 스냅샷으로 **복제**한다.
flat ``structured_data`` 는 **절대 삭제/수정하지 않는다**(§경계 "flat history 삭제 금지" —
전이 활성화는 하류 STATE-PROD-01 소관). ambiguous 주문은 손대지 않는다(자동 매핑 0).

멱등/resume: 주문에 이미 current run 이 있으면 새로 발급하지 않는다(부분 실패 후 재실행이
아직 run 없는 주문만 이어서 처리). ``uq_production_run_current`` partial-unique 가 DB
레벨에서도 한 주문 current run 을 1개로 강제한다 — runs.py 의 lease/checkpoint 대신 이
**자원 idempotency** 가 resume 을 보장한다.

:func:`can_enforce` 는 전이(STATE-PROD-01)를 켤 수 있는지 판정한다: ambiguous 0건이고
**모든** in-flight PRODUCTION 주문이 current IN_PROGRESS run 을 가질 때만 True(§ "in-flight
PRODUCTION current IN_PROGRESS 100%"). 그 전에는 command flag 를 켜지 않는다.

ponytail: 형제 ``backfill_order_item_identities`` 와 동일 lite 패턴 — 암호화 run state
machine(``runs.py``)을 끌어오지 않는다. 대량/재개가 필요해지면 그때 감싼다.
"""
from __future__ import annotations

import datetime
import uuid
from dataclasses import dataclass
from typing import List, Optional

from sqlalchemy.orm import Session

from foms.services.orders.audit_production_runs import (
    ProductionRunAudit,
    audit_production_runs,
)


@dataclass(frozen=True)
class BackfillResult:
    """backfill 적용 결과 요약.

    Attributes:
        runs_minted: 새로 발급된 IN_PROGRESS run 수.
        already_present: 이미 current run 이 있어 건너뛴 SAFE 주문 수(재실행 멱등 증거).
        ambiguous_skipped: 손대지 않은 ambiguous 주문 수(자동 매핑 0 증거).
    """

    runs_minted: int
    already_present: int
    ambiguous_skipped: int


def _parse_started_at(iso: Optional[str]) -> Optional[datetime.datetime]:
    """legacy 시작 ISO 문자열을 naive datetime 으로(파싱 불가 시 None)."""
    if not iso:
        return None
    try:
        parsed = datetime.datetime.fromisoformat(iso)
    except (ValueError, TypeError):
        return None
    return parsed.replace(tzinfo=None) if parsed.tzinfo is not None else parsed


def _current_run_exists(session: Session, order_id: int) -> bool:
    """주문에 current run(is_current=True)이 이미 있는가(멱등 판정)."""
    from models import ProductionRun

    return (
        session.query(ProductionRun.id)
        .filter(ProductionRun.order_id == order_id, ProductionRun.is_current.is_(True))
        .first()
        is not None
    )


def apply_safe_backfill(
    session: Session, audit: Optional[ProductionRunAudit] = None
) -> BackfillResult:
    """SAFE 주문에만 current IN_PROGRESS run 을 발급한다(ambiguous 무접근·멱등·flat 보존).

    이미 current run 이 있는 주문은 건너뛴다(재실행 멱등). flat structured_data 는 읽기만
    하고 수정하지 않는다 — steps/defects 는 run 컬럼에 **복제**된다. 커밋은 호출자 몫이다.

    Args:
        session: DB 세션.
        audit: 미리 계산한 audit(없으면 내부에서 :func:`audit_production_runs` 호출).

    Returns:
        :class:`BackfillResult`.
    """
    from models import ProductionRun

    if audit is None:
        audit = audit_production_runs(session)

    minted = 0
    already = 0
    new_runs: List[ProductionRun] = []
    for plan in audit.safe:
        if _current_run_exists(session, plan.order_id):
            already += 1
            continue
        new_runs.append(ProductionRun(
            id=str(uuid.uuid4()),
            order_id=plan.order_id,
            status=plan.status,
            started_at=_parse_started_at(plan.started_at),
            steps=list(plan.steps),
            defects=list(plan.defects),
            is_current=True,
        ))
        minted += 1

    session.add_all(new_runs)
    session.flush()
    return BackfillResult(
        runs_minted=minted,
        already_present=already,
        ambiguous_skipped=len(audit.ambiguous),
    )


def can_enforce(session: Session) -> bool:
    """전이(STATE-PROD-01) 활성화 게이트: ambiguous 0 AND in-flight IN_PROGRESS 100%.

    ambiguous 주문이 하나라도 있거나, main==PRODUCTION 인 주문 중 current IN_PROGRESS
    run 이 없는 주문이 하나라도 있으면 False.

    Args:
        session: DB 세션.

    Returns:
        enforcement 적용 가능하면 True.
    """
    from models import ProductionRun

    audit = audit_production_runs(session)
    if audit.ambiguous:
        return False
    for order_id in audit.in_flight_ids:
        run = (
            session.query(ProductionRun.status)
            .filter(
                ProductionRun.order_id == order_id,
                ProductionRun.is_current.is_(True),
            )
            .scalar()
        )
        if run != "IN_PROGRESS":
            return False
    return True


__all__ = [
    "BackfillResult",
    "apply_safe_backfill",
    "can_enforce",
]
