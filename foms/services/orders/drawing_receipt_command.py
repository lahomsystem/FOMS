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
from datetime import datetime
from typing import Any

from sqlalchemy.orm.attributes import flag_modified

from foms.services.datetime_kst import now_utc_naive
from foms.services.drawing_confirm_cleanup import finalize_drawing_files_on_confirm
from foms.services.erp_display import _ensure_dict
from foms.services.erp_sync_columns import sync_erp_flat_columns
from foms.services.orders.drawing_confirm_partial import apply_partial_confirm, cancel_event_payload

from foms.services.orders.order_transition_service import (
    COMMAND_REGISTRY,
    StageConflictError,
    TransitionCommand,
    transition_order,
)
from foms.services.orders.drawing_revision_source import attach_customer_ok
from foms.services.orders.revision import execute_single_order_write
from foms.services.orders.state_axes import AXIS_MAIN, read_main_stage
from models import OrderEvent, SecurityLog

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


def record_drawing_receipt(db: Any, order: Any, *, actor_user_id: int, actor_name: str, old_drawing_status: Any,
                           old_stage: Any, stage_moved: bool, body: dict[str, Any] | None,
                           partial_plan: Any = None, emergency_override: bool = False,
                           override_reason: str | None = None,
                           source_screen: str = "erp_drawing_dashboard") -> str:
    """도면 수령 확정의 도면 축 기록 — 직원 라우트와 협력사 라우트가 같은 한 경로를 쓴다.

    :func:`advance_receipt_stage` 로 단계를 옮긴(또는 건너뛴) **뒤에** 부른다. 도면 상태 CONFIRMED ·
    워크플로 이력 · CONFIRM_RECEIPT 전달 이력 · 최종 도면 확정 · 구조화 쓰기 · 이벤트 · 감사 줄을 남긴다.
    커밋은 호출자 몫이다. 협력사 확인(사용자 2026-10-28: FOMS 와 같은 2단계)은 ``actor_name`` 에
    "이름 (협력사)", ``source_screen`` 에 협력사 화면을 넣는다.

    :returns: 수령 확정 뒤의 단계 코드.
    """
    order_id = int(order.id)
    next_stage = read_main_stage(order) or old_stage or 'CONFIRM'

    # 전이가 structured_data 를 새로 썼으므로 도면 축 쓰기는 최신 dict 에서 이어 간다.
    s_data = copy.deepcopy(_ensure_dict(order.structured_data))
    s_data['drawing_status'] = 'CONFIRMED'
    s_data['drawing_confirmed_at'] = datetime.now().isoformat()
    s_data['drawing_confirmed_by'] = actor_name

    # 단계 축 타임스탬프(workflow.stage_updated_at)는 전이 엔진만 쓰고 라우트는 읽기만
    # 한다. 이력 행 시각은 이번 요청 시각이다 — 단계가 실제로 옮겨 간 경우에만 전이가
    # 방금 넣은 값을 써서 두 기록이 같은 순간을 가리킨다(drift 경로의 옛 시각 금지).
    request_at = now_utc_naive().isoformat()
    wf: dict = s_data.get('workflow') or {}
    wf['stage_updated_by'] = actor_name
    history_at = (wf.get('stage_updated_at') or request_at) if stage_moved else request_at

    hist: list = wf.get('history') or []
    hist.append({
        'stage': next_stage,
        'updated_at': history_at,
        'updated_by': wf['stage_updated_by'],
        'note': '도면 수령 확인 및 단계 이동' if stage_moved else '도면 수령 확인(단계 유지)'
    })
    wf['history'] = hist
    s_data['workflow'] = wf

    partial_summary = None
    if partial_plan is not None:
        partial_summary = apply_partial_confirm(
            s_data, partial_plan, actor_user_id=actor_user_id, at_iso=request_at)

    now_str = now_utc_naive().strftime('%Y-%m-%d %H:%M:%S')
    draw_history = list(s_data.get('drawing_transfer_history') or [])
    draw_history.append({
        'action': 'CONFIRM_RECEIPT',
        'at': now_str,
        'by_user_id': actor_user_id,
        'by_user_name': actor_name,
        'note': '도면 수령 확인',
        'files': list(s_data.get('drawing_current_files') or []),
        'files_count': len(s_data.get('drawing_current_files') or []),
    })

    final_files, _deleted_count = finalize_drawing_files_on_confirm(db, order_id, s_data)
    if partial_summary is not None:
        draw_history[-1].update(partial_summary)
    draw_history[-1]['files'] = final_files
    draw_history[-1]['files_count'] = len(final_files)
    s_data['drawing_transfer_history'] = draw_history

    # 단계 유지면 REV-00 콜백 안에서 쓰고 버전 +1, 단계 이동이면 전이 직후 같은 tx(2a-1②).
    write_receipt_structured(db, order, s_data, actor_user_id=actor_user_id,
                             stage_moving=stage_moved, body=body)

    event_payload = {
        'domain': 'SALES_DOMAIN',
        'action': 'DRAWING_STATUS_CHANGED',
        'target': 'drawing_status',
        'before': old_drawing_status,
        'after': 'CONFIRMED',
        'change_method': 'API',
        'source_screen': source_screen,
        'reason': '도면 수령 확인',
        'is_override': emergency_override,
        'override_reason': override_reason if emergency_override else None,
    }
    drawing_confirm_event = OrderEvent(
        order_id=order_id,
        event_type='DRAWING_STATUS_CHANGED',
        payload=event_payload,
        created_by_user_id=actor_user_id
    )
    db.add(drawing_confirm_event)
    if partial_summary is not None and partial_summary['cancelled_item_uids']:
        db.add(OrderEvent(order_id=order_id, event_type='ITEM_CANCELLED_AT_CONFIRM',
                          payload=cancel_event_payload(partial_plan, partial_summary),
                          created_by_user_id=actor_user_id))

    if stage_moved:
        security_note = f"주문 #{order_id} 도면 확정 및 단계 이동 ({old_stage} -> {next_stage})"
    else:
        security_note = (
            f"주문 #{order_id} 도면 확정(단계 유지 {next_stage}) — 전달된 도면이 "
            f"도면 단계 밖에서 확정되어 단계를 되돌리지 않았다."
        )
    db.add(SecurityLog(user_id=actor_user_id, message=security_note))
    return next_stage


__all__ = [
    "DRAWING_RECEIPT_CONFIRM",
    "POLICY_DRAWING_RECEIPT_CONFIRM",
    "POLICY_DRAWING_RECEIPT_KEEP_STAGE",
    "advance_receipt_stage",
    "receipt_transition_error",
    "record_drawing_receipt",
    "receipt_scope_hash",
    "receipt_request_hash",
    "write_receipt_structured",
]
