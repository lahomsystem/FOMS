"""워크플로 단계 강제 변경(역행·건너뛰기) SSOT.

structured PUT 가드·status API 잠금·override API가 동일 rank/mode를 쓴다.
단계 변경은 status/workflow.stage 만 건드리고 도면·이관 이력은 보존한다.

정책: to_stage 는 메인 파이프라인만(AS/DELETED 목표 불가).
from 이 AS/레거시면 → 메인으로의 jump 는 운영 복구용으로 허용한다.
"""

from __future__ import annotations

import datetime
from typing import Any, Optional

from sqlalchemy.orm.attributes import flag_modified

from foms.services.erp_order_flags import is_erp_order_record
from foms.services.erp_sync_columns import sync_erp_flat_columns
from foms.services.orders.erp_policy_constants import STAGE_LABELS, STAGE_NAME_TO_CODE
from models import Order, OrderEvent

# 메인 파이프라인만 (AS_*/DELETED/레거시 제외). structured PUT 가드와 동일.
STAGE_FORWARD_RANK: dict[str, int] = {
    "RECEIVED": 0,
    "주문접수": 0,
    "MEASURE": 1,
    "실측": 1,
    "DRAWING": 2,
    "도면": 2,
    "CONFIRM": 3,
    "고객컨펌": 3,
    "PRODUCTION": 4,
    "생산": 4,
    "CONSTRUCTION": 5,
    "시공": 5,
    "CS": 6,
    "COMPLETED": 7,
    "완료": 7,
}

MAIN_PIPELINE_CODES: tuple[str, ...] = (
    "RECEIVED",
    "MEASURE",
    "DRAWING",
    "CONFIRM",
    "PRODUCTION",
    "CONSTRUCTION",
    "CS",
    "COMPLETED",
)

OVERRIDE_ALLOWED_ROLES: frozenset[str] = frozenset({"ADMIN", "MANAGER"})
REASON_MIN_LEN = 8
OVERRIDE_BLOCK_MESSAGE = (
    "단계 역행/건너뛰기는 「단계 강제 변경」에서 사유·확인 후 진행하세요."
)


def stage_forward_rank(raw: Any) -> int:
    """workflow.stage / status 전방 순위. 메인 파이프라인 외·미지 = -1."""
    text = str(raw or "").strip()
    if not text:
        return -1
    if text in STAGE_FORWARD_RANK:
        return STAGE_FORWARD_RANK[text]
    mapped = STAGE_NAME_TO_CODE.get(text)
    if mapped and mapped in STAGE_FORWARD_RANK:
        return STAGE_FORWARD_RANK[mapped]
    if text in STAGE_LABELS and text in STAGE_FORWARD_RANK:
        return STAGE_FORWARD_RANK[text]
    return -1


def normalize_main_stage(raw: Any) -> Optional[str]:
    """메인 파이프라인 코드로 정규화. 불가하면 None."""
    text = str(raw or "").strip()
    if not text:
        return None
    if text in MAIN_PIPELINE_CODES:
        return text
    mapped = STAGE_NAME_TO_CODE.get(text)
    if mapped in MAIN_PIPELINE_CODES:
        return mapped
    if text in STAGE_FORWARD_RANK:
        # 한글 라벨 키 → 코드
        for code in MAIN_PIPELINE_CODES:
            if STAGE_FORWARD_RANK.get(code) == STAGE_FORWARD_RANK[text]:
                return code
    return None


def classify_stage_move(from_stage: Any, to_stage: Any) -> str:
    """이동 모드: same | advance | regress | skip | jump."""
    from_code = normalize_main_stage(from_stage)
    to_code = normalize_main_stage(to_stage)
    if from_code and to_code and from_code == to_code:
        return "same"
    from_rank = stage_forward_rank(from_stage if from_code is None else from_code)
    to_rank = stage_forward_rank(to_stage if to_code is None else to_code)
    if from_rank < 0 or to_rank < 0:
        return "jump"
    if to_rank < from_rank:
        return "regress"
    if to_rank == from_rank + 1:
        return "advance"
    if to_rank > from_rank + 1:
        return "skip"
    return "same"


def requires_privileged_override(from_stage: Any, to_stage: Any) -> bool:
    """ERP 메인 파이프라인끼리 역행·비인접 전진이면 True.

    한쪽이라도 메인 파이프라인 밖(AS_*/레거시)이면 False — 기존 status API 유지.
    """
    from_code = normalize_main_stage(from_stage)
    to_code = normalize_main_stage(to_stage)
    if from_code is None or to_code is None:
        return False
    mode = classify_stage_move(from_code, to_code)
    return mode in ("regress", "skip", "jump")


def current_stage_for_order(order: Order) -> str:
    """ERP면 workflow.stage 우선, 없으면 order.status."""
    status = str(getattr(order, "status", None) or "").strip()
    if not is_erp_order_record(order):
        return status
    sd = getattr(order, "structured_data", None)
    if isinstance(sd, dict):
        wf = sd.get("workflow")
        if isinstance(wf, dict):
            stage = str(wf.get("stage") or "").strip()
            if stage:
                return stage
    return status


def apply_stage_override(
    *,
    order: Order,
    to_stage: str,
    reason: str,
    user_id: Any,
    db: Any,
) -> dict[str, Any]:
    """status + workflow.stage 만 변경하고 STAGE_OVERRIDE 이벤트를 남긴다.

    퀘스트/_handle_stage_transition 부수효과는 호출하지 않는다.
    drawing_transfer_history 등 운영 JSON은 건드리지 않는다.

    :returns: {from, to, mode, reason}
    :raises ValueError: 검증 실패(메시지 한글)
    """
    to_code = normalize_main_stage(to_stage)
    if to_code is None or to_code not in MAIN_PIPELINE_CODES:
        raise ValueError("메인 파이프라인 단계만 강제 변경할 수 있습니다. (AS/삭제는 기존 경로 사용)")

    reason_clean = str(reason or "").strip()
    if len(reason_clean) < REASON_MIN_LEN:
        raise ValueError(f"사유는 {REASON_MIN_LEN}자 이상 입력하세요.")

    from_raw = current_stage_for_order(order)
    from_code = normalize_main_stage(from_raw) or str(from_raw or "").strip()
    mode = classify_stage_move(from_code, to_code)
    if mode == "same":
        raise ValueError("현재와 동일한 단계로는 변경할 수 없습니다.")

    order.status = to_code

    if is_erp_order_record(order):
        sd = getattr(order, "structured_data", None)
        if not isinstance(sd, dict):
            sd = {}
        else:
            # 셸 복사 — 중첩 리스트(이력)는 같은 참조 유지(리셋 금지)
            sd = dict(sd)
        wf_raw = sd.get("workflow")
        workflow = dict(wf_raw) if isinstance(wf_raw, dict) else {}
        workflow["stage"] = to_code
        workflow["stage_updated_at"] = datetime.datetime.now().isoformat()
        sd["workflow"] = workflow
        order.structured_data = sd
        flag_modified(order, "structured_data")
        sync_erp_flat_columns(order, sd)

    payload = {
        "from": from_code,
        "to": to_code,
        "mode": mode,
        "reason": reason_clean,
        "manual": True,
    }
    db.add(
        OrderEvent(
            order_id=order.id,
            event_type="STAGE_OVERRIDE",
            payload=payload,
            created_by_user_id=user_id,
        )
    )
    return payload


__all__ = [
    "MAIN_PIPELINE_CODES",
    "OVERRIDE_ALLOWED_ROLES",
    "OVERRIDE_BLOCK_MESSAGE",
    "REASON_MIN_LEN",
    "STAGE_FORWARD_RANK",
    "apply_stage_override",
    "classify_stage_move",
    "current_stage_for_order",
    "normalize_main_stage",
    "requires_privileged_override",
    "stage_forward_rank",
]
