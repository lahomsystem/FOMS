"""생산 쓰기를 누가 하나 — 한 곳 규칙(설계서 2026-11-21-production-pc-viewer §5 · §13 결정 2).

쓰는 사람 = **관리자 + 생산팀**뿐이다. 기기(PC · 태블릿 · 폰)와 상관없다. CS · 회계(CS 별칭) · 영업 · 도면 · 시공 · 출고는
생산 화면을 보기만 한다(2026-11-21 사장님 결정 — 예전에는 CS · 영업도 썼다).

이 함수 하나를 셋이 같이 본다. 셋이 어긋나면 단추는 있는데 서버가 막거나, 단추는 없는데 서버가 받는다.

* 문지기 정책 ``PRODUCTION_EDIT``(``foms/services/orders/order_mutation_policy.py`` 의 ``gate``) — 생산 쓰기 API 여덟
  (start · complete · rework · cancel · uncomplete · steps POST · defect · hold)의 앞문.
* 라우트 데코레이터 ``_production_steps_edit_required``(``foms/api/production/orders.py``) — 같은 API 의 뒷문.
* 화면 — 쓰기 단추를 그릴지(첫 화면 · 작업 시트 · 옛 보드).

파트 계정(생산팀 + 계정 파트, D50 · D53)은 이 함수로는 True 다. 그 사람이 주문 공정 칸을 직접 못 쓰고 자기 파트 카드만 쓰는
것은 그 위에 얹힌 따로 규칙(``foms/services/production/part_access.py`` 의 ``steps_locked_for`` · ``writable_parts``)이 정한다.

[확인했어요](change-ack)는 쓰기가 아니라 사람마다 남기는 확인 기록이다 — 생산 화면을 보는 사람 모두가 누른다(§13 결정 5,
2026-11-21 사장님: PC 보기 전용에서도 허용). 판정은 :func:`can_ack_production_change` 한 곳(문지기 정책 ``PRODUCTION_ACK`` ·
라우트 데코레이터 · 화면 단추가 같이 본다).

이 모듈은 팀 권한 판정(``order_mutation_policy.team_has_capability``)과 보기 판정(``home_access``)만 읽는다 — 정책 엔진이
``gate`` 문자열로 늦게 불러서 순환 import 가 없다.
"""

from __future__ import annotations

from typing import Any

from foms.services.orders.order_mutation_policy import team_has_capability
from foms.services.production.home_access import can_view_production_home

#: 생산 쓰기 팀(능력 이름). 관리자(role ADMIN)는 팀과 상관없이 쓴다.
PRODUCTION_WRITE_TEAMS: tuple[str, ...] = ("PRODUCTION",)

#: 쓰기 API 가 막을 때의 글(403) — 화면 오류 줄에 그대로 나온다.
PRODUCTION_WRITE_DENIED_MESSAGE = "생산 일은 관리자와 생산팀만 할 수 있어요. 이 화면은 보기만 돼요."
#: [확인했어요]를 막을 때의 글(403) — 생산 화면을 못 보는 사람 · 조회 전용 · 꺼진 계정.
PRODUCTION_ACK_DENIED_MESSAGE = "생산 화면을 볼 수 있는 사람만 확인할 수 있어요."


def can_write_production(user: Any) -> bool:
    """생산 쓰기(공정 체크 · 제작 시작/완료 · 보류 · 불량 · 파트 카드 …)를 할 수 있는지. 변경 확인은 :func:`can_ack_production_change`.

    Args:
        user: 사용자 객체(None 허용). ``role`` · ``team`` · ``partner_org_id`` · ``is_active`` 를 읽는다.

    Returns:
        활성 · 협력사 아님 · 조회 전용(VIEWER) 아님이고, 관리자이거나 생산 능력 팀이면 True. 그 밖(CS · 회계 · 영업 ·
        도면 · 시공 · 출고 · 팀 없음 · 로그인 없음)은 False.
    """
    if user is None or getattr(user, "is_active", None) is False:
        return False
    if getattr(user, "partner_org_id", None) is not None:
        return False
    role = str(getattr(user, "role", None) or "").strip().upper()
    if role == "ADMIN":
        return True
    if role == "VIEWER":
        return False
    return team_has_capability(getattr(user, "team", None), PRODUCTION_WRITE_TEAMS)


def can_ack_production_change(user: Any) -> bool:
    """[확인했어요](생산 변경 확인, change-ack)를 누를 수 있는지 — 생산 화면을 보는 사람 모두(§13 결정 5).

    확인은 주문을 바꾸지 않고 그 사람의 확인 기록(OrderEvent)만 남긴다. 그래서 쓰기 팀보다 넓다 — CS · 회계 · 영업 · 도면 ·
    시공 · 출고도 자기 '바뀐 것' 을 비운다(기기 무관, PC 보기 전용 포함).

    Args:
        user: 사용자 객체(None 허용). ``role`` · ``team`` · ``partner_org_id`` · ``is_active`` 를 읽는다.

    Returns:
        활성 · 조회 전용(VIEWER) 아님이고 :func:`~foms.services.production.home_access.can_view_production_home` 이면 True.
        조회 전용은 정책 엔진이 문지기보다 먼저 막는 규칙(F-01)과 같은 답을 낸다. 협력사 · 팀 없음 · 로그인 없음은 False.
    """
    if user is None or getattr(user, "is_active", None) is False:
        return False
    if str(getattr(user, "role", None) or "").strip().upper() == "VIEWER":
        return False
    return can_view_production_home(user)


__all__ = [
    "PRODUCTION_ACK_DENIED_MESSAGE",
    "PRODUCTION_WRITE_DENIED_MESSAGE",
    "PRODUCTION_WRITE_TEAMS",
    "can_ack_production_change",
    "can_write_production",
]
