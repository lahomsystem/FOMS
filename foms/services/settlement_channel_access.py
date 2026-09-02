"""채널(네이버) 정산 탭 열람 게이트 — NAVER-SETTLE-01 §1 판정 SSOT.

사용자 결정(2026-09-02): 채널 정산 탭은 **ADMIN 과 신설 회계팀(ACCOUNTING)만** 본다.

**정책 엔진으로 표현할 수 없는 이유**: :func:`foms.services.orders.order_mutation_policy.
evaluate_policy` 는 ``role == "MANAGER"`` 를 team 검사보다 **먼저** 통과시킨다
(`order_mutation_policy.py` §3 role override). 그래서 ``teams=("ACCOUNTING",)`` 만으로는
"CS 팀 MANAGER"까지 통과한다 — 운영 실측(2026-09-02)상 회계 업무 담당 예정자 2명이
바로 그 MANAGER·team=CS 조합이라, 팀 이관 전까지는 엔진 판정이 통째로 틀린다.
:data:`SETTLEMENT_CHANNEL_POLICY_ID` 등재는 route manifest·before_request pre-filter 용이고,
**진짜 판정은 이 모듈의 함수 하나**다. 페이지 컨텍스트·API 핸들러 둘 다 이것만 부른다.

읽기 전용 모듈이다 — DB 를 만지지 않고 사용자 객체의 속성만 본다.
"""

from __future__ import annotations

from typing import Any

from foms.services.orders.order_mutation_policy import normalize_team

#: 채널 정산 열람 정책 id(엔진 등재분). 문자열을 여러 곳에 적으면 오타가 조용한 403 이 된다.
SETTLEMENT_CHANNEL_POLICY_ID = "SETTLEMENT_CHANNEL_READ"

#: 채널 정산 수동 동기화(enqueue) 정책 id. 판정은 READ 와 같고 핸들러가 게이트로 재검사한다.
SETTLEMENT_CHANNEL_SYNC_POLICY_ID = "SETTLEMENT_CHANNEL_SYNC"

#: 회계팀 team 코드(`foms/web/auth/routes.py` ``TEAMS`` SSOT 와 같은 값).
ACCOUNTING_TEAM = "ACCOUNTING"

#: 팀 자격으로 통과할 수 있는 role. ADMIN 은 팀과 무관하게 통과하고, VIEWER 는 하드 deny 다.
_TEAM_CAPABLE_ROLES = ("MANAGER", "STAFF")


def can_view_channel_settlement(user: Any) -> bool:
    """채널(네이버) 정산 탭·API 를 열람할 수 있는 사용자인지 판정한다.

    허용 집합은 **ADMIN**, 또는 role 이 MANAGER/STAFF 이면서 team 이 ``ACCOUNTING`` 인
    사용자다. VIEWER·미인증(None)·그 밖의 팀·비활성 계정은 전부 거부한다.

    Args:
        user: 현재 사용자 객체(``None`` 이면 미인증). ``role``/``team``/``is_active`` 를 읽는다.

    Returns:
        열람 가능하면 True.
    """
    if user is None:
        return False
    if not getattr(user, "is_active", True):
        return False

    role = str(getattr(user, "role", "") or "").strip().upper()
    if role == "ADMIN":
        return True
    if role not in _TEAM_CAPABLE_ROLES:
        return False
    return normalize_team(getattr(user, "team", None)) == ACCOUNTING_TEAM
