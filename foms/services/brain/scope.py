"""보기 범위 — 묻는 사람이 볼 수 있는 항목만 **찾는 단계에서** 거른다(설계서 4절 표 · 17.9-2 · 12절 첫 줄).

| 범위 | 볼 수 있는 사람 |
|---|---|
| ``all`` | 로그인한 내부 직원 전부(VIEWER 포함) |
| ``team:<팀>`` | 그 팀(``User.team`` 정규화 값) + ADMIN |
| ``price`` | 가격 재량 — 사장님 · ADMIN 만 |
| ``admin`` | 관리(에이전트 설정 · 엇갈림 · 물어볼 것) — ADMIN 만 |

바깥 역할(PARTNER · 협력사 직원 ``partner_org_id``) · 꺼진 계정 · 로그인 안 함은 **아무것도** 못 본다(모아 센 수도 0).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from sqlalchemy import false, true
from sqlalchemy.sql.elements import ColumnElement

from foms.services.brain.constants import SCOPE_ALL, SCOPE_TEAM_PREFIX
from foms.services.orders.order_mutation_policy import normalize_team

ROLE_ADMIN, ROLE_MANAGER, ROLE_PARTNER = "ADMIN", "MANAGER", "PARTNER"


@dataclass(frozen=True)
class Viewer:
    """보는 사람 — 사용자 id · 역할 · 팀(정규화) · 내부 직원인가."""

    user_id: Optional[int]
    role: str
    team: str
    internal: bool

    @property
    def is_admin(self) -> bool:
        """켜진 내부 ADMIN(사장님 포함)."""
        return self.internal and self.role == ROLE_ADMIN


#: 아무것도 못 보는 사람(로그인 안 함).
NOBODY = Viewer(None, "", "", False)
#: 코드 안 읽기(지식 문서 다시 만들기 · 옮기기) — 사람 화면에는 쓰지 않는다.
SYSTEM = Viewer(None, ROLE_ADMIN, "", True)


def viewer_of(user: Any) -> Viewer:
    """로그인 사용자 → :class:`Viewer`. 없음 · 꺼짐 · PARTNER · 협력사 직원은 내부가 아니다."""
    if user is None:
        return NOBODY
    role = str(getattr(user, "role", "") or "").strip().upper()
    internal = (bool(getattr(user, "is_active", False)) and role not in ("", ROLE_PARTNER)
                and getattr(user, "partner_org_id", None) is None)
    user_id = getattr(user, "id", None)
    return Viewer(int(user_id) if user_id is not None else None, role, normalize_team(getattr(user, "team", None)),
                  internal)


def allowed_scopes(viewer: Viewer) -> Optional[frozenset[str]]:
    """볼 수 있는 범위 값 묶음. ``None`` = 모두(ADMIN), 빈 묶음 = 아무것도."""
    if not viewer.internal:
        return frozenset()
    if viewer.is_admin:
        return None
    scopes = {SCOPE_ALL}
    if viewer.team:
        scopes.add(SCOPE_TEAM_PREFIX + viewer.team)
    return frozenset(scopes)


def can_see(viewer: Viewer, visibility: str) -> bool:
    """범위 값 하나를 볼 수 있나(파이썬 쪽 — 질의 거르기와 같은 판정)."""
    scopes = allowed_scopes(viewer)
    return scopes is None or visibility in scopes


def scope_clause(viewer: Viewer, column: Any) -> ColumnElement[bool]:
    """질의 조건 — ``column``(보기 범위 칸)이 볼 수 있는 값인 줄만."""
    scopes = allowed_scopes(viewer)
    if scopes is None:
        return true()
    if not scopes:
        return false()
    return column.in_(sorted(scopes))
