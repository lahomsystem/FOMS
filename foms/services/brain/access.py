"""'회사 지식' 화면 · API 를 여는 사람(설계서 7.5 끝 '판 1 은 ADMIN · 승인자만' · 사장님 D101).

- 켜진 내부 ADMIN(사장님 포함), 그리고 **층 승인자 팀의 켜진 MANAGER**(상담 = CS · 도면 = DRAWING · 생산 = PRODUCTION —
  :data:`.constants.LAYER_APPROVER_TEAMS`)만 연다.
- 그 밖(다른 팀 MANAGER · STAFF · VIEWER · PARTNER · 협력사 직원 · 꺼진 계정)은 화면 · API 모두 404 — 있는지도 알리지 않는다.
- 연 사람이 무엇을 보는지는 따로다 — 모든 읽기는 :mod:`.scope` 의 보기 범위로 질의 단계에서 거른다(승인자 MANAGER 는 '내부
  모두' + 자기 팀 범위만, 가격 재량 · 관리 항목은 ADMIN 만).
"""

from __future__ import annotations

from typing import Any, Optional

from foms.services.brain.constants import LAYER_APPROVER_TEAMS
from foms.services.brain.scope import ROLE_MANAGER, Viewer, viewer_of

#: 화면을 여는 MANAGER 의 팀(층 승인자 팀).
APPROVER_TEAMS: frozenset[str] = frozenset(LAYER_APPROVER_TEAMS.values())


def screen_viewer(user: Any) -> Optional[Viewer]:
    """화면을 열 수 있으면 그 사람의 :class:`Viewer`, 아니면 ``None``.

    Args:
        user: 로그인 사용자(없으면 ``None``).

    Returns:
        켜진 내부 ADMIN 또는 층 승인자 팀 MANAGER 의 Viewer, 그 밖은 ``None``.
    """
    viewer = viewer_of(user)
    if not viewer.internal or viewer.user_id is None:
        return None
    if viewer.is_admin or (viewer.role == ROLE_MANAGER and viewer.team in APPROVER_TEAMS):
        return viewer
    return None


def can_open_screen(user: Any) -> bool:
    """메뉴에 '회사 지식'을 보일지 — :func:`screen_viewer` 와 같은 판정(DB 를 읽지 않는다)."""
    return screen_viewer(user) is not None
