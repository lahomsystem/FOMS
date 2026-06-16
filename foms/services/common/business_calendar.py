"""Common business-day calendar helpers."""

from __future__ import annotations

import datetime
import json
from functools import lru_cache
from pathlib import Path
from typing import Optional, Set

from foms.services.datetime_kst import get_today_kst

_REPO_ROOT = Path(__file__).resolve().parents[3]
DATA_DIR = _REPO_ROOT / "data"

__all__ = [
    "get_holidays_kr",
    "is_business_day",
    "business_days_between",
    "business_days_until",
    "add_business_days",
]


def _load_holidays_json(year: int) -> Optional[Set[str]]:
    path = DATA_DIR / f"holidays_kr_{year}.json"
    if not path.exists():
        return None
    with path.open("r", encoding="utf-8") as file:
        payload = json.load(file)
    dates = payload.get("dates") or []
    return {str(date_value) for date_value in dates}


def _generate_holidays_kr(year: int) -> Set[str]:
    """외부 API 없이 한국 공휴일 계산 후 root `data/`에 캐시한다."""
    try:
        import holidays  # type: ignore
    except Exception as exc:
        raise RuntimeError(
            "holidays 패키지가 필요합니다. requirements.txt에 포함되어야 합니다."
        ) from exc

    kr = holidays.country_holidays("KR", years=[year])
    dates = sorted(date_value.isoformat() for date_value in kr.keys())

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    out_path = DATA_DIR / f"holidays_kr_{year}.json"
    with out_path.open("w", encoding="utf-8") as file:
        json.dump(
            {"year": year, "country": "KR", "dates": dates},
            file,
            ensure_ascii=False,
            indent=2,
        )

    return set(dates)


@lru_cache(maxsize=None)
def get_holidays_kr(year: int) -> Set[str]:
    """공휴일(YYYY-MM-DD 문자열 집합)을 반환한다."""
    loaded = _load_holidays_json(year)
    if loaded is not None:
        return loaded
    return _generate_holidays_kr(year)


def is_business_day(day_value: datetime.date) -> bool:
    """영업일 = 주말(토/일) + 공휴일 제외."""
    if day_value.weekday() >= 5:
        return False
    return day_value.isoformat() not in get_holidays_kr(day_value.year)


def business_days_between(start: datetime.date, end: datetime.date) -> int:
    """start 다음날부터 end까지의 영업일 수를 계산한다."""
    if start == end:
        return 0

    step = 1 if end > start else -1
    lower, upper = (start, end) if step == 1 else (end, start)
    total_days = (upper - lower).days

    full_weeks = total_days // 7
    remainder = total_days % 7
    lower_weekday = lower.weekday()

    weekend_in_remainder = 0
    for offset in range(1, remainder + 1):
        if (lower_weekday + offset) % 7 >= 5:
            weekend_in_remainder += 1

    weekday_count = total_days - full_weeks * 2 - weekend_in_remainder

    holiday_deduction = 0
    for year in range(lower.year, upper.year + 1):
        for holiday_value in get_holidays_kr(year):
            holiday_date = datetime.date.fromisoformat(holiday_value)
            if lower < holiday_date <= upper and holiday_date.weekday() < 5:
                holiday_deduction += 1

    return step * (weekday_count - holiday_deduction)


def business_days_until(
    target_date_str: str, today: Optional[datetime.date] = None
) -> Optional[int]:
    """today 기준 target까지 남은 영업일을 계산한다."""
    if not target_date_str:
        return None
    try:
        target = datetime.date.fromisoformat(str(target_date_str))
    except Exception:
        return None

    base = today or get_today_kst()
    return business_days_between(base, target)


def add_business_days(start: datetime.date, delta_days: int) -> datetime.date:
    """영업일 기준 날짜 이동."""
    if delta_days == 0:
        return start

    step = 1 if delta_days > 0 else -1
    remaining = abs(delta_days)
    current = start
    while remaining > 0:
        current = current + datetime.timedelta(days=step)
        if is_business_day(current):
            remaining -= 1
    return current
