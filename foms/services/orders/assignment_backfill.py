"""legacy 이름 배정 audit/backfill (ASSIGNMENT-00, §2.1 line 172 / line 10 브리프).

기존 JSONB 이름 배정(``structured_data.assignments`` 표시 projection 등)을
``order_assignments`` user-ID row 로 옮기기 위한 **audit(분류)** + **명시 apply** 를
제공한다. 핵심 계약은 **자동 승격 0**:

* :func:`audit_legacy_names` 는 아무 것도 쓰지 않는다(read-only 분류만). active User 이름
  exact 1명 매치 → ``safe``, 0명/복수 → ``ambiguous``(0/복수/외주 모두 여기).
* exact 1명이어도 자동으로 배정 row 를 만들지 않는다. :func:`apply_safe_backfill` 로
  **명시 승인된 safe name** 만 ``source=BACKFILL`` 배정한다. ambiguous name 은 승인돼도
  거부한다(수동 CSV 검토 → reason 없이 AUTH enforcement 금지).
* :func:`to_manual_csv` 는 ambiguous 를 수동 매핑용 CSV 로 내보낸다.

ponytail: 이 audit 는 이름→ID 분류라 BACKFILL-ARTIFACT-00 의 암호화 run state machine
(lease/checkpoint/DPAPI)까지 끌어오지 않는다 — 그 무거운 파이프라인은 PII 대량 backfill 용
이고 여기 분류엔 과하다. 대량/재개 backfill 이 필요해지면 그때 runs.py 로 감싼다.
"""
from __future__ import annotations

import csv
import datetime
import io
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional

from sqlalchemy.orm import Session

from foms.services.datetime_kst import now_utc_naive
from foms.services.orders.assignment import AssignmentValidationError, _validate_domain
from models import OrderAssignment, User

# ambiguous 사유 코드.
NO_MATCH = "NO_MATCH"        # active User 이름 매치 0 (외주/오타/퇴사 포함)
MULTIPLE_MATCH = "MULTIPLE_MATCH"  # active User 이름 매치 복수(동명이인)


@dataclass(frozen=True)
class LegacyNameAudit:
    """legacy 이름 분류 결과(read-only).

    Attributes:
        safe: ``name -> user_id`` (active User exact 1명 매치). 자동 승격은 하지 않는다.
        ambiguous: ``name -> reason_code`` (NO_MATCH/MULTIPLE_MATCH). 수동 CSV 대상.
    """

    safe: Dict[str, int]
    ambiguous: Dict[str, str]


def audit_legacy_names(session: Session, names: Iterable[str]) -> LegacyNameAudit:
    """legacy 이름을 active User 로 분류한다(아무 것도 쓰지 않음).

    Args:
        session: DB 세션.
        names: 감사할 이름 목록(공백/None 은 무시). 중복은 한 번만 분류.

    Returns:
        LegacyNameAudit(safe, ambiguous).
    """
    safe: Dict[str, int] = {}
    ambiguous: Dict[str, str] = {}
    seen = set()
    for raw in names:
        name = (raw or "").strip()
        if not name or name in seen:
            continue
        seen.add(name)
        matches = (
            session.query(User)
            .filter(User.name == name, User.is_active.is_(True))
            .all()
        )
        if len(matches) == 1:
            safe[name] = matches[0].id
        elif not matches:
            ambiguous[name] = NO_MATCH
        else:
            ambiguous[name] = MULTIPLE_MATCH
    return LegacyNameAudit(safe=safe, ambiguous=ambiguous)


def to_manual_csv(audit: LegacyNameAudit) -> str:
    """ambiguous 항목을 수동 검토/매핑용 CSV 문자열로 내보낸다.

    헤더 ``name,reason,resolved_user_id`` + ambiguous 항목(이름 정렬). ``resolved_user_id``
    는 담당자가 채워 넣을 빈 칸이다. safe 항목은 CSV 에 넣지 않는다.

    Returns:
        CSV 텍스트(마지막에 개행 포함).
    """
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(["name", "reason", "resolved_user_id"])
    for name in sorted(audit.ambiguous):
        writer.writerow([name, audit.ambiguous[name], ""])
    return buf.getvalue()


def apply_safe_backfill(
    session: Session, *, order_id: int, domain: str, audit: LegacyNameAudit,
    approved_names: Iterable[str], assigned_by_user_id: int,
    now: Optional[datetime.datetime] = None,
) -> List[OrderAssignment]:
    """명시 승인된 **safe** name 만 ``source=BACKFILL`` 로 배정한다(자동 승격 0).

    Args:
        order_id: 대상 주문.
        domain: SALES|DRAWING|CONSTRUCTION.
        audit: :func:`audit_legacy_names` 결과.
        approved_names: 담당자가 명시 승인한 name 목록(safe 에 있어야 함).
        assigned_by_user_id: backfill 실행 주체.
        now: 테스트용 시각 주입.

    Returns:
        생성된 OrderAssignment row 목록(호출자가 commit).

    Raises:
        AssignmentValidationError: 승인 name 이 ambiguous 이거나 safe 에 없을 때(422).
            도메인이 잘못됐을 때도 마찬가지.
    """
    _validate_domain(domain)
    ts = now or now_utc_naive()
    created: List[OrderAssignment] = []
    for raw in approved_names:
        name = (raw or "").strip()
        if name in audit.ambiguous:
            raise AssignmentValidationError(
                f"refuse to backfill ambiguous name {name!r} "
                f"({audit.ambiguous[name]}); manual CSV resolution required."
            )
        if name not in audit.safe:
            raise AssignmentValidationError(
                f"name {name!r} is not in the safe audit map; no auto-promotion."
            )
        row = OrderAssignment(
            order_id=order_id, domain=domain, user_id=audit.safe[name],
            source="BACKFILL", active=True, assigned_at=ts,
            assigned_by_user_id=assigned_by_user_id,
        )
        session.add(row)
        created.append(row)
    return created


__all__ = [
    "NO_MATCH", "MULTIPLE_MATCH", "LegacyNameAudit",
    "audit_legacy_names", "to_manual_csv", "apply_safe_backfill",
]
