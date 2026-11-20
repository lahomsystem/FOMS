"""AS 접수 취소를 누가 · 언제 할 수 있는가 (설계서 2026-11-20-multi-item-split-schedule §4.4, 결정 M10).

화면(단추를 그릴지)과 API(막을지)가 같은 판정을 쓴다. 가벼운 모듈이다 — 템플릿 필터로도 등록되므로
AS 건 서비스(``as_cycle_service``)를 가져오지 않는다.
"""
from __future__ import annotations

from typing import Any

from foms.services.orders.as_axis_read import read_as_status
from foms.services.orders.order_mutation_policy import team_has_capability

#: 취소할 수 있는 AS 축 값 — 접수뿐이다. 처리 중 · 완료는 취소가 아니다.
CANCELLABLE_AS_STATUS = "RECEIVED"
CANCEL_FORBIDDEN_MESSAGE = "AS 접수 취소는 관리자 · CS팀 · 회계팀만 할 수 있습니다."


def user_may_cancel_as(user: Any) -> bool:
    """관리자 또는 CS 능력(회계팀 별칭 포함)이 있는 사용자인가."""
    if user is None:
        return False
    if str(getattr(user, "role", "") or "").upper() == "ADMIN":
        return True
    return team_has_capability(getattr(user, "team", None), ("CS",))


def as_cancel_allowed(order: Any, user: Any = None) -> bool:
    """[AS 접수 취소] 단추를 그릴 수 있는가 — 현재 AS 가 접수 상태이고 사용자에게 권한이 있다.

    AS 축은 ``as_lifecycle`` 현재 건이 먼저, 없으면 옛 상태 글이다(건 기록이 없는 옛 AS 접수 주문도 취소할 수 있다).
    """
    if order is None or not getattr(order, "id", None):
        return False
    return user_may_cancel_as(user) and read_as_status(order) == CANCELLABLE_AS_STATUS
