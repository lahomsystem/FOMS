"""도면 수령 확정 권한 판정 한 곳(순수 판정, 쓰기 없음).

라우트 파일이 500줄 래칫을 넘지 않도록 떼어 냈다. 판정 순서와 결과는 옮기기 전과 같다 —
도메인 권한 → SALES 배정 행(id 대조) → 배정이 하나도 없을 때만 담당자 이름 대조.
services 계층만 읽으므로 라우트 파일이 지고 있던 계층 의존은 늘지 않는다.
"""
from typing import Any

from foms.services.erp_display import manager_display_name
from foms.services.erp_policy import can_modify_domain, get_assignee_ids
from foms.services.orders.assignment import active_assignee_ids


def _manager_names(order: Any, s_data: Any) -> set:
    """이 주문의 영업 담당자로 볼 수 있는 이름 집합(소문자)."""
    names = set()
    parties = (s_data.get('parties') or {}) if isinstance(s_data, dict) else {}
    manager_name_sd = manager_display_name(parties)
    if manager_name_sd:
        names.add(manager_name_sd.lower())

    manager_name_col = (getattr(order, 'manager_name', '') or '').strip()
    if manager_name_col:
        names.add(manager_name_col.lower())

    workflow = (s_data.get('workflow') or {}) if isinstance(s_data, dict) else {}
    current_quest = (workflow.get('current_quest') or {})
    owner_person = (current_quest.get('owner_person') or '').strip()
    if owner_person:
        names.add(owner_person.lower())
    return names


def can_confirm_drawing_receipt(
    db: Any, order: Any, user: Any, s_data: Any, *,
    emergency_override: Any = False, override_reason: Any = '',
) -> bool:
    """이 사용자가 이 주문의 도면 수령 확정을 할 수 있는지 판정한다.

    Args:
        db: 활성 DB 세션(배정 행 조회용).
        order: 대상 주문.
        user: 요청 사용자.
        s_data: 주문 structured_data(읽기만 한다).
        emergency_override: 권한 소유 축 override 원값(MANAGER 의 도메인 넘기).
        override_reason: 그 사유.

    Returns:
        확정할 수 있으면 True.
    """
    if can_modify_domain(user, order, 'SALES_DOMAIN', emergency_override, override_reason):
        return True

    # 주문 생성 시 owner 는 OrderAssignment(SALES) 행에만 남는다(ORDER-CREATE-01)
    # — 이름 대조보다 id 대조가 먼저다(F9: owner STAFF 가 403 받던 것).
    if user.id in active_assignee_ids(db, order.id, 'SALES'):
        return True

    # 배정 행이 하나도 없을 때만 이름 대조로 물러선다.
    if get_assignee_ids(order, 'SALES_DOMAIN'):
        return False
    names = _manager_names(order, s_data)
    user_name = (getattr(user, 'name', '') or '').strip().lower()
    user_username = (getattr(user, 'username', '') or '').strip().lower()
    return user_name in names or user_username in names


__all__ = ["can_confirm_drawing_receipt"]
