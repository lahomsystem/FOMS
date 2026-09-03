"""라홈시스템(2공장)·지방주문 플래그 변경 권한 (ORDER-FLAG-01).

두 값은 업무 축을 가른다 — ``structured_data['flags']['factory2']`` 는 견적서 공급자와
입금 계좌를, ``Order.is_regional`` 은 지방 대시보드·지도·체크리스트의 모집단을 정한다.
그래서 접수를 맡는 CS(라홈팀/하우드팀)와 관리자만 켜고 끈다.

**거부(403)가 아니라 무시(기존값 유지)** 로 강제한다. 전체 저장 PUT 은 사용자가 저장을
누를 때만 발화하지 않는다 — 견적 미리보기·알림톡 발송도 같은 PUT 을 태운다. 403 으로
만들면 무권한 사용자의 정상 저장 전체가 함께 막힌다. 대신 화면은 체크박스를 ``disabled``
로 렌더하고(제거하면 폼 수집기가 ``false`` 를 실어 보내 값이 조용히 지워진다),
서버는 값이 실제로 달라진 요청만 ``ACCESS_DENIED`` 로 남긴다.
"""

from __future__ import annotations

from typing import Any

from foms.services.orders.order_mutation_policy import team_has_capability

__all__ = [
    "ORDER_FLAG_ALLOWED_ROLES",
    "ORDER_FLAG_ALLOWED_TEAMS",
    "can_toggle_order_flags",
]

#: 역할만으로 통과하는 집합. MANAGER 는 여기 없다 — 팀이 CS 일 때만 통과한다.
ORDER_FLAG_ALLOWED_ROLES = frozenset({"ADMIN"})

#: 팀으로 통과하는 집합. ``CS`` = 라홈팀/하우드팀 (foms/web/auth/routes.py ``TEAMS``).
ORDER_FLAG_ALLOWED_TEAMS = frozenset({"CS"})


def can_toggle_order_flags(user: Any) -> bool:
    """기존 주문의 라홈시스템·지방주문 체크박스를 바꿀 수 있는지 판정한다.

    신규 주문 생성 경로(주문 마법사·신규 등록)는 이 게이트를 쓰지 않는다 —
    접수 단계에서 값을 정하는 것 자체를 막으면 등록 업무가 막히기 때문이다.

    :param user: 현재 사용자(``role``·``team`` 속성). ``None`` 이면 거부.
    :return: 관리자(ADMIN)이거나 CS(라홈팀/하우드팀) 소속이면 ``True``.
    """
    if not user:
        return False
    role = (getattr(user, "role", None) or "").strip().upper()
    if role == "VIEWER":
        return False
    if role in ORDER_FLAG_ALLOWED_ROLES:
        return True
    return team_has_capability(getattr(user, "team", None), ORDER_FLAG_ALLOWED_TEAMS)
