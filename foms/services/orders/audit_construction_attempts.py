"""flat 시공 데이터 → UUID construction attempt 매핑 audit/분류 (CONSTRUCTION-BACKFILL-00, §5.2).

주문의 flat 시공 흔적(``workflow.history`` 의 ``시공 시작`` 진입·
``structured_data['construction_fail_history']`` 재작업 리스트·``schedule.construction``
예정일·``construction.evidence``)과 flat main-stage(:func:`read_main_stage`)를 **read-only
로 분류**한다. 핵심 계약은 **자동 매핑 0** — 사람이 봐야 하는 주문은 절대 자동 backfill 하지
않는다:

* :func:`audit_construction_attempts` 는 아무 것도 쓰지 않는다(순수 조회).
* **SAFE**: main-stage 가 in-flight ``CONSTRUCTION`` 이고 시공 시작이 **단일**(``시공 시작``
  history 1건)·시공 불가 재작업 0(``construction_fail_history`` 비어 있음)인 주문 →
  current ``IN_PROGRESS`` attempt 1개로 정확 매핑한다. schedule(예정일)·transition(시작)·
  evidence 는 그 attempt 의 스냅샷으로 복제된다.
* **AMBIGUOUS**: 복수 시작·재작업(``construction_fail_history`` 비어 있지 않음 → 복수
  attempt 인데 flat 은 attempt 경계 소실 :data:`MULTIPLE_STARTS`), main 이 CONSTRUCTION 을
  이미 지난 완료 이력(:data:`PAST_CONSTRUCTION` — **직접 COMPLETED 추론 금지**), in-flight
  CONSTRUCTION 인데 ``시공 시작`` history 누락(:data:`MISSING_START`),
  ``construction_fail_history`` 구조 이상(:data:`MALFORMED`) → 수동 CSV 로 보낸다(자동
  attempt 발급/선택 금지).
* 시공 활동이 전혀 없는 주문(시작 0·재작업 0·main != CONSTRUCTION)은 대상에서 제외한다.

**전이(start/complete) 활성화는 하류 STATE-CONST-CS 소관** 이므로 이 audit 은 flat status/
history/stage 를 **재작성하지 않고**(inferred stage rewrite 금지), 시공 완료 여부를
main-stage 로 **자동 추론하지 않는다**(직접 COMPLETED 자동 발급 금지 — 불명확은 ambiguous).

**in-flight CONSTRUCTION current IN_PROGRESS 100%**:
:attr:`ConstructionAttemptAudit.in_flight_ids`(main==CONSTRUCTION 주문)가 모두
SAFE(IN_PROGRESS) 인지는 :meth:`covers_all_in_flight` 로 검사한다 — ambiguous in-flight
주문이 있으면 coverage < 100% 이고 enforcement 는 게이트된다
(:func:`backfill_construction_attempts.can_enforce`).

ponytail: 이 audit 은 history/fail_history→UUID 분류라 형제 ``audit_production_runs`` /
``audit_as_cycles`` 와 동일한 lite 패턴을 쓴다 — BACKFILL-ARTIFACT-00 의 암호화 run state
machine(lease/checkpoint/OPS-APPROVAL)까지 끌어오지 않는다.
"""
from __future__ import annotations

import copy
import csv
import io
import json
from dataclasses import dataclass
from typing import Any, Dict, FrozenSet, Iterable, List, Optional, Tuple

from sqlalchemy.orm import Session

from foms.services.orders.state_axes import read_main_stage

CONSTRUCTION_STAGE = "CONSTRUCTION"
ATTEMPT_IN_PROGRESS = "IN_PROGRESS"

# workflow.history entry 가 "시공 시작"(construction start)임을 나타내는 note 마커.
_START_NOTE = "시공 시작"

# ambiguous 사유 코드.
MULTIPLE_STARTS = "MULTIPLE_STARTS"      # 시작/재작업 복수 → 복수 attempt(flat 경계 소실)
PAST_CONSTRUCTION = "PAST_CONSTRUCTION"  # main 이 CONSTRUCTION 을 지남 → 직접 COMPLETED(자동 금지)
MISSING_START = "MISSING_START"          # in-flight CONSTRUCTION 인데 시공 시작 history 없음
MALFORMED = "MALFORMED"                  # construction_fail_history 구조 이상


@dataclass(frozen=True)
class ConstructionAttemptPlan:
    """SAFE 주문 1건의 결정적 backfill plan(current IN_PROGRESS attempt 1개).

    Attributes:
        order_id: 주문 id.
        status: 발급할 attempt 상태(항상 :data:`ATTEMPT_IN_PROGRESS`).
        legacy_seq: 발급 근거 시공 시작 ordinal(provenance·멱등 키; 단일 시작이라 0).
        scheduled_date: flat ``schedule.construction.date`` 스냅샷(없으면 None).
        started_at: flat ``시공 시작`` history 의 시작 ISO 문자열(없으면 None).
        started_by: 시공 시작 담당(없으면 None).
        evidence: flat ``construction.evidence`` 스냅샷(복제 — flat 보존; 없으면 None).
    """

    order_id: int
    status: str
    legacy_seq: int
    scheduled_date: Optional[str]
    started_at: Optional[str]
    started_by: Optional[str]
    evidence: Optional[Dict[str, Any]]


@dataclass(frozen=True)
class AmbiguousConstructionAttempt:
    """자동 매핑 불가한 주문 1건(수동 CSV 대상·read-only).

    Attributes:
        order_id: 주문 id.
        main_stage: 발견 시점 canonical main-stage(참고).
        start_count: ``workflow.history`` 의 ``시공 시작`` 진입 수.
        fail_count: ``construction_fail_history`` 재작업 수(없으면 0).
        scheduled_date: flat 시공 예정일(참고, 없으면 None).
        started_at: flat 첫 시공 시작 ISO(참고, 없으면 None).
        reason: :data:`MULTIPLE_STARTS` | :data:`PAST_CONSTRUCTION` |
            :data:`MISSING_START` | :data:`MALFORMED`.
    """

    order_id: int
    main_stage: Optional[str]
    start_count: int
    fail_count: int
    scheduled_date: Optional[str]
    started_at: Optional[str]
    reason: str


@dataclass(frozen=True)
class ConstructionAttemptAudit:
    """분류 결과(read-only).

    Attributes:
        safe: SAFE 주문의 backfill plan 목록(order_id 오름차순).
        ambiguous: 자동 매핑 불가 주문 목록(수동 CSV 대상).
        in_flight_ids: main-stage 가 in-flight ``CONSTRUCTION`` 인 주문 id 집합(coverage 기준).
    """

    safe: Tuple[ConstructionAttemptPlan, ...]
    ambiguous: Tuple[AmbiguousConstructionAttempt, ...]
    in_flight_ids: FrozenSet[int]

    def covers_all_in_flight(self) -> bool:
        """모든 in-flight CONSTRUCTION 주문이 SAFE(IN_PROGRESS) plan 을 갖는가(100% 매핑)."""
        safe_ids = {p.order_id for p in self.safe}
        return self.in_flight_ids <= safe_ids


def _workflow_history(sd: Any) -> List[Dict[str, Any]]:
    """``workflow.history`` 리스트를 안전 반환(부재/이상 시 빈 리스트)."""
    if not isinstance(sd, dict):
        return []
    workflow = sd.get("workflow")
    if not isinstance(workflow, dict):
        return []
    history = workflow.get("history")
    return history if isinstance(history, list) else []


def _construction_starts(sd: Any) -> List[Dict[str, Any]]:
    """``workflow.history`` 중 시공 시작(stage==CONSTRUCTION + ``시공 시작`` note) 진입(발생 순)."""
    starts: List[Dict[str, Any]] = []
    for entry in _workflow_history(sd):
        if not isinstance(entry, dict):
            continue
        stage = str(entry.get("stage") or "").strip()
        note = str(entry.get("note") or "")
        if stage == CONSTRUCTION_STAGE and _START_NOTE in note:
            starts.append(entry)
    return starts


def _fail_history_raw(sd: Any) -> Any:
    """``structured_data['construction_fail_history']`` 를 그대로 반환(부재 시 None)."""
    if not isinstance(sd, dict):
        return None
    return sd.get("construction_fail_history")


def _fail_history_wellformed(fails: Any) -> bool:
    """construction_fail_history 가 dict 리스트이고 각 entry 가 정수 id 를 갖는가."""
    if not isinstance(fails, list):
        return False
    for entry in fails:
        if not isinstance(entry, dict):
            return False
        if not isinstance(entry.get("id"), int):
            return False
    return True


def _scheduled_date(sd: Any) -> Optional[str]:
    """``schedule.construction.date`` 시공 예정일 스냅샷(없으면 None)."""
    if not isinstance(sd, dict):
        return None
    schedule = sd.get("schedule")
    if not isinstance(schedule, dict):
        return None
    construction = schedule.get("construction")
    if not isinstance(construction, dict):
        return None
    return _opt_str(construction.get("date"))


def _evidence(sd: Any) -> Optional[Dict[str, Any]]:
    """``construction.evidence`` 스냅샷을 복제해 반환(없으면 None — flat 보존)."""
    if not isinstance(sd, dict):
        return None
    construction = sd.get("construction")
    if not isinstance(construction, dict):
        return None
    evidence = construction.get("evidence")
    if not isinstance(evidence, dict):
        return None
    return copy.deepcopy(evidence)


def _start_at(entry: Dict[str, Any]) -> Optional[str]:
    """시공 시작 history entry 의 ``updated_at`` ISO 문자열(없으면 None)."""
    return _opt_str(entry.get("updated_at"))


def _start_by(entry: Dict[str, Any]) -> Optional[str]:
    """시공 시작 history entry 의 ``updated_by`` 담당(없으면 None)."""
    return _opt_str(entry.get("updated_by"))


def _opt_str(value: Any) -> Optional[str]:
    """빈 값은 None, 그 외는 원문 문자열로(스냅샷 정규화)."""
    if value is None:
        return None
    text = str(value)
    return text if text != "" else None


def classify_order(order: Any) -> Optional[object]:
    """한 주문을 SAFE plan / ambiguous / None(대상 제외)로 분류한다(read-only).

    Args:
        order: ``structured_data``·``status`` 속성을 가진 주문 row.

    Returns:
        :class:`ConstructionAttemptPlan` (SAFE) | :class:`AmbiguousConstructionAttempt`
        (수동 CSV) | ``None`` (시공 활동 없음 — attempt 미발급).
    """
    order_id = getattr(order, "id", None)
    sd = getattr(order, "structured_data", None)
    main = read_main_stage(order)

    fails_raw = _fail_history_raw(sd)
    # construction_fail_history 키가 있는데 리스트/entry 구조가 이상하면 malformed.
    if fails_raw is not None and not _fail_history_wellformed(fails_raw):
        return _ambiguous(order_id, main, sd, MALFORMED)

    starts = _construction_starts(sd)
    start_count = len(starts)
    fail_count = len(fails_raw) if isinstance(fails_raw, list) else 0

    if start_count == 0 and fail_count == 0 and main != CONSTRUCTION_STAGE:
        return None  # 시공 흔적 없음 → 대상 아님.

    if main == CONSTRUCTION_STAGE:
        if fail_count >= 1 or start_count > 1:
            # 재작업/복수 시작 → attempt 경계가 flat 에 남지 않음(자동 분리 금지).
            return _ambiguous(order_id, main, sd, MULTIPLE_STARTS)
        if start_count == 0:
            # in-flight CONSTRUCTION 인데 명시 시공 시작이 없음(대기/누락 — 수동 검토).
            return _ambiguous(order_id, main, sd, MISSING_START)
        # 단일 시작·재작업 0 → current IN_PROGRESS attempt 1개.
        start = starts[0]
        return ConstructionAttemptPlan(
            order_id=order_id,
            status=ATTEMPT_IN_PROGRESS,
            legacy_seq=0,
            scheduled_date=_scheduled_date(sd),
            started_at=_start_at(start),
            started_by=_start_by(start),
            evidence=_evidence(sd),
        )

    # main 이 CONSTRUCTION 이 아닌데 시공 활동 존재: 지난 완료 이력(직접 COMPLETED)이든
    # CONSTRUCTION 이전 이상치든 자동 추론 금지 → 수동 검토(직접 COMPLETED 추론 금지).
    return _ambiguous(order_id, main, sd, PAST_CONSTRUCTION)


def _ambiguous(
    order_id: Any, main: Optional[str], sd: Any, reason: str
) -> AmbiguousConstructionAttempt:
    """ambiguous 레코드 구성(참고 카운트/스냅샷 — 수동 검토용)."""
    starts = _construction_starts(sd)
    fails_raw = _fail_history_raw(sd)
    fail_count = len(fails_raw) if isinstance(fails_raw, list) else 0
    return AmbiguousConstructionAttempt(
        order_id=order_id,
        main_stage=main,
        start_count=len(starts),
        fail_count=fail_count,
        scheduled_date=_scheduled_date(sd),
        started_at=_start_at(starts[0]) if starts else None,
        reason=reason,
    )


def iter_orders(session: Session, *, batch_size: int = 1000) -> Iterable[Any]:
    """모든 주문 row 를 스트리밍(read-only, 전수 coverage)."""
    from models import Order

    for order in session.query(Order).order_by(Order.id).yield_per(batch_size):
        yield order


def audit_construction_attempts(
    session: Session, *, batch_size: int = 1000
) -> ConstructionAttemptAudit:
    """전체 주문을 분류해 SAFE plan·ambiguous·in-flight 집합을 만든다(mutation 0).

    Args:
        session: SQLAlchemy Session(read-only 로만 사용).
        batch_size: 스트리밍 yield_per 크기.

    Returns:
        :class:`ConstructionAttemptAudit`.
    """
    safe: List[ConstructionAttemptPlan] = []
    ambiguous: List[AmbiguousConstructionAttempt] = []
    in_flight: set[int] = set()
    for order in iter_orders(session, batch_size=batch_size):
        if read_main_stage(order) == CONSTRUCTION_STAGE:
            in_flight.add(order.id)
        result = classify_order(order)
        if isinstance(result, ConstructionAttemptPlan):
            safe.append(result)
        elif isinstance(result, AmbiguousConstructionAttempt):
            ambiguous.append(result)
    safe.sort(key=lambda p: p.order_id)
    ambiguous_sorted = tuple(sorted(ambiguous, key=lambda a: a.order_id))
    return ConstructionAttemptAudit(tuple(safe), ambiguous_sorted, frozenset(in_flight))


def to_manual_csv(audit: ConstructionAttemptAudit) -> str:
    """ambiguous 주문을 수동 매핑용 CSV 문자열로 내보낸다(header 포함).

    Args:
        audit: :func:`audit_construction_attempts` 결과.

    Returns:
        ``order_id,main_stage,start_count,fail_count,legacy_scheduled_date,
        legacy_started_at,target_attempt_id,target_status,decision,reason,
        approved_by_user_id`` CSV(ambiguous 행만·자동 매핑 0·target 공란).
    """
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow([
        "order_id", "main_stage", "start_count", "fail_count", "legacy_scheduled_date",
        "legacy_started_at", "target_attempt_id", "target_status", "decision", "reason",
        "approved_by_user_id",
    ])
    for ref in audit.ambiguous:
        writer.writerow([
            ref.order_id,
            ref.main_stage or "",
            ref.start_count,
            ref.fail_count,
            ref.scheduled_date or "",
            ref.started_at or "",
            "",            # target_attempt_id: 자동 매핑 0 → 수동 결정 대상.
            "",            # target_status: 미결(수동).
            "MANUAL",      # decision: 사람이 결정(자동 attempt 발급/선택 금지).
            ref.reason,
            "",            # approved_by_user_id: 승인 전.
        ])
    return buf.getvalue()


__all__ = [
    "CONSTRUCTION_STAGE",
    "ATTEMPT_IN_PROGRESS",
    "MULTIPLE_STARTS",
    "PAST_CONSTRUCTION",
    "MISSING_START",
    "MALFORMED",
    "ConstructionAttemptPlan",
    "AmbiguousConstructionAttempt",
    "ConstructionAttemptAudit",
    "classify_order",
    "audit_construction_attempts",
    "to_manual_csv",
]
