"""퀘스트 승인 CTA 문구 SSOT — 단계별 버튼 이름·확인 문장·단계 이동 여부.

승인 버튼을 그리는 화면이 여럿(모바일 주문 상세·큐 카드)이라 템플릿마다 조건을 두면
문구가 약속하는 결과와 실제 전이 규칙이 갈라진다. 다음 stage 판정은 전이 서비스의
:func:`stage_advance_target` 에 위임한다.
"""

from __future__ import annotations

from typing import Any

from foms.services.orders.erp_policy_constants import STAGE_LABELS
from foms.services.orders.quest_transition_service import (
    is_command_required_stage,
    stage_advance_target,
)

__all__ = ["build_approve_cta"]


# stage 코드 → 승인 버튼 문구. 한 이름("퀘스트 승인")으로 묶으면 눌렀을 때 무엇이 되는지
# 화면이 말해 주지 못한다. DRAWING/CONFIRM 은 전용 command 단계라 여기에 없다(버튼 미노출).
# COMPLETED 도 없다 — 다음 단계가 없어 승인이 아무것도 바꾸지 않는다.
_QUEST_APPROVE_LABELS: dict[str, str] = {
    "RECEIVED": "접수 확인",
    "MEASURE": "실측 완료",
    "PRODUCTION": "생산 확인",
    "CONSTRUCTION": "시공 확인",
    "CS": "CS 확인",
    "AS": "AS 확인",
}

# 단계를 실제로 옮기는 stage 의 확인 문구(첫 줄). 나머지는 아래에서 "기록만" 문구로 만든다.
_QUEST_APPROVE_CONFIRM_HEADS: dict[str, str] = {
    "RECEIVED": "주문 접수 확인을 마치고 실측 단계로 넘길까요?",
    "MEASURE": "실측을 완료하고 도면 단계로 넘길까요?",
}


def _order_confirm_context(order: Any) -> str:
    """확인 대화상자 끝에 붙일 '누구의 어느 주문인지' 한 줄. 없으면 빈 문자열."""
    parts: list[str] = []
    name = str(getattr(order, "customer_name", "") or "").strip()
    if name:
        parts.append(name)
    order_id = getattr(order, "id", None)
    if order_id:
        parts.append(f"#{order_id}")
    return " / ".join(parts)


def build_approve_cta(stage_code: str | None, order: Any) -> dict[str, Any]:
    """승인 버튼 문구·확인 문장·단계 이동 여부를 한 곳에서 만든다.

    문구가 약속하는 결과와 실제 전이 규칙이 갈라지지 않도록 다음 stage 판정은
    :func:`stage_advance_target` (전이 서비스의 ``_STAGE_ADVANCE``)에 위임한다.

    :param stage_code: 영문 stage 코드.
    :param order: 확인 문구에 넣을 고객명/주문번호 출처 Order.
    :returns: ``approve_label`` (없으면 None = 버튼 미노출), ``approve_confirm``,
        ``advances_stage``, ``next_stage_label``, ``command_required``.
    """
    command_required = is_command_required_stage(stage_code)
    label = None if command_required else _QUEST_APPROVE_LABELS.get(stage_code or "")
    if not label:
        return {
            "approve_label": None,
            "approve_confirm": "",
            "advances_stage": False,
            "next_stage_label": "",
            "command_required": command_required,
        }

    next_stage_code = stage_advance_target(stage_code)
    next_stage_label = STAGE_LABELS.get(next_stage_code, next_stage_code or "")
    stage_label = STAGE_LABELS.get(stage_code or "", stage_code or "")

    if next_stage_code:
        head = _QUEST_APPROVE_CONFIRM_HEADS.get(
            stage_code or "", f"{stage_label} 확인을 마치고 {next_stage_label} 단계로 넘길까요?"
        )
    else:
        # 단계를 옮기지 않는 stage(생산·시공·CS·AS): 승인 기록만 남는다는 사실을 그대로 말한다.
        head = f"{stage_label} 확인을 기록할까요?\n단계는 '{stage_label}' 그대로 유지됩니다."

    context_line = _order_confirm_context(order)
    confirm = f"{head}\n\n{context_line}" if context_line else head
    return {
        "approve_label": label,
        "approve_confirm": confirm,
        "advances_stage": bool(next_stage_code),
        "next_stage_label": next_stage_label,
        "command_required": command_required,
    }
