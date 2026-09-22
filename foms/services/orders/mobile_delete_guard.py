"""모바일 주문 삭제 단계 가드·노출 컨텍스트 (MOBILE-DELETE-01, services 계층).

api(:mod:`foms.api.orders.mobile_delete`)와 web(:mod:`foms.web.orders.dashboard` 상세 렌더)이
**같은 함수**로 판정해 화면이 보여주는 것 == 서버가 허용하는 것을 유지한다.

- free    : RECEIVED · MEASURE · DRAWING — 사유 선택 → 삭제.
- warn    : CONFIRM · PRODUCTION · CONSTRUCTION — 경고 배너 + 사유 필수.
- blocked : CS · COMPLETED — 모바일 삭제 불가(409 ``MOBILE_DELETE_BLOCKED``), PC 에서만.
"""

from __future__ import annotations

from typing import Any

from foms.services.order_timeline_v3 import STATUS_TO_STAGE
from foms.services.orders.order_mutation_policy import user_can

POLICY_ID = "ORDER_SOFT_DELETE"

GUARD_FREE = "free"
GUARD_WARN = "warn"
GUARD_BLOCKED = "blocked"

_STAGE_GUARD: dict[str, str] = {
    "RECEIVED": GUARD_FREE,
    "MEASURE": GUARD_FREE,
    "DRAWING": GUARD_FREE,
    "CONFIRM": GUARD_WARN,
    "PRODUCTION": GUARD_WARN,
    "CONSTRUCTION": GUARD_WARN,
    "CS": GUARD_BLOCKED,
    "COMPLETED": GUARD_BLOCKED,
}

_GUARD_LABEL: dict[str, str] = {
    GUARD_FREE: "",
    GUARD_WARN: "이미 진행 중인 주문입니다. 삭제하면 생산·시공 일정 화면에서 사라져요.",
    GUARD_BLOCKED: "완료·AS 단계 주문은 PC에서만 삭제할 수 있어요.",
}

#: 되돌리기 토스트 유효 시간(초). UI 전용 — 서버는 시간 검사를 하지 않는다(PC 휴지통 복원과 같은 권한).
UNDO_WINDOW_SECONDS = 5


def stage_guard_for_order(order: Any) -> dict[str, str]:
    """주문의 단계 가드를 판정한다.

    ``erp_stage_code`` 를 우선 보고, 없으면 ``status`` 를 8단계 표준 코드로 접는다.
    알 수 없는 코드는 **warn** 으로 보수 처리한다(막지는 않되 사유는 받는다).

    Args:
        order: Order 행(``erp_stage_code``·``status`` 속성).

    Returns:
        ``{"level": free|warn|blocked, "label": 안내문, "stage": 표준 코드}``.
    """
    stage = str(getattr(order, "erp_stage_code", None) or "").strip().upper()
    if not stage:
        stage = STATUS_TO_STAGE.get(str(getattr(order, "status", None) or "").strip().upper(), "")
    stage = STATUS_TO_STAGE.get(stage, stage)
    level = _STAGE_GUARD.get(stage, GUARD_WARN)
    return {"level": level, "label": _GUARD_LABEL[level], "stage": stage}


def build_mobile_delete_context(order: Any, user: Any) -> dict[str, Any]:
    """상세 페이지 렌더용 컨텍스트(권한·가드·버전). 노출 판정 = 서버 게이트와 같은 값."""
    return {
        "can": bool(user_can(POLICY_ID, user)),
        "guard": stage_guard_for_order(order),
        "version": int(getattr(order, "mutation_version", None) or 1),
    }


__all__ = [
    "GUARD_BLOCKED", "GUARD_FREE", "GUARD_WARN", "POLICY_ID", "UNDO_WINDOW_SECONDS",
    "build_mobile_delete_context", "stage_guard_for_order",
]
