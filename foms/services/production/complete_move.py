"""일반 상태 쓰기의 생산 → 시공 문지기 — [제작 완료] 단추와 같은 규칙(사용자 결정 2026-11-21 · 설계서 2026-11-23 §4-3).

단건 상태 쓰기(``foms/api/orders/status.py`` ``update_order_status_response``) · 일괄 상태 쓰기(같은 파일
``bulk_update_order_status_response``) · 칸 고치기(``foms/api/orders/field_update.py``)가 이 함수 하나를 부른다 — 일반 쓰기가
옆문이 되지 않게 한다. 판정 · 글은 :func:`foms.services.production.part_progress.complete_block_body` 한 곳(카드를 쓴 주문은
그 주문 표시 줄로, 안 쓴 주문은 공정 칸 규칙 그대로).

2026-11-23 에 ``foms/services/orders/stage_override.py`` 에서 옮겼다 — 단계 모듈은 import 그래프 아래쪽(``state_axes`` 가
부른다)이라 표시 줄 판정(``part_progress`` → 확정 도면 읽기)을 끌어오면 모듈 순환이 생긴다. 단계 강제 변경
(``apply_stage_override``)은 이 규칙을 타지 않는다 — 막다른 길 비상구다.
"""

from __future__ import annotations

from typing import Any, Iterable, Optional

from foms.services.erp_order_flags import is_erp_order_record
from foms.services.orders.stage_override import is_production_complete_move
from foms.services.production.part_marks_query import attached_order_marks
from foms.services.production.part_progress import complete_block_body


def production_complete_move_block(order: Any, from_stage: Any, to_stage: Any, *,
                                   marks: Optional[Iterable[Any]] = None) -> Optional[dict[str, Any]]:
    """일반 상태 쓰기(단건 · 일괄 · 칸 고치기)의 생산 → 시공이 막히면 거절 본문, 아니면 None.

    ERP 주문만 본다(비 ERP 는 단계 축이 없다). 관리자 뚫기(``admin_override``)는 호출부가 게이트 코드 ``STEPS_INCOMPLETE``
    로 기록한다.

    Args:
        order: 대상 주문(세션에 붙은 것).
        from_stage: 지금 단계.
        to_stage: 쓰려는 단계.
        marks: 그 주문 표시 줄. 안 주면 생산 → 시공 이동일 때만 그 주문 줄을 한 번 읽는다(그 밖 이동은 쿼리 0). 일괄 쓰기는
            :func:`foms.services.production.part_marks_query.marks_by_order` 로 미리 한 번 읽어 넘긴다(N+1 없음).

    Returns:
        거절 본문(409 로 보낼 것) 또는 None.
    """
    if not is_erp_order_record(order) or not is_production_complete_move(from_stage, to_stage):
        return None
    marks = attached_order_marks(order) if marks is None else marks
    return complete_block_body(getattr(order, "structured_data", None), marks)
