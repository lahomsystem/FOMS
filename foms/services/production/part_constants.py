"""생산 파트(재단 · 엣지 · 조립 · 검수) 상수와 계정 파트 판정 — 한 곳 규칙(PRODPART, 설계서 §15.3).

설계 정본: ``docs/specs/2026-11-09-tablet-production-ui_SPEC.md`` §15(D47 계정 하나에 파트 하나 ·
D49 재단 상태 넷 · D51/D52 배지 색).

* 파트 key 는 주문 공정 칸 key(``foms/api/production/orders.py`` 의 ``_PRODUCTION_STEP_DEFS``)와 같다 —
  시험(``tests/domains/test_production_part_marks_model.py``)이 고정한다. 이 모듈은 services 층이라
  api 모듈을 import 하지 않는다(레이어 래칫).
* 표 ``production_part_marks`` 의 CHECK 글(``models.py`` ``ProductionPartMark`` · ``User``)은 models 가
  자기 글로 들고 있다 — models 가 이 모듈을 부르면 ``order_mutation_policy`` → ``partner_scope`` → models
  순환이 생긴다. 같은 값인지는 같은 시험이 본다.
* 계정 파트는 생산팀일 때만 뜻이 있다. 팀이 바뀌어도 칸 값이 남을 수 있으니 읽는 쪽은 늘
  :func:`account_production_parts` 를 거친다(생산팀이 아니면 빈 것).
* 계정마다 파트 0 ~ 4개(설계서 ``docs/specs/2026-11-23-production-self-claim-and-factory2_SPEC.md`` §4-12 · §6-1, P2).
  새 칸 ``users.production_parts``(목록)가 기준이고, 옛 칸 ``production_part`` 는 한 판 동안 첫 파트를 같이 적는다
  (:func:`production_part_columns` — 되돌린 옛 코드가 맞는 파트를 읽게). 둘이 어긋나면 옛 코드가 나중에 고친 것이라
  옛 칸을 따른다(:func:`account_production_parts`).
"""

from __future__ import annotations

from typing import Any, Optional

from foms.services.orders.order_mutation_policy import team_has_capability

PART_CUT = "cut"
PART_EDGE = "edge"
PART_ASSEMBLE = "assemble"
PART_INSPECT = "inspect"

#: 파트 key · 한글 이름(화면 순서 = 공정 순서).
PRODUCTION_PART_DEFS: tuple[tuple[str, str], ...] = (
    (PART_CUT, "재단"),
    (PART_EDGE, "엣지"),
    (PART_ASSEMBLE, "조립"),
    (PART_INSPECT, "검수"),
)
PRODUCTION_PART_KEYS: tuple[str, ...] = tuple(key for key, _ in PRODUCTION_PART_DEFS)
PRODUCTION_PART_LABELS: dict[str, str] = dict(PRODUCTION_PART_DEFS)

#: 표시 상태 — 안 봄 · 안 고름(되돌림 포함) / 작업 필요 / 기본(재단만) / 끝.
MARK_STATE_NONE = "NONE"
MARK_STATE_NEED = "NEED"
MARK_STATE_BASIC = "BASIC"
MARK_STATE_DONE = "DONE"
PART_MARK_STATES: tuple[str, ...] = (MARK_STATE_NONE, MARK_STATE_NEED, MARK_STATE_BASIC, MARK_STATE_DONE)

#: '기본'(이미 잘라 둔 판)은 재단에만 있다(D49 · D57).
BASIC_ALLOWED_PART = PART_CUT

#: 파트를 가질 수 있는 팀(능력 이름 — 별칭 팀도 ``team_has_capability`` 가 같이 판정한다).
PRODUCTION_PART_TEAMS: tuple[str, ...] = ("PRODUCTION",)

#: 배지 · 칩 클래스 이름 자리(모양은 화면 단계 P15-5 의 ``static/css/contexts/production/parts.css``).
#: 무채색 배지는 두지 않는다(D52) — 안 봄 · 안 고름은 배지 없이 다른 파트 한 줄만 보인다.
PART_BADGE_CLASSES: dict[str, str] = {
    "need": "fph-part-badge--need",
    "taken": "fph-part-badge--taken",
    "done": "fph-part-badge--done",
    "basic": "fph-part-badge--basic",
    "wait": "fph-part-chip--wait",
}


def normalize_production_part(raw: Any) -> Optional[str]:
    """폼 · 몸 값 하나를 파트 key 로 바꾼다.

    Args:
        raw: 받은 값(앞뒤 빈칸 · 대문자 허용).

    Returns:
        네 key 중 하나. 빈 값이면 None.

    Raises:
        ValueError: 비어 있지 않은데 네 key 가 아닐 때(조용히 버리지 않는다).
    """
    text = str(raw or "").strip().lower()
    if not text:
        return None
    if text not in PRODUCTION_PART_KEYS:
        raise ValueError(f"알 수 없는 생산 파트예요: {text}")
    return text


def team_can_hold_production_part(team: Optional[str]) -> bool:
    """팀이 생산 파트를 가질 수 있는지(생산팀).

    Args:
        team: 사용자 팀 글.

    Returns:
        생산팀(능력 PRODUCTION)이면 True.
    """
    return team_has_capability(team, PRODUCTION_PART_TEAMS)


def production_part_for_team(team: Optional[str], part: Optional[str]) -> Optional[str]:
    """저장할 계정 파트 — 생산팀이 아니면 None 으로 비운다(설계서 §15.3).

    Args:
        team: 저장할 팀 글.
        part: :func:`normalize_production_part` 를 거친 파트 key 또는 None.

    Returns:
        생산팀이면 ``part`` 그대로, 아니면 None.
    """
    return part if team_can_hold_production_part(team) else None


def normalize_production_parts(raw: Any) -> Optional[list[str]]:
    """폼 · 몸의 파트 여럿 → 저장할 목록(설계서 2026-11-23 §6-1).

    Args:
        raw: 받은 값들(목록 · 튜플 · 집합, 또는 글 하나 · None). 빈 글은 건너뛴다.

    Returns:
        정의 순서(재단 → 엣지 → 조립 → 검수) · 겹침 뺀 key 목록. 하나도 없으면 None(빈 목록은 저장하지 않는다 = NULL).

    Raises:
        ValueError: 네 key 가 아닌 값이 하나라도 있을 때(조용히 버리지 않는다).
    """
    values = list(raw) if isinstance(raw, (list, tuple, set, frozenset)) else [raw]
    picked = {part for part in (normalize_production_part(value) for value in values) if part}
    return [key for key in PRODUCTION_PART_KEYS if key in picked] or None


def production_part_columns(team: Optional[str], parts: Optional[list[str]]) -> tuple[Optional[list[str]], Optional[str]]:
    """저장할 두 칸 — 새 칸 ``production_parts`` · 옛 칸 ``production_part``(= 첫 파트). 생산팀이 아니면 둘 다 비운다.

    Args:
        team: 같이 저장할 팀 글.
        parts: :func:`normalize_production_parts` 를 거친 목록 또는 None.

    Returns:
        ``(새 칸 값, 옛 칸 값)`` — 파트가 없으면 ``(None, None)``.
    """
    kept = list(parts) if parts and team_can_hold_production_part(team) else None
    return kept, (kept[0] if kept else None)


def stored_production_parts(user: Any) -> tuple[str, ...]:
    """행에 적힌 파트(팀은 안 본다) — 새 칸이 기준. 새 칸이 비었거나 새 칸 첫 값이 옛 칸과 다르면 옛 칸 하나.

    새 코드는 두 칸을 늘 같이 쓴다(옛 칸 = 첫 파트). 옛 코드(배포 중 아직 도는 판 · 되돌린 판)는 옛 칸만 고치므로, 둘이 어긋나면
    옛 칸이 나중 값이다. 마이그레이션 전에 만든 행 · 새 칸을 모르는 판이 만든 행은 새 칸이 NULL 이라 옛 칸을 읽는다.

    Args:
        user: 사용자 객체(``production_parts`` · ``production_part`` 를 읽는다). None 허용.

    Returns:
        네 key 중 0 ~ 4개(정의 순서).
    """
    legacy = getattr(user, "production_part", None)
    legacy = legacy if legacy in PRODUCTION_PART_KEYS else None
    raw = getattr(user, "production_parts", None)
    parts = tuple(key for key in PRODUCTION_PART_KEYS if isinstance(raw, (list, tuple)) and key in raw)
    if not parts or parts[0] != legacy:
        return (legacy,) if legacy else ()
    return parts


def account_production_parts(user: Any) -> tuple[str, ...]:
    """계정의 생산 파트들(설계서 2026-11-23 §4-12) — 정의 순서. 생산팀이 아니거나 값이 없으면 빈 tuple.

    Args:
        user: 사용자 객체(``team`` · ``production_parts`` · ``production_part`` 를 읽는다 — 이미 읽은 행, 쿼리 0). None 허용.

    Returns:
        네 key 중 0 ~ 4개.
    """
    if user is None or not team_can_hold_production_part(getattr(user, "team", None)):
        return ()
    return stored_production_parts(user)


def account_production_part(user: Any) -> Optional[str]:
    """계정의 첫 생산 파트 key(옛 칸 ``production_part`` 와 같은 값) — 생산팀이 아니거나 값이 없으면 None.

    Args:
        user: 사용자 객체. None 허용.

    Returns:
        네 key 중 하나 또는 None.
    """
    parts = account_production_parts(user)
    return parts[0] if parts else None


def production_part_label(part: Optional[str]) -> Optional[str]:
    """파트 key → 한글 이름(재단 · 엣지 · 조립 · 검수). 모르는 값 · None 은 None."""
    return PRODUCTION_PART_LABELS.get(part or "")


def production_parts_label(parts: Any) -> Optional[str]:
    """파트 key 여럿 → "재단 · 엣지"(정의 순서). 하나도 없으면 None."""
    labels = [PRODUCTION_PART_LABELS[key] for key in PRODUCTION_PART_KEYS if parts and key in parts]
    return " · ".join(labels) or None
