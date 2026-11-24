"""생산 파트 카드를 누가 보고 누가 쓰는지 — 한 곳 규칙(설계서 §15.4 '권한' · D53 · D55).

쓰기 API(``foms/api/production/part_marks.py``) · 화면 분기(P15-5) · 시험이 모두 이 함수들을 본다.
둘이 어긋나면 화면에 단추가 있는데 서버가 막거나, 단추가 없는데 서버가 받는다.

* 파트 계정 = 활성 · 협력사 아님 · 생산팀 · VIEWER 아님 · 계정 파트 1 ~ 4개 → 자기 파트들만 쓴다(D53, 2026-11-23 §4-12 B9).
* 관리자(role ADMIN) = 아무 파트나 쓴다(D55). 계정에 파트가 있어도 무시하고 고른 파트로 쓴다.
  판정은 지금 공정 API 의 ``_can_edit_production_steps`` 와 같은 ``role == "ADMIN"`` 이다.
* 대신(반장, 2026-11-23 §4-12 B7 · '승인 때 고친 것' 5) = 생산 쓰기 사람(:func:`~foms.services.production.write_access.can_write_production`
  — 생산팀 STAFF · MANAGER)이고 관리자가 반장으로 체크한 계정(``users.production_lead``) → 관리자와 같은 카드 권한(네 파트 · 남의 장
  대신 완료 · 완료 취소 · 맡기 취소) + 공정 칸 손 체크(잠그지 않음). 반장이 파트를 가져도 반장이 이긴다(네 파트). 자기 공장 장만은 3단계(C9).
* 공장(설계서 2026-11-23 §4-13 · §5 · C9, 3단계) = 파트 계정 · 반장은 자기 계정 공장 장만, 관리자는 두 공장
  (:func:`writable_factories` · :func:`can_write_sheet`). 읽기 전용은 두 공장을 보기만 한다.
* 읽기 전용 = 생산 첫 화면을 볼 수 있지만 위 셋이 아닌 사람(CS · 영업 · 도면 · 다른 팀 매니저 · **파트도 반장도 아닌 생산팀** 등) —
  카드는 보고 쓰지 않는다. 파트도 반장도 아닌 생산팀은 공정 칸도 잠긴다(:func:`steps_lock`). [제작 시작] · [제작 완료] · 보류 · 불량 같은
  그 밖 생산 쓰기는 지금 그대로(:func:`~foms.services.production.write_access.can_write_production`).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from foms.services.production.factory_constants import (
    DEFAULT_FACTORY,
    FACTORIES,
    account_production_factory,
    stored_production_factory,
)
from foms.services.production.home_access import can_view_production_home
from foms.services.production.part_constants import PRODUCTION_PART_KEYS, account_production_lead, account_production_parts
from foms.services.production.write_access import can_write_production

#: 보기 모드 — 파트 계정 · 대신(반장) · 관리자 · 읽기 전용 · 못 봄.
VIEW_PART = "part"
VIEW_SUB = "sub"
VIEW_ADMIN = "admin"
VIEW_READONLY = "readonly"
VIEW_NONE = "none"

#: 파트 계정이 주문 공정 칸을 직접 쓰려 할 때의 글(403 ``PART_ACCOUNT_USE_CARDS`` · 시트 단추 아래 한 줄).
PART_ACCOUNT_STEPS_MESSAGE = "공정은 도면 카드에서 체크해요"
PART_ACCOUNT_STEPS_CODE = "PART_ACCOUNT_USE_CARDS"
#: 파트도 반장도 아닌 생산팀 계정이 공정 칸을 쓰려 할 때의 글(403 ``LEAD_REQUIRED`` · 시트 단추 아래 한 줄, '승인 때 고친 것' 5).
LEAD_ONLY_STEPS_MESSAGE = "반장으로 지정된 계정만 체크할 수 있어요."
LEAD_ONLY_STEPS_CODE = "LEAD_REQUIRED"


@dataclass(frozen=True)
class StepsLock:
    """공정 칸 직접 쓰기를 막는 까닭 — 403 코드 · 시트 · 바텀시트 한 줄 글."""

    code: str
    message: str


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


def is_production_lead(user: Any) -> bool:
    """반장인지 — 생산 쓰기 사람(활성 · 협력사 아님 · VIEWER 아님 · 생산팀)이고 계정 반장 칸이 참('승인 때 고친 것' 5).

    Args:
        user: 사용자 객체(None 허용). 이미 읽은 행의 칸만 본다 — 쿼리 0.

    Returns:
        반장이면 True. 관리자는 반장 칸과 상관없이 :func:`is_part_admin` 으로 따로 된다.
    """
    return _is_live_staff(user) and can_write_production(user) and account_production_lead(user)


def part_view_mode(user: Any) -> str:
    """생산 첫 화면 도면 카드의 보기 모드.

    관리자를 먼저 본다 — 관리자 계정에 파트가 있어도 관리자 모드(D55). 그다음 반장(대신 — 파트가 있어도 반장이 이긴다, '승인 때
    고친 것' 5), 그다음 파트 계정(파트 1개 이상). 파트도 반장도 아닌 생산팀은 읽기 전용이다.

    Args:
        user: 사용자 객체(None 허용).

    Returns:
        ``part`` · ``sub`` · ``admin`` · ``readonly`` · ``none`` 중 하나.
    """
    if not can_view_production_home(user) or not _is_live_staff(user):
        return VIEW_NONE
    if is_part_admin(user):
        return VIEW_ADMIN
    if is_production_lead(user):
        return VIEW_SUB
    if part_account_parts(user):
        return VIEW_PART
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


def steps_lock(user: Any) -> Optional[StepsLock]:
    """주문 공정 칸(``…/production/steps``)을 직접 못 쓰는 까닭 — 공정 API 403 · 시트 단추 읽기 전용 · 바텀시트가 이 함수 하나를 본다.

    파트 계정의 공정 칸은 도면 카드 동기화(설계서 §15.5)만 바꾼다. 길이 둘이면 동기화 값과 손 값이 서로 덮고,
    남의 파트 칸도 켤 수 있어 D53 이 깨진다(§15.4 끝). 공정 칸 손 체크는 반장 · 관리자만 한다('승인 때 고친 것' 3 · 5).

    Args:
        user: 사용자 객체(None 허용).

    Returns:
        관리자 · 반장 = None(잠그지 않음). 파트 계정 = ``PART_ACCOUNT_USE_CARDS``("공정은 도면 카드에서 체크해요"). 파트도 반장도 아닌
        생산 쓰기 사람 = ``LEAD_REQUIRED``. 생산 쓰기 사람이 아니면 None — 그 사람은 생산 쓰기 문(``can_write_production``)이 막는다
        (지금 그대로).
    """
    if is_part_admin(user) or is_production_lead(user):
        return None
    if part_account_parts(user):
        return StepsLock(PART_ACCOUNT_STEPS_CODE, PART_ACCOUNT_STEPS_MESSAGE)
    if can_write_production(user):
        return StepsLock(LEAD_ONLY_STEPS_CODE, LEAD_ONLY_STEPS_MESSAGE)
    return None


def steps_locked_for(user: Any) -> bool:
    """주문 공정 칸을 직접 못 쓰는 사람인지(:func:`steps_lock` 이 까닭을 주면 True).

    Args:
        user: 사용자 객체(None 허용).

    Returns:
        파트 계정(반장 · 관리자 아님) · 파트도 반장도 아닌 생산팀이면 True.
    """
    return steps_lock(user) is not None


def user_factory(user: Any) -> int:
    """보는 사람의 처음 공장 — 계정 공장(비면 1공장). 관리자 판 머리 공장 고르기의 처음 값도 이것(§4-13 · §19 열한째).

    Args:
        user: 사용자 객체(None 허용). 이미 읽은 행의 칸만 본다 — 쿼리 0.

    Returns:
        1 · 2.
    """
    return stored_production_factory(user)


def writable_factories(user: Any) -> tuple[int, ...]:
    """이 사람이 카드 · 공정을 쓸 수 있는 공장들(§5 권한 표 · C9).

    Args:
        user: 사용자 객체(None 허용).

    Returns:
        관리자 = 두 공장, 파트 계정 · 반장 = 자기 계정 공장 하나(비면 1공장), 그 밖 = 빈 tuple(보기만).
    """
    mode = part_view_mode(user)
    if mode == VIEW_ADMIN:
        return FACTORIES
    if mode in (VIEW_PART, VIEW_SUB):
        return (account_production_factory(user) or DEFAULT_FACTORY,)
    return ()


def can_write_sheet(user: Any, factory: Any) -> bool:
    """이 사람이 그 공장 장을 쓸 수 있는지(남의 공장 장은 보기만 — C6). 공장이 비면 1공장으로 본다.

    Args:
        user: 사용자 객체(None 허용).
        factory: 장의 공장(1 · 2 · None).

    Returns:
        :func:`writable_factories` 안이면 True.
    """
    return (factory if factory in FACTORIES else DEFAULT_FACTORY) in writable_factories(user)
