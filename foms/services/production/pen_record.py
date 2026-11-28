"""생산 도면 펜 기록 — 스위치와 문(설계서 ``docs/specs/2026-11-28-production-pen-record_SPEC.md`` §4-1 · §9-1 · §9-5 약속 1).

API(일꾼 ⓑ) · 화면(일꾼 ⓒ)은 이 모듈의 함수 셋만 부른다. 이름 · 인자는 약속이라 바꾸지 않는다.

* :func:`enabled` — 스위치 :data:`SWITCH_ENV`(기본 꺼짐)를 읽는 곳은 여기 하나다(현장 알람 ``floor_alarm.enabled`` 와 같은 꼴).
  꺼져 있으면 도면 보기 · 카드 · 작업 시트 · 쿼리가 지금과 한 글자도 같고 API 는 404 다. 템플릿 플래그 ``flag_pen_record`` 도
  이 값이다(:mod:`foms.services.production.screen_flags`).
* :func:`can_write` — 쓰기 문 = 스위치 켜짐 + 생산 쓰기 권한(:func:`~foms.services.production.write_access.can_write_production` —
  활성 · 협력사 아님 · 조회 전용 아님 · 관리자 또는 생산팀) + 계정 칸 '펜 기록 쓰기'. 반장이어도 칸이 꺼져 있으면 못 쓰고
  (3번 답 "따로 정한 사람만"), 관리자도 칸을 켜야 쓴다(13번 답).
* :func:`sees_note_first` — 기록이 있는 도면을 열 때 생산 기록이 먼저 보이는지(2 · 5번 답 — 쓰기 칸과 따로 정한다).
  나머지는 원본이 먼저 보이고 누구나 눌러 바꿔 볼 수 있다(6번 답).

셋 다 이미 읽은 사용자 행만 보므로 쿼리 0 이다. 마이그레이션 · 계정 칸 · 첨부 분류 '생산'은 스위치와 상관없이 올라간다.
"""

from __future__ import annotations

from typing import Any

from foms.services.feature_flags import env_bool
from foms.services.production.part_constants import account_pen_first, account_pen_write
from foms.services.production.write_access import can_write_production

SWITCH_ENV = "FOMS_PRODUCTION_PEN_RECORD"


def enabled() -> bool:
    """펜 기록 스위치가 켜졌는지 — 읽는 곳은 여기 하나(환경 변수 ``FOMS_PRODUCTION_PEN_RECORD``, 없거나 ``off`` = 꺼짐).

    Returns:
        켜졌으면 True.
    """
    return env_bool(SWITCH_ENV, False)


def can_write(user: Any) -> bool:
    """도면에 펜 기록을 쓰고 고칠 수 있는지(쓰기 문 — 단추를 그릴지 · 저장 API 가 받을지 둘 다 이것을 본다).

    Args:
        user: 사용자 객체(None 허용). ``role`` · ``team`` · ``partner_org_id`` · ``is_active`` · ``production_pen_write`` 를 읽는다.

    Returns:
        스위치 켜짐 + 생산 쓰기 권한 + '펜 기록 쓰기' 칸 켜짐이면 True.
    """
    return enabled() and can_write_production(user) and account_pen_write(user)


def sees_note_first(user: Any) -> bool:
    """기록이 있는 도면을 열면 생산 기록이 먼저 보이는지('생산 기록 먼저 보기' 칸).

    Args:
        user: 사용자 객체(None 허용). ``role`` · ``team`` · ``production_pen_first`` 를 읽는다.

    Returns:
        스위치 켜짐 + 칸 켜짐(생산팀 · 관리자)이면 True. 그 밖은 원본이 먼저.
    """
    return enabled() and account_pen_first(user)


__all__ = ["SWITCH_ENV", "can_write", "enabled", "sees_note_first"]
