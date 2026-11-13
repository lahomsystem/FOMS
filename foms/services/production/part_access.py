"""생산 파트 카드를 누가 보고 누가 쓰는지 — 한 곳 규칙(설계서 §15.4 '권한' · D53 · D55).

쓰기 API(``foms/api/production/part_marks.py``) · 화면 분기(P15-5) · 시험이 모두 이 함수들을 본다.
둘이 어긋나면 화면에 단추가 있는데 서버가 막거나, 단추가 없는데 서버가 받는다.

* 파트 계정 = 활성 · 협력사 아님 · 생산팀 · VIEWER 아님 · 계정 파트 있음 → 자기 파트 하나만 쓴다(D53).
* 관리자(role ADMIN) = 아무 파트나 쓴다(D55). 계정에 파트가 있어도 무시하고 고른 파트로 쓴다.
  판정은 지금 공정 API 의 ``_can_edit_production_steps`` 와 같은 ``role == "ADMIN"`` 이다.
* 읽기 전용 = 생산 첫 화면을 볼 수 있지만 위 둘이 아닌 사람(CS · 영업 · 파트 없는 생산 · 매니저 등) — 카드는 보고 쓰지 않는다.
"""

from __future__ import annotations

from typing import Any, Optional

from foms.services.production.home_access import can_view_production_home
from foms.services.production.part_constants import PRODUCTION_PART_KEYS, account_production_part

#: 보기 모드 — 파트 계정 · 관리자 · 읽기 전용 · 못 봄.
VIEW_PART = "part"
VIEW_ADMIN = "admin"
VIEW_READONLY = "readonly"
VIEW_NONE = "none"


def _is_live_staff(user: Any) -> bool:
    """로그인한 활성 계정이고 협력사가 아닌지."""
    if user is None or getattr(user, "is_active", None) is False:
        return False
    return getattr(user, "partner_org_id", None) is None


def is_part_admin(user: Any) -> bool:
    """아무 파트나 쓸 수 있는 관리자인지(D55).

    Args:
        user: 사용자 객체(None 허용).

    Returns:
        활성 · 협력사 아님 · ``role == "ADMIN"`` 이면 True.
    """
    return _is_live_staff(user) and getattr(user, "role", None) == "ADMIN"


def part_account_part(user: Any) -> Optional[str]:
    """파트 계정이면 그 파트 key, 아니면 None.

    Args:
        user: 사용자 객체(None 허용).

    Returns:
        활성 · 협력사 아님 · 생산팀 · VIEWER 아님 · 계정 파트가 있으면 파트 key. 그 밖은 None.
    """
    if not _is_live_staff(user):
        return None
    if str(getattr(user, "role", None) or "").strip().upper() == "VIEWER":
        return None
    return account_production_part(user)


def part_view_mode(user: Any) -> str:
    """생산 첫 화면 도면 카드의 보기 모드.

    관리자를 먼저 본다 — 관리자 계정에 파트가 있어도 관리자 모드(D55).

    Args:
        user: 사용자 객체(None 허용).

    Returns:
        ``part`` · ``admin`` · ``readonly`` · ``none`` 중 하나.
    """
    if not can_view_production_home(user) or not _is_live_staff(user):
        return VIEW_NONE
    if is_part_admin(user):
        return VIEW_ADMIN
    if part_account_part(user):
        return VIEW_PART
    return VIEW_READONLY


def writable_parts(user: Any) -> tuple[str, ...]:
    """이 사람이 표시를 쓸 수 있는 파트들.

    Args:
        user: 사용자 객체(None 허용).

    Returns:
        관리자 = 네 파트 모두, 파트 계정 = 자기 파트 하나, 그 밖 = 빈 tuple.
    """
    mode = part_view_mode(user)
    if mode == VIEW_ADMIN:
        return PRODUCTION_PART_KEYS
    if mode == VIEW_PART:
        part = part_account_part(user)
        return (part,) if part else ()
    return ()
