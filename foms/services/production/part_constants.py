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
* 반장(설계서 2026-11-23 '승인 때 고친 것' 5) = 생산팀 계정에서 관리자가 체크한 사람(``users.production_lead``) —
  :func:`account_production_lead`. 파트와 따로다(반장이 파트를 가져도 된다).
* 펜 기록 칸 둘(설계서 2026-11-28 펜 기록 §4-1) = '펜 기록 쓰기' · '생산 기록 먼저 보기'(``users.production_pen_write`` ·
  ``production_pen_first``) — :func:`account_pen_write` · :func:`account_pen_first`. 반장과 달리 관리자(ADMIN)도 칸을 가진다.
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

#: 표시 상태 — 안 봄 · 안 고름(되돌림 포함) / 작업 필요 / 기본(재단 '기본' · 조립 '조립 없음') / 끝.
MARK_STATE_NONE = "NONE"
MARK_STATE_NEED = "NEED"
MARK_STATE_BASIC = "BASIC"
MARK_STATE_DONE = "DONE"
PART_MARK_STATES: tuple[str, ...] = (MARK_STATE_NONE, MARK_STATE_NEED, MARK_STATE_BASIC, MARK_STATE_DONE)
#: '도면 없음' 주문 카드의 약속 key(설계서 2026-11-28-production-my-steps-flow §3-5 · 답 11) — 확정 도면이 0장인 생산 단계 주문의 표시 줄
#: 한 장(파트마다). 저장소 key(``orders/…``)는 ``@`` 로 시작하지 않아 겹치지 않는다. 규칙 · 도우미는 :mod:`.order_card`.
ORDER_CARD_KEY = "@order"

#: '기본'(이미 잘라 둔 판)은 재단 낱말이다(D49 · D57) — 감사 글의 재단 낱말 갈래("안 봄")가 쓴다.
BASIC_ALLOWED_PART = PART_CUT
#: 사람 손 없이 장을 끝낼 수 있는(상태 ``BASIC``) 파트들 — 재단 '기본' + 조립 '조립 없음'(사장님 2026-11-28 "조립 없음" · "조립만",
#: 설계서 2026-11-28 흐름 셋 §3). ``part_progress.mark_finished`` 가 이것을 읽어 검수 열림 · 제작 완료 · "조립 2/3" · 공정 칸이 같이 맞는다.
#: 엣지 · 검수에는 없다 — DB 제약 ``ck_production_part_marks_basic_part`` 도 같은 두 파트만 받는다(models.py · prodpart_03_basic_parts).
BASIC_ALLOWED_PARTS: tuple[str, ...] = (PART_CUT, PART_ASSEMBLE)
#: 파트마다 그 처리의 글 — 화면 · 감사 · 거절 글 · JS 설정이 모두 여기서 읽는다(JS 에 글을 따로 박지 않는다).
#: ``full`` = 단추 · 칸 · 문장 속 낱말, ``short`` = 다른 파트 한 줄 낱말("조립 없음" — 앞에 파트 이름이 이미 있다), ``ask`` = 확인 창 제목,
#: ``unseen`` = 판 머리 "<…> 3장"의 앞 글, ``audit`` = 일괄 감사 글 머리("재단 기본 50장" · "조립 없음 3장").
BASIC_WORDS: dict[str, dict[str, str]] = {
    PART_CUT: {"full": "기본", "short": "기본", "ask": "기본으로 처리할까요?", "unseen": "안 본 도면", "audit": "재단 기본"},
    PART_ASSEMBLE: {"full": "조립 없음", "short": "없음", "ask": "조립할 것이 없는 도면인가요?", "unseen": "미정 도면", "audit": "조립 없음"},
}

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


def basic_word(part: Any, short: bool = False) -> str:
    """그 파트의 '기본' 낱말 — 재단 "기본" · 조립 "조립 없음"(``short`` 면 "없음"). 그 처리가 없는 파트 · 모르는 값은 재단 낱말(지금 글).

    Args:
        part: 파트 key(None 허용).
        short: 다른 파트 한 줄 낱말이면 True.
    """
    words = BASIC_WORDS.get(part) or BASIC_WORDS[BASIC_ALLOWED_PART]
    return words["short" if short else "full"]


def basic_view(part: Any) -> Optional[dict[str, str]]:
    """판 · JS 설정에 싣는 그 파트의 '기본' 글 한 벌 — 그 처리가 없는 파트(엣지 · 검수)는 None(단추 · 일괄 머리 없음).

    Returns:
        ``{word, short, toward, ask, undo, undo_ask, unseen}`` — ``word`` = 단추 · 칸 글, ``toward`` = "기본으로" · "조립 없음으로",
        ``undo`` = 취소 단추 글, ``undo_ask`` = 취소 창 제목. 두 낱말 모두 받침으로 끝나 토씨는 '으로' · '을'이다.
    """
    words = BASIC_WORDS.get(part)
    if words is None:
        return None
    full = words["full"]
    return {"word": full, "short": words["short"], "toward": f"{full}으로", "ask": words["ask"], "undo": f"{full} 취소",
            "undo_ask": f"{full}을 취소할까요?", "unseen": words["unseen"]}


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


def production_lead_for_team(team: Optional[str], checked: bool) -> Optional[bool]:
    """저장할 반장 칸(설계서 2026-11-23 '승인 때 고친 것' 5) — 생산팀이고 체크했으면 참, 아니면 None(NULL = 반장 아님).

    Args:
        team: 같이 저장할 팀 글.
        checked: 관리자 화면의 '반장' 체크칸이 켜졌는지.

    Returns:
        ``True`` 또는 None — 다른 팀이면 체크했어도 비운다(팀을 바꾸면 같이 비워진다).
    """
    return True if checked and team_can_hold_production_part(team) else None


def stored_production_lead(user: Any) -> bool:
    """행에 적힌 반장 칸이 참인지(팀은 안 본다 — 감사 스냅샷용). NULL · 거짓 = 아님."""
    return getattr(user, "production_lead", None) is True


def account_production_lead(user: Any) -> bool:
    """계정이 반장인지 — 생산팀이고 반장 칸이 참(이미 읽은 행, 쿼리 0). 활성 · 역할은 :mod:`part_access` 가 같이 본다.

    Args:
        user: 사용자 객체(``team`` · ``production_lead`` 를 읽는다). None 허용.

    Returns:
        생산팀 + 반장 칸 참이면 True.
    """
    return user is not None and team_can_hold_production_part(getattr(user, "team", None)) and stored_production_lead(user)


def pen_account_eligible(team: Optional[str], role: Optional[str]) -> bool:
    """펜 기록 칸 둘(설계서 2026-11-28 펜 기록 §4-1)을 가질 수 있는 계정인지 — 생산팀 또는 관리자(ADMIN, 13번 답 "관리자도 칸을 켜야 씀").

    반장 칸(:func:`production_lead_for_team`)은 생산팀만이지만 이 칸 둘은 관리자도 켤 수 있어야 해서 역할을 같이 본다.
    """
    return team_can_hold_production_part(team) or str(role or "").strip().upper() == "ADMIN"


def pen_flag_for(team: Optional[str], role: Optional[str], checked: bool) -> Optional[bool]:
    """저장할 펜 기록 칸 하나(쓰기 · 먼저 보기 같은 규칙) — 켰고 생산팀 · 관리자면 참, 아니면 None(NULL = 꺼짐).

    Args:
        team: 같이 저장할 팀 글.
        role: 같이 저장할 역할 글.
        checked: 관리자 화면의 체크칸이 켜졌는지(화면에 칸이 없을 때는 지금 값).

    Returns:
        ``True`` 또는 None — 다른 팀(관리자 아님)이면 켰어도 비운다(팀 · 역할을 바꾸면 같이 비워진다).
    """
    return True if checked and pen_account_eligible(team, role) else None


def _account_pen_flag(user: Any, column: str) -> bool:
    if user is None or getattr(user, column, None) is not True:
        return False
    return pen_account_eligible(getattr(user, "team", None), getattr(user, "role", None))


def account_pen_write(user: Any) -> bool:
    """계정의 '펜 기록 쓰기' 칸이 켜졌는지 — 생산팀 · 관리자이고 칸이 참(이미 읽은 행, 쿼리 0).

    쓰기 문 전체(스위치 · 생산 쓰기 권한 · 활성)는 :func:`foms.services.production.pen_record.can_write` 가 본다.
    """
    return _account_pen_flag(user, "production_pen_write")


def account_pen_first(user: Any) -> bool:
    """계정의 '생산 기록 먼저 보기' 칸이 켜졌는지 — 생산팀 · 관리자이고 칸이 참(쿼리 0). 화면 판정은 ``pen_record.sees_note_first``."""
    return _account_pen_flag(user, "production_pen_first")


def production_part_label(part: Optional[str]) -> Optional[str]:
    """파트 key → 한글 이름(재단 · 엣지 · 조립 · 검수). 모르는 값 · None 은 None."""
    return PRODUCTION_PART_LABELS.get(part or "")


def production_parts_label(parts: Any) -> Optional[str]:
    """파트 key 여럿 → "재단 · 엣지"(정의 순서). 하나도 없으면 None."""
    labels = [PRODUCTION_PART_LABELS[key] for key in PRODUCTION_PART_KEYS if parts and key in parts]
    return " · ".join(labels) or None
