"""도면 수령 확정(DRAWING→CONFIRM) 전이 command 등록과 조립 헬퍼.

도면 수령 확정은 2026-09-20 까지 ``workflow.stage`` 와 ``order.status`` 를 라우트가 직접
써서 버전·영수증·전이 이벤트가 남지 않았다. 여기서 STATE-CORE 엔진 command 를 registry 에
additive 로 등록해(엔진 파일은 import 만 — 무편집) 라우트가
:func:`~foms.services.orders.order_transition_service.transition_order` 한 경로만 타게 한다.

``erp_orders_draftsman.py`` 가 500줄 래칫에 가까워 등록·해시 헬퍼를 이 모듈로 분리했다.
"""

import hashlib
import json
from typing import Any

from foms.services.orders.order_transition_service import (
    COMMAND_REGISTRY,
    StageConflictError,
    TransitionCommand,
    transition_order,
)
from foms.services.orders.state_axes import AXIS_MAIN, read_main_stage

#: 도면 수령 확정 command id(registry key).
DRAWING_RECEIPT_CONFIRM = "DRAWING_RECEIPT_CONFIRM"

#: REV-00 receipt idempotency scope 식별자(POLICY_REGISTRY 와 무관 — STATE-PROD 관례).
POLICY_DRAWING_RECEIPT_CONFIRM = "STATE_DRAWING_RECEIPT_CONFIRM"

COMMAND_REGISTRY.setdefault(
    DRAWING_RECEIPT_CONFIRM,
    TransitionCommand(
        command_id=DRAWING_RECEIPT_CONFIRM,
        policy_id=POLICY_DRAWING_RECEIPT_CONFIRM,
        axis=AXIS_MAIN,
        from_values=("DRAWING",),
        to_values=("CONFIRM",),
        event_type="DRAWING_RECEIPT_CONFIRMED",
        effect_type="STAGE_NOTIFICATION",
    ),
)


def receipt_scope_hash(order_id: int) -> str:
    """도면 수령 확정 전이 scope 의 sha256 hex(영수증 저장용)."""
    return hashlib.sha256(
        f"{DRAWING_RECEIPT_CONFIRM}:{order_id}".encode("utf-8")
    ).hexdigest()


def receipt_request_hash(body: dict[str, Any]) -> str:
    """요청 payload 의 sha256 hex(같은 key·다른 payload 감지용)."""
    canonical = json.dumps(body or {}, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def advance_receipt_stage(db: Any, order: Any, *, actor_user_id: int,
                          body: dict[str, Any]) -> bool:
    """도면 단계면 CONFIRM 으로 전이한다. 옮겼으면 True, 건너뛰었으면 False.

    재전달된 도면이 CONFIRM·PRODUCTION 등에서 확정되는 경로에서는 전이를 건너뛴다 —
    단계를 되돌리는 조용한 역행을 만들지 않기 위해서다. 전이 예외(TransitionError·
    RevisionError)는 잡지 않는다: 호출자가 rollback 하고 409 로 매핑한다.
    """
    if read_main_stage(order) != "DRAWING":
        return False
    transition_order(
        db,
        command_id=DRAWING_RECEIPT_CONFIRM,
        order_id=int(order.id),
        actor_user_id=actor_user_id,
        expected_from="DRAWING",
        target_value="CONFIRM",
        scope_hash=receipt_scope_hash(int(order.id)),
        request_hash=receipt_request_hash(body),
        reason="도면 수령 확인",
        source_screen="erp_drawing_dashboard",
    )
    return True


def receipt_transition_error(exc: Exception) -> tuple[str, int]:
    """전이 예외를 (오류 코드, HTTP 상태)로 매핑한다(단계 불일치는 INVALID_STAGE)."""
    code = ("INVALID_STAGE" if isinstance(exc, StageConflictError)
            else getattr(exc, "error_code", "TRANSITION_ERROR"))
    return code, int(getattr(exc, "status_code", 409))


__all__ = [
    "DRAWING_RECEIPT_CONFIRM",
    "POLICY_DRAWING_RECEIPT_CONFIRM",
    "advance_receipt_stage",
    "receipt_transition_error",
    "receipt_scope_hash",
    "receipt_request_hash",
]
