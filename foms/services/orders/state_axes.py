"""다축 order 상태 canonical read model·constants (STATE-MODEL-00, SSOT §2.2·§2.2.1).

order 상태는 서로 직교(orthogonal)한 여러 축이 legacy ``order.status`` 단일 문자열에
섞여 있다. 이 모듈은 기존 저장 형식(``order.status`` / ``structured_data.workflow`` /
``shipment`` / ``as_lifecycle`` / ``deleted_at`` / ``construction``)에서 **read-only 파생**으로
각 축의 canonical 값을 계산한다. 기존 저장 형식은 **변경하지 않으며**(migration 0), 새 컬럼도
만들지 않는다 — 모두 이미 존재하는 컬럼/JSON path에서 읽는다.

축(§2.2.1):

* main stage: ``workflow.stage`` (+ indexed mirror ``erp_stage_code``)
* logistics: ``shipment.logistics_status`` — ``NONE|MEASURED|REGIONAL_MEASURED|SCHEDULED|SHIPPED_PENDING``
* hold: ``workflow.hold.active`` (legacy ``order.status == 'ON_HOLD'``)
* AS: ``as_lifecycle`` 현재 cycle projection ``NONE|RECEIVED|IN_PROGRESS|COMPLETED``
* delete: ``deleted_at`` (legacy ``order.status == 'DELETED'``)
* construction run: ``construction.attempts`` 현재 attempt ``NONE|IN_PROGRESS|READY|COMPLETED|REWORKED``

legacy ``order.status``는 위 축이 섞인 **display projection**이며 정본이 아니다. 우선순위
``DELETED > ON_HOLD > AS_* > logistics > main``으로 각 canonical 축에서 재계산한다.

STATE-CORE-00 인터페이스: transition service는 canonical 축만 읽고(``read_state_axes``),
legacy projection이 필요할 때만 :func:`legacy_status_projection`으로 파생한다. 이 모듈은
**read model + constants**만 제공하고 어떤 값도 쓰지 않는다 — 실제 축 소유 write는 하류
STATE-CORE-00 / STATE-OVERLAY-01 command가 담당한다.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from foms.services.erp_order_flags import is_erp_order_record
from foms.services.orders.erp_policy_constants import STAGE_NAME_TO_CODE
from foms.services.orders.stage_override import (
    MAIN_PIPELINE_CODES,
    normalize_main_stage,
)
from foms.services.orders.status_constants import (
    LOGISTICS_STATUS_PRESERVE_WORKFLOW_STAGE,
)

# --- 축 식별자 ---------------------------------------------------------------
AXIS_MAIN = "MAIN"
AXIS_LOGISTICS = "LOGISTICS"
AXIS_HOLD = "HOLD"
AXIS_AS = "AS"
AXIS_DELETE = "DELETE"
AXIS_CONSTRUCTION = "CONSTRUCTION"

# --- 축별 canonical 값 enum ---------------------------------------------------
LOGISTICS_VALUES: Tuple[str, ...] = (
    "NONE",
    "MEASURED",
    "REGIONAL_MEASURED",
    "SCHEDULED",
    "SHIPPED_PENDING",
)
HOLD_VALUES: Tuple[str, ...] = ("NONE", "HELD")
AS_VALUES: Tuple[str, ...] = ("NONE", "RECEIVED", "IN_PROGRESS", "COMPLETED")
DELETE_VALUES: Tuple[str, ...] = ("NONE", "DELETED")
CONSTRUCTION_VALUES: Tuple[str, ...] = (
    "NONE",
    "IN_PROGRESS",
    "READY",
    "COMPLETED",
    "REWORKED",
)

# legacy ``order.status`` 문자열 → (axis, canonical_value). main 파이프라인 코드는
# normalize_main_stage로 별도 처리하므로 여기엔 넣지 않는다.
LEGACY_STATUS_ALIAS: Dict[str, Tuple[str, str]] = {
    "MEASURED": (AXIS_LOGISTICS, "MEASURED"),
    "REGIONAL_MEASURED": (AXIS_LOGISTICS, "REGIONAL_MEASURED"),
    "SCHEDULED": (AXIS_LOGISTICS, "SCHEDULED"),
    "SHIPPED_PENDING": (AXIS_LOGISTICS, "SHIPPED_PENDING"),
    "ON_HOLD": (AXIS_HOLD, "HELD"),
    "AS_RECEIVED": (AXIS_AS, "RECEIVED"),
    "AS": (AXIS_AS, "IN_PROGRESS"),
    "AS_COMPLETED": (AXIS_AS, "COMPLETED"),
    "DELETED": (AXIS_DELETE, "DELETED"),
}

# writer가 없는 display alias(§2.2). canonical 축으로 매핑하지 않고 backfill-only로 보존한다.
LEGACY_DISPLAY_ALIAS: frozenset[str] = frozenset({"HAPPYCALL", "SHIPMENT"})

# AS canonical status → legacy projection 문자열.
_AS_TO_LEGACY: Dict[str, str] = {
    "RECEIVED": "AS_RECEIVED",
    "IN_PROGRESS": "AS",
    "COMPLETED": "AS_COMPLETED",
}

_AS_TERMINAL = {"COMPLETED"}


@dataclass(frozen=True)
class OrderStateAxes:
    """order의 다축 canonical read projection(read-only 파생).

    Attributes:
        main: 메인 파이프라인 코드(``RECEIVED``..``COMPLETED``) 또는 정규화 불가 시 None.
        logistics: ``NONE|MEASURED|REGIONAL_MEASURED|SCHEDULED|SHIPPED_PENDING``.
        hold: ``NONE|HELD``.
        as_status: ``NONE|RECEIVED|IN_PROGRESS|COMPLETED``.
        deleted: ``NONE|DELETED``.
        construction: ``NONE|IN_PROGRESS|READY|COMPLETED|REWORKED``.
    """

    main: Optional[str]
    logistics: str
    hold: str
    as_status: str
    deleted: str
    construction: str


def _structured(order: Any) -> Dict[str, Any]:
    """order.structured_data를 dict로 안전 반환(없으면 빈 dict)."""
    sd = getattr(order, "structured_data", None)
    return sd if isinstance(sd, dict) else {}


def _status_text(order: Any) -> str:
    """order.status를 trim한 문자열로 반환."""
    return str(getattr(order, "status", None) or "").strip()


def read_main_stage(order: Any) -> Optional[str]:
    """main-stage 축 canonical 값. ``workflow.stage`` 우선, 없으면 ``order.status``.

    legacy overlay(AS/logistics/hold/delete)가 stage/status에 들어 있으면 메인으로
    정규화되지 않아 None을 돌려준다 — 이 모호함은 audit이 잡는다.
    """
    sd = _structured(order)
    workflow = sd.get("workflow") if isinstance(sd.get("workflow"), dict) else {}
    raw = str(workflow.get("stage") or "").strip()
    if not raw and not is_erp_order_record(order):
        raw = _status_text(order)
    elif not raw:
        raw = _status_text(order)
    return normalize_main_stage(raw)


def read_logistics(order: Any) -> str:
    """logistics 축 canonical 값. ``shipment.logistics_status`` 우선, 없으면 legacy status."""
    sd = _structured(order)
    shipment = sd.get("shipment") if isinstance(sd.get("shipment"), dict) else {}
    canonical = str(shipment.get("logistics_status") or "").strip()
    if canonical in LOGISTICS_VALUES:
        return canonical
    axis = LEGACY_STATUS_ALIAS.get(_status_text(order))
    if axis and axis[0] == AXIS_LOGISTICS:
        return axis[1]
    return "NONE"


def read_hold(order: Any) -> str:
    """hold 축 canonical 값. ``workflow.hold.active`` 우선, 없으면 legacy ``ON_HOLD``."""
    sd = _structured(order)
    workflow = sd.get("workflow") if isinstance(sd.get("workflow"), dict) else {}
    hold = workflow.get("hold") if isinstance(workflow.get("hold"), dict) else None
    if hold is not None:
        return "HELD" if hold.get("active") else "NONE"
    return "HELD" if _status_text(order) == "ON_HOLD" else "NONE"


def _current_cycle_status(as_lifecycle: Dict[str, Any]) -> Optional[str]:
    """as_lifecycle의 current cycle projection 상태(마지막 transition의 ``to``)."""
    cycles = as_lifecycle.get("cycles")
    current_id = as_lifecycle.get("current_cycle_id")
    if not isinstance(cycles, list) or not current_id:
        return None
    cycle = next(
        (c for c in cycles if isinstance(c, dict) and c.get("cycle_id") == current_id),
        None,
    )
    if cycle is None:
        return None
    transitions = cycle.get("transitions")
    if isinstance(transitions, list) and transitions:
        last = transitions[-1]
        if isinstance(last, dict):
            to = str(last.get("to") or "").strip()
            if to in AS_VALUES:
                return to
    return "RECEIVED"  # cycle은 열려 있으나 transition 없음 = 접수 상태


def read_as_status(order: Any) -> str:
    """AS 축 canonical 값. ``as_lifecycle`` 현재 cycle 우선, 없으면 legacy status."""
    sd = _structured(order)
    lifecycle = sd.get("as_lifecycle")
    if isinstance(lifecycle, dict):
        status = _current_cycle_status(lifecycle)
        if status is not None:
            return status
    axis = LEGACY_STATUS_ALIAS.get(_status_text(order))
    if axis and axis[0] == AXIS_AS:
        return axis[1]
    return "NONE"


def read_deleted(order: Any) -> str:
    """delete 축 canonical 값. ``deleted_at`` 또는 legacy ``DELETED``."""
    if getattr(order, "deleted_at", None) is not None:
        return "DELETED"
    return "DELETED" if _status_text(order) == "DELETED" else "NONE"


def read_construction(order: Any) -> str:
    """construction run 축 canonical 값. ``construction.attempts`` 현재 attempt 상태.

    attempt가 없으면 not-started(``NONE``). legacy 데이터는 attempt registry가 없어
    대개 NONE이며, 실제 attempt backfill은 CONSTRUCTION-BACKFILL-00이 담당한다.
    """
    sd = _structured(order)
    construction = sd.get("construction")
    if not isinstance(construction, dict):
        return "NONE"
    attempts = construction.get("attempts")
    current_id = construction.get("current_attempt_id")
    if not isinstance(attempts, list) or not current_id:
        return "NONE"
    attempt = next(
        (a for a in attempts if isinstance(a, dict) and a.get("attempt_id") == current_id),
        None,
    )
    if attempt is None:
        return "NONE"
    status = str(attempt.get("status") or "").strip()
    return status if status in CONSTRUCTION_VALUES else "NONE"


def read_state_axes(order: Any) -> OrderStateAxes:
    """order에서 6개 canonical 축을 read-only로 파생한다(아무 것도 쓰지 않음).

    Args:
        order: ``status``/``deleted_at``/``structured_data``를 가진 Order-like 객체.

    Returns:
        OrderStateAxes(main, logistics, hold, as_status, deleted, construction).
    """
    return OrderStateAxes(
        main=read_main_stage(order),
        logistics=read_logistics(order),
        hold=read_hold(order),
        as_status=read_as_status(order),
        deleted=read_deleted(order),
        construction=read_construction(order),
    )


def legacy_status_projection(axes: OrderStateAxes) -> str:
    """canonical 축에서 legacy ``order.status`` projection을 계산한다.

    우선순위 ``DELETED > ON_HOLD > AS_* > logistics > main``(§2.2). 이 함수가 canonical
    mirror이며, audit은 실제 ``order.status``와 이 값을 비교해 projection mismatch를 잡는다.

    Returns:
        projection 문자열(main 정규화 실패 시 빈 문자열).
    """
    if axes.deleted == "DELETED":
        return "DELETED"
    if axes.hold == "HELD":
        return "ON_HOLD"
    if axes.as_status != "NONE":
        return _AS_TO_LEGACY[axes.as_status]
    if axes.logistics != "NONE":
        return axes.logistics
    return axes.main or ""


# --- legacy alias 분류(audit용) ---------------------------------------------
def classify_status_to_axes(status: Any) -> List[Tuple[str, str]]:
    """legacy ``order.status`` 문자열을 canonical (axis, value) 목록으로 분류한다.

    정상이면 정확히 1개. 0개 = 어느 축에도 매핑 안 됨(unmapped/display alias),
    2개 이상 = overlay ambiguity. audit이 이 길이로 safe/ambiguous를 나눈다.

    Args:
        status: order.status 문자열(또는 한글 라벨).

    Returns:
        [(axis, canonical_value), ...] — UTF-8 정렬된 결정적 목록.
    """
    text = str(status or "").strip()
    if not text:
        return []
    matches: List[Tuple[str, str]] = []
    # main 파이프라인(코드 또는 한글 라벨)
    main = normalize_main_stage(text)
    if main in MAIN_PIPELINE_CODES:
        matches.append((AXIS_MAIN, main))
    # overlay legacy alias(코드 또는 한글 라벨→코드 정규화)
    alias_key = text if text in LEGACY_STATUS_ALIAS else STAGE_NAME_TO_CODE.get(text, text)
    axis = LEGACY_STATUS_ALIAS.get(alias_key)
    if axis is not None and axis not in matches:
        matches.append(axis)
    return sorted(set(matches))


def is_legacy_display_alias(status: Any) -> bool:
    """writer 없는 display alias(``HAPPYCALL``/``SHIPMENT``) 여부."""
    return str(status or "").strip() in LEGACY_DISPLAY_ALIAS


# --- registry canonical target read model(production run / quest / drawing) ---
def read_current_production_run(order: Any) -> Optional[Dict[str, Any]]:
    """``production.runs[]``에서 ``current_run_id``가 가리키는 run dict(없으면 None)."""
    sd = _structured(order)
    production = sd.get("production")
    if not isinstance(production, dict):
        return None
    runs = production.get("runs")
    current_id = production.get("current_run_id")
    if not isinstance(runs, list) or not current_id:
        return None
    return next(
        (r for r in runs if isinstance(r, dict) and r.get("run_id") == current_id),
        None,
    )


def read_current_quest(order: Any) -> Optional[Dict[str, Any]]:
    """``quests[]``에서 ``workflow.current_quest_id``가 가리키는 non-terminal quest(없으면 None).

    terminal(SUPERSEDED 등)로 종결된 quest는 current가 아니므로 None을 돌려준다.
    """
    sd = _structured(order)
    quests = sd.get("quests")
    workflow = sd.get("workflow") if isinstance(sd.get("workflow"), dict) else {}
    current_id = workflow.get("current_quest_id")
    if not isinstance(quests, list) or not current_id:
        return None
    quest = next(
        (q for q in quests if isinstance(q, dict) and q.get("quest_id") == current_id),
        None,
    )
    if quest is None:
        return None
    transitions = quest.get("transitions")
    if isinstance(transitions, list) and transitions:
        last = transitions[-1]
        if isinstance(last, dict) and str(last.get("to") or "").upper() == "SUPERSEDED":
            return None
    return quest


def read_drawing_revision_registry(order: Any) -> Dict[str, Any]:
    """drawing revision registry pointer projection(§2.2.1).

    Returns:
        canonical pointer ID들(``current_revision_id`` 등)과 현재 revision dict를 담은 dict.
        drawing 정보가 없으면 모든 pointer가 None.
    """
    sd = _structured(order)
    drawing = sd.get("drawing") if isinstance(sd.get("drawing"), dict) else {}
    revisions = drawing.get("revisions") if isinstance(drawing.get("revisions"), list) else []
    current_id = drawing.get("current_revision_id")
    current = next(
        (r for r in revisions if isinstance(r, dict) and r.get("revision_id") == current_id),
        None,
    )
    return {
        "current_revision_id": current_id,
        "receipt_revision_id": drawing.get("receipt_revision_id"),
        "customer_confirmed_revision_id": drawing.get("customer_confirmed_revision_id"),
        "customer_confirmation_quest_id": drawing.get("customer_confirmation_quest_id"),
        "current_revision_request_id": drawing.get("current_revision_request_id"),
        "current_revision": current,
    }


__all__ = [
    "AXIS_MAIN",
    "AXIS_LOGISTICS",
    "AXIS_HOLD",
    "AXIS_AS",
    "AXIS_DELETE",
    "AXIS_CONSTRUCTION",
    "LOGISTICS_VALUES",
    "HOLD_VALUES",
    "AS_VALUES",
    "DELETE_VALUES",
    "CONSTRUCTION_VALUES",
    "LEGACY_STATUS_ALIAS",
    "LEGACY_DISPLAY_ALIAS",
    "OrderStateAxes",
    "read_state_axes",
    "read_main_stage",
    "read_logistics",
    "read_hold",
    "read_as_status",
    "read_deleted",
    "read_construction",
    "legacy_status_projection",
    "classify_status_to_axes",
    "is_legacy_display_alias",
    "read_current_production_run",
    "read_current_quest",
    "read_drawing_revision_registry",
]
