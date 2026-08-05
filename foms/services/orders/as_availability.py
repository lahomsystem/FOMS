"""AS 방문 가능시간 (`schedule.as_visit.availability`) SSOT.

스키마: {"days": "any|weekday|weekend", "time": "any|am|pm|evening", "note": str<=80}
- 미기입(키 부재)과 명시적 '무관'(any)을 구분한다 — 지도 필터가 "미기입 N건 제외"를
  고지해야 하므로 기본값 주입 금지.
- 쓰기 경로: /api/update_order_field `as_visit_availability` (field_update.py).
"""
from __future__ import annotations

from typing import Any, Optional

AS_AVAILABILITY_DAYS = ("any", "weekday", "weekend")
AS_AVAILABILITY_TIMES = ("any", "am", "pm", "evening")
AS_AVAILABILITY_DAY_LABELS = {"any": "요일무관", "weekday": "평일", "weekend": "주말"}
AS_AVAILABILITY_TIME_LABELS = {"any": "시간무관", "am": "오전", "pm": "오후", "evening": "저녁"}
AS_AVAILABILITY_NOTE_MAX = 80


def normalize_as_availability(value: Any) -> Optional[dict]:
    """가능시간 입력을 canonical dict로 정규화한다.

    Args:
        value: 클라이언트 입력(dict 또는 None/빈값).

    Returns:
        {"days","time"[,"note"]} 또는 None(초기화 — 전부 무관·메모 없음 포함).

    Raises:
        ValueError: 형식/값이 허용 집합을 벗어날 때.
    """
    if value in (None, "", {}):
        return None
    if not isinstance(value, dict):
        raise ValueError("가능시간 형식이 올바르지 않습니다.")
    days = str(value.get("days") or "any").strip().lower()
    time = str(value.get("time") or "any").strip().lower()
    note = str(value.get("note") or "").strip()[:AS_AVAILABILITY_NOTE_MAX]
    if days not in AS_AVAILABILITY_DAYS:
        raise ValueError("가능 요일 값이 올바르지 않습니다.")
    if time not in AS_AVAILABILITY_TIMES:
        raise ValueError("가능 시간대 값이 올바르지 않습니다.")
    if days == "any" and time == "any" and not note:
        return None
    out: dict = {"days": days, "time": time}
    if note:
        out["note"] = note
    return out


def as_availability_label(avail: Optional[dict]) -> str:
    """가능시간 dict를 사람이 읽는 라벨로 ("주말·오후 (경비실 경유)")."""
    if not isinstance(avail, dict) or not avail:
        return ""
    days = AS_AVAILABILITY_DAY_LABELS.get(str(avail.get("days") or "any"), "")
    time = AS_AVAILABILITY_TIME_LABELS.get(str(avail.get("time") or "any"), "")
    parts = [p for p in (days, time) if p]
    label = "·".join(parts)
    note = str(avail.get("note") or "").strip()
    if note:
        label = f"{label} ({note})" if label else f"({note})"
    return label


def get_as_availability(structured_data: Any) -> Optional[dict]:
    """structured_data에서 availability 블록을 읽는다(없으면 None)."""
    if not isinstance(structured_data, dict):
        return None
    schedule = structured_data.get("schedule")
    if not isinstance(schedule, dict):
        return None
    as_visit = schedule.get("as_visit")
    if not isinstance(as_visit, dict):
        return None
    avail = as_visit.get("availability")
    return avail if isinstance(avail, dict) and avail else None


__all__ = [
    "AS_AVAILABILITY_DAYS",
    "AS_AVAILABILITY_TIMES",
    "AS_AVAILABILITY_DAY_LABELS",
    "AS_AVAILABILITY_TIME_LABELS",
    "normalize_as_availability",
    "as_availability_label",
    "get_as_availability",
]
