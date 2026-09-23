"""실측 방문시각(자유 텍스트) 파싱·정렬 SSOT.

ERP 주문은 `orders.measurement_time` 컬럼이 비어 있고(운영 확인: 실측 일정이
잡힌 ERP 주문 전부 NULL) 실제 시각은 `structured_data.schedule.measurement.time`
에 자유 텍스트로 들어간다("10시", "오후", "1시~2시", "8시30분~9시").

컬럼 기준으로 SQL 정렬하면 키가 전부 NULL 이라 사실상 `id ASC`(접수순)로
떨어져 동선 스트립 순서·'다음 방문' 판정이 실제 방문 순서와 어긋난다
(2026-08-10 운영 재현: 스트립 "1번 전은영(4시)" vs 히어로 "정재영(10시)").
그래서 정렬 키는 이 모듈의 파서가 만든 **분(minute) 단위 정수** 하나로 통일하고,
동선/히어로/카운트다운이 모두 같은 키를 쓴다.

오전/오후 판정 경계는 `meas_daypart`(erp_template_filters)와 같은 규약을 쓴다 —
상수·정규식을 여기서 정의하고 그쪽이 import 해 드리프트를 막는다.
"""
from __future__ import annotations

import re
import unicodedata
from typing import Any

# 오전 판정 경계(포함): 7~11시는 오전, 그 밖의 1~6시·12~23시는 오후.
MEAS_AM_START_HOUR = 7
MEAS_AM_END_HOUR = 11

# 시각 토큰: "9시", "11:", "10시 30분", "09:00". 분은 선택.
MEAS_HOUR_RE = re.compile(r'(\d{1,2})\s*(?::|시)')
MEAS_HOUR_MIN_RE = re.compile(r'(\d{1,2})\s*(?::|시)\s*(\d{1,2})?\s*분?')

# 시각 숫자 없이 구간 표현만 있을 때의 대표 시각(정렬 전용 — 표시는 원문 유지).
ALLDAY_MINUTES = 8 * 60
AM_MINUTES = 9 * 60
PM_MINUTES = 13 * 60
EVENING_MINUTES = 18 * 60

# 시각 미상 주문의 정렬 버킷(항상 마지막).
_UNKNOWN_BUCKET = 1
_KNOWN_BUCKET = 0

_AM_MARKERS = ('오전', '새벽', '아침')
_PM_MARKERS = ('오후', '낮')
_EVENING_MARKERS = ('저녁', '밤')
_EMPTY_TOKENS = {'', '-', '--', '미정', '없음'}


def _marker_hits(text: str) -> list[tuple[int, str]]:
    """오전/오후/저녁 마커의 (위치, 종류) 목록. 위치 오름차순 정렬 전 원시 목록."""
    lower = text.lower()
    hits: list[tuple[int, str]] = []
    for marker in _AM_MARKERS:
        idx = text.find(marker)
        if idx != -1:
            hits.append((idx, 'am'))
    for marker in _PM_MARKERS:
        idx = text.find(marker)
        if idx != -1:
            hits.append((idx, 'pm'))
    for marker in _EVENING_MARKERS:
        idx = text.find(marker)
        if idx != -1:
            hits.append((idx, 'evening'))
    am_idx = lower.find('am')
    if am_idx != -1:
        hits.append((am_idx, 'am'))
    pm_idx = lower.find('pm')
    if pm_idx != -1:
        hits.append((pm_idx, 'pm'))
    hits.sort(key=lambda hit: hit[0])
    return hits


def parse_measurement_time_minutes(value: Any) -> int | None:
    """실측 시간 자유 텍스트 → 자정 기준 분(0~1439). 판정 불가면 None.

    판정 순서(첫 매치에서 종료):
      1. 빈값/'-'/'미정' → None.
      2. 숫자 시각이 있으면 그 값(범위면 시작값). 앞쪽 오후/저녁 마커가 있으면
         12를 더하고, 마커가 없어도 1~6시는 관용적으로 오후로 본다
         (`meas_daypart`와 동일 규약).
      3. 숫자 없이 '종일' → 08:00, 오전 마커 → 09:00, 오후 → 13:00, 저녁/밤 → 18:00.
      4. 그 외 → None.

    Args:
        value: 실측 시간 원문("10시", "오후 5시-5시30분", "종일", None 등).

    Returns:
        분 단위 정수(예: "10시 30분" → 630) 또는 None.
    """
    if value is None:
        return None
    text = str(value).strip()
    if text.lower() in _EMPTY_TOKENS:
        return None

    hits = _marker_hits(text)
    match = MEAS_HOUR_MIN_RE.search(text)

    if match:
        hour = int(match.group(1))
        minute = int(match.group(2)) if match.group(2) else 0
        if minute > 59:
            minute = 0
        if hour <= 0 or hour >= 24:
            return None
        leading = [kind for idx, kind in hits if idx < match.start()]
        if leading and leading[0] in ('pm', 'evening'):
            if hour < 12:
                hour += 12
        elif not leading and 1 <= hour < MEAS_AM_START_HOUR:
            # 마커 없는 "4시"는 실무상 오후 4시다(오전 4시 실측은 없다).
            hour += 12
        return hour * 60 + minute

    if '종일' in text or 'all day' in text.lower():
        return ALLDAY_MINUTES
    if hits:
        kind = hits[0][1]
        if kind == 'am':
            return AM_MINUTES
        if kind == 'evening':
            return EVENING_MINUTES
        return PM_MINUTES
    return None


def format_minutes_hm(minutes: int | None) -> str | None:
    """분 정수 → 'HH:MM'. None 이면 None (카운트다운 위젯 계약 형식)."""
    if minutes is None:
        return None
    if minutes < 0 or minutes >= 24 * 60:
        return None
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def measurement_time_text(order: Any) -> str | None:
    """주문의 실측 시각 원문 — `structured_data` 우선, flat 컬럼 폴백.

    flat 컬럼(`Order.measurement_time`)은 ERP 주문에서 비어 있고, 표시 계보
    (`erp_display.apply_erp_display_fields_to_orders`)가 같은 요청 안에서 ORM
    인스턴스에 structured_data 값을 덮어쓰기도 한다. 어느 쪽 경로로 들어와도
    같은 값이 나오도록 여기서 순서를 고정한다.

    Args:
        order: Order ORM 인스턴스(또는 같은 속성을 가진 객체).

    Returns:
        공백 제거한 시각 원문 또는 None.
    """
    sd = getattr(order, 'structured_data', None)
    if isinstance(sd, dict):
        schedule = sd.get('schedule')
        if isinstance(schedule, dict):
            measurement = schedule.get('measurement')
            if isinstance(measurement, dict):
                raw = measurement.get('time')
                if isinstance(raw, str) and raw.strip():
                    return raw.strip()
    column = getattr(order, 'measurement_time', None)
    if isinstance(column, str) and column.strip():
        return column.strip()
    return None


def measurement_time_minutes_of(order: Any) -> int | None:
    """주문 → 방문시각 분 정수(원문 SSOT 경유). 판정 불가면 None."""
    return parse_measurement_time_minutes(measurement_time_text(order))


def measurement_time_sort_key(order: Any) -> tuple[int, int, int]:
    """방문 순서 정렬 키 `(버킷, 분, id)` — 시각 미상은 항상 뒤로.

    Args:
        order: Order ORM 인스턴스.

    Returns:
        `sorted(key=...)`에 바로 쓰는 튜플. 같은 시각이면 id 오름차순으로 결정론.
    """
    order_id = getattr(order, 'id', 0) or 0
    minutes = measurement_time_minutes_of(order)
    if minutes is None:
        return (_UNKNOWN_BUCKET, 0, order_id)
    return (_KNOWN_BUCKET, minutes, order_id)



# ── 모바일 '오늘 체크리스트' 묶음 안 정렬 키 ─────────────────────────────────────
# 방문 시각은 전날 17시에 확정한 계획값이다(당일 바뀌어도 ERP 에 안 들어온다) —
# 이 키는 계획의 표시 순서만 정한다. 위 파서(동선·카운트다운 SSOT)와 달리 숫자 없는
# 구간 낱말을 대표 시각으로 끼우지 않고, 스테이징 실데이터(1,444행·280종, 2026-09-23)의
# 시작부 표기("9~10시"·"오후 3"·"12시반"·"２시"·"오전: 11~ 12시반/오후 2시반~")를 읽는다.

# 한눈 정렬 버킷(작을수록 위). 숫자 시각·'오전' 낱말 0, '오후'류 1, 종일 2, 미상 3.
_GLANCE_TIMED = 0
_GLANCE_PM_WORD = 1
_GLANCE_ALLDAY = 2
_GLANCE_UNKNOWN = 3
# '오전'(숫자 없음)은 명시 오전 시각(~11:59) 뒤, 12:00 앞 — (11:59, 부순위 1).
_GLANCE_AM_WORD_MINUTES = 11 * 60 + 59

_GLANCE_NUM_RE = re.compile(r'(?<!\d)(\d{1,2})(?!\d)')
# 숫자 바로 뒤: "9:30" / "9시" / "9시 30분" / "9시반".
_GLANCE_CLOCK_TAIL_RE = re.compile(r'\s*(?::\s*(\d{1,2})|시\s*(?:(\d{1,2})|(반))?)')
# 숫자 바로 뒤 범위: "9~10시", "10~2시", "1-2시", "11~ 12시반" (끝값이 시각이어야 한다).
_GLANCE_RANGE_TAIL_RE = re.compile(r'\s*[~\-]\s*\d{1,2}\s*(?::|시)')
# 숫자 바로 앞 마커: "오전 9", "오후 1~2", "오전: 11".
_GLANCE_MARKER_BEFORE_RE = re.compile(r'(오전|오후|아침|새벽|저녁|밤|낮|am|pm)\s*:?\s*$', re.IGNORECASE)


def _glance_start_minutes(text: str) -> int | None:
    """첫 시작 시각(분). 시각 숫자가 없으면(맨 숫자 "9", "11tl") None, "0시"·"25시"는 -1."""
    for num in _GLANCE_NUM_RE.finditer(text):
        tail = text[num.end():]
        clock = _GLANCE_CLOCK_TAIL_RE.match(tail)
        before = _GLANCE_MARKER_BEFORE_RE.search(text[:num.start()])
        if not (clock or _GLANCE_RANGE_TAIL_RE.match(tail) or before):
            continue
        hour = int(num.group(1))
        minute = 0
        if clock:
            if clock.group(3):
                minute = 30
            else:
                raw_min = clock.group(1) or clock.group(2)
                minute = int(raw_min) if raw_min else 0
        if minute > 59:
            minute = 0
        if hour <= 0 or hour >= 24:
            return -1
        # 시작값에 가장 가까운 앞쪽 마커를 쓴다("오전: 11~/오후 2시반~" 의 11 은 오전).
        leading = [kind for idx, kind in _marker_hits(text) if idx < num.start()]
        kind = leading[-1] if leading else None
        if kind in ('pm', 'evening'):
            if hour < 12:
                hour += 12
        elif kind is None and 1 <= hour < MEAS_AM_START_HOUR:
            hour += 12  # 마커 없는 "2시"는 오후 2시(오전 1~6시 실측은 없다)
        return hour * 60 + minute
    return None


def measurement_glance_time_key(value: Any) -> tuple[int, int, int]:
    """모바일 '오늘 체크리스트' 담당자 묶음 안 행 정렬 키 — 이른 순.

    사용자 요구(2026-09-23): "9:00, 10:00, 오전, 13:00, 2시, 오후" 순.

    - 첫 시작 시각(범위·여러 칸이면 맨 앞, NFKC 로 전각 숫자 정규화, '반'=30분)
      → ``(0, 분, 0)``. 앞 마커 오후/PM/저녁/밤/낮이면 +12, 마커 없으면 1~6시 +12
      (7~11시 오전, 12시 정오 — ``meas_daypart`` 규약과 같다).
    - '오전'·아침·새벽·AM(시각 없음) → ``(0, 11:59, 1)`` — 명시 오전 시각 뒤, 12시 앞.
    - '오후'·낮·PM → ``(1, 0, 0)``, 저녁·밤 → ``(1, 0, 1)`` — 모든 명시 시각 뒤.
    - '종일' → ``(2, 0, 0)``. 빈값·'-'·'미정'·'조율'·맨 숫자 "9"·판정 불가 → ``(3, 0, 0)``.

    같은 키는 호출 쪽 ``sorted`` 의 안정 정렬로 원래 순서를 지킨다.

    Args:
        value: 실측 시간 원문(또는 None).

    Returns:
        ``sorted(key=...)`` 에 쓰는 튜플.
    """
    if value is None:
        return (_GLANCE_UNKNOWN, 0, 0)
    text = unicodedata.normalize('NFKC', str(value)).strip()
    if text.lower() in _EMPTY_TOKENS:
        return (_GLANCE_UNKNOWN, 0, 0)
    minutes = _glance_start_minutes(text)
    if minutes == -1:
        return (_GLANCE_UNKNOWN, 0, 0)
    if minutes is not None:
        return (_GLANCE_TIMED, minutes, 0)
    if '종일' in text or 'all day' in text.lower():
        return (_GLANCE_ALLDAY, 0, 0)
    hits = _marker_hits(text)
    if not hits:
        return (_GLANCE_UNKNOWN, 0, 0)
    kind = hits[0][1]
    if kind == 'am':
        return (_GLANCE_TIMED, _GLANCE_AM_WORD_MINUTES, 1)
    if kind == 'evening':
        return (_GLANCE_PM_WORD, 0, 1)
    return (_GLANCE_PM_WORD, 0, 0)
