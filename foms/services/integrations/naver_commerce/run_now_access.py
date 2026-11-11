"""네이버 "지금 수집" 을 누를 수 있는 사람 — 판정 정본 하나(2026-11-11 사용자 결정).

처음에는 ADMIN 전용이었다. CS 팀이 네이버 주문을 받아 접수하는데, 방금 들어온 주문이
아직 안 보이면 관리자에게 "지금 수집 눌러 주세요"라고 부탁해야만 했다. 그래서 **"지금
수집" 한 가지만** CS 팀(STAFF · MANAGER)에게 연다.

넓힌 것은 그 단추(와 끝났는지 묻는 읽기 경로)뿐이다. 과거 주문 소급 수집 · 인증 만료일
등록 · 전체 다시 읽기는 한 번에 네이버 호출이 수십~수백 번 나가거나 수집 설정을 바꾸는
일이라 계속 ADMIN 전용이다.

팀 비교는 ``normalize_team`` 뒤 **정확히 ``CS``** 다. 정책 엔진의 "회계팀 → CS 능력"
별칭(``team_has_capability``)은 쓰지 않는다 — 사용자는 CS 팀만 열라고 했고, 회계팀 ·
영업팀은 이력 열람만 한다(2026-11-11 선택지에서 "영업 · 회계팀도" 는 고르지 않았다).

정책 엔진(``NAVER_INGEST_RUN`` 의 ``gate``)과 라우트 · 화면이 모두 이 함수 하나를 부른다 —
한쪽만 넓히면 보이는 단추가 403 을 받는다.
"""

from __future__ import annotations

from typing import Any

from foms.services.auth.partner_scope import is_partner_user
from foms.services.orders.order_mutation_policy import normalize_team

__all__ = ["RUN_NOW_TEAMS", "can_run_ingest_now"]

#: "지금 수집" 을 팀 자격으로 누를 수 있는 팀(``foms/web/auth/routes.py`` ``TEAMS`` 값).
RUN_NOW_TEAMS = ("CS",)

_TEAM_CAPABLE_ROLES = ("STAFF", "MANAGER")


def can_run_ingest_now(user: Any) -> bool:
    """이 사용자가 "지금 수집" 을 누를 수 있나 — ADMIN, 또는 CS 팀의 STAFF · MANAGER.

    Args:
        user: ``g.current_user`` 와 같은 사용자 객체(없으면 ``None``).

    Returns:
        켜진 우리 직원 중 ADMIN 이거나 CS 팀 STAFF · MANAGER 면 True. VIEWER · 협력사 ·
        비활성 · 다른 팀은 False.
    """
    if user is None or getattr(user, "is_active", None) is False or is_partner_user(user):
        return False
    role = str(getattr(user, "role", "") or "").strip().upper()
    if role == "ADMIN":
        return True
    if role not in _TEAM_CAPABLE_ROLES:
        return False
    return normalize_team(getattr(user, "team", None)) in RUN_NOW_TEAMS
