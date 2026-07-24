"""다축 상태 read-only audit — canonical mirror / projection / overlay ambiguity 분리 분류.

STATE-MODEL-00 (SSOT §7.1·§7.2). ``order.status``/``workflow.stage``/``erp_stage_code``와
canonical 축(:mod:`foms.services.orders.state_axes`)을 비교해 세 종류의 불일치를 **분리**해서
분류한다. **아무 것도 쓰지 않는다**(자동 stage 역변경·projection 자동수정 0). 실제 repair는
하류 STATE-AXES-REPAIR-00 (`repair_order_state_axes.py`)이 명시 승인·manual mapping 하에 수행한다.

분류 3종:

* **canonical mirror mismatch**: ``workflow.stage != erp_stage_code``.
* **projection mismatch**: canonical 축에서 계산한 legacy projection != ``order.status``.
  정상 overlay divergence(``LOGISTICS_STATUS_PRESERVE_WORKFLOW_STAGE``)는 projection이
  status와 일치하므로 mismatch가 아니며 별도로 집계한다.
* **overlay source ambiguity**: ``order.status``가 0개(unmapped/display alias) 또는 2개 이상
  canonical 축으로 해석되는 건.

BACKFILL library 계약(assignment_backfill.py 선례와 동일 lite 패턴):

* **safe**: mirror mismatch 중 ``workflow.stage``가 유효 main 코드인 건(erp_stage_code
  dry-run remap 후보) + canonical 축으로 재계산 가능한 projection mismatch.
* **ambiguous → manual**: overlay ambiguity. :func:`to_manual_csv`로 수동 매핑 CSV 내보내기.

ponytail: 이 audit은 순수 분류 라이브러리다 — DPAPI/lease/checkpoint 암호화 run state machine
(BACKFILL-ARTIFACT-00)이나 encrypted CLI 러너는 끌어오지 않는다(assignment_backfill.py와 동일 판단).
그 무거운 파이프라인은 STATE-AXES-REPAIR-00의 apply 단계 소관이다.
"""
from __future__ import annotations

import csv
import io
from dataclasses import dataclass, field
from typing import Any, Iterable, List, Optional

from foms.services.orders.stage_override import MAIN_PIPELINE_CODES, normalize_main_stage
from foms.services.orders.state_axes import (
    classify_status_to_axes,
    is_legacy_display_alias,
    legacy_status_projection,
    read_state_axes,
)
from foms.services.orders.status_constants import (
    LOGISTICS_STATUS_PRESERVE_WORKFLOW_STAGE,
)

# overlay ambiguity 사유 코드.
UNMAPPED = "UNMAPPED"            # 어느 canonical 축에도 매핑 안 됨
MULTI_AXIS = "MULTI_AXIS"        # 2개 이상 축으로 해석됨
DISPLAY_ALIAS = "DISPLAY_ALIAS"  # writer 없는 legacy display alias(HAPPYCALL/SHIPMENT)


@dataclass(frozen=True)
class MirrorMismatch:
    """``workflow.stage != erp_stage_code`` 건.

    Attributes:
        order_id: 주문 ID.
        workflow_stage: ``structured_data.workflow.stage`` 원값.
        erp_stage_code: indexed mirror 컬럼 값.
        safe_target: workflow.stage가 유효 main 코드면 그 코드(erp_stage_code remap 후보),
            아니면 None(수동 판단 필요).
    """

    order_id: Any
    workflow_stage: Optional[str]
    erp_stage_code: Optional[str]
    safe_target: Optional[str]


@dataclass(frozen=True)
class ProjectionMismatch:
    """canonical projection != ``order.status`` 건.

    Attributes:
        order_id: 주문 ID.
        actual_status: 저장된 ``order.status``.
        expected_projection: canonical 축에서 계산한 projection.
        recomputable: canonical 축으로 안전 재계산 가능 여부(True면 safe bucket).
    """

    order_id: Any
    actual_status: str
    expected_projection: str
    recomputable: bool


@dataclass(frozen=True)
class OverlayAmbiguity:
    """``order.status`` overlay source ambiguity 건.

    Attributes:
        order_id: 주문 ID.
        status: 저장된 ``order.status``.
        reason: UNMAPPED | MULTI_AXIS | DISPLAY_ALIAS.
    """

    order_id: Any
    status: str
    reason: str


@dataclass
class OrderStateAxesAudit:
    """다축 상태 audit 결과(read-only 분류).

    세 종류를 분리 보관한다. safe/ambiguous bucket은 property로 파생한다.
    """

    mirror_mismatch: List[MirrorMismatch] = field(default_factory=list)
    projection_mismatch: List[ProjectionMismatch] = field(default_factory=list)
    overlay_ambiguity: List[OverlayAmbiguity] = field(default_factory=list)
    normal_overlay_divergence: int = 0
    total: int = 0

    @property
    def safe(self) -> List[Any]:
        """자동 재계산 후보(mirror safe_target + recomputable projection). 여전히 명시 승인 필요."""
        rows: List[Any] = [m for m in self.mirror_mismatch if m.safe_target is not None]
        rows.extend(p for p in self.projection_mismatch if p.recomputable)
        return rows

    @property
    def ambiguous(self) -> List[OverlayAmbiguity]:
        """수동 매핑(manual CSV) 필요 건. ADMIN/MANAGER reason 없이는 enforce 금지."""
        return list(self.overlay_ambiguity)


def _stage_raw(order: Any) -> Optional[str]:
    """structured_data.workflow.stage 원값(문자열 또는 None)."""
    sd = getattr(order, "structured_data", None)
    if not isinstance(sd, dict):
        return None
    workflow = sd.get("workflow")
    if not isinstance(workflow, dict):
        return None
    stage = workflow.get("stage")
    return stage if isinstance(stage, str) else None


def _classify_mirror(order: Any) -> Optional[MirrorMismatch]:
    """workflow.stage vs erp_stage_code 불일치 분류(일치/양쪽 None이면 None)."""
    stage = _stage_raw(order)
    mirror = getattr(order, "erp_stage_code", None)
    stage_norm = (stage or "").strip() or None
    mirror_norm = (mirror or "").strip() or None
    if stage_norm == mirror_norm:
        return None
    safe_target = normalize_main_stage(stage_norm) if stage_norm else None
    if safe_target not in MAIN_PIPELINE_CODES:
        safe_target = None
    return MirrorMismatch(
        order_id=getattr(order, "id", None),
        workflow_stage=stage_norm,
        erp_stage_code=mirror_norm,
        safe_target=safe_target,
    )


def _classify_projection(order: Any) -> Optional[ProjectionMismatch]:
    """canonical projection vs order.status 불일치 분류(일치면 None)."""
    status = str(getattr(order, "status", None) or "").strip()
    projection = legacy_status_projection(read_state_axes(order))
    if not projection or projection == status:
        return None
    matches = classify_status_to_axes(status)
    recomputable = len(matches) <= 1  # MULTI_AXIS(>1)는 모호 → 자동 재계산 금지
    return ProjectionMismatch(
        order_id=getattr(order, "id", None),
        actual_status=status,
        expected_projection=projection,
        recomputable=recomputable,
    )


def _classify_overlay(order: Any) -> Optional[OverlayAmbiguity]:
    """order.status overlay source ambiguity 분류(단일 매핑이면 None)."""
    status = str(getattr(order, "status", None) or "").strip()
    if not status:
        return None
    if is_legacy_display_alias(status):
        reason = DISPLAY_ALIAS
    else:
        matches = classify_status_to_axes(status)
        if len(matches) == 1:
            return None
        reason = UNMAPPED if not matches else MULTI_AXIS
    return OverlayAmbiguity(order_id=getattr(order, "id", None), status=status, reason=reason)


def _is_normal_overlay_divergence(order: Any) -> bool:
    """order.status가 정상 overlay divergence(logistics/hold preserve)인지."""
    status = str(getattr(order, "status", None) or "").strip()
    if status not in LOGISTICS_STATUS_PRESERVE_WORKFLOW_STAGE:
        return False
    # workflow.stage가 main 코드로 살아 있으면(=overlay가 stage를 보존) 정상 divergence.
    return normalize_main_stage(_stage_raw(order)) in MAIN_PIPELINE_CODES


def audit_order_state_axes(orders: Iterable[Any]) -> OrderStateAxesAudit:
    """order 목록을 세 종류 불일치로 분리 분류한다(아무 것도 쓰지 않음).

    Args:
        orders: ``status``/``erp_stage_code``/``structured_data``를 가진 Order-like 목록.

    Returns:
        OrderStateAxesAudit — mirror/projection/overlay 분리 + normal divergence count.
    """
    result = OrderStateAxesAudit()
    for order in orders:
        result.total += 1
        mirror = _classify_mirror(order)
        if mirror is not None:
            result.mirror_mismatch.append(mirror)
        projection = _classify_projection(order)
        if projection is not None:
            result.projection_mismatch.append(projection)
        overlay = _classify_overlay(order)
        if overlay is not None:
            result.overlay_ambiguity.append(overlay)
        if _is_normal_overlay_divergence(order):
            result.normal_overlay_divergence += 1
    return result


def to_manual_csv(audit: OrderStateAxesAudit) -> str:
    """overlay ambiguity를 수동 매핑용 CSV로 내보낸다.

    헤더 ``order_id,status,reason,resolved_axis,resolved_value``(order_id 정렬).
    ``resolved_*``는 ADMIN/MANAGER가 채우는 빈 칸이다. safe 건은 CSV에 넣지 않는다.

    Returns:
        CSV 텍스트(마지막 개행 포함).
    """
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(["order_id", "status", "reason", "resolved_axis", "resolved_value"])
    for row in sorted(audit.overlay_ambiguity, key=lambda r: (str(r.order_id), r.status)):
        writer.writerow([row.order_id, row.status, row.reason, "", ""])
    return buf.getvalue()


__all__ = [
    "UNMAPPED",
    "MULTI_AXIS",
    "DISPLAY_ALIAS",
    "MirrorMismatch",
    "ProjectionMismatch",
    "OverlayAmbiguity",
    "OrderStateAxesAudit",
    "audit_order_state_axes",
    "to_manual_csv",
]
