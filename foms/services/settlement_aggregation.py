"""정산 대시보드 집계 서비스 — SETTLE-DASH-01 M1 (읽기 전용).

완료 대시보드(:mod:`foms.web.cs.completion_dashboard`)는 무검색 브라우즈 200건 캡이
있어 월별 합계를 낼 수 없다. 이 모듈은 **같은 모집단·같은 파생 규칙**을 캡 없이 전량으로
읽고 기간 버킷·미수 aging·채널·정산 현황·단계별 물린 금액을 집계한다.

파리티 원칙: 금액(출고가·예약금·잔금·과입금)·미수·현금영수증·정산 청구 판정은 완료
대시보드/erp_display/estimate_service 의 SSOT 헬퍼를 **직접 import 해서** 쓴다. 같은
규칙을 두 번 적어 두면 같은 주문의 잔금이 화면마다 갈린다(완료 대시보드 `_completion_row`
주석의 같은 이유).

성능(SPEC §4.1): **날짜 술어를 SQL 에 걸지 않는다.** 미수·aging 이 기간 무관 지표라
어차피 전량이 필요하다. 기간은 파이썬 버킷 단계에서만 적용한다. 로드 컬럼은
``id/status/manager_name/as_axis_status`` + **얇은** ``structured_data``
(:mod:`foms.services.settlement_source` — 판정이 읽는 경로만, 2026-10-05 스테이징 1,586행
출력 3,675kB → 801kB)로 최소화하고 ``apply_erp_display_fields``(행마다 User 쿼리 = N+1)는
부르지 않는다.

이 모듈은 읽기 전용이다 — 커밋·flag_modified·Order 속성 대입을 하지 않는다.
"""

from __future__ import annotations

import calendar
import datetime
import re
from collections import Counter
from typing import Any

# 순서 주의(알파벳 순 아님): `foms.services.orders.*` 를 `erp_display` 보다 **먼저** 둔다.
# erp_display → erp_policy → foms.services.orders → erp_order_detail → erp_display 라는
# 기존 순환이 있어, 신선한 인터프리터에서 erp_display 를 첫 import 로 잡으면
# `partially initialized module` ImportError 가 난다(erp_display 자체도 단독 import 불가).
# orders 패키지를 먼저 완주시키면 그 고리가 풀린다 — as_dashboard_display 가
# `foms.api.files` 를 먼저 import 해서 우연히 피해 가는 것과 같은 회피다.
from foms.services.orders.erp_policy_constants import (
    ORDER_SETTLEMENT_ALERT_TARGET_STATUSES,
    STAGE_LABELS,
)
# AS 청구 4분류 SSOT. 이 모듈은 `foms.api.files` 를 먼저 import 해서 위 순환 고리를 스스로
# 피하므로(모듈 상단 주석의 회피와 같은 것) orders 블록 뒤 어디에 놓아도 안전하다.
from foms.services.as_dashboard_display import as_billing_badge_kind
from foms.services.datetime_kst import get_today_kst
from foms.services.erp_display import (
    _ensure_dict,
    erp_deposit_amount_from_structured,
    erp_shipping_price_from_structured,
)
from foms.services.estimate_service import (
    _balance_after_payments,
    _overpaid_after_payments,
)
from foms.services.settlement_source import fetch_settlement_rows
# 완료 대시보드 파생 SSOT 를 재구현하지 않고 그대로 쓴다(비트 단위 파리티).
# SETTLEMENT_DEPARTMENT_OPTIONS 는 `foms.api.cs.dashboard.SETTLEMENT_DEPARTMENTS` 와
# 같은 5종·같은 순서에 라벨이 붙은 형태다(그 모듈 주석의 "API 와 정합" 선언).
from foms.web.cs.completion_dashboard import (
    SETTLEMENT_DEPARTMENT_OPTIONS,
    _cash_receipt_issued,
    _cash_receipt_state,
    _completion_month_key,
)
from models import ExternalOrderLink, Order

__all__ = [
    "AGING_BUCKETS",
    "BRAND_CHANNELS",
    "MAX_RANGE_DAYS",
    "aggregate_settlement",
    "aging_bucket",
    "brand_channel_of",
    "completion_day_key",
    "completion_month_key",
    "parse_day_range",
    "week_key",
]

_MONTH_RE = re.compile(r"^\d{4}-\d{2}$")
_DAY_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_GRANULARITIES = ("day", "week", "month")
# 성능 가드(SPEC §4.2): 한 번에 12개월까지만. prev 구간까지 하면 최대 24개월 스캔이다.
_MAX_RANGE_MONTHS = 12
#: 날짜 범위 조회 상한(일). 화면의 '올해' 빠른 선택(1/1~12/31)이 윤년에도 들어가는 폭이다.
#: 네이버 정산 탭 상한(``settlement_channel.MAX_RANGE_DAYS`` 400일)보다 좁아서 공통 기간 바가
#: 고른 범위를 그 탭도 그대로 받는다.
MAX_RANGE_DAYS = 366
# 링크 없는 주문의 채널 표기. 네이버 등 외부 수집분만 링크가 붙는다.
_DEFAULT_CHANNEL = "일반"
_NAVER_CHANNEL = "NAVER"
#: 매출 비중 카드의 두 칸(사용자 결정 2026-10-06). 순서가 화면 순서다.
#: 라홈 = 발주사 이름에 '라홈'이 들어간 주문 + 네이버 주문 전부, 일반 = 나머지.
BRAND_GENERAL = "GENERAL"
BRAND_LAHOM = "LAHOM"
BRAND_CHANNELS: tuple[tuple[str, str], ...] = ((BRAND_GENERAL, "일반"), (BRAND_LAHOM, "라홈"))
#: 발주사 브랜드 판정 낱말 — `kakao_alimtalk.resolve_brand`·도면 로고 규칙과 같은 판정이다.
#: 그 함수를 import 하지 않는 이유: 읽기 전용 집계가 알림 발송 모듈(엔진·outbox)을 끌고 오게
#: 된다. 대신 두 판정이 갈리지 않음을 테스트가 고정한다.
_LAHOM_ORDERER_KEYWORD = "라홈"
# 단계 카드에서 빼는 완료 계열 stage code(SPEC §4.4).
_COMPLETED_STAGE_CODES = ("COMPLETED", "AS_COMPLETED")
# 담당자 미상 버킷. 조회 결과에서 **항상 마지막**에 온다(매출 순위와 섞이면 "1등 담당자"가
# 사람이 아닌 빈칸이 되는 일이 생긴다).
_MANAGER_UNASSIGNED_LABEL = "(미지정)"
# 담당자 표기가 이 값들이면 미지정으로 접는다("-" 는 파생 실패의 표시값이다).
_MANAGER_UNASSIGNED_KEYS = ("", "-")
# 부서별 차감 카드가 세는 부서 집합. `deduction_total` 도 같은 범위여야 현재 구간 카드와
# 직전 구간 스칼라를 나란히 놓고 비교할 수 있다.
_SETTLEMENT_DEPARTMENT_CODES = frozenset(code for code, _ in SETTLEMENT_DEPARTMENT_OPTIONS)

# 미수 경과일 버킷 — (코드, 라벨) 고정 순서. 반환 스키마의 `aging` 순서 정본.
AGING_BUCKETS: tuple[tuple[str, str], ...] = (
    ("LE7", "7일 이하"),
    ("D8_30", "8~30일"),
    ("D31_60", "31~60일"),
    ("D61_90", "61~90일"),
    ("D91_PLUS", "91일 이상"),
)


# ---------------------------------------------------------------------------
# 순수 키 파생
# ---------------------------------------------------------------------------


def completion_month_key(completion_date: Any) -> str:
    """완료일 원본 → 월 키("YYYY-MM"). 파생 불가면 빈 문자열.

    완료 대시보드 ``_completion_month_key`` 에 **위임**한다(복제 아님 — 규칙이 갈릴 수
    없게). 원본은 콤마 조인 복수 날짜를 담을 수 있는데(운영 55건, 예: "2026-05-27,
    2026-05-28") ``text[:7]`` 이라 **첫 날짜의 월 1개**에만 귀속된다. 한 주문이 두 달
    버킷에 동시에 들어가는 이중 계상이 없다.

    Args:
        completion_date: ``sd.schedule.construction.date`` 원본 값.

    Returns:
        "YYYY-MM" 또는 "".
    """
    return _completion_month_key(completion_date)


def completion_day_key(completion_date: Any) -> str:
    """완료일 원본 → 일 키("YYYY-MM-DD"). 파생 불가면 빈 문자열.

    월 키와 같은 방어를 먼저 거친 뒤 **첫 날짜**(콤마 앞)만 본다. 실재하는 날짜여야
    한다 — "2026-02-30" 처럼 달력에 없는 값은 빈 문자열이다(그래야 기간 버킷·aging·
    미상 집계가 같은 판정을 쓴다).

    Args:
        completion_date: ``sd.schedule.construction.date`` 원본 값.

    Returns:
        "YYYY-MM-DD" 또는 "".
    """
    if not completion_date or not isinstance(completion_date, str):
        return ""
    text = completion_date.strip()
    if len(text) < 7 or text[4] != "-":
        return ""
    first = text.split(",")[0].strip()
    if len(first) < 10 or first[7] != "-":
        return ""
    head = first[:10]
    return head if _day_to_date(head) is not None else ""


def _day_to_date(day_key: str) -> datetime.date | None:
    """"YYYY-MM-DD" 키를 ``date`` 로 변환한다(불가하면 None).

    예외를 던지지 않는다 — 달력 상한을 ``calendar.monthrange`` 로 먼저 확인하고
    유효할 때만 ``date`` 를 만든다.

    Args:
        day_key: 일 키 후보 문자열.

    Returns:
        ``datetime.date`` 또는 None.
    """
    if not isinstance(day_key, str) or len(day_key) != 10:
        return None
    year, month, day = day_key[0:4], day_key[5:7], day_key[8:10]
    if not (year.isdigit() and month.isdigit() and day.isdigit()):
        return None
    y, m, d = int(year), int(month), int(day)
    if not (datetime.MINYEAR <= y <= datetime.MAXYEAR and 1 <= m <= 12):
        return None
    if not 1 <= d <= calendar.monthrange(y, m)[1]:
        return None
    return datetime.date(y, m, d)


def week_key(day_key: str) -> str:
    """일 키 → **월 내 주차** 키("YYYY-MM-W{n}"). 파생 불가면 빈 문자열.

    ISO 주가 아니다. 주 시작은 월요일이고, 그 달 1일이 속한 주가 1주차다. 그래서
    1주차는 1일이 무슨 요일이냐에 따라 1~7일 길이가 된다(1일이 일요일이면 1주차는
    하루뿐).

    Args:
        day_key: "YYYY-MM-DD" 일 키.

    Returns:
        "YYYY-MM-W{n}" 또는 "".
    """
    day = _day_to_date(day_key)
    if day is None:
        return ""
    first_weekday = datetime.date(day.year, day.month, 1).weekday()
    week_no = ((day.day + first_weekday) - 1) // 7 + 1
    return f"{day.year:04d}-{day.month:02d}-W{week_no}"


def aging_bucket(days: int) -> str:
    """미수 경과일 → aging 버킷 코드.

    경계는 닫힌 구간이다: 7 이하 / 8~30 / 31~60 / 61~90 / 91 이상. 완료일이 미래라
    음수가 나와도 최연소 버킷("LE7")으로 간다.

    Args:
        days: 완료일로부터 오늘까지의 경과 일수.

    Returns:
        "LE7" | "D8_30" | "D31_60" | "D61_90" | "D91_PLUS".
    """
    if days <= 7:
        return "LE7"
    if days <= 30:
        return "D8_30"
    if days <= 60:
        return "D31_60"
    if days <= 90:
        return "D61_90"
    return "D91_PLUS"


# ---------------------------------------------------------------------------
# 기간 파라미터
# ---------------------------------------------------------------------------


def _month_index(month_key: str) -> int:
    """"YYYY-MM" → 월 일련번호(년*12 + 월-1). 산술·비교 전용."""
    return int(month_key[0:4]) * 12 + (int(month_key[5:7]) - 1)


def _month_from_index(index: int) -> str:
    """월 일련번호 → "YYYY-MM"."""
    return f"{index // 12:04d}-{index % 12 + 1:02d}"


def _validate_month(value: Any, field: str) -> str:
    """월 파라미터를 검증한다(형식 + 월 범위).

    Args:
        value: 검증 대상.
        field: 오류 메시지에 쓸 파라미터 이름.

    Returns:
        검증된 "YYYY-MM" 문자열.

    Raises:
        ValueError: 형식이 "YYYY-MM" 이 아니거나 월이 1~12 밖일 때.
    """
    if not isinstance(value, str) or not _MONTH_RE.match(value):
        raise ValueError(f"{field} 은(는) 'YYYY-MM' 형식이어야 합니다: {value!r}")
    if not 1 <= int(value[5:7]) <= 12:
        raise ValueError(f"{field} 의 월이 1~12 범위를 벗어났습니다: {value!r}")
    return value


def _month_range(month_from: Any, month_to: Any) -> list[str]:
    """조회 범위의 월 키 목록(오름차순, 양끝 포함).

    Args:
        month_from: 시작 월 "YYYY-MM".
        month_to: 종료 월 "YYYY-MM".

    Returns:
        ["YYYY-MM", ...] 오름차순.

    Raises:
        ValueError: 형식 오류·범위 역전·12개월 초과.
    """
    start = _month_index(_validate_month(month_from, "month_from"))
    end = _month_index(_validate_month(month_to, "month_to"))
    if start > end:
        raise ValueError(f"month_from 이 month_to 보다 뒤입니다: {month_from} > {month_to}")
    span = end - start + 1
    if span > _MAX_RANGE_MONTHS:
        raise ValueError(
            f"조회 범위는 최대 {_MAX_RANGE_MONTHS}개월입니다(요청 {span}개월)."
        )
    return [_month_from_index(i) for i in range(start, end + 1)]


def _previous_month_range(months: list[str]) -> list[str]:
    """요청 범위 **직전**의 동일 개월수 구간(전월 비교선용).

    Args:
        months: 요청 범위 월 키 목록(오름차순).

    Returns:
        같은 길이의 직전 구간 월 키 목록.
    """
    start = _month_index(months[0]) - len(months)
    return [_month_from_index(start + i) for i in range(len(months))]


def _month_span(months: list[str]) -> tuple[datetime.date, datetime.date]:
    """월 키 목록 → (첫 달 1일, 마지막 달 말일)."""
    first, last = months[0], months[-1]
    y, m = int(last[0:4]), int(last[5:7])
    return (
        datetime.date(int(first[0:4]), int(first[5:7]), 1),
        datetime.date(y, m, calendar.monthrange(y, m)[1]),
    )


def parse_day_range(date_from: Any, date_to: Any) -> tuple[datetime.date, datetime.date]:
    """날짜 범위 파라미터를 검증해 ``date`` 쌍으로 낸다(정산 탭 공통 기간 바).

    Args:
        date_from: 시작일 "YYYY-MM-DD"(포함).
        date_to: 종료일 "YYYY-MM-DD"(포함).

    Returns:
        (시작일, 종료일).

    Raises:
        ValueError: 형식 오류·달력에 없는 날짜·범위 역전·:data:`MAX_RANGE_DAYS` 초과.
    """
    parsed = []
    for value, field in ((date_from, "date_from"), (date_to, "date_to")):
        day = _day_to_date(value) if isinstance(value, str) and _DAY_RE.match(value) else None
        if day is None:
            raise ValueError(f"{field} 은(는) 'YYYY-MM-DD' 형식의 실제 날짜여야 합니다: {value!r}")
        parsed.append(day)
    start, end = parsed
    if start > end:
        raise ValueError(f"date_from 이 date_to 보다 뒤입니다: {date_from} > {date_to}")
    span = (end - start).days + 1
    if span > MAX_RANGE_DAYS:
        raise ValueError(f"조회 범위는 최대 {MAX_RANGE_DAYS}일입니다(요청 {span}일).")
    return start, end


def _whole_months(start: datetime.date, end: datetime.date) -> list[str] | None:
    """범위가 정확히 달 단위(1일~말일)면 그 월 키 목록, 아니면 None."""
    if start.day != 1 or end.day != calendar.monthrange(end.year, end.month)[1]:
        return None
    first = start.year * 12 + start.month - 1
    last = end.year * 12 + end.month - 1
    return [_month_from_index(i) for i in range(first, last + 1)]


def _resolve_period(
    month_from: Any, month_to: Any, date_from: Any, date_to: Any,
) -> dict:
    """조회 구간과 직전 비교 구간을 정한다.

    날짜 범위가 오면 그것이 우선이다. 범위가 **정확히 달 단위**면 직전 구간도 달 단위
    (같은 개월수의 직전 달들)로 잡는다 — 월 파라미터로 부른 것과 결과가 똑같아야 화면의
    '이번 달'이 예전 화면과 같은 전월 비교선을 그린다. 달 단위가 아니면 같은 일수의 바로
    앞 구간이다.

    Returns:
        ``start``/``end``/``prev_start``/``prev_end``(date) dict.

    Raises:
        ValueError: 파라미터 검증 실패.
    """
    if date_from is not None or date_to is not None:
        start, end = parse_day_range(date_from, date_to)
        months = _whole_months(start, end)
        if months is not None and len(months) <= _MAX_RANGE_MONTHS:
            prev_start, prev_end = _month_span(_previous_month_range(months))
        else:
            length = (end - start).days + 1
            prev_end = start - datetime.timedelta(days=1)
            prev_start = prev_end - datetime.timedelta(days=length - 1)
    else:
        months = _month_range(month_from, month_to)
        start, end = _month_span(months)
        prev_start, prev_end = _month_span(_previous_month_range(months))
    return {"start": start, "end": end, "prev_start": prev_start, "prev_end": prev_end}


# ---------------------------------------------------------------------------
# 행 파생 (완료 대시보드 `_completion_row` 파리티)
# ---------------------------------------------------------------------------


def _deduction_entries(settlement: Any) -> list[tuple[str, int]]:
    """정산 blob → [(부서코드, 차감액 절대값)] 리스트.

    저장 시 ``amount`` 는 음수로 정규화된다(`api_settlement_issue`: ``amount > 0`` 이면
    부호를 뒤집는다). 집계는 **절대값(양수)** 으로 내고 "차감"이라는 사실은 키 이름
    (``deductions_by_department``)이 말한다.

    Args:
        settlement: ``sd["settlement"]`` 값.

    Returns:
        (부서코드 대문자, 금액 절대값) 튜플 리스트. 금액이 int 가 아니면 0.
    """
    if not isinstance(settlement, dict):
        return []
    deductions = settlement.get("deductions")
    if not isinstance(deductions, list):
        return []
    entries: list[tuple[str, int]] = []
    for ded in deductions:
        if not isinstance(ded, dict):
            continue
        amount = ded.get("amount")
        entries.append((
            str(ded.get("department") or "").strip().upper(),
            abs(amount) if isinstance(amount, int) else 0,
        ))
    return entries


def _as_billing_paid_amount(billing: Any) -> int | None:
    """AS 유상 **확정** 청구액. 유상·확정이 아니면 None.

    ``foms.services.as_dashboard_display.as_billing_badge_kind`` 규약을 따른다 —
    ``type == "paid"`` 이고 ``confirmed is True``(엄격)일 때만 확정이다. 미수 판정의
    truthiness 와 달리 여기는 엄격 비교라는 점이 다르다.

    Args:
        billing: ``sd.shipment.as_billing`` 값.

    Returns:
        확정 유상이면 금액(int 아님·0 이하면 0), 아니면 None.
    """
    if not isinstance(billing, dict):
        return None
    if str(billing.get("type") or "free").lower() != "paid":
        return None
    if billing.get("confirmed") is not True:
        return None
    amount = billing.get("amount")
    return amount if isinstance(amount, int) and amount > 0 else 0


def _manager_display_name(sd: dict, manager_name: Any) -> str:
    """담당자 표시명 — 완료 대시보드 카드(`_serialize_completion_orders`)와 같은 파생.

    ``sd.parties.manager.name`` → ``Order.manager_name`` → ``"-"`` 순으로 첫 유효값을 쓴다.
    이웃 표면이 이미 이 순서로 그리고 있어, 여기서 순서를 바꾸면 같은 주문의 담당자가
    카드와 집계에서 갈린다.

    ``normalize_manager_name``/``apply_erp_display_fields`` 는 **부르지 않는다** —
    ``erp_display`` 가 숫자형 후보마다 ``User`` SELECT 를 날려 행 루프에서 N+1 이 된다
    (모듈 docstring 이 못박은 금지선). 문자열만 본다.

    Args:
        sd: ``_ensure_dict`` 를 통과한 structured_data.
        manager_name: ``Order.manager_name`` 컬럼값.

    Returns:
        표시명(앞뒤 공백 제거). 파생 불가면 ``"-"``.
    """
    parties = sd.get("parties")
    manager = parties.get("manager") if isinstance(parties, dict) else None
    name = manager.get("name") if isinstance(manager, dict) else None
    text = str(name).strip() if name else ""
    if text:
        return text
    fallback = str(manager_name).strip() if manager_name else ""
    return fallback or "-"


def brand_channel_of(sd: Any, channel: Any) -> str:
    """매출 비중 카드의 채널(일반/라홈) 판정.

    라홈 = 발주사(``parties.orderer.name``)에 '라홈'이 들어간 주문 **또는** 네이버 주문.
    네이버 주문은 발주사가 비어 있거나 다르게 적혀 있어도 라홈이다(사용자 결정 2026-10-06 —
    운영 네이버 주문 190건 중 189건이 이미 발주사 '라홈'이다). 그 밖은 전부 일반이다.

    Args:
        sd: structured_data(dict 가 아니면 발주사 없음으로 본다).
        channel: 외부 판매채널 코드 또는 "일반".

    Returns:
        :data:`BRAND_LAHOM` 또는 :data:`BRAND_GENERAL`.
    """
    if str(channel or "").strip().upper() == _NAVER_CHANNEL:
        return BRAND_LAHOM
    parties = sd.get("parties") if isinstance(sd, dict) else None
    orderer = parties.get("orderer") if isinstance(parties, dict) else None
    name = orderer.get("name") if isinstance(orderer, dict) else None
    return BRAND_LAHOM if _LAHOM_ORDERER_KEYWORD in str(name or "") else BRAND_GENERAL


def _row_amounts(sd: dict) -> dict:
    """출고가·예약금·잔금·과입금 파생 — 완료 대시보드 ``_completion_row`` 와 같은 식.

    잔금 클램프의 정본은 서버 파생식(``orders.structured_form_projection.recompute_totals``)
    이고, 그 식과 **같은 값**을 내는 ``_balance_after_payments`` 를 쓴다. 표면마다 새 식을
    쓰면 같은 주문의 잔금이 화면마다 갈린다. 세 번째 인자(discount)는 넣지 않는다 —
    할인은 출고가에 이미 반영돼 있어 넣으면 이중 차감이다.

    출고가/예약금/잔금은 ``None`` 이 될 수 있다(품목합 미산출, 운영 191건). ``or 0`` 으로
    뭉개지 않고 None 을 그대로 낸다 — 합산 단계가 "금액 미상"과 "0원"을 구분한다.

    Args:
        sd: ``_ensure_dict`` 를 통과한 structured_data.

    Returns:
        {"shipping_price", "deposit", "balance", "overpaid"}.
    """
    shipping_price = erp_shipping_price_from_structured(sd)
    deposit = erp_deposit_amount_from_structured(sd)
    return {
        "shipping_price": shipping_price,
        "deposit": deposit,
        "balance": (
            None if shipping_price is None
            else _balance_after_payments(shipping_price, deposit or 0)
        ),
        # 잔금은 0 에서 잘린다 — 넘친 금액은 그 클램프가 삼킨다. 돌려줄 돈이 있다는
        # 사실이 집계에서 사라지지 않게 넘친 만큼을 따로 낸다(CEO L-1).
        "overpaid": (
            0 if shipping_price is None
            else _overpaid_after_payments(shipping_price, deposit or 0)
        ),
    }


def _settlement_row(order: Any, channel: str) -> dict:
    """모집단 1행 → 집계용 파생 dict(신규 쿼리 없음).

    금액·미수·현금영수증·정산 판정은 완료 대시보드 ``_completion_row`` 와 **같은 식**을
    같은 헬퍼로 낸다.

    Args:
        order: ``id/status/manager_name/as_axis_status/structured_data`` 만 실린 결과 행.
        channel: 외부 판매채널 코드 또는 "일반".

    Returns:
        집계 단계가 쓰는 파생 dict.
    """
    sd = _ensure_dict(order.structured_data)
    completion_date = ((sd.get("schedule") or {}).get("construction") or {}).get("date")
    payment = sd.get("payment")
    cash_receipt = (
        str(payment.get("cash_receipt") or "").strip()
        if isinstance(payment, dict) else ""
    )
    settlement = sd.get("settlement")
    issued = _cash_receipt_issued(settlement)
    shipment = sd.get("shipment")
    as_billing = shipment.get("as_billing") if isinstance(shipment, dict) else None
    return {
        "id": order.id,
        "status": order.status,
        "channel": channel,
        "brand": brand_channel_of(sd, channel),
        "manager": _manager_display_name(sd, order.manager_name),
        # AS 모집단 판정은 AS 축 투영(AS-AXIS-01). status 는 overlay 라 외부 write 한 번에
        # 모집단이 통째로 빠진다(2026-08-14 사고).
        "has_as_axis": order.as_axis_status is not None,
        "month_key": completion_month_key(completion_date),
        "day_key": completion_day_key(completion_date),
        **_row_amounts(sd),
        # 미수 판정은 truthiness — 저장값이 bool 로 강제되지 않아 "Y" 같은 값이 온다.
        "paid": bool(isinstance(payment, dict) and payment.get("balance_confirmed")),
        "settlement_issued": bool(
            isinstance(settlement, dict) and settlement.get("deductions")
        ),
        "cash_receipt_state": _cash_receipt_state(cash_receipt, issued),
        "cash_receipt_issued": issued,
        "deductions": _deduction_entries(settlement),
        "as_billing_paid": _as_billing_paid_amount(as_billing),
        # 4분류('paid'|'paid_unconfirmed'|'undecided'|None)를 규칙 복제 없이 그대로 싣는다.
        "as_billing_kind": as_billing_badge_kind(as_billing),
    }


def _is_receivable(row: dict) -> bool:
    """미수 여부 — 완료 대시보드 KPI(`_compute_completion_kpis`)와 같은 술어."""
    balance = row["balance"]
    return not row["paid"] and isinstance(balance, int) and balance > 0


def _row_month(row: dict) -> str:
    """행의 기간 귀속 월. 일 키가 없으면 "" (= 완료일 미상)."""
    return row["day_key"][:7]


def _rows_in_span(rows: list[dict], start: datetime.date, end: datetime.date) -> list[dict]:
    """일 키가 [start, end] 안인 행. 일 키는 ISO 문자열이라 사전순 비교가 날짜순이다."""
    lo, hi = start.isoformat(), end.isoformat()
    return [row for row in rows if row["day_key"] and lo <= row["day_key"] <= hi]


# ---------------------------------------------------------------------------
# 모집단 로드
# ---------------------------------------------------------------------------


def _erp_scope_filters() -> tuple:
    """예상 매출 모집단 — 진행 단계와 무관한 살아 있는 ERP 주문 전부.

    ``Order.dashboard_active_filter()`` 를 쓰지 않는다 — 완료 60일 경과분을 잘라
    과거 월이 통째로 증발한다.
    """
    return (
        Order.active_filter(),
        Order.is_erp_order.is_(True),
    )


def _population_filters() -> tuple:
    """주 모집단 3조건 — 완료 대시보드 ``_completion_base_query`` 와 정확히 동일."""
    return (
        *_erp_scope_filters(),
        Order.status.in_(ORDER_SETTLEMENT_ALERT_TARGET_STATUSES),
    )


def _is_settlement_row(row: dict) -> bool:
    """실제 매출(시공완료) 모집단 — :func:`_population_filters` 의 status 조건과 같다."""
    return row["status"] in ORDER_SETTLEMENT_ALERT_TARGET_STATUSES


def _channel_map(db: Any) -> dict[int, str]:
    """모집단 주문의 외부 판매채널 코드 맵(단일 배치 쿼리, N+1 없음).

    한 주문에 링크가 여럿 붙을 수 있어(ADDON/REPAY 는 기존 주문에 붙는다) 주 쿼리에
    조인하지 않고 따로 읽는다 — 조인하면 같은 주문이 여러 행으로 늘어 매출이 중복된다.
    링크가 여럿이면 **가장 먼저 만들어진 것**의 채널을 쓴다.

    Args:
        db: SQLAlchemy Session.

    Returns:
        {order_id: 채널코드}. 링크 없는 주문은 키가 없다.
    """
    rows = (
        db.query(ExternalOrderLink.order_id, ExternalOrderLink.channel)
        .join(Order, ExternalOrderLink.order_id == Order.id)
        .filter(*_erp_scope_filters())
        .order_by(ExternalOrderLink.id.asc())
        .all()
    )
    mapping: dict[int, str] = {}
    for order_id, channel in rows:
        if order_id is None:
            continue
        mapping.setdefault(int(order_id), str(channel or "").strip() or _DEFAULT_CHANNEL)
    return mapping


def _load_rows(db: Any) -> list[dict]:
    """살아 있는 ERP 주문 전량을 파생 행 리스트로 읽는다(날짜·상태 술어 없음).

    예상 매출은 진행 단계와 무관하게 시공일이 있는 주문 전부라 status 로 거르지 않고
    읽는다. 실제 매출·미수·정산 카드의 모집단(완료·AS접수·AS완료)은 호출부가
    :func:`_is_settlement_row` 로 같은 행에서 가른다 — 쿼리를 두 번 하지 않는다.

    담당자(``manager_name``)·AS 축(``as_axis_status``)은 **같은 쿼리에 컬럼으로만** 더
    붙인다. 별도 쿼리나 행별 조회로 가져오면 모듈 docstring 이 금지한 N+1 이 된다.
    ``structured_data`` 는 판정이 읽는 경로만 남긴 투영이다(:func:`fetch_settlement_rows`).

    Args:
        db: SQLAlchemy Session.

    Returns:
        ``_settlement_row`` 파생 dict 리스트.
    """
    channels = _channel_map(db)
    orders = fetch_settlement_rows(
        db,
        (Order.id, Order.status, Order.manager_name, Order.as_axis_status),
        _erp_scope_filters(),
    )
    return [
        _settlement_row(order, channels.get(int(order.id), _DEFAULT_CHANNEL))
        for order in orders
    ]


# ---------------------------------------------------------------------------
# 버킷 (시계열)
# ---------------------------------------------------------------------------


def _bucket_key(row: dict, granularity: str) -> str:
    """행의 시계열 버킷 키(granularity 별)."""
    if granularity == "day":
        return row["day_key"]
    if granularity == "week":
        return week_key(row["day_key"])
    return _row_month(row)


def _enumerate_bucket_keys(
    start: datetime.date, end: datetime.date, granularity: str,
) -> list[str]:
    """기간 내 모든 버킷 키(빈 구간 0 채우기용, 시간순).

    구간 안의 날을 하루씩 버킷 키로 접는다. 달 단위 구간이면 예전(월 목록 기반) 열거와
    같은 키가 같은 순서로 나온다. 달 중간에서 시작·끝나는 구간은 그 주·그 달 버킷이
    부분 구간이 된다.

    Args:
        start: 구간 시작일(포함).
        end: 구간 종료일(포함).
        granularity: "day" | "week" | "month".

    Returns:
        버킷 키 목록(시간 오름차순, 중복 없음).
    """
    keys: list[str] = []
    seen: set[str] = set()
    day = start
    while day <= end:
        day_key = day.isoformat()
        key = (
            day_key if granularity == "day"
            else week_key(day_key) if granularity == "week"
            else day_key[:7]
        )
        if key not in seen:
            seen.add(key)
            keys.append(key)
        day += datetime.timedelta(days=1)
    return keys


def _bucket_label(key: str, granularity: str, with_year: bool = False) -> str:
    """버킷 키 → 화면 라벨("7/1" / "7월 1주" / "7월").

    ``with_year`` 면 주·월 라벨 앞에 "25년 " 을 붙인다 — 해를 넘는 구간에서 "1월"이 두 번
    나오는 것을 막는다. 일 라벨은 폭이 좁아 붙이지 않는다(툴팁·표가 키를 말한다).
    """
    month_no = int(key[5:7])
    year = f"{key[2:4]}년 " if with_year else ""
    if granularity == "day":
        return f"{month_no}/{int(key[8:10])}"
    if granularity == "week":
        return f"{year}{month_no}월 {key.rsplit('W', 1)[1]}주"
    return f"{year}{month_no}월"


def _build_buckets(
    rows: list[dict], start: datetime.date, end: datetime.date, granularity: str,
) -> list[dict]:
    """기간 내 행을 시계열 버킷으로 집계한다(빈 구간도 0 으로 채운다).

    Args:
        rows: 기간 내 파생 행(이미 구간으로 걸러진 것).
        start: 구간 시작일.
        end: 구간 종료일.
        granularity: "day" | "week" | "month".

    Returns:
        [{"key", "label", "revenue", "count"}] 시간 오름차순.
    """
    with_year = start.year != end.year
    buckets = {
        key: {
            "key": key, "label": _bucket_label(key, granularity, with_year),
            "revenue": 0, "count": 0,
        }
        for key in _enumerate_bucket_keys(start, end, granularity)
    }
    for row in rows:
        entry = buckets.get(_bucket_key(row, granularity))
        if entry is None:
            continue
        entry["count"] += 1
        if isinstance(row["shipping_price"], int):
            entry["revenue"] += row["shipping_price"]
    return list(buckets.values())


# ---------------------------------------------------------------------------
# 카드별 집계
# ---------------------------------------------------------------------------


def _revenue_of(rows: list[dict]) -> int:
    """출고가 합계. 미산출(None)은 0 기여 — 건수에는 남고 금액만 빠진다."""
    return sum(row["shipping_price"] for row in rows if isinstance(row["shipping_price"], int))


def _collected_split(rows: list[dict]) -> tuple[int, int]:
    """수금 근사를 두 항으로 나눈다: (완료월 귀속 예약금, 잔금 확인된 건의 잔금).

    두 항의 합이 ``collected_approx`` 다. 카드가 '예약금 얼마·잔금 얼마'를 따로 그려도
    총액이 갈리지 않게 한 곳에서만 낸다 — 화면이 따로 더하면 반올림·모집단이 어긋난다.

    Args:
        rows: 합산 대상 파생 행.

    Returns:
        (예약금 합, 확인된 잔금 합).
    """
    deposit = sum(row["deposit"] or 0 for row in rows)
    balance = sum(
        row["balance"] for row in rows
        if row["paid"] and isinstance(row["balance"], int)
    )
    return deposit, balance


def _deduction_total(rows: list[dict]) -> int:
    """부서별 차감 합계(절대값). 카드가 세는 부서 집합과 같은 범위만 센다."""
    return sum(
        amount
        for row in rows
        for department, amount in row["deductions"]
        if department in _SETTLEMENT_DEPARTMENT_CODES
    )


def _build_kpi(in_period: list[dict], all_rows: list[dict]) -> dict:
    """상단 KPI. 매출·건수·수금·과입금은 기간 내, 미수는 **기간 무관 모집단 전체**.

    Args:
        in_period: 기간 내 파생 행.
        all_rows: 모집단 전체 파생 행.

    Returns:
        반환 스키마의 ``kpi`` dict.
    """
    revenue = _revenue_of(in_period)
    count = len(in_period)
    collected_deposit, collected_balance = _collected_split(in_period)
    receivable = [row for row in all_rows if _is_receivable(row)]
    return {
        "revenue": revenue,
        "completed_count": count,
        "avg_shipping_price": revenue // count if count else 0,
        "receivable_total": sum(row["balance"] for row in receivable),
        "receivable_count": len(receivable),
        # 두 항을 따로 낸다(분석 탭이 수금 구성을 쪼개 본다). 합은 기존 키 그대로다 —
        # `collected_deposit + collected_balance == collected_approx` 는 항등식이다.
        "collected_deposit": collected_deposit,
        "collected_balance": collected_balance,
        "collected_approx": collected_deposit + collected_balance,
        "overpaid_total": sum(row["overpaid"] for row in in_period),
    }


def _build_period_totals(rows: list[dict]) -> dict:
    """기간 스칼라 합계 — ``prev_totals``(직전 구간 비교선)용. 신규 쿼리 없음.

    이미 계산해 둔 직전 구간 행을 다시 접기만 한다.

    ``receivable_*``·aging 은 **넣지 않는다**. 그 둘은 기간 무관 지표(모집단 전체)라
    "직전 구간의 미수" 라는 값이 애초에 존재하지 않는다 — 담으면 화면이 없는 비교를 그린다.

    Args:
        rows: 직전 구간 파생 행.

    Returns:
        revenue/completed_count/avg_shipping_price/collected_*/overpaid_total/
        deduction_total 스칼라 dict.
    """
    revenue = _revenue_of(rows)
    count = len(rows)
    collected_deposit, collected_balance = _collected_split(rows)
    return {
        "revenue": revenue,
        "completed_count": count,
        "avg_shipping_price": revenue // count if count else 0,
        "collected_deposit": collected_deposit,
        "collected_balance": collected_balance,
        "collected_approx": collected_deposit + collected_balance,
        "overpaid_total": sum(row["overpaid"] for row in rows),
        "deduction_total": _deduction_total(rows),
    }


def _build_aging(all_rows: list[dict], today: datetime.date) -> tuple[list[dict], dict]:
    """미수 경과일 분포. 완료일 미상 미수는 **암묵 drop 하지 않고** 따로 낸다.

    미수는 기간 무관 지표라 모집단 전체를 본다(KPI ``receivable_*`` 와 같은 모집단 —
    버킷 합 + 미상 = ``receivable_count`` 가 항상 성립한다).

    Args:
        all_rows: 모집단 전체 파생 행.
        today: KST 오늘 날짜.

    Returns:
        (aging 리스트 5종 고정 순서, aging_unknown dict).
    """
    counts = {code: 0 for code, _ in AGING_BUCKETS}
    amounts = {code: 0 for code, _ in AGING_BUCKETS}
    unknown = {"count": 0, "amount": 0}
    for row in all_rows:
        if not _is_receivable(row):
            continue
        day = _day_to_date(row["day_key"])
        if day is None:
            unknown["count"] += 1
            unknown["amount"] += row["balance"]
            continue
        code = aging_bucket((today - day).days)
        counts[code] += 1
        amounts[code] += row["balance"]
    aging = [
        {"bucket": code, "label": label, "count": counts[code], "amount": amounts[code]}
        for code, label in AGING_BUCKETS
    ]
    return aging, unknown


def _build_channels(in_period: list[dict]) -> list[dict]:
    """채널별 건수·매출(기간 내). "일반"은 데이터가 없어도 항상 1행 낸다.

    Args:
        in_period: 기간 내 파생 행.

    Returns:
        [{"channel", "count", "revenue"}] — "일반" 먼저, 나머지는 코드 오름차순.
    """
    stats: dict[str, dict] = {}
    for row in in_period:
        entry = stats.setdefault(
            row["channel"], {"channel": row["channel"], "count": 0, "revenue": 0}
        )
        entry["count"] += 1
        if isinstance(row["shipping_price"], int):
            entry["revenue"] += row["shipping_price"]
    stats.setdefault(
        _DEFAULT_CHANNEL, {"channel": _DEFAULT_CHANNEL, "count": 0, "revenue": 0}
    )
    ordered = [stats.pop(_DEFAULT_CHANNEL)]
    ordered.extend(stats[name] for name in sorted(stats))
    return ordered


def _priced(row: dict) -> int:
    """출고가(미산출 None 은 0 기여)."""
    price = row["shipping_price"]
    return price if isinstance(price, int) else 0


def _build_forecast(
    expected_rows: list[dict],
    actual_rows: list[dict],
    prev_expected: list[dict],
    prev_actual: list[dict],
    start: datetime.date,
    end: datetime.date,
    granularity: str,
) -> dict:
    """예상 매출 vs 실제 매출(사용자 결정 2026-10-06).

    - **예상** = 진행 단계와 무관하게 시공일이 구간 안인 주문 전부의 출고가 합.
    - **실제** = 그중 시공완료(완료·AS접수·AS완료)의 출고가 합. ``kpi.revenue`` 와 같은 값이다
      — 같은 행·같은 구간이라 갈릴 수 없다(테스트가 항등식으로 고정).

    실제 모집단은 예상 모집단의 부분집합이라 버킷마다 ``actual <= expected`` 다.

    Args:
        expected_rows: 구간 안의 ERP 주문 전체 행.
        actual_rows: 구간 안의 시공완료 행.
        prev_expected: 직전 구간의 ERP 주문 전체 행.
        prev_actual: 직전 구간의 시공완료 행.
        start: 구간 시작일.
        end: 구간 종료일.
        granularity: "day" | "week" | "month".

    Returns:
        expected_*/actual_*/prev/buckets 를 가진 dict. ``expected_unpriced_count`` 는
        출고가를 아직 못 낸(품목 미입력) 건수 — 건수에는 들고 금액에는 0 으로 든다.
    """
    with_year = start.year != end.year
    buckets = {
        key: {
            "key": key, "label": _bucket_label(key, granularity, with_year),
            "expected": 0, "expected_count": 0, "actual": 0, "actual_count": 0,
        }
        for key in _enumerate_bucket_keys(start, end, granularity)
    }
    for rows, field in ((expected_rows, "expected"), (actual_rows, "actual")):
        for row in rows:
            entry = buckets.get(_bucket_key(row, granularity))
            if entry is None:
                continue
            entry[field] += _priced(row)
            entry[f"{field}_count"] += 1
    return {
        "expected_revenue": sum(_priced(row) for row in expected_rows),
        "expected_count": len(expected_rows),
        "expected_unpriced_count": sum(
            1 for row in expected_rows if not isinstance(row["shipping_price"], int)
        ),
        "actual_revenue": _revenue_of(actual_rows),
        "actual_count": len(actual_rows),
        "prev": {
            "expected_revenue": sum(_priced(row) for row in prev_expected),
            "expected_count": len(prev_expected),
            "actual_revenue": _revenue_of(prev_actual),
            "actual_count": len(prev_actual),
        },
        "buckets": list(buckets.values()),
    }


def _build_brand_channels(expected_rows: list[dict], actual_rows: list[dict]) -> list[dict]:
    """일반/라홈 두 칸의 예상·실제 매출. 데이터가 없어도 두 칸을 항상 낸다.

    Args:
        expected_rows: 구간 안의 ERP 주문 전체 행.
        actual_rows: 구간 안의 시공완료 행.

    ``naver_*`` 는 그 칸 **안의** 네이버 주문 몫이다(사용자 결정 2026-10-06 — 라홈 막대 안에
    네이버를 따로, shop in shop). 네이버는 늘 라홈 칸에 들므로 일반 칸의 ``naver_*`` 는 0 이다.
    칸 합계에 이미 포함된 값이라 더하면 이중 계상이다.

    Returns:
        [{"channel", "label", "expected_revenue", "expected_count",
          "actual_revenue", "actual_count", "naver_expected_revenue",
          "naver_expected_count", "naver_actual_revenue", "naver_actual_count"}]
        — :data:`BRAND_CHANNELS` 순서.
    """
    stats = {
        code: {
            "channel": code, "label": label,
            "expected_revenue": 0, "expected_count": 0,
            "actual_revenue": 0, "actual_count": 0,
            "naver_expected_revenue": 0, "naver_expected_count": 0,
            "naver_actual_revenue": 0, "naver_actual_count": 0,
        }
        for code, label in BRAND_CHANNELS
    }
    for rows, field in ((expected_rows, "expected"), (actual_rows, "actual")):
        for row in rows:
            entry = stats[row["brand"]]
            entry[f"{field}_revenue"] += _priced(row)
            entry[f"{field}_count"] += 1
            if row["channel"] == _NAVER_CHANNEL:
                entry[f"naver_{field}_revenue"] += _priced(row)
                entry[f"naver_{field}_count"] += 1
    return [stats[code] for code, _ in BRAND_CHANNELS]


def _manager_group_key(name: str) -> str:
    """담당자 그룹 키 — 앞뒤 공백·대소문자 차이를 한 행으로 접는다.

    "Kim" / " kim" / "KIM" 은 한 사람이다. 접지 않으면 같은 담당자가 순위표에 여러 줄로
    쪼개져 1등이 실제보다 작아진다. ``casefold`` 는 ``lower`` 보다 넓은 접기다.

    Args:
        name: 행에서 파생한 담당자 표시명.

    Returns:
        그룹 키. 미지정(빈 값·"-")이면 빈 문자열(= 미지정 버킷 sentinel).
    """
    key = name.strip().casefold()
    return "" if key in _MANAGER_UNASSIGNED_KEYS else key


def _build_managers(in_period: list[dict]) -> tuple[list[dict], dict]:
    """담당자별 건수·매출(기간 내)과 그 합계.

    모집단은 ``channels``/``settlement_status`` 와 같은 기간 스코프다. 그래야
    ``managers_total`` 이 ``kpi.revenue``/``kpi.completed_count`` 와 정확히 맞는다 —
    한 행도 빠지지 않으니(미지정도 버킷을 받는다) 합이 KPI 와 갈릴 수 없다.

    Args:
        in_period: 기간 내 파생 행.

    Returns:
        ([{"manager", "count", "revenue"}] 매출 내림차순(미지정은 항상 마지막),
         {"count", "revenue"} 합계).
    """
    stats: dict[str, dict] = {}
    spellings: dict[str, Counter] = {}
    for row in in_period:
        key = _manager_group_key(row["manager"])
        entry = stats.setdefault(
            key, {"manager": _MANAGER_UNASSIGNED_LABEL, "count": 0, "revenue": 0}
        )
        entry["count"] += 1
        if isinstance(row["shipping_price"], int):
            entry["revenue"] += row["shipping_price"]
        if key:
            spellings.setdefault(key, Counter())[row["manager"]] += 1
    for key, counter in spellings.items():
        # 표기는 가장 흔한 원본 철자로 낸다. 동수면 사전순으로 갈라 결과가 DB 행 순서에
        # 따라 흔들리지 않게 한다.
        stats[key]["manager"] = sorted(counter.items(), key=lambda kv: (-kv[1], kv[0]))[0][0]
    unassigned = stats.pop("", None)
    ordered = sorted(
        stats.values(), key=lambda item: (-item["revenue"], -item["count"], item["manager"])
    )
    if unassigned is not None:
        ordered.append(unassigned)
    return ordered, {
        "count": sum(item["count"] for item in ordered),
        "revenue": sum(item["revenue"] for item in ordered),
    }


def _as_billing_breakdown(in_period: list[dict]) -> dict:
    """AS 청구 판정 분포(기간 내) — 4분류 SSOT ``as_billing_badge_kind`` 를 3버킷으로 접는다.

    모집단은 **``as_axis_status IS NOT NULL``**(AS-AXIS-01, `erp_as_scope_condition`).
    구 술어 ``status in ('AS_RECEIVED','AS_COMPLETED')`` 는 status 가 overlay 라 외부
    write 한 번에 AS 건이 통째로 빠졌다(2026-08-14 사고). 다만 AS 축 투영이 비었는데 유상
    확정만 남은 레거시 행이 있어 그런 행도 **분모에 넣는다** — 안 넣으면
    ``as_billing_paid_count`` 가 ``as_total_count`` 를 넘는다(분자 > 분모).

    분류는 정확히 3갈래라 합이 ``as_total_count`` 다:
    'paid'=유상 확정 / None=무상(또는 유상 계열 아님) / 'paid_unconfirmed'·'undecided'=미확정.

    Args:
        in_period: 기간 내 파생 행.

    Returns:
        as_total_count/as_billing_paid_count/as_billing_paid_amount/
        as_billing_free_count/as_billing_undecided_count.
    """
    total = paid_count = paid_amount = free = undecided = 0
    for row in in_period:
        is_paid = row["as_billing_paid"] is not None
        if is_paid:
            paid_count += 1
            paid_amount += row["as_billing_paid"]
        if not (row["has_as_axis"] or is_paid):
            continue
        total += 1
        if is_paid:
            continue
        if row["as_billing_kind"] is None:
            free += 1
        else:
            undecided += 1
    return {
        "as_total_count": total,
        "as_billing_paid_count": paid_count,
        "as_billing_paid_amount": paid_amount,
        "as_billing_free_count": free,
        "as_billing_undecided_count": undecided,
    }


def _build_settlement_status(in_period: list[dict]) -> dict:
    """정산 현황(기간 내): 청구 여부·현금영수증·AS 청구 분포·부서별 차감.

    Args:
        in_period: 기간 내 파생 행.

    Returns:
        반환 스키마의 ``settlement_status`` dict.
    """
    issued = sum(1 for row in in_period if row["settlement_issued"])
    dept_amount = {code: 0 for code, _ in SETTLEMENT_DEPARTMENT_OPTIONS}
    dept_count = {code: 0 for code, _ in SETTLEMENT_DEPARTMENT_OPTIONS}
    for row in in_period:
        for department, amount in row["deductions"]:
            if department in dept_amount:
                dept_amount[department] += amount
                dept_count[department] += 1
    return {
        "issued_count": issued,
        "pending_count": len(in_period) - issued,
        "cash_receipt_requested": sum(
            1 for row in in_period if row["cash_receipt_state"] == "requested"
        ),
        "cash_receipt_issued": sum(1 for row in in_period if row["cash_receipt_issued"]),
        **_as_billing_breakdown(in_period),
        "deductions_by_department": [
            {
                "department": code,
                "label": label,
                "amount": dept_amount[code],
                "count": dept_count[code],
            }
            for code, label in SETTLEMENT_DEPARTMENT_OPTIONS
        ],
    }


def _stage_sort_index(code: str) -> tuple[int, str]:
    """단계 정렬 키 — ``STAGE_LABELS`` 선언 순서, 미등재 코드는 뒤에 사전순."""
    order = list(STAGE_LABELS)
    return (order.index(code), "") if code in order else (len(order), code)


def _build_stages(db: Any) -> list[dict]:
    """단계별 물린 금액(현재 시점 스냅샷 — 기간 스코프 밖, SPEC §4.4 별도 모집단).

    완료 계열(COMPLETED/AS_COMPLETED)을 뺀 진행 중 ERP 주문을 stage code 로 묶는다.
    라벨은 ``STAGE_LABELS`` 정본이며, 목업의 '해피콜' 같은 실재하지 않는 단계는 만들지
    않는다. 데이터에 없는 단계는 행을 내지 않는다(가짜 0 행 금지).

    Args:
        db: SQLAlchemy Session.

    Returns:
        [{"stage", "label", "count", "amount"}] — STAGE_LABELS 선언 순.
    """
    rows = fetch_settlement_rows(
        db,
        (Order.erp_stage_code,),
        (
            Order.active_filter(),
            Order.is_erp_order.is_(True),
            Order.erp_stage_code.isnot(None),
            ~Order.erp_stage_code.in_(_COMPLETED_STAGE_CODES),
        ),
    )
    stats: dict[str, dict] = {}
    for row in rows:
        code = str(row.erp_stage_code)
        entry = stats.setdefault(
            code,
            {"stage": code, "label": STAGE_LABELS.get(code, code), "count": 0, "amount": 0},
        )
        entry["count"] += 1
        price = erp_shipping_price_from_structured(_ensure_dict(row.structured_data))
        if isinstance(price, int):
            entry["amount"] += price
    return [stats[code] for code in sorted(stats, key=_stage_sort_index)]


def _build_unknown_completion(all_rows: list[dict]) -> dict:
    """완료일 미상 건(기간 합계에 미포함 — 별도 표기용). 암묵 drop 금지.

    Args:
        all_rows: 모집단 전체 파생 행.

    Returns:
        {"count", "amount"} — amount 는 출고가 합(미산출 건은 0 기여).
    """
    unknown = [row for row in all_rows if not row["day_key"]]
    return {
        "count": len(unknown),
        "amount": sum(
            row["shipping_price"] for row in unknown
            if isinstance(row["shipping_price"], int)
        ),
    }


# ---------------------------------------------------------------------------
# 공개 진입점
# ---------------------------------------------------------------------------


def aggregate_settlement(
    db: Any,
    *,
    month_from: str | None = None,
    month_to: str | None = None,
    granularity: str = "month",
    date_from: str | None = None,
    date_to: str | None = None,
) -> dict:
    """정산 대시보드 집계 — 완료 대시보드 200건 캡과 무관한 전량 집계.

    구간은 월(``month_from``/``month_to``) 또는 날짜(``date_from``/``date_to``)로 준다.
    날짜가 오면 날짜가 우선이다(정산 탭 공통 기간 바). 직전 비교 구간 규칙은
    :func:`_resolve_period`.

    Args:
        db: SQLAlchemy Session.
        month_from: 조회 시작 월 "YYYY-MM"(포함).
        month_to: 조회 종료 월 "YYYY-MM"(포함).
        granularity: "day" | "week" | "month".
        date_from: 조회 시작일 "YYYY-MM-DD"(포함).
        date_to: 조회 종료일 "YYYY-MM-DD"(포함).

    Returns:
        range/kpi/buckets/prev_buckets/prev_totals/aging/aging_unknown/channels/
        managers/managers_total/settlement_status/stages/unknown_completion/
        forecast/brand_channels 키를 가진 dict.

    Raises:
        ValueError: 월·날짜 형식 오류, granularity 미지원, 범위 역전, 상한 초과.
    """
    if granularity not in _GRANULARITIES:
        raise ValueError(
            f"granularity 는 {'|'.join(_GRANULARITIES)} 중 하나여야 합니다: {granularity!r}"
        )
    period = _resolve_period(month_from, month_to, date_from, date_to)
    start, end = period["start"], period["end"]
    prev_start, prev_end = period["prev_start"], period["prev_end"]
    erp_rows = _load_rows(db)
    all_rows = [row for row in erp_rows if _is_settlement_row(row)]
    in_period = _rows_in_span(all_rows, start, end)
    prev_period = _rows_in_span(all_rows, prev_start, prev_end)
    expected = _rows_in_span(erp_rows, start, end)
    aging, aging_unknown = _build_aging(all_rows, get_today_kst())
    managers, managers_total = _build_managers(in_period)
    return {
        "range": {
            "month_from": start.isoformat()[:7],
            "month_to": end.isoformat()[:7],
            "granularity": granularity,
            "date_from": start.isoformat(),
            "date_to": end.isoformat(),
            "prev_date_from": prev_start.isoformat(),
            "prev_date_to": prev_end.isoformat(),
        },
        "kpi": _build_kpi(in_period, all_rows),
        "buckets": _build_buckets(in_period, start, end, granularity),
        "prev_buckets": _build_buckets(prev_period, prev_start, prev_end, granularity),
        "prev_totals": _build_period_totals(prev_period),
        "aging": aging,
        "aging_unknown": aging_unknown,
        "channels": _build_channels(in_period),
        "managers": managers,
        "managers_total": managers_total,
        "settlement_status": _build_settlement_status(in_period),
        "stages": _build_stages(db),
        "unknown_completion": _build_unknown_completion(all_rows),
        "forecast": _build_forecast(
            expected, in_period,
            _rows_in_span(erp_rows, prev_start, prev_end), prev_period,
            start, end, granularity,
        ),
        "brand_channels": _build_brand_channels(expected, in_period),
    }
