"""flat 생산 데이터 → UUID production run 매핑 audit/분류 (PRODUCTION-BACKFILL-00, §5.2).

주문의 flat ``structured_data['production']``(단일 steps/defects 리스트·rework marker)와
``workflow.history`` 의 PRODUCTION 진입 이력을 **read-only 로 분류**한다. 핵심 계약은
**자동 매핑 0** — 사람이 봐야 하는 주문은 절대 자동 backfill 하지 않는다:

* :func:`audit_production_runs` 는 아무 것도 쓰지 않는다(순수 조회).
* **SAFE**: main-stage 가 in-flight ``PRODUCTION`` 이고 생산 시작이 **단일**(``제작 시작``
  history 1건)·rework 0 인 주문 → current ``IN_PROGRESS`` run 1개로 정확 매핑. flat
  steps/defects 는 그 run 의 scope 스냅샷으로 복제된다(§1387 "단일 start/step/defect
  history만 current IN_PROGRESS run으로").
* **AMBIGUOUS**: 복수 start·rework(복수 run 인데 flat 은 scope 경계 소실)·main 이
  PRODUCTION 을 이미 지난 완료 이력(직접 COMPLETED 는 자동 추론 금지)·start history 누락·
  malformed 구조 → 수동 CSV 로 보낸다(§1387 "직접 COMPLETED·복수 start … manual CSV").
* 생산 활동이 전혀 없는 주문은 대상에서 제외한다(run 미발급).

**in-flight PRODUCTION current IN_PROGRESS 100%**: :attr:`ProductionRunAudit.in_flight_ids`
(main==PRODUCTION 주문)가 모두 SAFE(IN_PROGRESS) 인지는 :meth:`covers_all_in_flight` 로
검사한다 — ambiguous in-flight 주문이 있으면 coverage < 100% 이고 enforcement 는 게이트된다
(``backfill_production_runs.can_enforce``).

ponytail: 이 audit 은 index/history→UUID 분류라 형제 ``audit_order_item_identities`` 와
동일한 lite 패턴을 쓴다 — BACKFILL-ARTIFACT-00 의 암호화 run state machine(lease/checkpoint/
OPS-APPROVAL)까지 끌어오지 않는다. 그 무거운 파이프라인은 대량 PII resume backfill 용이고,
in-flight 주문당 IN_PROGRESS run 1개를 발급하는 이 매핑엔 과하다.
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

PRODUCTION_STAGE = "PRODUCTION"
RUN_IN_PROGRESS = "IN_PROGRESS"

# ambiguous 사유 코드.
MULTIPLE_STARTS = "MULTIPLE_STARTS"          # start/rework 복수 → 복수 run(flat scope 소실)
PAST_PRODUCTION = "PAST_PRODUCTION"          # main 이 PRODUCTION 을 지남 → 직접 COMPLETED(자동 금지)
MISSING_START = "MISSING_START"              # in-flight PRODUCTION 인데 start history 없음
MALFORMED = "MALFORMED"                      # production/steps/defects 구조 이상


@dataclass(frozen=True)
class ProductionRunPlan:
    """SAFE 주문 1건의 결정적 backfill plan(current IN_PROGRESS run 1개).

    Attributes:
        order_id: 주문 id.
        status: 발급할 run 상태(항상 :data:`RUN_IN_PROGRESS`).
        started_at: legacy 생산 시작 ISO 문자열(history 없으면 None).
        steps: flat ``production.steps`` 스냅샷(복제 — flat 보존).
        defects: flat ``production.defects`` 스냅샷(복제 — flat 보존).
    """

    order_id: int
    status: str
    started_at: Optional[str]
    steps: Tuple[Dict[str, Any], ...]
    defects: Tuple[Dict[str, Any], ...]


@dataclass(frozen=True)
class AmbiguousProductionRun:
    """자동 매핑 불가한 주문 1건(수동 CSV 대상·read-only).

    Attributes:
        order_id: 주문 id.
        main_stage: 발견 시점 canonical main-stage(참고).
        start_count: workflow.history 의 PRODUCTION 진입 수.
        rework_count: ``production.rework.count`` (없으면 0).
        started_at: legacy 첫 생산 시작 ISO(참고, 없으면 None).
        steps: flat steps 스냅샷(수동 검토용).
        defects: flat defects 스냅샷(수동 검토용).
        reason: :data:`MULTIPLE_STARTS` | :data:`PAST_PRODUCTION` | :data:`MISSING_START`
            | :data:`MALFORMED`.
    """

    order_id: int
    main_stage: Optional[str]
    start_count: int
    rework_count: int
    started_at: Optional[str]
    steps: Tuple[Any, ...]
    defects: Tuple[Any, ...]
    reason: str


@dataclass(frozen=True)
class ProductionRunAudit:
    """분류 결과(read-only).

    Attributes:
        safe: SAFE 주문의 backfill plan 목록(order_id 오름차순).
        ambiguous: 자동 매핑 불가 주문 목록(수동 CSV 대상).
        in_flight_ids: main-stage 가 in-flight ``PRODUCTION`` 인 주문 id 집합(coverage 기준).
    """

    safe: Tuple[ProductionRunPlan, ...]
    ambiguous: Tuple[AmbiguousProductionRun, ...]
    in_flight_ids: FrozenSet[int]

    def covers_all_in_flight(self) -> bool:
        """모든 in-flight PRODUCTION 주문이 SAFE(IN_PROGRESS) plan 을 갖는가(100% 매핑)."""
        safe_ids = {p.order_id for p in self.safe}
        return self.in_flight_ids <= safe_ids


def _production_dict(sd: Any) -> Any:
    """``structured_data['production']`` 를 그대로 반환(부재 시 None)."""
    if not isinstance(sd, dict):
        return None
    return sd.get("production")


def _production_start_history(sd: Any) -> List[Dict[str, Any]]:
    """``workflow.history`` 중 stage==PRODUCTION 인 진입 이력(발생 순)."""
    if not isinstance(sd, dict):
        return []
    workflow = sd.get("workflow")
    if not isinstance(workflow, dict):
        return []
    history = workflow.get("history")
    if not isinstance(history, list):
        return []
    return [
        h for h in history
        if isinstance(h, dict) and str(h.get("stage") or "").strip() == PRODUCTION_STAGE
    ]


def _rework_count(production: Dict[str, Any]) -> int:
    """``production.rework.count`` (dict/정수 아니면 0)."""
    rework = production.get("rework")
    if not isinstance(rework, dict):
        return 0
    count = rework.get("count")
    return count if isinstance(count, int) and count > 0 else 0


def _has_activity(production: Dict[str, Any], start_count: int) -> bool:
    """주문이 생산 공정을 한 번이라도 돌렸는지(run 발급 대상 여부)."""
    if start_count >= 1 or _rework_count(production) >= 1:
        return True
    steps = production.get("steps")
    if isinstance(steps, list) and any(
        isinstance(s, dict) and s.get("done") for s in steps
    ):
        return True
    defects = production.get("defects")
    return isinstance(defects, list) and len(defects) > 0


def classify_order(order: Any) -> Optional[object]:
    """한 주문을 SAFE plan / ambiguous / None(대상 제외)로 분류한다(read-only).

    Args:
        order: ``structured_data``·``status``·``is_erp_order`` 속성을 가진 주문 row.

    Returns:
        :class:`ProductionRunPlan` (SAFE) | :class:`AmbiguousProductionRun` (수동 CSV)
        | ``None`` (생산 활동 없음 — run 미발급).
    """
    order_id = getattr(order, "id", None)
    sd = getattr(order, "structured_data", None)
    main = read_main_stage(order)
    production = _production_dict(sd)

    if production is None:
        return None  # 생산 데이터 없음 → 대상 아님.
    if not isinstance(production, dict) or not _steps_defects_wellformed(production):
        return _ambiguous(order_id, main, sd, production, MALFORMED)

    start_history = _production_start_history(sd)
    start_count = len(start_history)
    rework = _rework_count(production)

    if not _has_activity(production, start_count):
        return None  # production 키만 있고 실제 활동 0 → 대상 아님.

    if main == PRODUCTION_STAGE:
        if rework >= 1 or start_count > 1:
            return _ambiguous(order_id, main, sd, production, MULTIPLE_STARTS)
        if start_count == 0:
            return _ambiguous(order_id, main, sd, production, MISSING_START)
        # 단일 start·rework 0 → current IN_PROGRESS run 1개.
        return ProductionRunPlan(
            order_id=order_id,
            status=RUN_IN_PROGRESS,
            started_at=_first_start_at(start_history),
            steps=tuple(copy.deepcopy(production.get("steps") or [])),
            defects=tuple(copy.deepcopy(production.get("defects") or [])),
        )

    # main 이 PRODUCTION 이 아닌데 생산 활동 존재: 지난 완료 이력(직접 COMPLETED)이든
    # PRODUCTION 이전 이상치든 자동 추론 금지 → 수동 검토(§1387 "직접 COMPLETED … manual CSV").
    return _ambiguous(order_id, main, sd, production, PAST_PRODUCTION)


def _steps_defects_wellformed(production: Dict[str, Any]) -> bool:
    """steps/defects 키가 있으면 list 여야 한다(malformed 판정)."""
    steps = production.get("steps")
    if steps is not None and not isinstance(steps, list):
        return False
    defects = production.get("defects")
    if defects is not None and not isinstance(defects, list):
        return False
    return True


def _first_start_at(start_history: List[Dict[str, Any]]) -> Optional[str]:
    """첫 PRODUCTION 진입 history 의 ``updated_at`` (없으면 None)."""
    if not start_history:
        return None
    at = start_history[0].get("updated_at")
    return str(at) if at else None


def _ambiguous(
    order_id: Any, main: Optional[str], sd: Any, production: Any, reason: str
) -> AmbiguousProductionRun:
    """ambiguous 레코드 구성(steps/defects 는 원문 그대로 스냅샷 — 수동 검토용)."""
    start_history = _production_start_history(sd)
    prod = production if isinstance(production, dict) else {}
    steps = prod.get("steps")
    defects = prod.get("defects")
    return AmbiguousProductionRun(
        order_id=order_id,
        main_stage=main,
        start_count=len(start_history),
        rework_count=_rework_count(prod),
        started_at=_first_start_at(start_history),
        steps=tuple(steps) if isinstance(steps, list) else (),
        defects=tuple(defects) if isinstance(defects, list) else (),
        reason=reason,
    )


def iter_orders(session: Session, *, batch_size: int = 1000) -> Iterable[Any]:
    """모든 주문 row 를 스트리밍(read-only, 전수 coverage)."""
    from models import Order

    for order in session.query(Order).order_by(Order.id).yield_per(batch_size):
        yield order


def audit_production_runs(session: Session, *, batch_size: int = 1000) -> ProductionRunAudit:
    """전체 주문을 분류해 SAFE plan·ambiguous·in-flight 집합을 만든다(mutation 0).

    Args:
        session: SQLAlchemy Session(read-only 로만 사용).
        batch_size: 스트리밍 yield_per 크기.

    Returns:
        :class:`ProductionRunAudit`.
    """
    safe: List[ProductionRunPlan] = []
    ambiguous: List[AmbiguousProductionRun] = []
    in_flight: set[int] = set()
    for order in iter_orders(session, batch_size=batch_size):
        if read_main_stage(order) == PRODUCTION_STAGE:
            in_flight.add(order.id)
        result = classify_order(order)
        if isinstance(result, ProductionRunPlan):
            safe.append(result)
        elif isinstance(result, AmbiguousProductionRun):
            ambiguous.append(result)
    safe.sort(key=lambda p: p.order_id)
    ambiguous_sorted = tuple(sorted(ambiguous, key=lambda a: a.order_id))
    return ProductionRunAudit(tuple(safe), ambiguous_sorted, frozenset(in_flight))


def to_manual_csv(audit: ProductionRunAudit) -> str:
    """ambiguous 주문을 수동 매핑용 CSV 문자열로 내보낸다(header 포함, §1376 컬럼).

    Args:
        audit: :func:`audit_production_runs` 결과.

    Returns:
        ``order_id,legacy_started_at,legacy_steps_json,legacy_defects_json,target_run_id,
        target_status,decision,reason,approved_by_user_id`` CSV(ambiguous 행만·자동 매핑 0).
    """
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow([
        "order_id", "legacy_started_at", "legacy_steps_json", "legacy_defects_json",
        "target_run_id", "target_status", "decision", "reason", "approved_by_user_id",
    ])
    for ref in audit.ambiguous:
        writer.writerow([
            ref.order_id,
            ref.started_at or "",
            json.dumps(list(ref.steps), ensure_ascii=False, default=str),
            json.dumps(list(ref.defects), ensure_ascii=False, default=str),
            "",            # target_run_id: 자동 매핑 0 → 수동 결정 대상.
            "",            # target_status: 미결(수동).
            "MANUAL",      # decision: 사람이 결정.
            ref.reason,
            "",            # approved_by_user_id: 승인 전.
        ])
    return buf.getvalue()


__all__ = [
    "PRODUCTION_STAGE",
    "RUN_IN_PROGRESS",
    "MULTIPLE_STARTS",
    "PAST_PRODUCTION",
    "MISSING_START",
    "MALFORMED",
    "ProductionRunPlan",
    "AmbiguousProductionRun",
    "ProductionRunAudit",
    "classify_order",
    "audit_production_runs",
    "to_manual_csv",
]
