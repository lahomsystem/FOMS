"""물어보기(직원 챗봇)를 여는 사람 — 여는 단계 설정(설계서 10.1 · 13절 2 · 사장님 D99 'ADMIN 2주 → 팀장 → 내부 직원 전부').

| 단계 | 묻는 사람 |
|---|---|
| ``admin`` | 켜진 내부 ADMIN 만 |
| ``leads`` | ADMIN + 켜진 MANAGER(모든 팀 팀장) |
| ``all`` | 로그인한 내부 직원 전부(VIEWER 포함) |

- 바깥 역할(PARTNER · 협력사 직원) · 꺼진 계정 · 로그인 안 함은 **어느 단계에서도** 못 연다(화면 · API 404 — 있는지도 알리지
  않는다). 스위치가 꺼져 있으면 ADMIN 만 화면(설정)을 보고 아무도 묻지 못한다.
- 무엇을 보는지는 따로다 — 답의 후보 · 근거 · 수는 늘 그 사람의 보기 범위(:mod:`.scope`)로 찾는 단계에서 거른다.
"""

from __future__ import annotations

from typing import Any, Optional

from foms.services.brain.chat_settings import STAGE_ADMIN, STAGE_ALL, STAGE_LEADS, ChatSettings
from foms.services.brain.scope import ROLE_ADMIN, ROLE_MANAGER, Viewer, viewer_of

#: 단계마다 묻는 역할(내부 · 켜진 계정만 — :func:`foms.services.brain.scope.viewer_of`).
STAGE_ROLES: dict[str, frozenset[str]] = {
    STAGE_ADMIN: frozenset({ROLE_ADMIN}),
    STAGE_LEADS: frozenset({ROLE_ADMIN, ROLE_MANAGER}),
    STAGE_ALL: frozenset({ROLE_ADMIN, ROLE_MANAGER, "STAFF", "VIEWER"}),
}
#: 어느 단계에서든 묻는 역할 — 이 밖 역할은 단계 · 스위치와 상관없이 못 연다(설정을 읽을 까닭이 없다).
ANY_STAGE_ROLES: frozenset[str] = frozenset().union(*STAGE_ROLES.values())


def _internal(user: Any) -> Optional[Viewer]:
    """켜진 내부 사람이면 그 Viewer."""
    viewer = viewer_of(user)
    return viewer if viewer.internal and viewer.user_id is not None else None


def ask_viewer(user: Any, cfg: ChatSettings) -> Optional[Viewer]:
    """지금 물을 수 있으면 그 사람의 Viewer — 스위치 켬 · 단계 안 역할 · 내부 계정. 아니면 ``None``."""
    viewer = _internal(user)
    if viewer is None or not cfg.enabled:
        return None
    return viewer if viewer.role in STAGE_ROLES.get(cfg.stage, frozenset()) else None


def page_viewer(user: Any, cfg: ChatSettings) -> Optional[Viewer]:
    """물어보기 화면을 열 수 있으면 Viewer — 물을 수 있는 사람 + ADMIN(꺼져 있어도 설정을 보려고)."""
    viewer = _internal(user)
    if viewer is None:
        return None
    if viewer.is_admin:
        return viewer
    return ask_viewer(user, cfg)


def page_open_without_settings(user: Any) -> Optional[bool]:
    """설정을 읽지 않고도 :func:`page_viewer` 의 답을 알면 그 답(화면을 열 수 있나), 설정에 달렸으면 ``None``.

    모든 화면 메뉴처럼 자주 부르는 곳이 설정 줄을 덜 읽게 한다 — 바깥 역할 · 꺼진 계정 · 로그인 안 함 · 어느 단계에도 없는
    역할은 ``False``, ADMIN 은 ``True``(꺼져 있어도 설정을 보려고 연다), 그 밖 내부 직원은 ``None``(여는 단계 · 스위치를 봐야 안다).
    """
    viewer = _internal(user)
    if viewer is None or viewer.role not in ANY_STAGE_ROLES:
        return False
    return True if viewer.is_admin else None
