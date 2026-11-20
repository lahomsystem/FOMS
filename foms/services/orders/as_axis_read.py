"""AS 축 읽기 — ``as_lifecycle`` 현재 건이 먼저, 없으면 옛 ``order.status`` 글.

잎 모듈이다(다른 ``foms`` 모듈을 가져오지 않는다). ``state_axes`` 가 ``stage_override`` 를 가져오므로,
강제 단계 변경(``stage_override``)이 "열린 AS 인가"를 물으려면 이 읽기가 둘의 바깥에 있어야 한다.
``state_axes`` 는 여기 값을 그대로 다시 내보낸다(읽는 쪽 이름은 그대로다).
"""
from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

AS_VALUES: Tuple[str, ...] = ("NONE", "RECEIVED", "IN_PROGRESS", "COMPLETED")
#: 열린 AS — 접수 · 처리 중. 완료는 닫힌 AS 다.
AS_OPEN_VALUES: Tuple[str, ...] = ("RECEIVED", "IN_PROGRESS")
#: 옛 ``order.status`` 글 → AS 축 값(건 기록이 없는 옛 AS 주문은 이 글이 유일한 근거다).
LEGACY_AS_STATUS_TO_AXIS: Dict[str, str] = {
    "AS_RECEIVED": "RECEIVED",
    "AS": "IN_PROGRESS",
    "AS_COMPLETED": "COMPLETED",
}


def current_cycle_status(as_lifecycle: Dict[str, Any]) -> Optional[str]:
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
    sd = getattr(order, "structured_data", None)
    lifecycle = sd.get("as_lifecycle") if isinstance(sd, dict) else None
    if isinstance(lifecycle, dict):
        status = current_cycle_status(lifecycle)
        if status is not None:
            return status
    return LEGACY_AS_STATUS_TO_AXIS.get(str(getattr(order, "status", None) or "").strip(), "NONE")


def open_as_status_text(order: Any) -> str:
    """열린 AS(접수 · 처리 중)가 주문 상태 글에 남긴 AS 표시(``AS_RECEIVED`` · ``AS`` …). 아니면 빈 글.

    본 흐름 목표 상태 쓰기가 덮으면 안 되는 값이다(STATE-AS-01 — 설계서 2026-11-20-multi-item-split-schedule §4.3).
    상태 글이 AS 가 아닌 주문(지킬 AS 표시가 없다)과 닫힌 AS(완료)는 빈 글이라 지금처럼 덮인다.
    """
    status = str(getattr(order, "status", None) or "").strip()
    if status not in LEGACY_AS_STATUS_TO_AXIS:
        return ""
    return status if read_as_status(order) in AS_OPEN_VALUES else ""
