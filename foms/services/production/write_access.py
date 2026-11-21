"""생산 쓰기를 누가 하나 — 한 곳 규칙(설계서 2026-11-21-production-pc-viewer §5 · §13 결정 2).

쓰는 사람 = **관리자 + 생산팀**뿐이다. 기기(PC · 태블릿 · 폰)와 상관없다. CS · 회계(CS 별칭) · 영업 · 도면 · 시공 · 출고는
생산 화면을 보기만 한다(2026-11-21 사장님 결정 — 예전에는 CS · 영업도 썼다).

이 함수 하나를 셋이 같이 본다. 셋이 어긋나면 단추는 있는데 서버가 막거나, 단추는 없는데 서버가 받는다.

* 문지기 정책 ``PRODUCTION_EDIT``(``foms/services/orders/order_mutation_policy.py`` 의 ``gate``) — 생산 쓰기 API 아홉
  (start · complete · rework · cancel · uncomplete · change-ack · steps POST · defect · hold)의 앞문.
* 라우트 데코레이터 ``_production_steps_edit_required``(``foms/api/production/orders.py``) — 같은 API 의 뒷문.
* 화면 — 쓰기 단추를 그릴지(첫 화면 · 작업 시트 · 옛 보드).

파트 계정(생산팀 + 계정 파트, D50 · D53)은 이 함수로는 True 다. 그 사람이 주문 공정 칸을 직접 못 쓰고 자기 파트 카드만 쓰는
것은 그 위에 얹힌 따로 규칙(``foms/services/production/part_access.py`` 의 ``steps_locked_for`` · ``writable_parts``)이 정한다.

이 모듈은 팀 권한 판정(``order_mutation_policy.team_has_capability``)만 읽는다 — 정책 엔진이 ``gate`` 문자열로 늦게 불러서
순환 import 가 없다.
"""

from __future__ import annotations

from typing import Any

from foms.services.orders.order_mutation_policy import team_has_capability

#: 생산 쓰기 팀(능력 이름). 관리자(role ADMIN)는 팀과 상관없이 쓴다.
PRODUCTION_WRITE_TEAMS: tuple[str, ...] = ("PRODUCTION",)

#: 쓰기 API 가 막을 때의 글(403) — 화면 오류 줄에 그대로 나온다.
PRODUCTION_WRITE_DENIED_MESSAGE = "생산 일은 관리자와 생산팀만 할 수 있어요. 이 화면은 보기만 돼요."


def can_write_production(user: Any) -> bool:
    """생산 쓰기(공정 체크 · 제작 시작/완료 · 보류 · 불량 · 변경 확인 · 파트 카드 …)를 할 수 있는지.

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


__all__ = ["PRODUCTION_WRITE_DENIED_MESSAGE", "PRODUCTION_WRITE_TEAMS", "can_write_production"]
