"""모바일 홈 달력 — 시공 금액별 칸 색 기준: 회사 전체가 공유하는 전역 설정 (2026-10-14).

근거: docs/specs/2026-10-14-mobile-calendar-amount-colors_SPEC.md

왜 전역인가
-----------
"이 날은 많이 나간다"는 표시는 팀 배치 이야기를 할 때 모두가 같은 칸을 보고 말해야 뜻이 있다.
그래서 기준은 사람마다가 아니라 **한 벌**이고, 고치는 사람은 관리자·팀장이다(사용자 결정 2026-10-14).

저장 자리
---------
새 표를 파지 않는다 — ``SystemSetting`` 키 하나. 모양은 반품 거부 상용구
(:mod:`foms.services.integrations.naver_commerce.reject_templates`)와 같다: 통째 저장 + 낙관적 잠금,
영수증 표는 두지 않는다(되돌릴 수 있는 설정이고 재전송의 최악은 같은 값을 한 번 더 쓰는 것).

값과 단위
---------
``{"enabled": bool, "yellow_from": int|None, "pink_from": int|None}`` — 금액 단위는 **만 원**
(달력 칸이 보여 주는 단위와 같다). None = 그 단계를 쓰지 않음. 분홍이 노랑보다 우선한다.
"""

from __future__ import annotations

import copy
from typing import Any, Optional

from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from models import SystemSetting

__all__ = [
    "CALENDAR_COLORS_KEY",
    "DEFAULT_COLORS",
    "MAX_MAN",
    "CalendarColorsError",
    "CalendarColorsConflict",
    "sanitize_colors",
    "load_colors",
    "colors_version",
    "save_colors",
    "tone_for",
]

CALENDAR_COLORS_KEY = "mobile_calendar_amount_colors"

#: 저장된 값이 없을 때 쓰는 기준(사용자 예시 2026-10-14: 2,500만 노랑 · 3,000만 분홍).
DEFAULT_COLORS: dict[str, Any] = {"enabled": True, "yellow_from": 2500, "pink_from": 3000}

#: 입력 상한(만 원) — 10억. 하루 시공 출고가가 이를 넘는 일은 없다.
MAX_MAN = 100_000


class CalendarColorsError(Exception):
    """기준을 저장할 수 없는 입력 — 사유를 사람에게 그대로 보여준다."""


class CalendarColorsConflict(CalendarColorsError):
    """다른 사람이 먼저 저장했다(낙관적 잠금 충돌)."""

    def __init__(self, message: str, *, current_version: int) -> None:
        super().__init__(message)
        self.current_version = int(current_version)


def _threshold(value: Any) -> tuple[Optional[int], str]:
    """기준 한 칸 → (만 원 정수 또는 None(빈 칸), 오류 문장). 오류가 없으면 빈 문자열."""
    if value is None or (isinstance(value, str) and not value.strip()):
        return None, ""
    text = str(value).replace(",", "").strip()
    if isinstance(value, bool) or not text.isdigit():
        return None, "기준은 0 이상의 숫자로 넣어 주세요."
    number = int(text)
    if number > MAX_MAN:
        return None, f"기준은 0~{MAX_MAN:,}만 원 사이로 넣어 주세요."
    return number, ""


def _clean(value: Any) -> tuple[Optional[dict[str, Any]], str]:
    """정규화 본체 — 예외 없이 (값, 오류 문장)을 돌려준다(읽기 경로가 오류를 삼키지 않게)."""
    if not isinstance(value, dict):
        return None, "저장할 기준이 없습니다."
    yellow, err_y = _threshold(value.get("yellow_from"))
    pink, err_p = _threshold(value.get("pink_from"))
    if err_y or err_p:
        return None, err_y or err_p
    if yellow is not None and pink is not None and pink <= yellow:
        return None, "분홍 기준은 노랑 기준보다 커야 해요."
    return {"enabled": bool(value.get("enabled", True)), "yellow_from": yellow, "pink_from": pink}, ""


def sanitize_colors(value: Any) -> dict[str, Any]:
    """신뢰할 수 없는 입력을 저장 모양으로 정규화한다.

    Args:
        value: ``{"enabled", "yellow_from", "pink_from"}`` 기대.

    Returns:
        정규화된 dict.

    Raises:
        CalendarColorsError: 숫자가 아니거나 범위 밖, 또는 분홍 기준이 노랑 기준 이하일 때.
    """
    cleaned, error = _clean(value)
    if cleaned is None:
        raise CalendarColorsError(error)
    return cleaned


def _row(session: Session, *, for_update: bool = False) -> Optional[SystemSetting]:
    query = session.query(SystemSetting).filter(SystemSetting.setting_key == CALENDAR_COLORS_KEY)
    if for_update:
        query = query.with_for_update()
    return query.first()


def load_colors(session: Session) -> dict[str, Any]:
    """지금 쓰는 기준 — **저장된 것이 없거나 깨졌으면 기본값**.

    기본값을 DB 에 미리 심지 않는다(반품 거부 상용구와 같은 이유: 손대지 않은 상태와
    끈 상태를 구분하려면 '행 없음'이 기본값이어야 한다).
    """
    row = _row(session)
    # 저장 경로가 검증하므로 깨진 값은 손으로 넣은 것뿐 — 그때는 기본값으로 그린다.
    cleaned, _error = _clean(row.setting_value) if row is not None else (None, "")
    return cleaned if cleaned is not None else dict(DEFAULT_COLORS)


def colors_version(session: Session) -> int:
    """낙관적 잠금 버전(저장 행이 없으면 0 — 화면이 그 값을 그대로 되보낸다)."""
    row = _row(session)
    return int(getattr(row, "version", 0) or 0) if row is not None else 0


def save_colors(session: Session, *, value: Any, if_match_version: Optional[int]) -> dict[str, Any]:
    """기준을 통째로 저장한다 (커밋은 호출자가 소유한다).

    Args:
        session: DB 세션.
        value: 저장할 기준(정규화 전).
        if_match_version: 화면이 읽은 버전. 지금 값과 다르면 저장하지 않는다(None 도 거부 —
            버전 없이 쓰면 다른 사람이 막 바꾼 값을 조용히 덮는다).

    Returns:
        ``{"colors": {...}, "version": int}``.

    Raises:
        CalendarColorsError: 입력 오류.
        CalendarColorsConflict: 버전 불일치.
    """
    cleaned = sanitize_colors(value)
    row = _row(session, for_update=True)
    current = int(getattr(row, "version", 0) or 0) if row is not None else 0
    if if_match_version is None or int(if_match_version) != current:
        raise CalendarColorsConflict(
            "다른 사람이 먼저 바꿨어요. 새로 불러올게요.", current_version=current)

    if row is None:
        row = SystemSetting(
            setting_key=CALENDAR_COLORS_KEY,
            setting_value=copy.deepcopy(cleaned),
            description="모바일 홈 달력 시공 금액별 칸 색 기준(전역 공유, 관리자·팀장 수정)",
            version=1,
        )
        session.add(row)
        next_version = 1
    else:
        # JSONB 는 통째로 갈아 끼우고 flag_modified 를 붙인다(프로젝트 규약).
        row.setting_value = copy.deepcopy(cleaned)
        flag_modified(row, "setting_value")
        next_version = current + 1
        row.version = next_version
    session.flush()
    return {"colors": cleaned, "version": next_version}


def tone_for(amount_won: int | None, colors: dict[str, Any]) -> str:
    """그날 시공 출고가 합(원) → 칸 색 ``"pink"|"yellow"|""``. 분홍 우선, 꺼져 있으면 빈 문자열."""
    if not colors.get("enabled") or not amount_won:
        return ""
    man = int(round(amount_won / 10000))  # 칸에 보이는 금액(만 원 반올림)과 같은 값으로 비교
    pink, yellow = colors.get("pink_from"), colors.get("yellow_from")
    if pink is not None and man >= pink:
        return "pink"
    if yellow is not None and man >= yellow:
        return "yellow"
    return ""
