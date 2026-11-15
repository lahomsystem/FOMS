"""FOMS 접목판 스위치 판정 한 곳(설계서 ``docs/specs/2026-11-14-foms-graft_SPEC.md`` 4절 — 모두 처음 끔).

- 스위치 아홉은 env 다. 사람별 스위치는 ``<이름>_ENABLED`` + ``<이름>_COHORT``(사용자 번호들 또는 ``all``) —
  :func:`foms.services.feature_flags.is_enabled_for_user` 그대로. 뒤 셋(``FOMS_GRAFT_PROPOSERS`` · ``…_CONSTRUCTION_ALIMTALK``
  · ``…_PUSH``)은 ``_ENABLED`` 하나(사람별 아님 — 밤 단계 · 제안을 만드는 서비스가 읽는다, 설계서 3.13 · 3.14).
- 기대는 스위치: ``actions`` 는 ``brain_ui`` 도 켜진 사람만, 분홍 칸 셋(``cell_pc`` · ``cell_tablet`` · ``cell_mobile``)은
  ``actions`` 도 켜진 사람만 참이다. 전역 판정(:func:`enabled_global`)도 같은 사슬을 전역 스위치로 본다.
- DB 를 읽지 않는다(env 만) — 메뉴 · 레일처럼 모든 화면에서 불러도 질의가 늘지 않는다.
- 템플릿 전역 ``graft_enabled('<짧은 이름>')`` 은 :mod:`foms.web.brain` 이 ``g.current_user`` 로 올린다.
"""

from __future__ import annotations

from typing import Any

from foms.services.feature_flags import env_bool, is_enabled_for_user

__all__ = [
    "FLAGS",
    "GLOBAL_ONLY",
    "REQUIRES",
    "SHORT_NAMES",
    "enabled",
    "enabled_global",
    "flag_name",
]

#: 짧은 이름 → env 이름 머리(``_ENABLED`` · ``_COHORT`` 를 붙여 읽는다). 설계서 4절 표 차례.
FLAGS: dict[str, str] = {
    "brain_ui": "FOMS_GRAFT_BRAIN_UI",
    "erp_read": "FOMS_GRAFT_ERP_READ",
    "actions": "FOMS_GRAFT_ACTIONS",
    "cell_pc": "FOMS_GRAFT_CELL_PC",
    "cell_tablet": "FOMS_GRAFT_CELL_TABLET",
    "cell_mobile": "FOMS_GRAFT_CELL_MOBILE",
    "proposers": "FOMS_GRAFT_PROPOSERS",
    "construction_alimtalk": "FOMS_GRAFT_CONSTRUCTION_ALIMTALK",
    "push": "FOMS_GRAFT_PUSH",
}

#: 짧은 이름 차례(템플릿 · 시험이 같이 쓴다).
SHORT_NAMES: tuple[str, ...] = tuple(FLAGS)

#: 사람별이 아닌 스위치 — ``_ENABLED`` 하나만 본다(``_COHORT`` 를 읽지 않는다).
GLOBAL_ONLY: frozenset[str] = frozenset({"proposers", "construction_alimtalk", "push"})

#: 함께 켜져 있어야 참인 스위치(한 걸음 — 사슬은 판정 함수가 따라간다).
REQUIRES: dict[str, str] = {
    "actions": "brain_ui",
    "cell_pc": "actions",
    "cell_tablet": "actions",
    "cell_mobile": "actions",
}

_BY_ENV: dict[str, str] = {env: short for short, env in FLAGS.items()}


def flag_name(name: str) -> str:
    """짧은 이름 또는 env 이름 머리(``FOMS_GRAFT_…``, ``_ENABLED`` 붙어도 됨)를 짧은 이름으로 바꾼다.

    Args:
        name: ``'brain_ui'`` · ``'FOMS_GRAFT_BRAIN_UI'`` · ``'FOMS_GRAFT_BRAIN_UI_ENABLED'`` 같은 이름.

    Returns:
        :data:`FLAGS` 의 짧은 이름.

    Raises:
        ValueError: 모르는 이름(글자 틀림을 조용히 '끔'으로 삼키지 않는다).
    """
    raw = str(name or "").strip()
    if raw in FLAGS:
        return raw
    base = raw[: -len("_ENABLED")] if raw.endswith("_ENABLED") else raw
    if base in _BY_ENV:
        return _BY_ENV[base]
    raise ValueError(f"모르는 접목판 스위치: {raw!r}")


def _own_global(short: str) -> bool:
    """그 스위치 하나의 전역 켬(``<이름>_ENABLED``)만 — 기대는 스위치는 보지 않는다."""
    return env_bool(f"{FLAGS[short]}_ENABLED")


def _own_for_user(short: str, user_id: int | None) -> bool:
    """그 스위치 하나의 사람별 켬 — 사람별이 아닌 스위치는 전역 켬."""
    if short in GLOBAL_ONLY:
        return _own_global(short)
    return is_enabled_for_user(FLAGS[short], user_id)


def enabled(name: str, user: Any) -> bool:
    """이 사람에게 켜져 있나 — 기대는 스위치까지 모두 켜져야 참.

    Args:
        name: 짧은 이름(:data:`SHORT_NAMES`) 또는 env 이름.
        user: 로그인 사용자(``id`` 를 읽는다) 또는 ``None``(로그인 안 함 = 사람별 스위치는 끔).

    Returns:
        켜져 있으면 True.
    """
    short = flag_name(name)
    user_id = getattr(user, "id", None) if user is not None else None
    while True:
        if not _own_for_user(short, user_id):
            return False
        if short not in REQUIRES:
            return True
        short = REQUIRES[short]


def enabled_global(name: str) -> bool:
    """전역 스위치(``_ENABLED``)만으로 켜져 있나 — 사람 목록은 보지 않는다. 기대는 스위치도 전역으로 본다.

    미리 그려 두는 조각(대시보드 표 · 폰 홈)의 빈 자리처럼 사람마다 갈라 그리면 안 되는 곳에 쓴다(설계서 4절).

    Args:
        name: 짧은 이름 또는 env 이름.

    Returns:
        전역으로 켜져 있으면 True.
    """
    short = flag_name(name)
    while True:
        if not _own_global(short):
            return False
        if short not in REQUIRES:
            return True
        short = REQUIRES[short]
