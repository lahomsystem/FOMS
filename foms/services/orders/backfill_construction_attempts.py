"""SAFE 주문에 current IN_PROGRESS construction attempt 발급 + 게이트 (CONSTRUCTION-BACKFILL-00, §5.2).

:func:`~foms.services.orders.audit_construction_attempts.audit_construction_attempts` 가
``SAFE`` 로 분류한 주문에만 UUID :class:`~models.OrderConstructionAttempt`(status
``IN_PROGRESS``, ``is_current``)를 발급하고, flat 시공 예정일/시작/evidence 를 그 attempt 의
스냅샷으로 **복제**한다. flat ``structured_data`` 는 **절대 삭제/수정하지 않는다**(전이 활성화는
하류 STATE-CONST-CS 소관). ambiguous 주문은 손대지 않는다(자동 매핑 0).

**dry-run / apply / verify 3단계 + 승인 게이트(BACKFILL-ARTIFACT)**:

* :func:`dry_run` 은 무엇이 발급될지 미리 계산만 한다(DB write 0).
* :func:`apply_safe_backfill` 은 **명시 승인 토큰**(:data:`APPROVAL_TOKEN`)이 있어야만
  발급한다 — 기본 인자는 승인 없음이고, 승인 없이 호출하면 :class:`ApprovalRequiredError`
  로 거부한다. **command flag ON 금지**(자동 실행·기본 켜짐 금지·명시 승인만).
* :func:`verify` 는 발급 완료 후 **모든 SAFE 주문이 current attempt 를 갖는지 100% 검증**한다.

멱등/resume: 주문에 이미 current attempt 가 있으면 새로 발급하지 않는다(부분 실패 후 재실행이
아직 attempt 없는 주문만 이어서 처리). ``uq_construction_attempt_current`` partial-unique 가
DB 레벨에서도 한 주문 current attempt 를 1개로 강제한다 — 이 **자원 idempotency** 가 resume 을
보장한다.

:func:`can_enforce` 는 전이(STATE-CONST-CS)를 켤 수 있는지 판정한다: ambiguous 0건이고
**모든** in-flight CONSTRUCTION 주문이 current IN_PROGRESS attempt 를 가질 때만 True. 그 전에는
command flag 를 켜지 않는다.

ponytail: 형제 ``backfill_production_runs`` / ``backfill_as_cycles`` 와 동일 lite 패턴 — 암호화
run state machine(``runs.py``)을 끌어오지 않는다. 승인 게이트는 명시 토큰 1개면 충분하다(대량
PII resume 이 필요해지면 그때 BACKFILL-ARTIFACT 파이프라인으로 감싼다).
"""
from __future__ import annotations

import datetime
import uuid
from dataclasses import dataclass
from typing import List, Optional

from sqlalchemy.orm import Session

from foms.services.orders.audit_construction_attempts import (
    ConstructionAttemptAudit,
    audit_construction_attempts,
)

#: apply 를 실행하려면 호출자가 명시로 넘겨야 하는 승인 토큰(BACKFILL-ARTIFACT 게이트).
#: 기본값 없음(=승인 안 함)이라 자동 실행·기본 켜짐(command flag ON)이 불가능하다.
APPROVAL_TOKEN = "CONSTRUCTION-BACKFILL-00-APPLY"


class ApprovalRequiredError(RuntimeError):
    """apply 가 명시 승인 토큰 없이 호출됐을 때(자동 실행 금지 게이트)."""


@dataclass(frozen=True)
class BackfillPreview:
    """dry-run 미리보기(DB write 0).

    Attributes:
        would_mint: 이번 apply 로 새로 발급될 attempt 수(이미 있는 것 제외).
        already_present: 이미 current attempt 가 있어 건너뛸 SAFE 주문 수.
        ambiguous_skipped: 손대지 않을 ambiguous 주문 수(수동 CSV 대상).
        order_ids: 새로 발급될 주문 id 목록(오름차순).
    """

    would_mint: int
    already_present: int
    ambiguous_skipped: int
    order_ids: tuple


@dataclass(frozen=True)
class BackfillResult:
    """apply 적용 결과 요약.

    Attributes:
        attempts_minted: 새로 발급된 IN_PROGRESS attempt 수.
        already_present: 이미 current attempt 가 있어 건너뛴 SAFE 주문 수(재실행 멱등 증거).
        ambiguous_skipped: 손대지 않은 ambiguous 주문 수(자동 매핑 0 증거).
    """

    attempts_minted: int
    already_present: int
    ambiguous_skipped: int


@dataclass(frozen=True)
class VerifyResult:
    """verify(100% 검증) 결과.

    Attributes:
        ok: 모든 SAFE 주문이 current attempt 를 갖는가(발급 완결 여부).
        safe_total: SAFE 주문 수.
        safe_covered: current attempt 를 가진 SAFE 주문 수.
        missing_order_ids: current attempt 가 없는 SAFE 주문 id 목록(오름차순).
    """

    ok: bool
    safe_total: int
    safe_covered: int
    missing_order_ids: tuple


def _parse_dt(iso: Optional[str]) -> Optional[datetime.datetime]:
    """legacy 시작 ISO 문자열을 naive datetime 으로(파싱 불가 시 None — provenance 유실 허용)."""
    if not iso:
        return None
    try:
        parsed = datetime.datetime.fromisoformat(iso)
    except (ValueError, TypeError):
        return None
    return parsed.replace(tzinfo=None) if parsed.tzinfo is not None else parsed


def _current_attempt_exists(session: Session, order_id: int) -> bool:
    """주문에 current attempt(is_current=True)가 이미 있는가(멱등 판정)."""
    from models import OrderConstructionAttempt

    return (
        session.query(OrderConstructionAttempt.id)
        .filter(
            OrderConstructionAttempt.order_id == order_id,
            OrderConstructionAttempt.is_current.is_(True),
        )
        .first()
        is not None
    )


def dry_run(
    session: Session, audit: Optional[ConstructionAttemptAudit] = None
) -> BackfillPreview:
    """무엇이 발급될지 미리 계산한다(DB write 0 — apply 전 변경 미리보기).

    Args:
        session: DB 세션(read-only 로만 사용).
        audit: 미리 계산한 audit(없으면 내부에서 :func:`audit_construction_attempts` 호출).

    Returns:
        :class:`BackfillPreview`.
    """
    if audit is None:
        audit = audit_construction_attempts(session)

    would: List[int] = []
    already = 0
    for plan in audit.safe:
        if _current_attempt_exists(session, plan.order_id):
            already += 1
        else:
            would.append(plan.order_id)
    return BackfillPreview(
        would_mint=len(would),
        already_present=already,
        ambiguous_skipped=len(audit.ambiguous),
        order_ids=tuple(sorted(would)),
    )


def apply_safe_backfill(
    session: Session, *, approval: Optional[str] = None,
    audit: Optional[ConstructionAttemptAudit] = None,
) -> BackfillResult:
    """SAFE 주문에만 current IN_PROGRESS attempt 를 발급한다(명시 승인 필수·멱등·flat 보존).

    ``approval`` 이 :data:`APPROVAL_TOKEN` 이 아니면 :class:`ApprovalRequiredError` 로
    거부한다(자동 실행·기본 켜짐 금지). 이미 current attempt 가 있는 주문은 건너뛴다(재실행
    멱등). flat structured_data 는 읽기만 하고 수정하지 않는다 — 예정일/시작/evidence 는
    attempt 컬럼에 **복제**된다. 커밋은 호출자 몫이다.

    Args:
        session: DB 세션.
        approval: 명시 승인 토큰(:data:`APPROVAL_TOKEN`). 없거나 틀리면 거부.
        audit: 미리 계산한 audit(없으면 내부에서 :func:`audit_construction_attempts` 호출).

    Returns:
        :class:`BackfillResult`.

    Raises:
        ApprovalRequiredError: ``approval`` 이 승인 토큰과 일치하지 않을 때(승인 게이트).
    """
    from models import OrderConstructionAttempt

    if approval != APPROVAL_TOKEN:
        raise ApprovalRequiredError(
            "construction attempt backfill requires explicit approval "
            f"(approval must equal APPROVAL_TOKEN); refusing auto-run."
        )

    if audit is None:
        audit = audit_construction_attempts(session)

    minted = 0
    already = 0
    new_attempts: List[OrderConstructionAttempt] = []
    for plan in audit.safe:
        if _current_attempt_exists(session, plan.order_id):
            already += 1
            continue
        new_attempts.append(OrderConstructionAttempt(
            id=str(uuid.uuid4()),
            order_id=plan.order_id,
            status=plan.status,
            legacy_seq=plan.legacy_seq,
            scheduled_date=plan.scheduled_date,
            started_at=_parse_dt(plan.started_at),
            started_by=plan.started_by,
            evidence=plan.evidence,
            is_current=True,
        ))
        minted += 1

    session.add_all(new_attempts)
    session.flush()
    return BackfillResult(
        attempts_minted=minted,
        already_present=already,
        ambiguous_skipped=len(audit.ambiguous),
    )


def verify(
    session: Session, audit: Optional[ConstructionAttemptAudit] = None
) -> VerifyResult:
    """apply 완료 검증: 모든 SAFE 주문이 current attempt 를 갖는지 100% 확인한다.

    Args:
        session: DB 세션.
        audit: 미리 계산한 audit(없으면 내부에서 :func:`audit_construction_attempts` 호출).

    Returns:
        :class:`VerifyResult` (``ok`` 은 SAFE 전량이 current attempt 를 가질 때만 True).
    """
    if audit is None:
        audit = audit_construction_attempts(session)

    missing: List[int] = []
    for plan in audit.safe:
        if not _current_attempt_exists(session, plan.order_id):
            missing.append(plan.order_id)
    safe_total = len(audit.safe)
    return VerifyResult(
        ok=not missing,
        safe_total=safe_total,
        safe_covered=safe_total - len(missing),
        missing_order_ids=tuple(sorted(missing)),
    )


def can_enforce(session: Session) -> bool:
    """전이(STATE-CONST-CS) 활성화 게이트: ambiguous 0 AND in-flight IN_PROGRESS 100%.

    ambiguous 주문이 하나라도 있거나, main==CONSTRUCTION 인 주문 중 current IN_PROGRESS
    attempt 가 없는 주문이 하나라도 있으면 False.

    Args:
        session: DB 세션.

    Returns:
        enforcement 적용 가능하면 True.
    """
    from models import OrderConstructionAttempt

    audit = audit_construction_attempts(session)
    if audit.ambiguous:
        return False
    for order_id in audit.in_flight_ids:
        status = (
            session.query(OrderConstructionAttempt.status)
            .filter(
                OrderConstructionAttempt.order_id == order_id,
                OrderConstructionAttempt.is_current.is_(True),
            )
            .scalar()
        )
        if status != "IN_PROGRESS":
            return False
    return True


__all__ = [
    "APPROVAL_TOKEN",
    "ApprovalRequiredError",
    "BackfillPreview",
    "BackfillResult",
    "VerifyResult",
    "dry_run",
    "apply_safe_backfill",
    "verify",
    "can_enforce",
]
