"""Common business-day calendar helpers."""

from __future__ import annotations

import datetime
import json
import os
import time
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
    """캐시 파일을 읽는다 — 다른 프로세스가 **갈아 끼우는 중**이어도 견딘다.

    쓰기는 :func:`_write_json_atomic` 이 원자적으로 하므로 반쪽 파일은 없다. 남는 창은
    Windows 뿐이다: ``os.replace`` 가 도는 순간 그 이름을 열려 하면 거절당한다(POSIX
    에는 없는 제약). 교체는 순간이라 짧게 물러났다 다시 읽으면 끝난다.

    **실패를 삼키지 않는다.** 몇 번을 물러나도 안 되면 예외를 그대로 올린다 — 여기서
    조용히 ``None`` 을 돌려주면 공휴일이 통째로 사라진 채 영업일이 계산된다(D-day 가
    조용히 틀린다).

    Args:
        year: 연도.

    Returns:
        공휴일 문자열 집합. 파일이 아직 없으면 ``None``.
    """
    path = DATA_DIR / f"holidays_kr_{year}.json"
    for attempt in range(5):
        if not path.exists():
            return None
        try:
            with path.open("r", encoding="utf-8") as file:
                payload = json.load(file)
        except (PermissionError, json.JSONDecodeError):
            if attempt == 4:
                raise
            time.sleep(0.02 * (attempt + 1))
            continue
        dates = payload.get("dates") or []
        return {str(date_value) for date_value in dates}
    return None


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
    _write_json_atomic(out_path, {"year": year, "country": "KR", "dates": dates})
    return set(dates)


def _write_json_atomic(out_path: Path, payload: dict) -> None:
    """임시 파일에 쓰고 **원자적으로 갈아 끼운다**.

    왜 곧바로 쓰지 않는가: 이 캐시는 저장소에 없다(``.gitignore`` 가 무시한다). CI 는
    테스트가 처음 참조하는 연도를 런타임에 만드는데, pytest-xdist 워커는 별도
    프로세스지만 **파일시스템은 하나**다. 대상 경로에 곧바로 ``open("w")`` 하면 그
    호출이 파일을 먼저 비우고, 그 창에서 다른 워커가 읽으면 빈 문자열을 파싱해 터진다
    (2026-09-05 ``0c66f6d61`` CI — ``JSONDecodeError: Expecting value``).

    ``os.replace`` 는 같은 볼륨에서 원자적이라, 읽는 쪽은 **옛 완결본 아니면 새 완결본**만
    본다. 반쪽 파일이라는 상태가 아예 없어진다.

    Args:
        out_path: 최종 경로.
        payload: 저장할 값.

    Returns:
        None.
    """
    # 임시 파일은 **같은 디렉토리**에 만든다 — 볼륨이 갈리면 os.replace 가 원자적이지 않다.
    # 이름에 pid 를 넣어 워커끼리 같은 임시 파일을 두고 다투지 않게 한다.
    tmp_path = out_path.with_name(f"{out_path.name}.{os.getpid()}.tmp")
    try:
        with tmp_path.open("w", encoding="utf-8") as file:
            json.dump(payload, file, ensure_ascii=False, indent=2)
            file.flush()
            os.fsync(file.fileno())
        # Windows 는 대상이 다른 프로세스에 **열려 있는 동안** 교체를 거절한다
        # (POSIX 에는 없는 제약이다). 읽기는 순간이라 짧게 물러났다 다시 시도한다.
        for attempt in range(5):
            try:
                os.replace(tmp_path, out_path)
                return
            except PermissionError:
                if attempt == 4:
                    raise
                time.sleep(0.02 * (attempt + 1))
    finally:
        # 교체가 끝났으면 이미 사라진 이름이다. 실패했을 때만 쓰레기를 걷는다.
        try:
            tmp_path.unlink()
        except OSError:
            pass


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
