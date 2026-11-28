"""생산 화면 스위치의 템플릿 플래그 — ``inject_foms_flags`` 가 한 줄로 펼쳐 싣는다.

``foms/services/context_processors.py`` 는 500줄 래칫에 닿아 있어 스위치가 늘 때마다 줄을 더할 수 없다. 생산 화면 스위치의
템플릿 플래그는 여기 한 곳에 모은다. 값은 각 모듈의 ``enabled()`` 를 그대로 옮긴다(스위치를 읽는 곳은 그 모듈 하나).

* ``flag_floor_alarm`` — 생산 현장 알람(:func:`foms.services.production.floor_alarm.enabled`). 거짓이면 알람 조각은 아무것도 안 그린다.
* ``flag_pen_record`` — 생산 도면 펜 기록(:func:`foms.services.production.pen_record.enabled`, 설계서 2026-11-28 §9-5 약속 6).
  거짓이면 펜 기록의 새 마크업이 0 이다.
"""

from __future__ import annotations

from foms.services.production import floor_alarm, pen_record


def production_template_flags() -> dict[str, bool]:
    """생산 화면 스위치 템플릿 플래그(쿼리 0 — 환경 변수만 읽는다).

    Returns:
        ``{"flag_floor_alarm": bool, "flag_pen_record": bool}``.
    """
    return {"flag_floor_alarm": floor_alarm.enabled(), "flag_pen_record": pen_record.enabled()}


__all__ = ["production_template_flags"]
