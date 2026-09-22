"""지방/자가실측 체크리스트 불리언 1개를 쓰는 **공용 writer** (DATA-MEASUREMENT-01).

왜 따로 뽑았나
--------------
같은 값(`measurement_completed` 등)을 켜는 표면이 둘이다.

1. 체크박스 — ``POST /api/update_regional_status`` (:mod:`foms.api.orders.regional`)
2. '도면 전달'/'실측 완료' 버튼의 MEASURE→DRAWING 전이 (:mod:`foms.api.quest`)

두 경로가 컬럼만 같고 **원장 path 나 OrderEvent 타입이 다르면 감사 화면에서 한 축으로
읽히지 않는다**. 그래서 세 동작(컬럼 write · event parity · 원장 기록)을 여기 한 벌만 둔다.

이 함수는 세션을 **커밋하지 않는다.** 호출자가 자기 tx 안에서 부르고 커밋한다 —
체크박스 경로는 ``execute_order_mutation`` 의 ``FOR UPDATE`` 락 안에서, 전이 경로는
``transition_order`` 가 이미 잡아 둔 같은 tx 안에서 부른다.

축 주의: 이 모듈은 **평면 불리언 컬럼**만 만진다. ``workflow.stage``(본공정 단계)도,
``drawing_status``(도면 파일 전달)도 건드리지 않는다.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from foms.services.orders.order_field_change_writer import record_field_changes
from models import OrderEvent

__all__ = [
    "REGIONAL_CHECKLIST_EVENT",
    "mark_checklist_flag",
]


#: 체크리스트 write 의 legacy OrderEvent 타입. 두 표면이 같은 값을 써야 감사가 한 축이다.
REGIONAL_CHECKLIST_EVENT = "REGIONAL_CHECKLIST_UPDATED"


def mark_checklist_flag(
    session: Session,
    order: Any,
    field: str,
    value: bool,
    *,
    actor_user_id: Any,
    change_set_id: str,
) -> bool:
    """체크리스트 불리언 1개를 설정하고 event·원장을 같은 tx 에 남긴다.

    원장 비교 기준은 ``setattr`` **전에** 뜬다. 컬럼이 NULL 인 낡은 행이 있어 불리언으로
    정규화한다 — NULL 은 '체크 안 됨'이지 별개 값이 아니다(NULL→False 저장이 변경으로
    남으면 진짜 토글이 묻힌다).

    Args:
        session: 호출자 소유 세션(커밋하지 않는다).
        order: 대상 ``Order``. 지방/자가실측 판정은 **호출자 책임**이다.
        field: 체크리스트 컬럼명(예: ``measurement_completed``).
        value: 설정할 불리언.
        actor_user_id: 행위자 user id(event·원장 author).
        change_set_id: 감사 헤더(``security_logs.detail['change_set']``)와 원장을 잇는 열쇠.
            호출자가 같은 값을 ``log_access`` 에도 넣어야 감사 화면이 조인한다.

    Returns:
        값이 실제로 바뀌었으면 True, 같은 값 재저장이면 False(원장 행을 만들지 않았다).
    """
    before_flag = bool(getattr(order, field, None))
    setattr(order, field, value)
    session.add(OrderEvent(
        order_id=order.id,
        event_type=REGIONAL_CHECKLIST_EVENT,
        payload={"field": field, "value": value},
        created_by_user_id=actor_user_id,
    ))
    if before_flag == value:
        # 무변경 저장(같은 값 재클릭·중복 요청)은 행을 만들지 않는다.
        return False
    record_field_changes(
        session,
        # path 는 점 없는 평면 컬럼명 그대로(ORDER-FLAG-01 확정 규약).
        [{"path": field, "before": before_flag, "after": value, "op": "set"}],
        order_id=order.id,
        actor_user_id=actor_user_id,
        change_set_id=change_set_id,
    )
    return True
