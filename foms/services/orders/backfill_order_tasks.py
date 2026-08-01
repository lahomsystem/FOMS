"""SAFE order_tasks 에 UUID identity/version/LEGACY provenance seed + enforcement 게이트
(TASK-BACKFILL-00, §5.2).

:func:`~foms.services.orders.audit_order_tasks.audit_order_tasks` 가 ``SAFE`` 로 분류한
task 에만 안정 ``task_uuid`` (UUID)·``version`` (=1)·``provenance`` (``'LEGACY'``) 를
seed 한다. flat 컬럼(status/owner_team/due_date/meta …)은 **절대 재작성하지 않는다**
(expand 단계 — 전이·정규화는 하류 TASK-01 소관). ambiguous(orphan/status/date/team/
user/auto_key collision) task 는 손대지 않는다 — ``task_uuid`` 를 NULL 로 남겨
**quarantine** 한다(자동 매핑 0·**active task collision enforcement 금지**).

멱등/resume: 이미 ``task_uuid`` 가 채워진 task 는 다시 seed 하지 않는다(재실행 멱등).
``uq_order_task_uuid`` partial-unique 가 DB 레벨에서도 중복 UUID 를 막아, 부분 실패 후
재실행이 아직 NULL 인 SAFE task 만 이어서 seed 한다 — 무거운 lease/checkpoint 대신 이
**자원 idempotency** 가 resume 을 보장한다.

:func:`can_enforce` 는 전이/NOT NULL enforcement(하류 TASK-01)를 켤 수 있는지 판정한다:
ambiguous 0건이고 **모든** 활성(OPEN/IN_PROGRESS) task 가 ``task_uuid`` 를 가질 때만
True. 그 전에는 enforcement 를 걸지 않는다(expand 단계 유지).

ponytail: 형제 ``backfill_as_cycles`` / ``backfill_order_item_identities`` 와 동일 lite
패턴 — 암호화 run state machine 을 끌어오지 않는다. 매우 큰 SAFE 집합에서 메모리가 문제면
그때 id 청크로 나눈다.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Optional

from sqlalchemy.orm import Session

from foms.services.orders.audit_order_tasks import (
    TaskAudit,
    audit_order_tasks,
)

# backfill provenance 표식(creator 추정 금지 — 항상 LEGACY).
PROVENANCE_LEGACY = "LEGACY"


@dataclass(frozen=True)
class BackfillResult:
    """backfill 적용 결과 요약.

    Attributes:
        tasks_seeded: 새로 identity(UUID/version/provenance)를 채운 SAFE task 수.
        already_present: 이미 ``task_uuid`` 가 있어 건너뛴 SAFE task 수(재실행 멱등 증거).
        ambiguous_skipped: 손대지 않은 ambiguous task 수(자동 매핑 0·quarantine 증거).
    """

    tasks_seeded: int
    already_present: int
    ambiguous_skipped: int


def apply_safe_backfill(
    session: Session, audit: Optional[TaskAudit] = None
) -> BackfillResult:
    """SAFE task 에만 UUID/version/LEGACY provenance 를 seed 한다(ambiguous 무접근·멱등).

    이미 ``task_uuid`` 가 있는 task 는 건너뛴다(재실행 멱등). flat 컬럼은 읽기만 하고
    수정하지 않는다. 커밋 cadence 는 호출자 몫이다.

    Args:
        session: DB 세션.
        audit: 미리 계산한 audit(없으면 내부에서 :func:`audit_order_tasks` 호출).

    Returns:
        :class:`BackfillResult`.
    """
    from models import OrderTask

    if audit is None:
        audit = audit_order_tasks(session)

    safe_ids = [s.task_id for s in audit.safe]
    seeded = 0
    already = 0
    if safe_ids:
        for task in (
            session.query(OrderTask).filter(OrderTask.id.in_(safe_ids)).all()
        ):
            if task.task_uuid is not None:
                already += 1
                continue
            task.task_uuid = str(uuid.uuid4())
            task.version = 1
            task.provenance = PROVENANCE_LEGACY
            seeded += 1
        session.flush()

    return BackfillResult(
        tasks_seeded=seeded,
        already_present=already,
        ambiguous_skipped=len(audit.ambiguous),
    )


def can_enforce(session: Session) -> bool:
    """enforcement(하류 TASK-01) 활성화 게이트: ambiguous 0 AND 활성 task identity 100%.

    ambiguous task 가 하나라도 있거나, 활성(OPEN/IN_PROGRESS) task 중 ``task_uuid`` 가
    없는 task 가 하나라도 있으면 False.

    Args:
        session: DB 세션.

    Returns:
        enforcement 적용 가능하면 True.
    """
    from models import OrderTask

    audit = audit_order_tasks(session)
    if audit.ambiguous:
        return False
    active_ids = audit.active_ids
    if not active_ids:
        return True
    missing = (
        session.query(OrderTask.id)
        .filter(OrderTask.id.in_(active_ids), OrderTask.task_uuid.is_(None))
        .count()
    )
    return missing == 0


__all__ = [
    "PROVENANCE_LEGACY",
    "BackfillResult",
    "apply_safe_backfill",
    "can_enforce",
]
