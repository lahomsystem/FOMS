"""채널(네이버) 정산 조회 커널 — SETTLE-CHANNEL-01 §5 (읽기 전용).

적재(:mod:`foms.services.integrations.naver_commerce.settle_sync`)가 채워 둔 5개 테이블을
화면 한 벌이 필요한 모양으로 한 번에 접는다. **네이버가 준 금액을 다시 계산하지 않는다** —
유일한 파생은 실효 수수료율(``commission_rate``)과 매칭률(``match_rate``)이라는 두 개의
**비(比)** 뿐이고, 그 분자·분모는 응답에 그대로 함께 실어 화면이 근거를 보여줄 수 있게 한다.

축 규율(계약 D-2):

* **일별 집계·KPI·워터폴·입금 채널은 언제나 정산 예정일**(``settle_expect_date``) 축이다.
  ``basis`` 셀렉터는 **원장에만** 적용된다 — 위쪽 고정 컨텍스트가 축을 바꾸면 일별↔건별
  대사(``reconcile``)가 같은 화면 안에서 두 축을 비교하게 되어 항상 어긋난다.
* 부가세는 ``settle_basis_date`` 축이다(매출이 일어난 날로 신고하므로 정산 예정일과 다르다).

부호 규율(계약 D-1): 취소·환급 행의 음수를 절대값으로 바꾸지 않는다. 합계는 음수를 포함한
실제 합이다. 워터폴만 **방향 선언**을 한다 — 차감 단계(수수료·보류·충전금 상계)에 ``-1`` 을
곱해 부동 막대가 아래로 향하게 하되 크기는 네이버 값 그대로다(재계산이 아니라 표시 방향).

워터마크(``SystemSetting`` 한 행)는 ``settle_sync`` 를 import 하지 않고 **여기서 직접 읽는다**.
조회 커널이 적재 모듈에 의존하면 화면 한 번 그리는 데 네이버 클라이언트·rq·requests 가 전부
import 되고, 적재 쪽 실패가 조회 화면까지 끌고 내려간다(키 문자열만 공유하면 충분하다).

이 모듈은 읽기 전용이다 — 커밋·flag_modified·속성 대입을 하지 않는다.
"""

from __future__ import annotations

import datetime
import math
from decimal import Decimal, InvalidOperation
from typing import Any, Optional

from sqlalchemy import func, or_

from foms.services.datetime_kst import now_utc_naive
from foms.services.integrations.naver_commerce.settle_enums import (
    BANK_TYPES,
    COMMISSION_TYPES,
    PAY_MEANS_TYPES,
    PERIOD_TYPES,
    PRODUCT_ORDER_TYPES,
    SETTLE_METHOD_TYPES,
    SETTLE_TYPES,
    VAT_DETAIL_TYPES,
    VAT_STATUSES,
    label,
)
from models import (
    NaverSettleCase,
    NaverSettleCommission,
    NaverSettleDaily,
    NaverSettleSyncRun,
    NaverVatCase,
    NaverVatDaily,
    SystemSetting,
)

__all__ = [
    "BASES",
    "BASIS_LABELS",
    "DEFAULT_PER_PAGE",
    "GRANULARITIES",
    "LEDGER_KINDS",
    "MAX_PER_PAGE",
    "MAX_RANGE_DAYS",
    "SETTLE_SYNC_SETTING_KEY",
    "STALE_AFTER_HOURS",
    "build_channel_dashboard",
    "mask_account_no",
]

#: 워터마크 행 키. :data:`foms.services.integrations.naver_commerce.settle_sync.SETTING_KEY`
#: 와 **같은 문자열**이다(그 모듈을 import 하지 않으려고 여기 한 번 더 적는다 — 두 값이
#: 갈리면 화면이 영원히 "아직 한 번도 동기화되지 않았습니다"를 말한다).
SETTLE_SYNC_SETTING_KEY = "naver_settle_sync_state"

#: 마지막 **성공** 시각이 이보다 오래되면 화면이 "오래됐다"고 말한다.
STALE_AFTER_HOURS = 36

#: 정산 예정일이 이보다 과거면 네이버가 더 이상 바꾸지 않는다(확정 구간 표시용).
FINAL_BEFORE_DAYS = 30

#: 기준일 축 4종. 기본은 정산 예정일(#1481 — settle/daily 의 필터 기준과 같아야 대사가 선다).
BASES = ("expect", "complete", "basis", "pay")
BASIS_LABELS: dict[str, str] = {
    "expect": "정산 예정일 기준",
    "complete": "정산 완료일 기준",
    "basis": "정산 기준일 기준",
    "pay": "결제일 기준",
}
DEFAULT_BASIS = "expect"

GRANULARITIES = ("day", "week", "month")
DEFAULT_GRANULARITY = "day"

LEDGER_KINDS = ("case", "commission", "vat_case")
DEFAULT_LEDGER = "case"

#: 조회 폭 상한(일). 전기 비교까지 하면 실제 스캔은 두 배다.
MAX_RANGE_DAYS = 400
#: 원장 페이지 크기 상한/기본(화면 기본은 60건 — `channel.js` 의 ``PER_PAGE``).
MAX_PER_PAGE = 200
DEFAULT_PER_PAGE = 60

#: 예외 큐가 한 종류에서 담아 오는 최대 행수. 넘치면 화면이 스크롤 괴물이 된다.
_EXCEPTION_CAP = 50

#: 원장 행 직렬화 타입 태그.
_DATE, _MONEY, _TEXT, _INT = "date", "money", "text", "int"

#: 필드명 → enum 카탈로그. 직렬화가 ``<필드>_label`` 을 자동으로 붙인다(화면은 한글만 쓴다).
_ENUM_MAPS: dict[str, dict[str, str]] = {
    "period_type": PERIOD_TYPES,
    "product_order_type": PRODUCT_ORDER_TYPES,
    "settle_type": SETTLE_TYPES,
    "commission_type": COMMISSION_TYPES,
    "pay_means_type": PAY_MEANS_TYPES,
    "settle_method_type": SETTLE_METHOD_TYPES,
    "bank_type": BANK_TYPES,
    "detail_type": VAT_DETAIL_TYPES,
    "status": VAT_STATUSES,
}

#: ``basis`` → 원장 날짜 컬럼 이름. 없는 모델(수수료 상세엔 ``pay_date`` 가 없다)은
#: :func:`_ledger_date_expr` 이 예정일로 되돌린다.
_BASIS_COLUMN: dict[str, str] = {
    "expect": "settle_expect_date",
    "complete": "settle_complete_date",
    "basis": "settle_basis_date",
    "pay": "pay_date",
}

#: 부가세 8금액 — (응답 키, 컬럼명). 일자표·합계·건별이 같은 이름을 쓴다.
_VAT_AMOUNTS: tuple[tuple[str, str], ...] = (
    ("total_sales", "total_sales_amount"),
    ("taxation_sales", "taxation_sales_amount"),
    ("tax_exemption_sales", "tax_exemption_sales_amount"),
    ("credit_card", "credit_card_amount"),
    ("cash_income_deduction", "cash_income_deduction_amount"),
    ("cash_outgoing_evidence", "cash_outgoing_evidence_amount"),
    ("cash_exclusion_issuance", "cash_exclusion_issuance_amount"),
    ("other", "other_amount"),
)

#: 워터폴 7단계 — (key, label, 합계 키, 방향). **네이버가 부호를 이미 준다**(스테이징 실측
#: 2026-09-02: ``commissionSettleAmount`` -950081, ``payHoldbackAmount`` -10053445, 취소 행의
#: 수수료는 +). 그래서 방향은 전부 +1 이고 값을 그대로 그린다 — 차감 단계에 -1 을 곱하면
#: 음수가 양수로 뒤집혀 워터폴이 거꾸로 선다(재계산 금지 계약 D-4 위반).
_WATERFALL_STEPS: tuple[tuple[str, str, str, int], ...] = (
    ("pay_settle", "결제 정산액", "pay_settle", 1),
    ("commission", "수수료", "commission", 1),
    ("benefit", "혜택 정산", "benefit", 1),
    ("deduction_restore", "공제 환급", "deduction_restore", 1),
    ("holdback", "지급 보류·한도", "holdback", 1),
    ("minus_charge", "충전금 상계", "minus_charge", 1),
    ("settle_amount", "정산 금액", "settle_amount", 1),
)

#: 일별 버킷이 접는 (응답 키, 컬럼명) — ``holdback`` 만 두 컬럼의 합이다(KPI 타일과 같은 정의).
_DAILY_SUMS: tuple[tuple[str, str], ...] = (
    ("normal", "normal_settle_amount"),
    ("quick", "quick_settle_amount"),
    ("deduction_restore", "deduction_restore_settle_amount"),
    ("commission", "commission_settle_amount"),
    ("benefit", "benefit_settle_amount"),
    ("minus_charge", "minus_charge_amount"),
    ("pay_settle", "pay_settle_amount"),
    ("settle_amount", "settle_amount"),
)

_CASE_FIELDS: tuple[tuple[str, str], ...] = (
    ("search_date", _DATE), ("period_type", _TEXT),
    ("settle_basis_date", _DATE), ("settle_expect_date", _DATE),
    ("settle_complete_date", _DATE), ("pay_date", _DATE),
    ("order_id", _TEXT), ("product_order_id", _TEXT),
    ("product_order_type", _TEXT), ("settle_type", _TEXT),
    ("product_id", _TEXT), ("product_name", _TEXT), ("purchaser_name", _TEXT),
    ("pay_settle_amount", _MONEY), ("total_pay_commission_amount", _MONEY),
    ("free_installment_commission_amount", _MONEY),
    ("selling_interlock_commission_amount", _MONEY),
    ("benefit_settle_amount", _MONEY), ("settle_expect_amount", _MONEY),
    ("merchant_id", _TEXT), ("merchant_name", _TEXT), ("contract_no", _TEXT),
    ("link_id", _INT),
)

_COMMISSION_FIELDS: tuple[tuple[str, str], ...] = (
    ("search_date", _DATE), ("period_type", _TEXT),
    ("order_no", _TEXT), ("product_order_id", _TEXT),
    ("product_order_type", _TEXT), ("product_id", _TEXT), ("product_name", _TEXT),
    ("merchant_id", _TEXT), ("merchant_name", _TEXT), ("purchaser_name", _TEXT),
    ("settle_type", _TEXT), ("settle_basis_date", _DATE),
    ("settle_expect_date", _DATE), ("settle_complete_date", _DATE),
    ("tax_return_date", _DATE), ("commission_basis_amount", _MONEY),
    ("commission_type", _TEXT), ("pay_means_type", _TEXT),
    ("commission_amount", _MONEY),
    ("maximum_selling_interlock_commission_amount", _MONEY),
)

_VAT_CASE_FIELDS: tuple[tuple[str, str], ...] = (
    ("settle_basis_date", _DATE), ("order_id", _TEXT),
    ("product_order_id", _TEXT), ("product_order_type", _TEXT),
    ("detail_type", _TEXT), ("status", _TEXT), ("product_name", _TEXT),
) + tuple((column, _MONEY) for _key, column in _VAT_AMOUNTS) + (
    ("merchant_id", _TEXT), ("merchant_name", _TEXT),
)

#: 원장 종류 → (모델, 필드표, 합계 컬럼, 유형 필터 필드, 검색 필드).
_LEDGER_SPEC: dict[str, tuple] = {
    "case": (NaverSettleCase, _CASE_FIELDS, "settle_expect_amount",
             ("product_order_type", "settle_type"), ("order_id", "product_order_id")),
    "commission": (NaverSettleCommission, _COMMISSION_FIELDS, "commission_amount",
                   ("commission_type", "pay_means_type"), ("order_no", "product_order_id")),
    "vat_case": (NaverVatCase, _VAT_CASE_FIELDS, "total_sales_amount",
                 ("detail_type", "status"), ("order_id", "product_order_id")),
}

_ZERO = Decimal("0")


# ---------------------------------------------------------------------------
# 값 변환 — 합산은 Decimal, 직렬화 직전에 한 번만 숫자로 바꾼다
# ---------------------------------------------------------------------------


def _dec(value: Any) -> Decimal:
    """어떤 값이든 합산 가능한 :class:`~decimal.Decimal` 로(빈 값·파싱 실패는 0).

    Args:
        value: DB 에서 온 ``Numeric``/문자열/숫자/``None``.

    Returns:
        Decimal 값(변환 불가면 0).
    """
    if value is None:
        return _ZERO
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return _ZERO


def _money(value: Any, *, default: Any = None) -> Any:
    """금액 → JSON 숫자. 정수로 떨어지면 ``int``, 소수부가 있으면 ``float``.

    원화라 실무 값은 전부 정수지만 컬럼이 ``Numeric(16, 2)`` 라 소수를 **버리지 않는다**
    (버림은 회계에서 조용한 손실이다).

    Args:
        value: Decimal/숫자/``None``.
        default: ``None`` 일 때 돌려줄 값(합계는 0, 행 필드는 None 을 쓴다).

    Returns:
        ``int`` | ``float`` | ``default``.
    """
    if value is None:
        return default
    amount = _dec(value)
    return int(amount) if amount == amount.to_integral_value() else float(amount)


def _day(value: Any) -> Optional[str]:
    """날짜 값 → ``"YYYY-MM-DD"``(SQLite 는 문자열로 돌려주므로 둘 다 받는다)."""
    if value is None or value == "":
        return None
    if isinstance(value, (datetime.date, datetime.datetime)):
        return value.isoformat()[:10]
    return str(value)[:10]


def _ratio(numerator: Decimal, denominator: Decimal) -> Optional[float]:
    """비(比). 분모가 0 이면 ``None`` — "0% 로 그리기"는 없는 사실을 말하는 것이다."""
    if denominator == 0:
        return None
    return float(numerator / denominator)


def mask_account_no(value: Any) -> str:
    """계좌번호 → ``'****1234'``(뒤 4자리만). 값이 없으면 빈 문자열.

    화면·CSV 어디에도 전체 계좌번호를 내지 않는다. 뒤 4자리는 통장 대사에 필요한 최소한이다.

    Args:
        value: 원본 계좌번호(구분자 포함 가능).

    Returns:
        마스킹 문자열. 자릿수가 4 미만이면 ``'****'``.
    """
    text = "".join(ch for ch in str(value or "") if ch.isalnum())
    if not text:
        return ""
    return "****" + text[-4:] if len(text) >= 4 else "****"


# ---------------------------------------------------------------------------
# 기간·버킷
# ---------------------------------------------------------------------------


def _previous_range(date_from: datetime.date,
                    date_to: datetime.date) -> tuple[datetime.date, datetime.date]:
    """같은 길이의 **직전** 구간. (from-길이, from-1일).

    Args:
        date_from: 현재 구간 시작.
        date_to: 현재 구간 끝(포함).

    Returns:
        (직전 시작, 직전 끝).
    """
    span = (date_to - date_from).days + 1
    prev_to = date_from - datetime.timedelta(days=1)
    return prev_to - datetime.timedelta(days=span - 1), prev_to


def _previous_month_end(today: datetime.date) -> datetime.date:
    """전월 말일 — 부가세 자료가 제공되는 마지막 날(당월분은 익월 마감 후)."""
    first = today.replace(day=1)
    return first - datetime.timedelta(days=1)


def _bucket_key(day: datetime.date, granularity: str) -> str:
    """날짜 → 버킷 키. day="YYYY-MM-DD", week=그 주 월요일, month="YYYY-MM-01"."""
    if granularity == "month":
        return day.replace(day=1).isoformat()
    if granularity == "week":
        return (day - datetime.timedelta(days=day.weekday())).isoformat()
    return day.isoformat()


def _enumerate_buckets(date_from: datetime.date, date_to: datetime.date,
                       granularity: str) -> list[str]:
    """구간 전체의 버킷 키를 오름차순으로(빈 버킷도 포함 — 시간축에 구멍을 내지 않는다).

    Args:
        date_from: 시작일.
        date_to: 종료일(포함).
        granularity: day|week|month.

    Returns:
        버킷 키 목록(중복 없음, 오름차순).
    """
    keys: list[str] = []
    seen: set[str] = set()
    cursor = date_from
    while cursor <= date_to:
        key = _bucket_key(cursor, granularity)
        if key not in seen:
            seen.add(key)
            keys.append(key)
        cursor += datetime.timedelta(days=1)
    return keys


# ---------------------------------------------------------------------------
# 동기화 상태(워터마크)
# ---------------------------------------------------------------------------


def read_sync_state(session: Any) -> dict[str, Any]:
    """``SystemSetting`` 한 행에 담긴 정산 동기화 상태(없으면 빈 dict).

    ``settle_sync`` 를 import 하지 않는다(모듈 docstring 참고) — 키 문자열만 공유한다.

    Args:
        session: SQLAlchemy Session.

    Returns:
        상태 dict.
    """
    row = session.get(SystemSetting, SETTLE_SYNC_SETTING_KEY)
    value = row.setting_value if row is not None else None
    return dict(value) if isinstance(value, dict) else {}


def _hours_since(stamp: Any) -> Optional[float]:
    """naive UTC ISO 문자열이 몇 시간 전인지(파싱 실패·빈 값은 None)."""
    text = str(stamp or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is not None:
        parsed = parsed.replace(tzinfo=None)
    return (now_utc_naive() - parsed).total_seconds() / 3600.0


def _build_sync(session: Any, today: datetime.date) -> dict[str, Any]:
    """S0 동기화 헤더가 읽는 상태 블록.

    ``never``(아직 한 번도)와 ``stale``(오래됨)을 **다른 사실**로 구분한다 — 화면이 결측을
    0 으로 그리지 않게 하는 계약 D-10 의 서버 쪽 절반이다.

    Args:
        session: SQLAlchemy Session.
        today: KST 오늘.

    Returns:
        계약 §5 의 ``sync`` dict.
    """
    state = read_sync_state(session)
    never = not state or not state.get("last_run_at")
    age = _hours_since(state.get("last_ok_at"))
    return {
        "last_run_at": state.get("last_run_at"),
        "last_ok_at": state.get("last_ok_at"),
        "status": state.get("last_status") or state.get("status"),
        "coverage_from": state.get("coverage_from"),
        "coverage_to": state.get("coverage_to"),
        "rolling_days": state.get("rolling_days"),
        "final_before": (today - datetime.timedelta(days=FINAL_BEFORE_DAYS)).isoformat(),
        "vat_available_to": _previous_month_end(today).isoformat(),
        "rev": state.get("rev"),
        "stale": (not never) and (age is None or age > STALE_AFTER_HOURS),
        "never": never,
    }


def _latest_run(session: Any, channel: str) -> Optional[Any]:
    """가장 최근 동기화 실행 1행(없으면 None). 예외 큐의 소급 변경이 여기서 나온다."""
    return (session.query(NaverSettleSyncRun)
            .filter(NaverSettleSyncRun.channel == channel)
            .order_by(NaverSettleSyncRun.started_at.desc(),
                      NaverSettleSyncRun.id.desc())
            .first())


# ---------------------------------------------------------------------------
# 일별 축(정산 예정일) — KPI·차트·워터폴·입금 채널의 원천
# ---------------------------------------------------------------------------


def _daily_rows(session: Any, channel: str, date_from: datetime.date,
                date_to: datetime.date) -> list[Any]:
    """구간 안의 ``naver_settle_daily`` 행(정산 예정일 축, 인덱스 그대로 탄다).

    Args:
        session: SQLAlchemy Session.
        channel: 채널 코드.
        date_from: 시작일.
        date_to: 종료일(포함).

    Returns:
        ORM 행 목록(예정일 오름차순).
    """
    return (session.query(NaverSettleDaily)
            .filter(NaverSettleDaily.channel == channel,
                    NaverSettleDaily.settle_expect_date >= date_from,
                    NaverSettleDaily.settle_expect_date <= date_to)
            .order_by(NaverSettleDaily.settle_expect_date.asc(),
                      NaverSettleDaily.id.asc())
            .all())


def _holdback_of(row: Any) -> Decimal:
    """지급 보류 + 한도 보류. KPI 타일·일별 계열·워터폴이 **같은 정의**를 쓴다."""
    return _dec(row.pay_holdback_amount) + _dec(row.settlement_limit_amount)


def _build_daily(rows: list[Any], date_from: datetime.date, date_to: datetime.date,
                 granularity: str) -> list[dict]:
    """일별(주별·월별) 정산 흐름. 행이 하나도 없으면 **빈 목록**(0 으로 그리지 않는다).

    Args:
        rows: :func:`_daily_rows` 결과.
        date_from: 시작일.
        date_to: 종료일(포함).
        granularity: day|week|month.

    Returns:
        계약 §5 의 ``daily`` 목록(버킷 키 오름차순, 구간 전체를 채운다).
    """
    if not rows:
        return []
    keys = _enumerate_buckets(date_from, date_to, granularity)
    sums: dict[str, dict[str, Decimal]] = {
        key: {name: _ZERO for name, _col in _DAILY_SUMS} for key in keys
    }
    for key in keys:
        sums[key]["holdback"] = _ZERO
    done: dict[str, list[bool]] = {key: [] for key in keys}
    for row in rows:
        expect = row.settle_expect_date
        if expect is None:
            continue
        key = _bucket_key(expect, granularity)
        bucket = sums.get(key)
        if bucket is None:
            continue
        for name, column in _DAILY_SUMS:
            bucket[name] += _dec(getattr(row, column))
        bucket["holdback"] += _holdback_of(row)
        done[key].append(row.settle_complete_date is not None)
    return [_daily_bucket(key, sums[key], done[key]) for key in keys]


def _daily_bucket(key: str, sums: dict[str, Decimal], done: list[bool]) -> dict:
    """버킷 1개를 응답 모양으로. ``completed`` 는 **그 버킷의 행이 전부 완료**일 때만 True."""
    bucket = {"date": key, "completed": bool(done) and all(done)}
    for name in list(sums):
        bucket[name] = _money(sums[name], default=0)
    return bucket


def _daily_totals(rows: list[Any]) -> dict[str, Decimal]:
    """구간 합계(Decimal 그대로). KPI·워터폴·대사가 이 한 벌을 나눠 쓴다."""
    totals: dict[str, Decimal] = {name: _ZERO for name, _col in _DAILY_SUMS}
    totals.update({"holdback": _ZERO, "settled": _ZERO, "expected": _ZERO,
                   "expected_account": _ZERO, "expected_charge": _ZERO})
    for row in rows:
        for name, column in _DAILY_SUMS:
            totals[name] += _dec(getattr(row, column))
        totals["holdback"] += _holdback_of(row)
        amount = _dec(row.settle_amount)
        if row.settle_complete_date is not None:
            totals["settled"] += amount
            continue
        totals["expected"] += amount
        method = str(row.settle_method_type or "").upper()
        if method == "ACCOUNT":
            totals["expected_account"] += amount
        elif method == "CHARGE_AMT":
            totals["expected_charge"] += amount
    return totals


# ---------------------------------------------------------------------------
# 건별(case) 축 — 매칭률·대사
# ---------------------------------------------------------------------------


def _case_scope(channel: str, date_from: datetime.date, date_to: datetime.date) -> tuple:
    """건별 정산의 구간 술어(정산 예정일, 없으면 조회일로 되돌린다).

    ``search_date`` 는 파티션 축이고 기본 ``period_type`` 이 정산 예정일 기준이라 둘은
    사실상 같은 날이다. 그래도 ``coalesce`` 로 되돌리는 이유는 예정일이 아직 안 잡힌 행
    (미확정 건)이 조용히 빠지지 않게 하기 위함이다.
    """
    axis = func.coalesce(NaverSettleCase.settle_expect_date, NaverSettleCase.search_date)
    return (NaverSettleCase.channel == channel, axis >= date_from, axis <= date_to)


def _build_case_stats(session: Any, channel: str, date_from: datetime.date,
                      date_to: datetime.date) -> dict[str, Any]:
    """건별 축 통계 — 건수·미매칭·매칭률 분모·결제 정산액 합(대사용).

    한 번의 group-by 로 끝낸다(행을 파이썬으로 끌어오지 않는다 — 원장은 페이지 단위다).

    Args:
        session: SQLAlchemy Session.
        channel: 채널 코드.
        date_from: 시작일.
        date_to: 종료일(포함).

    Returns:
        ``case_count``·``unmatched``·``matched``·``prod_orders``·``pay_settle`` dict.
    """
    scope = _case_scope(channel, date_from, date_to)
    rows = (session.query(NaverSettleCase.match_status,
                          func.count(NaverSettleCase.id),
                          func.sum(NaverSettleCase.pay_settle_amount))
            .filter(*scope).group_by(NaverSettleCase.match_status).all())
    stats = {"case_count": 0, "unmatched": 0, "matched": 0, "prod_orders": 0,
             "pay_settle": _ZERO}
    for status, count, total in rows:
        code = str(status or "NA").upper()
        stats["case_count"] += int(count or 0)
        stats["pay_settle"] += _dec(total)
        if code in ("MATCHED", "UNMATCHED"):
            stats["prod_orders"] += int(count or 0)
            stats["matched" if code == "MATCHED" else "unmatched"] += int(count or 0)
    return stats


# ---------------------------------------------------------------------------
# KPI · 워터폴 · 입금 채널 · 대사
# ---------------------------------------------------------------------------


def _kpi_block(totals: dict[str, Decimal], case_stats: dict[str, Any]) -> dict:
    """KPI 6타일이 읽는 스칼라 한 벌(전기 블록도 같은 함수를 쓴다).

    ``commission_rate`` 와 ``match_rate`` 는 이 화면의 **유일한 파생**이다. 분모가 0 이면
    ``None`` 을 내고 화면이 "분모가 0" 이라고 말한다(0% 라고 그리지 않는다).

    Args:
        totals: :func:`_daily_totals` 결과.
        case_stats: :func:`_build_case_stats` 결과.

    Returns:
        계약 §5 의 ``kpi`` dict(중첩 ``prev`` 는 호출부가 넣는다).
    """
    return {
        "settled_amount": _money(totals["settled"], default=0),
        "expected_amount": _money(totals["expected"], default=0),
        "expected_account_amount": _money(totals["expected_account"], default=0),
        "expected_charge_amount": _money(totals["expected_charge"], default=0),
        "commission_total": _money(totals["commission"], default=0),
        # 수수료는 음수로 오므로 비율은 크기(abs)로 낸다 — 파생값이라 부호를 정의할 수 있다.
        "commission_rate": _ratio(abs(totals["commission"]), totals["pay_settle"]),
        "holdback_amount": _money(totals["holdback"], default=0),
        "match_rate": (None if not case_stats["prod_orders"]
                       else case_stats["matched"] / case_stats["prod_orders"]),
        "unmatched_count": case_stats["unmatched"],
        "case_count": case_stats["case_count"],
    }


def _build_waterfall(totals: dict[str, Decimal]) -> list[dict]:
    """정산 구성 워터폴 7단계. 네이버 원본 부호를 그대로 그린다(차감은 이미 음수로 온다).

    Args:
        totals: :func:`_daily_totals` 결과.

    Returns:
        계약 §5 의 ``waterfall`` 목록(순서 고정).
    """
    return [
        {"key": key, "label": text,
         "amount": _money(_dec(totals.get(source)) * direction, default=0)}
        for key, text, source, direction in _WATERFALL_STEPS
    ]


def _build_deposit_channels(rows: list[Any]) -> list[dict]:
    """입금 채널 카드. 계좌 이체(ACCOUNT)와 충전금 상계(CHARGE_AMT)를 섞지 않는다.

    ``CHARGE_AMT`` 는 통장에 찍히지 않는 상계라 은행 대사 대상이 아니다(계약 D-7).
    계좌번호는 :func:`mask_account_no` 로 뒤 4자리만 낸다.

    Args:
        rows: :func:`_daily_rows` 결과.

    Returns:
        계약 §5 의 ``deposit_channels`` 목록(금액 절대값 내림차순).
    """
    buckets: dict[tuple, dict] = {}
    for row in rows:
        key = (str(row.settle_method_type or ""), str(row.bank_type or ""),
               str(row.depositor_name or ""), mask_account_no(row.account_no))
        item = buckets.setdefault(key, {"amount": _ZERO, "count": 0})
        item["amount"] += _dec(row.settle_amount)
        item["count"] += 1
    channels = [
        {"method": method or None, "method_label": label(SETTLE_METHOD_TYPES, method),
         "bank_type": bank or None, "bank_label": label(BANK_TYPES, bank),
         "depositor_name": depositor or None, "account_no_masked": masked,
         "amount": _money(item["amount"], default=0), "count": item["count"]}
        for (method, bank, depositor, masked), item in buckets.items()
    ]
    channels.sort(key=lambda item: abs(item["amount"]), reverse=True)
    return channels


def _build_reconcile(totals: dict[str, Decimal], case_stats: dict[str, Any]) -> dict:
    """일별↔건별 대사. 같은 예정일의 ``paySettleAmount`` 합이 같아야 한다(허용 오차 0).

    차이를 감추지 않는다 — 다르면 적재 누락이거나 소급 변경이고, 둘 다 사람이 알아야 한다.
    """
    daily_total = _dec(totals["pay_settle"])
    case_total = _dec(case_stats["pay_settle"])
    return {"daily_total": _money(daily_total, default=0),
            "case_total": _money(case_total, default=0),
            "diff": _money(daily_total - case_total, default=0)}


# ---------------------------------------------------------------------------
# 수수료 · 부가세
# ---------------------------------------------------------------------------


def _commission_scope(channel: str, date_from: datetime.date,
                      date_to: datetime.date) -> tuple:
    """수수료 상세의 구간 술어(정산 예정일, 없으면 조회일)."""
    axis = func.coalesce(NaverSettleCommission.settle_expect_date,
                         NaverSettleCommission.search_date)
    return (NaverSettleCommission.channel == channel, axis >= date_from, axis <= date_to)


def _build_commission(session: Any, channel: str, date_from: datetime.date,
                      date_to: datetime.date) -> dict:
    """수수료 유형별 구성 + 매출 연동 수수료 상한 미터.

    ``total`` 은 수수료 상세(commission-details)의 합이라 KPI 의 ``commission_total``
    (일별 정산의 ``commissionSettleAmount`` 합)과 **원천이 다르다**. 두 값이 어긋나면
    그 자체가 적재 신호라 어느 한쪽으로 맞추지 않는다.

    Args:
        session: SQLAlchemy Session.
        channel: 채널 코드.
        date_from: 시작일.
        date_to: 종료일(포함).

    Returns:
        계약 §5 의 ``commission`` dict.
    """
    scope = _commission_scope(channel, date_from, date_to)
    rows = (session.query(NaverSettleCommission.commission_type,
                          func.sum(NaverSettleCommission.commission_amount))
            .filter(*scope).group_by(NaverSettleCommission.commission_type).all())
    pairs = [(str(code or ""), _dec(total)) for code, total in rows]
    total = sum((amount for _code, amount in pairs), _ZERO)
    scale = sum((abs(amount) for _code, amount in pairs), _ZERO)
    pairs.sort(key=lambda pair: abs(pair[1]), reverse=True)
    by_type = [
        {"type": code or None, "label": label(COMMISSION_TYPES, code),
         "amount": _money(amount, default=0),
         "share": (None if scale == 0 else float(abs(amount) / scale))}
        for code, amount in pairs
    ]
    return {"by_type": by_type, "total": _money(total, default=0),
            "max_interlock": _interlock_meter(session, channel, date_from, date_to)}


def _interlock_meter(session: Any, channel: str, date_from: datetime.date,
                     date_to: datetime.date) -> dict:
    """매출 연동 수수료 소진 미터 — (부과 합, 상한 합).

    분자는 건별 정산의 ``sellingInterlockCommissionAmount`` 합, 분모는 수수료 상세의
    ``maximumSellingInterlockCommissionAmount`` 합이다(상한이 적힌 행만 센다).
    """
    charged = (session.query(func.sum(NaverSettleCase.selling_interlock_commission_amount))
               .filter(*_case_scope(channel, date_from, date_to)).scalar())
    column = NaverSettleCommission.maximum_selling_interlock_commission_amount
    cap = (session.query(func.sum(column))
           .filter(*_commission_scope(channel, date_from, date_to),
                   column.isnot(None)).scalar())
    return {"amount": _money(charged, default=0), "cap": _money(cap, default=0)}


def _build_vat(session: Any, channel: str, date_from: datetime.date,
               date_to: datetime.date, today: datetime.date) -> dict:
    """부가세 일자표 + 합계. **당월처럼 아직 제공되지 않는 구간은 0 으로 그리지 않는다**.

    축은 ``settle_basis_date``(매출이 일어난 날)다 — 정산 예정일 축과 섞으면 달 경계에서
    신고 금액이 어긋난다.

    Args:
        session: SQLAlchemy Session.
        channel: 채널 코드.
        date_from: 시작일.
        date_to: 종료일(포함).
        today: KST 오늘(제공 한계일 판정용).

    Returns:
        계약 §5 의 ``vat`` dict.
    """
    available_to = _previous_month_end(today)
    ceiling = min(date_to, available_to)
    rows: list[Any] = []
    if date_from <= ceiling:
        rows = (session.query(NaverVatDaily)
                .filter(NaverVatDaily.channel == channel,
                        NaverVatDaily.settle_basis_date >= date_from,
                        NaverVatDaily.settle_basis_date <= ceiling)
                .order_by(NaverVatDaily.settle_basis_date.asc()).all())
    return {"available_to": available_to.isoformat(), **_vat_rows(rows)}


def _vat_rows(rows: list[Any]) -> dict:
    """부가세 행을 날짜별로 접고 합계를 낸다(8금액 이름은 일자표·합계·건별이 공유)."""
    per_day: dict[str, dict[str, Decimal]] = {}
    order: list[str] = []
    totals = {key: _ZERO for key, _column in _VAT_AMOUNTS}
    final = True
    for row in rows:
        day = _day(row.settle_basis_date) or ""
        if day not in per_day:
            per_day[day] = {key: _ZERO for key, _column in _VAT_AMOUNTS}
            order.append(day)
        for key, column in _VAT_AMOUNTS:
            amount = _dec(getattr(row, column))
            per_day[day][key] += amount
            totals[key] += amount
        final = final and bool(row.is_final)
    return {
        "rows": [{"date": day,
                  **{key: _money(per_day[day][key], default=0)
                     for key, _column in _VAT_AMOUNTS}} for day in order],
        "total": {key: _money(totals[key], default=0) for key, _column in _VAT_AMOUNTS},
        "final": bool(rows) and final,
    }


# ---------------------------------------------------------------------------
# 예외 큐
# ---------------------------------------------------------------------------


def _exception(kind: str, text: str, day: Any, amount: Any, today: datetime.date,
               ref: dict, action_url: Optional[str] = None) -> dict:
    """예외 1행. ``age_days`` 는 날짜를 알 때만 낸다(모르는 값을 0 으로 만들지 않는다)."""
    iso = _day(day)
    age = None
    if iso:
        try:
            age = (today - datetime.date.fromisoformat(iso)).days
        except ValueError:
            age = None
    return {"kind": kind, "label": text, "date": iso, "amount": _money(amount),
            "age_days": age, "ref": ref, "action_url": action_url}


def _daily_exceptions(rows: list[Any], today: datetime.date) -> list[dict]:
    """지급 보류(HOLDBACK)·한도 보류(LIMIT)·음수 정산(NEGATIVE) — 일별 행에서 나온다."""
    found: list[dict] = []
    for row in rows:
        ref = {"settle_expect_date": _day(row.settle_expect_date),
               "settle_method_type": row.settle_method_type}
        if _dec(row.pay_holdback_amount) != 0:
            found.append(_exception("HOLDBACK", "지급 보류", row.settle_expect_date,
                                    row.pay_holdback_amount, today, ref))
        if _dec(row.settlement_limit_amount) != 0:
            found.append(_exception("LIMIT", "정산 한도 보류/해제", row.settle_expect_date,
                                    row.settlement_limit_amount, today, ref))
        if _dec(row.settle_amount) < 0:
            found.append(_exception("NEGATIVE", "음수 정산(취소·환급)",
                                    row.settle_expect_date, row.settle_amount, today, ref))
    return found[:_EXCEPTION_CAP]


def _unmatched_exceptions(session: Any, channel: str, date_from: datetime.date,
                          date_to: datetime.date, today: datetime.date) -> list[dict]:
    """FOMS 주문에 붙지 않은 상품주문 행(UNMATCHED). 배송비·기타비용 행은 대상이 아니다."""
    rows = (session.query(NaverSettleCase)
            .filter(*_case_scope(channel, date_from, date_to),
                    NaverSettleCase.match_status == "UNMATCHED")
            .order_by(NaverSettleCase.settle_expect_date.desc(),
                      NaverSettleCase.id.desc())
            .limit(_EXCEPTION_CAP).all())
    return [
        _exception("UNMATCHED", "FOMS 주문 미연결",
                   row.settle_expect_date or row.search_date, row.settle_expect_amount,
                   today,
                   {"order_id": row.order_id, "product_order_id": row.product_order_id,
                    "product_name": row.product_name},
                   "/admin/naver-ingest")
        for row in rows
    ]


def _run_exceptions(run: Any, reconcile: dict, today: datetime.date) -> list[dict]:
    """마지막 실행이 남긴 소급 변경(RETRO)과 일별↔건별 합 불일치(COUNT_MISMATCH).

    소급 변경 금액은 **우리가 적재한 두 스냅샷의 차**다(네이버 값을 다시 계산한 것이 아니다).
    """
    found: list[dict] = []
    stats = getattr(run, "stats", None) if run is not None else None
    for change in (stats or {}).get("retro_changes", [])[:_EXCEPTION_CAP]:
        if not isinstance(change, dict):
            continue
        delta = _dec(change.get("new_total")) - _dec(change.get("old_total"))
        found.append(_exception("RETRO", "소급 변경(확정 후 값 변동)", change.get("date"),
                                delta, today, dict(change)))
    if reconcile["diff"]:
        found.append(_exception("COUNT_MISMATCH", "일별↔건별 합계 불일치", None,
                                reconcile["diff"], today,
                                {"daily_total": reconcile["daily_total"],
                                 "case_total": reconcile["case_total"]}))
    return found


# ---------------------------------------------------------------------------
# 원장
# ---------------------------------------------------------------------------


def _ledger_date_expr(model: Any, kind: str, basis: str):
    """원장 행의 날짜 축 식 — 프론트의 ``rowDateOf`` 와 **같은 되돌림 순서**다.

    (기준일 컬럼 → 정산 예정일 → 조회일). 두 곳이 다른 날짜를 고르면 서버가 만든 날짜
    그룹에 그 행이 안 들어가 "이 날짜의 행은 다른 페이지에 있습니다"만 남고 표가 빈다.
    """
    if kind == "vat_case":
        return model.settle_basis_date
    candidates = [getattr(model, _BASIS_COLUMN.get(basis, ""), None),
                  getattr(model, "settle_expect_date", None),
                  getattr(model, "search_date", None)]
    columns = [column for column in candidates if column is not None]
    return columns[0] if len(columns) == 1 else func.coalesce(*columns)


def _ledger_filters(model: Any, spec: tuple, filters: dict) -> list:
    """유형 필터·검색어 술어. 파라미터 바인딩만 쓴다(문자열 조립 금지)."""
    _model, _fields, _amount, type_fields, search_fields = spec
    clauses: list = []
    wanted = str(filters.get("type") or "").strip()
    if wanted:
        clauses.append(or_(*[getattr(model, name) == wanted for name in type_fields]))
    query = str(filters.get("q") or "").strip()
    if query:
        pattern = f"%{query}%"
        clauses.append(or_(*[getattr(model, name).ilike(pattern)
                             for name in search_fields]))
    return clauses


def _serialize_ledger_row(row: Any, fields: tuple) -> dict:
    """원장 행 1개 → 응답 dict(원본 필드 snake_case + enum 라벨 + 원본 스냅샷)."""
    out: dict[str, Any] = {}
    for name, tag in fields:
        value = getattr(row, name, None)
        if tag == _DATE:
            out[name] = _day(value)
        elif tag == _MONEY:
            out[name] = _money(value)
        elif tag == _INT:
            out[name] = int(value) if value is not None else None
        else:
            out[name] = value
        if name in _ENUM_MAPS:
            out[name + "_label"] = label(_ENUM_MAPS[name], value)
    out["match_status"] = str(getattr(row, "match_status", None) or "NA").upper()
    foms_order_id = getattr(row, "foms_order_id", None)
    out["foms_order_id"] = int(foms_order_id) if foms_order_id is not None else None
    out["raw"] = getattr(row, "raw_snapshot", None)
    return out


def _build_ledger(session: Any, channel: str, kind: str, basis: str,
                  date_from: datetime.date, date_to: datetime.date,
                  page: int, per_page: int, filters: dict) -> dict:
    """원장 한 페이지 + 기간 전체의 날짜 그룹 합계 + 페이지네이션.

    그룹 합계는 **기간 전체**, 행은 **이 페이지**다(화면이 둘을 같은 숫자인 척하지 않는다).

    Args:
        session: SQLAlchemy Session.
        channel: 채널 코드.
        kind: case|commission|vat_case.
        basis: 날짜 축(원장에만 적용).
        date_from: 시작일.
        date_to: 종료일(포함).
        page: 1부터.
        per_page: 페이지 크기.
        filters: ``type``·``q``.

    Returns:
        계약 §5 의 ``ledger`` dict.
    """
    spec = _LEDGER_SPEC[kind]
    model, fields, amount_column = spec[0], spec[1], spec[2]
    axis = _ledger_date_expr(model, kind, basis)
    scope = [model.channel == channel, axis >= date_from, axis <= date_to]
    scope.extend(_ledger_filters(model, spec, filters))
    groups = (session.query(axis, func.count(model.id),
                            func.sum(getattr(model, amount_column)))
              .filter(*scope).group_by(axis).order_by(axis.desc()).all())
    total = sum(int(count or 0) for _day_value, count, _sum in groups)
    pages = max(1, math.ceil(total / per_page)) if total else 1
    page = max(1, min(int(page or 1), pages))
    rows = (session.query(model).filter(*scope)
            .order_by(axis.desc(), model.id.desc())
            .limit(per_page).offset((page - 1) * per_page).all())
    return {
        "kind": kind,
        "groups": [{"date": _day(day_value), "count": int(count or 0),
                    "amount": _money(total_amount, default=0)}
                   for day_value, count, total_amount in groups],
        "rows": [_serialize_ledger_row(row, fields) for row in rows],
        "pagination": {"page": page, "per_page": per_page, "total": total,
                       "pages": pages},
    }


# ---------------------------------------------------------------------------
# 진입점
# ---------------------------------------------------------------------------


def _validated(basis: str, granularity: str, ledger: str,
               date_from: datetime.date, date_to: datetime.date) -> tuple[str, str, str]:
    """파라미터 허용 집합·구간 폭 검사. 사람이 읽는 한글 사유로 :class:`ValueError`."""
    if basis not in BASES:
        raise ValueError(f"basis 는 {'|'.join(BASES)} 중 하나여야 합니다: {basis!r}")
    if granularity not in GRANULARITIES:
        raise ValueError(
            f"granularity 는 {'|'.join(GRANULARITIES)} 중 하나여야 합니다: {granularity!r}")
    if ledger not in LEDGER_KINDS:
        raise ValueError(f"ledger 는 {'|'.join(LEDGER_KINDS)} 중 하나여야 합니다: {ledger!r}")
    if date_from > date_to:
        raise ValueError("조회 시작일이 종료일보다 뒤입니다.")
    if (date_to - date_from).days + 1 > MAX_RANGE_DAYS:
        raise ValueError(f"조회 구간은 최대 {MAX_RANGE_DAYS}일입니다.")
    return basis, granularity, ledger


def _build_exceptions(session: Any, channel: str, date_from: datetime.date,
                      date_to: datetime.date, rows: list[Any], reconcile: dict,
                      today: datetime.date) -> list[dict]:
    """예외 큐 — 미매칭·보류·한도·음수·소급 변경·합계 불일치를 한 목록으로 잇는다.

    순서가 곧 조치 우선순위다(사람이 붙일 것 → 돈이 묶인 것 → 값이 바뀐 것).

    Args:
        session: SQLAlchemy Session.
        channel: 채널 코드.
        date_from: 시작일.
        date_to: 종료일(포함).
        rows: :func:`_daily_rows` 결과(다시 조회하지 않는다).
        reconcile: :func:`_build_reconcile` 결과.
        today: KST 오늘(경과일 계산 기준).

    Returns:
        계약 §5 의 ``exceptions`` 목록.
    """
    return (_unmatched_exceptions(session, channel, date_from, date_to, today)
            + _daily_exceptions(rows, today)
            + _run_exceptions(_latest_run(session, channel), reconcile, today))


def _core(session: Any, channel: str, date_from: datetime.date,
          date_to: datetime.date, prev_from: datetime.date,
          prev_to: datetime.date) -> tuple:
    """현재·직전 구간을 한 번씩만 읽어 KPI·대사가 나눠 쓸 한 벌을 만든다.

    같은 행을 블록마다 다시 조회하지 않기 위한 지점이다(일별 2회 + 건별 집계 2회로 끝난다).

    Args:
        session: SQLAlchemy Session.
        channel: 채널 코드.
        date_from: 현재 구간 시작.
        date_to: 현재 구간 끝(포함).
        prev_from: 직전 구간 시작.
        prev_to: 직전 구간 끝(포함).

    Returns:
        ``(현재 일별 행, 직전 일별 행, 현재 합계, kpi(prev 포함), reconcile)``.
    """
    rows = _daily_rows(session, channel, date_from, date_to)
    prev_rows = _daily_rows(session, channel, prev_from, prev_to)
    totals, prev_totals = _daily_totals(rows), _daily_totals(prev_rows)
    case_stats = _build_case_stats(session, channel, date_from, date_to)
    kpi = _kpi_block(totals, case_stats)
    kpi["prev"] = _kpi_block(prev_totals,
                             _build_case_stats(session, channel, prev_from, prev_to))
    return rows, prev_rows, totals, kpi, _build_reconcile(totals, case_stats)


def build_channel_dashboard(session: Any, *, date_from: datetime.date,
                            date_to: datetime.date, channel: str = "NAVER",
                            basis: str = DEFAULT_BASIS, page: int = 1,
                            granularity: str = DEFAULT_GRANULARITY,
                            ledger: str = DEFAULT_LEDGER, per_page: int = DEFAULT_PER_PAGE,
                            filters: Optional[dict] = None,
                            today: Optional[datetime.date] = None) -> dict:
    """채널 정산 탭 한 화면이 필요한 전부를 한 번에 만든다(읽기 전용).

    Args:
        session: SQLAlchemy Session. channel: 채널 코드(현재 ``NAVER`` 만 적재된다).
        date_from: 조회 시작일(포함). date_to: 조회 종료일(포함).
        basis: 원장 날짜 축 expect|complete|basis|pay(위쪽 집계는 언제나 예정일이다).
        granularity: 시계열 세밀도 day|week|month.
        ledger: 원장 종류 case|commission|vat_case. page/per_page: 원장 페이지.
        filters: ``{'type': 유형코드, 'q': 주문번호 부분일치}``.
        today: KST 오늘(테스트가 고정할 수 있게 인자로 받는다).

    Returns:
        계약 §5 의 ``data`` dict.

    Raises:
        ValueError: 허용 집합 밖 파라미터 또는 구간 폭 초과.
    """
    basis, granularity, ledger = _validated(basis, granularity, ledger, date_from, date_to)
    today = today or datetime.date.today()
    per_page = max(1, min(int(per_page or DEFAULT_PER_PAGE), MAX_PER_PAGE))
    filters = dict(filters or {})
    prev_from, prev_to = _previous_range(date_from, date_to)
    rows, prev_rows, totals, kpi, reconcile = _core(
        session, channel, date_from, date_to, prev_from, prev_to)
    return {
        "channel": channel, "basis": basis,
        "basis_label": BASIS_LABELS[basis],
        "range": {"from": date_from.isoformat(), "to": date_to.isoformat()},
        "granularity": granularity,
        "sync": _build_sync(session, today),
        "kpi": kpi,
        "daily": _build_daily(rows, date_from, date_to, granularity),
        "daily_prev": _build_daily(prev_rows, prev_from, prev_to, granularity),
        "waterfall": _build_waterfall(totals),
        "deposit_channels": _build_deposit_channels(rows),
        "reconcile": reconcile,
        "commission": _build_commission(session, channel, date_from, date_to),
        "vat": _build_vat(session, channel, date_from, date_to, today),
        "exceptions": _build_exceptions(session, channel, date_from, date_to,
                                        rows, reconcile, today),
        "ledger": _build_ledger(session, channel, ledger, basis, date_from, date_to,
                                page, per_page, filters),
    }
