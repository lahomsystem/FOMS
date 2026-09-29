"""도면 수령 확정(DRAWING→CONFIRM) 전이 command 등록과 조립 헬퍼.

도면 수령 확정은 2026-09-20 까지 ``workflow.stage`` 와 ``order.status`` 를 라우트가 직접
써서 버전·영수증·전이 이벤트가 남지 않았다. 여기서 STATE-CORE 엔진 command 를 registry 에
additive 로 등록해(엔진 파일은 import 만 — 무편집) 라우트가
:func:`~foms.services.orders.order_transition_service.transition_order` 한 경로만 타게 한다.

``erp_orders_draftsman.py`` 가 500줄 래칫에 가까워 등록·해시 헬퍼를 이 모듈로 분리했다.
확정 때의 구조화 쓰기(:func:`write_receipt_structured`)도 같은 이유로 여기 있다(2a-1②).
"""

import copy
import hashlib
import json
from typing import Any

from sqlalchemy.orm.attributes import flag_modified

from foms.services.erp_sync_columns import sync_erp_flat_columns

from foms.services.orders.order_transition_service import (
    COMMAND_REGISTRY,
    StageConflictError,
    TransitionCommand,
    transition_order,
)
from foms.services.orders.drawing_revision_source import attach_customer_ok
from foms.services.orders.revision import execute_single_order_write
from foms.services.orders.state_axes import AXIS_MAIN, read_main_stage

#: 도면 수령 확정 command id(registry key).
DRAWING_RECEIPT_CONFIRM = "DRAWING_RECEIPT_CONFIRM"

#: REV-00 receipt idempotency scope 식별자(POLICY_REGISTRY 와 무관 — STATE-PROD 관례).
POLICY_DRAWING_RECEIPT_CONFIRM = "STATE_DRAWING_RECEIPT_CONFIRM"

#: 단계를 옮기지 않는 확정(단계 유지)의 receipt scope 식별자. 전이 엔진을 타지 않는다.
POLICY_DRAWING_RECEIPT_KEEP_STAGE = "DRAWING_RECEIPT_CONFIRM_KEEP_STAGE"

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


def write_receipt_structured(db: Any, order: Any, s_data: dict[str, Any], *,
                             actor_user_id: int, stage_moving: bool,
                             body: dict[str, Any] | None = None) -> None:
    """수령 확정의 도면 축 쓰기(``structured_data`` 재대입 + flat 컬럼 동기화).

    * 단계가 옮겨진 경우(``stage_moving``): :func:`advance_receipt_stage` 의 전이가 방금
      ``execute_order_mutation`` 으로 행을 잠그고 버전을 올렸다. 같은 트랜잭션에서 곧바로
      반영한다 — 버전을 한 번 더 올리지 않는다(선례 ``foms/api/cs/complete.py``).
    * 단계 유지: 전이가 없으므로 REV-00 엔진 콜백 안에서 쓰고 버전을 1 올린다. 호출자는
      주문을 :func:`~foms.services.orders.revision.lock_order_row` 로 먼저 잠가 읽는다.

    커밋은 호출자 몫이다.
    """
    final_sd = copy.deepcopy(s_data)
    attach_customer_ok(final_sd, body)  # 고객 OK 기록(선택, 설계서 2026-09-29 §4.2) — 마지막 CONFIRM_RECEIPT 에

    def _apply(target: Any) -> None:
        target.structured_data = final_sd
        flag_modified(target, "structured_data")
        sync_erp_flat_columns(target, final_sd)

    if stage_moving:
        _apply(order)
        return
    execute_single_order_write(
        db, order_id=int(order.id), actor_user_id=actor_user_id,
        policy_id=POLICY_DRAWING_RECEIPT_KEEP_STAGE, payload=body or {},
        write=_apply,
    )


def receipt_transition_error(exc: Exception) -> tuple[str, int]:
    """전이 예외를 (오류 코드, HTTP 상태)로 매핑한다(단계 불일치는 INVALID_STAGE)."""
    code = ("INVALID_STAGE" if isinstance(exc, StageConflictError)
            else getattr(exc, "error_code", "TRANSITION_ERROR"))
    return code, int(getattr(exc, "status_code", 409))


__all__ = [
    "DRAWING_RECEIPT_CONFIRM",
    "POLICY_DRAWING_RECEIPT_CONFIRM",
    "POLICY_DRAWING_RECEIPT_KEEP_STAGE",
    "advance_receipt_stage",
    "receipt_transition_error",
    "receipt_scope_hash",
    "receipt_request_hash",
    "write_receipt_structured",
]
