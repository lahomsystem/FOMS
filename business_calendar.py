import json
import os
import datetime
from typing import Iterable, Set, Optional


DATA_DIR = os.path.join(os.path.dirname(__file__), "data")


def _load_holidays_json(year: int) -> Optional[Set[str]]:
    path = os.path.join(DATA_DIR, f"holidays_kr_{year}.json")
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        payload = json.load(f)
    dates = payload.get("dates") or []
    return set(str(x) for x in dates)


def _generate_holidays_kr(year: int) -> Set[str]:
    """
    외부 API 없이 한국 공휴일 계산.
    holidays 패키지를 사용하고, 결과를 data/holidays_kr_YYYY.json으로 저장한다.
    """
    try:
        import holidays  # type: ignore
    except Exception as e:
        raise RuntimeError("holidays 패키지가 필요합니다. requirements.txt에 포함되어야 합니다.") from e

    kr = holidays.KR(years=[year])
    dates = sorted([d.isoformat() for d in kr.keys()])

    os.makedirs(DATA_DIR, exist_ok=True)
    out_path = os.path.join(DATA_DIR, f"holidays_kr_{year}.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({"year": year, "country": "KR", "dates": dates}, f, ensure_ascii=False, indent=2)

    return set(dates)


def get_holidays_kr(year: int) -> Set[str]:
    """공휴일(YYYY-MM-DD 문자열 집합)"""
    loaded = _load_holidays_json(year)
    if loaded is not None:
        return loaded
    return _generate_holidays_kr(year)


def is_business_day(d: datetime.date) -> bool:
    """영업일 = 주말(토/일) + 공휴일 제외"""
    if d.weekday() >= 5:
        return False
    holidays_set = get_holidays_kr(d.year)
    return d.isoformat() not in holidays_set


def business_days_between(start: datetime.date, end: datetime.date) -> int:
    """
    start -> end 사이 영업일 수(양수/0/음수)
    - end가 start 이후면: start 다음날부터 end까지(포함) 카운트
    - end가 start 이전이면: 음수
    """
    if start == end:
        return 0
    step = 1 if end > start else -1
    cur = start
    count = 0
    while cur != end:
        cur = cur + datetime.timedelta(days=step)
        if is_business_day(cur):
            count += step
    return count


def business_days_until(target_date_str: str, today: Optional[datetime.date] = None) -> Optional[int]:
    """today 기준 target까지 남은 영업일(오늘 제외, target 포함). 파싱 실패 시 None."""
    if not target_date_str:
        return None
    try:
        target = datetime.date.fromisoformat(str(target_date_str))
    except Exception:
        return None
    base = today or datetime.date.today()
    return business_days_between(base, target)


def add_business_days(start: datetime.date, delta_days: int) -> datetime.date:
    """
    영업일 기준 날짜 이동.
    - delta_days > 0: start 다음 영업일부터 카운트
    - delta_days < 0: start 이전 영업일부터 카운트
    """
    if delta_days == 0:
        return start
    step = 1 if delta_days > 0 else -1
    remaining = abs(delta_days)
    cur = start
    while remaining > 0:
        cur = cur + datetime.timedelta(days=step)
        if is_business_day(cur):
            remaining -= 1
    return cur

