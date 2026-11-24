"""공장(1공장 · 2공장) 상수와 계정 공장 판정 — 한 곳 규칙(PRODFACTORY, 설계서 2026-11-23 §4-13 · §6-2 · C9).

* 계정 공장 = 생산팀 계정마다 1공장 또는 2공장(한 사람 한 공장, '둘 다' 값 없음). 칸 ``users.production_factory`` — NULL = 1공장
  (지금과 같다, 채우기 없음). 관리자 화면은 2공장만 적고 1공장은 비운다(저장해도 헛바뀜 · 헛 감사가 없게). 생산팀이 아니면 저장 때 비운다.
* 관리자(role ADMIN)는 칸과 상관없이 두 공장 — :mod:`foms.services.production.part_access` 가 본다(이 모듈은 값만).
* ``flags.factory2``(주문의 '라홈시스템 계약')와 다른 것이다 — 장의 공장은 그 값에서 만들지 않는다(C7, §20).
* 이 모듈은 services 층 상수 · 순수 함수만(쿼리 0). models 는 CHECK 글을 자기 글로 들고 있다(순환 import — ``part_constants`` 와 같은 까닭).
"""

from __future__ import annotations

from typing import Any, Optional

from foms.services.production.part_constants import team_can_hold_production_part

FACTORY_1 = 1
FACTORY_2 = 2
#: 공장 번호(화면 순서).
FACTORIES: tuple[int, ...] = (FACTORY_1, FACTORY_2)
#: 비었을 때의 공장(NULL = 1공장 — 지금과 같음).
DEFAULT_FACTORY = FACTORY_1
FACTORY_LABELS: dict[int, str] = {FACTORY_1: "1공장", FACTORY_2: "2공장"}


def normalize_factory(raw: Any) -> Optional[int]:
    """폼 · 몸 값 하나를 공장 번호로 바꾼다.

    Args:
        raw: 받은 값(1 · 2 · "1" · "2", 앞뒤 빈칸 허용). 빈 값 · None 은 None.

    Returns:
        1 · 2 또는 None.

    Raises:
        ValueError: 비어 있지 않은데 1 · 2 가 아닐 때(불린 포함 — 조용히 버리지 않는다).
    """
    if raw is None or (isinstance(raw, str) and not raw.strip()):
        return None
    if isinstance(raw, bool):
        raise ValueError("알 수 없는 공장이에요.")
    try:
        value = int(str(raw).strip())
    except ValueError:
        raise ValueError("알 수 없는 공장이에요.") from None
    if value not in FACTORIES:
        raise ValueError("알 수 없는 공장이에요.")
    return value


def production_factory_for_team(team: Optional[str], factory: Optional[int]) -> Optional[int]:
    """저장할 계정 공장 — 생산팀이고 2공장이면 2, 그 밖(1공장 · 다른 팀 · 없음)은 None(= 1공장).

    Args:
        team: 같이 저장할 팀 글.
        factory: :func:`normalize_factory` 를 거친 값.

    Returns:
        2 또는 None.
    """
    return FACTORY_2 if factory == FACTORY_2 and team_can_hold_production_part(team) else None


def stored_production_factory(user: Any) -> int:
    """행에 적힌 공장(팀은 안 본다 — 감사 스냅샷용). NULL · 모르는 값 = 1공장."""
    return FACTORY_2 if getattr(user, "production_factory", None) == FACTORY_2 else FACTORY_1


def account_production_factory(user: Any) -> Optional[int]:
    """생산팀 계정의 공장(1 · 2) — 생산팀이 아니면 None(이미 읽은 행, 쿼리 0). 관리자 두 공장은 ``part_access`` 가 본다.

    Args:
        user: 사용자 객체(``team`` · ``production_factory`` 를 읽는다). None 허용.

    Returns:
        1 · 2 또는 None.
    """
    if user is None or not team_can_hold_production_part(getattr(user, "team", None)):
        return None
    return stored_production_factory(user)


def factory_label(factory: Any) -> str:
    """공장 번호 → "1공장" · "2공장"(모르는 값은 1공장 — 비면 1공장인 규칙과 같다)."""
    return FACTORY_LABELS.get(factory, FACTORY_LABELS[DEFAULT_FACTORY])
