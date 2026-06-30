"""KST datetime 표시·변환 SSOT (models 등 저수준 모듈에서도 안전하게 import 가능)."""
from __future__ import annotations

import datetime

import pytz

_KST_TZ = pytz.timezone('Asia/Seoul')

__all__ = [
    'format_datetime_kst',
    'get_today_kst',
    'now_kst',
    'now_utc_naive',
    'parse_datetime_utc',
    'to_utc_naive',
]


def get_today_kst() -> datetime.date:
    """한국 시간(KST, Asia/Seoul) 기준 오늘 날짜.

    Railway 등 UTC 서버에서 ``date.today()``는 한국 09:00 이전에 하루 밀린다.
    ERP 대시보드·일정·영업일 계산의 '오늘' SSOT.
    """
    try:
        return datetime.datetime.now(_KST_TZ).date()
    except Exception:
        return datetime.datetime.now(
            datetime.timezone(datetime.timedelta(hours=9))
        ).date()


def now_kst() -> datetime.datetime:
    """현재 시각(KST, timezone-aware). 접수일·접수시간 기본값 SSOT."""
    try:
        return datetime.datetime.now(_KST_TZ)
    except Exception:
        return datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=9)))


def now_utc_naive() -> datetime.datetime:
    """현재 시각을 UTC naive datetime으로 반환한다.

    기존 운영 DB의 ``TIMESTAMP WITHOUT TIME ZONE`` 컬럼과 비교할 때 쓰는 기준.
    """
    return datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)


def parse_datetime_utc(
    value: datetime.datetime | str | None,
    *,
    assume_utc_if_naive: bool = True,
) -> datetime.datetime | None:
    """datetime/ISO 문자열을 UTC timezone-aware datetime으로 정규화한다."""
    if value is None:
        return None

    if isinstance(value, datetime.datetime):
        dt = value
    else:
        text = str(value).strip()
        if not text:
            return None
        normalized = text.replace('Z', '+00:00')
        try:
            dt = datetime.datetime.fromisoformat(normalized)
        except ValueError:
            parsed = None
            for fmt in ('%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M'):
                try:
                    parsed = datetime.datetime.strptime(text, fmt)
                    break
                except ValueError:
                    continue
            if parsed is None:
                return None
            dt = parsed

    if dt.tzinfo is None:
        if assume_utc_if_naive:
            dt = pytz.UTC.localize(dt)
        else:
            dt = _KST_TZ.localize(dt)
    return dt.astimezone(pytz.UTC)


def to_utc_naive(
    value: datetime.datetime | str | None,
    *,
    assume_utc_if_naive: bool = True,
) -> datetime.datetime | None:
    """datetime/ISO 문자열을 DB 비교용 UTC naive datetime으로 정규화한다."""
    dt = parse_datetime_utc(value, assume_utc_if_naive=assume_utc_if_naive)
    return dt.replace(tzinfo=None) if dt is not None else None


def format_datetime_kst(
    value: datetime.datetime | str | None,
    fmt: str = '%Y-%m-%d %H:%M:%S',
    *,
    assume_utc_if_naive: bool = True,
) -> str | None:
    """naive/aware datetime을 KST 문자열로 포맷한다.

    Railway 등 운영 DB의 naive timestamp는 UTC로 저장된다고 가정한다.
    timezone-aware 값은 해당 시각을 KST로 변환한다.

    Args:
        value: 포맷할 datetime. None이면 None 반환.
        fmt: ``datetime.strftime`` 포맷. 기본은 ``YYYY-MM-DD HH:MM:SS``.
        assume_utc_if_naive: naive일 때 UTC로 해석할지 여부(기본 True).

    Returns:
        KST 기준 포맷 문자열, 또는 None.
    """
    if value is None:
        return None

    dt = parse_datetime_utc(value, assume_utc_if_naive=assume_utc_if_naive)
    if dt is None:
        return None
    return dt.astimezone(_KST_TZ).strftime(fmt)
