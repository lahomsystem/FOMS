"""생산 파트 카드를 누가 보고 누가 쓰는지 — 한 곳 규칙(설계서 §15.4 '권한' · D53 · D55).

쓰기 API(``foms/api/production/part_marks.py``) · 화면 분기(P15-5) · 시험이 모두 이 함수들을 본다.
둘이 어긋나면 화면에 단추가 있는데 서버가 막거나, 단추가 없는데 서버가 받는다.

* 파트 계정 = 활성 · 협력사 아님 · 생산팀 · VIEWER 아님 · 계정 파트 1 ~ 4개 → 자기 파트들만 쓴다(D53, 2026-11-23 §4-12 B9).
* 관리자(role ADMIN) = 아무 파트나 쓴다(D55). 계정에 파트가 있어도 무시하고 고른 파트로 쓴다.
  판정은 지금 공정 API 의 ``_can_edit_production_steps`` 와 같은 ``role == "ADMIN"`` 이다.
* 대신(반장, 2026-11-23 §4-12 B7) = 생산 쓰기 사람(:func:`~foms.services.production.write_access.can_write_production` —
  생산팀 STAFF · MANAGER)인데 파트가 없는 계정 → 관리자와 같은 카드 권한(네 파트 · 남의 장 대신 완료 · 완료 취소 · 맡기 취소)
  + 공정 칸 손 체크(잠그지 않음). 자기 공장 장만은 3단계(C9).
* 읽기 전용 = 생산 첫 화면을 볼 수 있지만 위 셋이 아닌 사람(CS · 영업 · 도면 · 다른 팀 매니저 등) — 카드는 보고 쓰지 않는다.
"""

from __future__ import annotations

from typing import Any

from foms.services.production.home_access import can_view_production_home
from foms.services.production.part_constants import PRODUCTION_PART_KEYS, account_production_parts
from foms.services.production.write_access import can_write_production

#: 보기 모드 — 파트 계정 · 대신(파트 없는 생산팀) · 관리자 · 읽기 전용 · 못 봄.
VIEW_PART = "part"
VIEW_SUB = "sub"
VIEW_ADMIN = "admin"
VIEW_READONLY = "readonly"
VIEW_NONE = "none"

#: 파트 계정이 주문 공정 칸을 직접 쓰려 할 때의 글(403 ``PART_ACCOUNT_USE_CARDS`` · 시트 단추 아래 한 줄).
PART_ACCOUNT_STEPS_MESSAGE = "공정은 도면 카드에서 체크해요"


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


def part_account_parts(user: Any) -> tuple[str, ...]:
    """파트 계정이면 그 파트들(정의 순서), 아니면 빈 tuple.

    Args:
        user: 사용자 객체(None 허용). 이미 읽은 행(``g.current_user``)의 칸만 본다 — 쿼리 0.

    Returns:
        활성 · 협력사 아님 · 생산팀 · VIEWER 아님이면 계정 파트들(0 ~ 4개). 그 밖은 빈 tuple.
    """
    if not _is_live_staff(user):
        return ()
    if str(getattr(user, "role", None) or "").strip().upper() == "VIEWER":
        return ()
    return account_production_parts(user)


def part_view_mode(user: Any) -> str:
    """생산 첫 화면 도면 카드의 보기 모드.

    관리자를 먼저 본다 — 관리자 계정에 파트가 있어도 관리자 모드(D55). 그다음 파트 계정(파트 1개 이상), 그다음 대신
    (생산 쓰기 사람인데 파트 없음 — 2026-11-23 §4-12, 예전 읽기 전용에서 옮김).

    Args:
        user: 사용자 객체(None 허용).

    Returns:
        ``part`` · ``sub`` · ``admin`` · ``readonly`` · ``none`` 중 하나.
    """
    if not can_view_production_home(user) or not _is_live_staff(user):
        return VIEW_NONE
    if is_part_admin(user):
        return VIEW_ADMIN
    if part_account_parts(user):
        return VIEW_PART
    if can_write_production(user):
        return VIEW_SUB
    return VIEW_READONLY


def writable_parts(user: Any) -> tuple[str, ...]:
    """이 사람이 표시를 쓸 수 있는 파트들.

    Args:
        user: 사용자 객체(None 허용).

    Returns:
        관리자 · 대신 = 네 파트 모두, 파트 계정 = 자기 파트들, 그 밖 = 빈 tuple.
    """
    mode = part_view_mode(user)
    if mode in (VIEW_ADMIN, VIEW_SUB):
        return PRODUCTION_PART_KEYS
    if mode == VIEW_PART:
        return part_account_parts(user)
    return ()


def own_parts(user: Any) -> tuple[str, ...]:
    """'내 파트'(파트 계정의 파트들) — 관리자 · 대신 · 읽기 전용은 빈 tuple. 다른 파트 한 줄 "엣지 내 담당"(§4-12)이 본다.

    Args:
        user: 사용자 객체(None 허용).

    Returns:
        파트 계정이면 :func:`part_account_parts`, 아니면 빈 tuple.
    """
    return part_account_parts(user) if part_view_mode(user) == VIEW_PART else ()


def can_override_marks(user: Any) -> bool:
    """남이 맡거나 끝낸 장을 대신 완료 · 완료 취소 · 맡기 취소할 수 있는지 — 관리자 · 대신(§5 권한 표).

    Args:
        user: 사용자 객체(None 허용).

    Returns:
        보기 모드가 관리자 또는 대신이면 True.
    """
    return part_view_mode(user) in (VIEW_ADMIN, VIEW_SUB)


def steps_locked_for(user: Any) -> bool:
    """주문 공정 칸(``…/production/steps``)을 직접 못 쓰는 사람인지 — 파트 계정(관리자 아님).

    파트 계정의 공정 칸은 도면 카드 동기화(설계서 §15.5)만 바꾼다. 길이 둘이면 동기화 값과 손 값이 서로 덮고,
    남의 파트 칸도 켤 수 있어 D53 이 깨진다(§15.4 끝). 공정 API 403 과 시트 단추 읽기 전용이 이 함수 하나를 본다.

    Args:
        user: 사용자 객체(None 허용).

    Returns:
        파트 계정(파트 1개 이상)이고 관리자가 아니면 True. 대신(파트 없는 생산팀)은 잠그지 않는다(§4-12).
    """
    return bool(part_account_parts(user)) and not is_part_admin(user)
