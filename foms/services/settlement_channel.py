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

from sqlalchemy import and_, case, func, or_

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
    "STRIP_TAB_KEY",
    "build_channel_dashboard",
    "build_channel_strip",
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

#: 요약 탭 크로스 스트립(S11)이 "네이버 정산 열기" 로 활성화할 탭 키. 서버가 내려 주므로
#: 프론트가 문자열을 다시 적지 않는다(탭 버튼 ``data-settlement-tab="channel"`` 과 같은 값).
STRIP_TAB_KEY = "channel"

#: 예외 큐가 한 갈래에서 담아 오는 최대 행수. 넘치면 화면이 스크롤 괴물이 된다.
#: 상한은 **목록**에만 걸린다 — 응답 ``exception_totals`` 는 상한 전 모집단이다(감사 D-02).
_EXCEPTION_CAP = 50
#: 예외 종류 7종 — 응답 ``exception_totals`` 의 고정 키(0건이어도 키가 있어야 화면이 "없다"를 말한다).
_EXCEPTION_KINDS: tuple[str, ...] = ("UNMATCHED", "UNLINKED", "HOLDBACK", "LIMIT",
                                     "NEGATIVE", "RETRO", "COUNT_MISMATCH")
#: 미매칭 정산 예정일 경과 구간 — 응답 ``kpi.unmatched_aging`` 의 고정 키(이 순서).
_AGING_BUCKETS: tuple[str, ...] = ("lt30", "d30_59", "d60_89", "d90_plus", "future")
#: 미연결 예외의 조치 링크 — 같은 출처 상대 경로만(프론트 ``actionCell`` 이 외부 URL 을 안 건다).
_WORKBENCH_URL = "/admin/naver-ingest/triage"
_INGEST_URL = "/admin/naver-ingest"

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

#: 원장 종류별로 **실제로 있는** 날짜 축(첫 값이 그 표의 기본 축). 없는 축을 고르면 기본 축으로
#: 되돌리되 응답 ``ledger.axis.supported`` 가 그 사실을 말한다 — 수수료 표엔 결제일이 없고,
#: 부가세 건별은 정산 기준일 하나뿐이라 "결제일 기준" 라벨만 바뀌던 결함(2026-09-03 실측)을 막는다.
_LEDGER_BASES: dict[str, tuple[str, ...]] = {
    "case": ("expect", "complete", "basis", "pay"),
    "commission": ("expect", "complete", "basis"),
    "vat_case": ("basis",),
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
#: 건별 검색 필드는 내보내기 커널 ``FILTER_FIELDS["settle_case"]`` 와 **같은 3개**여야 한다
#: (두 곳이 갈리면 화면에서 본 행이 파일에 없다 — 계약 테스트가 두 튜플을 정확 비교한다).
_LEDGER_SPEC: dict[str, tuple] = {
    "case": (NaverSettleCase, _CASE_FIELDS, "settle_expect_amount",
             ("product_order_type", "settle_type"),
             ("order_id", "product_order_id", "purchaser_name")),
    "commission": (NaverSettleCommission, _COMMISSION_FIELDS, "commission_amount",
                   ("commission_type", "pay_means_type"), ("order_no", "product_order_id")),
    "vat_case": (NaverVatCase, _VAT_CASE_FIELDS, "total_sales_amount",
                 ("detail_type", "status"), ("order_id", "product_order_id")),
}

#: 원장 종류별 합계 금액 컬럼(``_LEDGER_SPEC[kind][2]``)의 한글 이름 — 응답 ``ledger.totals.amount_label``.
#: 수수료·부가세 표에서 "정산 예정 금액"이라고 거짓말하지 않게 서버가 라벨을 내린다(감사 C-02).
_LEDGER_AMOUNT_LABELS: dict[str, str] = {
    "case": "정산 예정 금액",
    "commission": "수수료 금액",
    "vat_case": "총매출 금액",
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


def _is_full_calendar_months(date_from: datetime.date, date_to: datetime.date) -> bool:
    """from 이 1일이고 to 가 그 달 말일인가(여러 달 연속도 참).

    Args:
        date_from: 구간 시작.
        date_to: 구간 끝(포함).

    Returns:
        꽉 찬 달력 월(들)이면 True.
    """
    return date_from.day == 1 and (date_to + datetime.timedelta(days=1)).day == 1


def _previous_range(date_from: datetime.date, date_to: datetime.date,
                    granularity: str = DEFAULT_GRANULARITY) -> tuple[datetime.date, datetime.date]:
    """직전 비교 구간.

    ``granularity == "month"`` 이고 조회가 **꽉 찬 달력 월**(1일~말일, 여러 달 가능)이면 직전
    같은 개월수의 달력 월 — 집계 탭 ``_previous_month_range`` 와 같은 뜻이다. 같은 일수 규칙만
    있으면 2월 조회의 전기가 01-04~01-31 이라 "전월 대비"의 분모가 달마다 다르게 틀렸다(감사
    C-01). 그 밖(부분 월·day·week)은 기존처럼 같은 길이의 직전 구간 (from-길이, from-1일).

    Args:
        date_from: 현재 구간 시작.
        date_to: 현재 구간 끝(포함).
        granularity: day|week|month.

    Returns:
        (직전 시작, 직전 끝).
    """
    if granularity == "month" and _is_full_calendar_months(date_from, date_to):
        months = (date_to.year - date_from.year) * 12 + date_to.month - date_from.month + 1
        prev_to = date_from - datetime.timedelta(days=1)
        # 연·월을 12진 색인 하나로 접어 (months-1) 개월 되감는다 — 해 넘김(01월 → 전년 12월)을
        # 분기 없이 처리한다(테스트 `2026-01 → 2025-12`).
        index = prev_to.year * 12 + prev_to.month - 1 - (months - 1)
        return datetime.date(index // 12, index % 12 + 1, 1), prev_to
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
                   "expected_account": _ZERO, "expected_charge": _ZERO,
                   "expected_unassigned": _ZERO})
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
        else:
            # 예정일이 아직 안 온 행은 네이버가 방식을 비워 보낸다(실측은 빈 값뿐). 계좌·충전금이
            # 아닌 나머지(빈 값·낯선 코드)를 전부 "미정" 몫으로 세야 타일 세부(계좌+충전금+미정)가
            # 어떤 코드가 와도 예정액과 맞는다(감사 A-03).
            totals["expected_unassigned"] += amount
    return totals


def _build_holdback(rows: list[Any]) -> dict:
    """지급 보류·한도 보류의 일자별 상세 — KPI "보류·한도" 타일이 펼친다(v1.2 F2).

    두 컬럼(``pay_holdback_amount``·``settlement_limit_amount``) 중 하나라도 0 이 아닌 일별
    행만 싣는다(0 행을 채우면 "그날도 보류가 있었다"로 읽힌다). 부호는 네이버 원본 그대로다 —
    운영 실측(2026-09-03)에서 같은 금액이 음수로 잡혔다가 뒤에 양수로 다시 나타난다(보류와
    해제의 짝). 합계는 더하기뿐이며 KPI 타일(:func:`_holdback_of`)과 같은 정의다.

    Args:
        rows: :func:`_daily_rows` 결과(정산 예정일 오름차순).

    Returns:
        ``rows``(정산 예정일 내림차순)·``count``·``total`` dict.
    """
    found: list[dict] = []
    total_hold, total_limit = _ZERO, _ZERO
    ordered = sorted(rows, key=lambda item: (item.settle_expect_date, item.id), reverse=True)
    for row in ordered:
        hold, limit = _dec(row.pay_holdback_amount), _dec(row.settlement_limit_amount)
        if hold == 0 and limit == 0:
            continue
        total_hold += hold
        total_limit += limit
        method = str(row.settle_method_type or "").upper()
        found.append({
            "date": _day(row.settle_expect_date),
            "settle_method_type": row.settle_method_type,
            "settle_method_label": label(SETTLE_METHOD_TYPES, method) if method else "미정",
            "pay_holdback": _money(hold, default=0),
            "settlement_limit": _money(limit, default=0),
            "amount": _money(hold + limit, default=0),
            "completed": row.settle_complete_date is not None,
        })
    return {
        "rows": found,
        "count": len(found),
        "total": {"pay_holdback": _money(total_hold, default=0),
                  "settlement_limit": _money(total_limit, default=0),
                  "amount": _money(total_hold + total_limit, default=0)},
    }


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


def _case_group_columns(today: datetime.date) -> tuple[Any, Any, Any, Any]:
    """group-by 축 4개: match_status · 링크 유무 · 완료 여부 · 정산 예정일 경과 구간.

    경과 구간은 날짜 뺄셈이 아니라 **기준일과의 비교**로 쓴다 — PG·SQLite 양쪽에서 같은 SQL 이
    돈다(SQLite 는 날짜 산술이 없다). 축은 :func:`_case_scope` 와 같은 coalesce 식이다.
    미매칭을 링크 유무로 가르는 이유(v1.2 F1): 워크벤치 대기(링크 있음·주문 없음)와 수집 전
    주문(링크 없음)은 조치하는 사람과 화면이 다르다.

    Args:
        today: KST 오늘(경과 구간 기준일).

    Returns:
        ``(match_status, 링크 있음, 완료됨, 경과 구간)`` SQL 식 4개.
    """
    axis = func.coalesce(NaverSettleCase.settle_expect_date, NaverSettleCase.search_date)
    day = datetime.timedelta(days=1)
    aging = case(
        (axis > today, "future"),
        (axis > today - 30 * day, "lt30"),
        (axis > today - 60 * day, "d30_59"),
        (axis > today - 90 * day, "d60_89"),
        else_="d90_plus",
    )
    return (NaverSettleCase.match_status, NaverSettleCase.link_id.isnot(None),
            NaverSettleCase.settle_complete_date.isnot(None), aging)


def _empty_case_stats() -> dict[str, Any]:
    """건별 통계의 출발값 — 행이 없어도 모든 키와 5구간이 있어야 화면이 "없다"를 말한다."""
    return {"case_count": 0, "unmatched": 0, "matched": 0, "prod_orders": 0,
            "unmatched_pending": 0, "unmatched_unlinked": 0, "pay_settle": _ZERO,
            "unmatched_amount": _ZERO, "unmatched_settled_amount": _ZERO,
            "unmatched_aging": {key: {"count": 0, "amount": _ZERO} for key in _AGING_BUCKETS}}


def _fold_case_group(stats: dict[str, Any], row: tuple) -> None:
    """group-by 1행을 통계에 접는다(:func:`_case_group_columns` 순서 + count·pay 합·expect 합).

    미매칭 금액은 ``settle_expect_amount`` **원값 부호합**이다 — 취소 행의 음수를 그대로 더한다
    (계약 D-1). 완료 여부·경과 구간은 미매칭 행에서만 의미가 있다(감사 D-01).

    Args:
        stats: :func:`_empty_case_stats` 로 시작한 누적 dict(제자리 갱신).
        row: ``(status, linked, settled, bucket, count, pay_total, expect_total)``.
    """
    status, linked, settled, bucket, count, pay_total, expect_total = row
    code = str(status or "NA").upper()
    count = int(count or 0)
    stats["case_count"] += count
    stats["pay_settle"] += _dec(pay_total)
    if code in ("MATCHED", "UNMATCHED"):
        stats["prod_orders"] += count
        stats["matched" if code == "MATCHED" else "unmatched"] += count
    if code != "UNMATCHED":
        return
    stats["unmatched_pending" if linked else "unmatched_unlinked"] += count
    amount = _dec(expect_total)
    stats["unmatched_amount"] += amount
    if settled:
        stats["unmatched_settled_amount"] += amount
    slot = stats["unmatched_aging"][str(bucket)]
    slot["count"] += count
    slot["amount"] += amount


def _build_case_stats(session: Any, channel: str, date_from: datetime.date,
                      date_to: datetime.date, today: datetime.date) -> dict[str, Any]:
    """건별 축 통계 — 건수·미매칭(건수·금액·완료분·경과 구간)·매칭률 분모·결제 정산액 합(대사용).

    한 번의 group-by 로 끝낸다(행을 파이썬으로 끌어오지 않는다 — 원장은 페이지 단위다). 축이
    4개(상태 3 × 링크 2 × 완료 2 × 구간 5)라 그룹은 최대 60행이고 질의는 여전히 **1개**다 —
    스트립 질의 예산(6)이 이 수에 걸려 있다.

    Args:
        session: SQLAlchemy Session.
        channel: 채널 코드.
        date_from: 시작일.
        date_to: 종료일(포함).
        today: KST 오늘(경과 구간 기준일).

    Returns:
        ``case_count``·``unmatched``·``matched``·``prod_orders``·``unmatched_pending``
        (링크 있음·주문 없음)·``unmatched_unlinked``(링크 없음)·``pay_settle``·
        ``unmatched_amount``·``unmatched_settled_amount``·``unmatched_aging`` dict.
    """
    status_col, has_link, is_settled, aging = _case_group_columns(today)
    rows = (session.query(status_col, has_link, is_settled, aging,
                          func.count(NaverSettleCase.id),
                          func.sum(NaverSettleCase.pay_settle_amount),
                          func.sum(NaverSettleCase.settle_expect_amount))
            .filter(*_case_scope(channel, date_from, date_to))
            .group_by(status_col, has_link, is_settled, aging).all())
    stats = _empty_case_stats()
    for row in rows:
        _fold_case_group(stats, row)
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
        "unmatched_pending_count": case_stats["unmatched_pending"],
        "unmatched_unlinked_count": case_stats["unmatched_unlinked"],
        # 미매칭 채권(감사 D-01): 원값 부호합·완료분·예정일 경과 5구간. 전부 저장값의 SUM/COUNT 다.
        "unmatched_amount": _money(case_stats["unmatched_amount"], default=0),
        "unmatched_settled_amount": _money(case_stats["unmatched_settled_amount"], default=0),
        "unmatched_aging": {
            key: {"count": slot["count"], "amount": _money(slot["amount"], default=0)}
            for key, slot in case_stats["unmatched_aging"].items()
        },
        # 입금 방식이 빈 미완료 몫(감사 A-03) — 계좌+충전금+미정 = 예정액.
        "expected_unassigned_amount": _money(totals["expected_unassigned"], default=0),
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
        if _dec(row.settle_amount) == 0:
            continue  # 정산액 0 인 날은 입금이 없다 — 은행 정보도 비어 "계좌 이체 · *" 로 오독된다(실측 16행)
        key = (str(row.settle_method_type or ""), str(row.bank_type or ""),
               str(row.depositor_name or ""), mask_account_no(row.account_no))
        item = buckets.setdefault(key, {"amount": _ZERO, "count": 0})
        item["amount"] += _dec(row.settle_amount)
        item["count"] += 1
    channels = [
        {"method": method or None,
         # 정산 예정일이 아직 안 온 행은 네이버가 방식을 비워 보낸다(실측) — "미상"이 아니라 "미정".
         "method_label": label(SETTLE_METHOD_TYPES, method) if method else "미정(정산 예정)",
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
    """지급 보류(HOLDBACK)·한도 보류(LIMIT)·음수 정산(NEGATIVE) — 일별 행에서 **전부** 나온다.

    상한은 :func:`_build_exceptions` 가 건다 — 여기서 자르면 모집단 건수를 셀 수 없다(감사 D-02).
    """
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
    return found


def _unmatched_rows(session: Any, channel: str, date_from: datetime.date,
                    date_to: datetime.date, *, linked: bool) -> list[Any]:
    """UNMATCHED 상품주문 행 한 갈래(링크 있음/없음), 최신 정산 예정일부터 상한까지."""
    predicate = (NaverSettleCase.link_id.isnot(None) if linked
                 else NaverSettleCase.link_id.is_(None))
    return (session.query(NaverSettleCase)
            .filter(*_case_scope(channel, date_from, date_to),
                    NaverSettleCase.match_status == "UNMATCHED", predicate)
            .order_by(NaverSettleCase.settle_expect_date.desc(),
                      NaverSettleCase.id.desc())
            .limit(_EXCEPTION_CAP).all())


def _unmatched_exception(row: Any, today: datetime.date, *, linked: bool) -> dict:
    """미연결 예외 1행. 링크가 있으면 워크벤치의 그 집을, 없으면 수집 운영 화면을 가리킨다."""
    link_id = int(row.link_id) if row.link_id is not None else None
    ref = {"order_id": row.order_id, "product_order_id": row.product_order_id,
           "product_name": row.product_name, "link_id": link_id}
    day = row.settle_expect_date or row.search_date
    if linked:
        return _exception("UNMATCHED", "워크벤치 대기(주문 미생성)", day,
                          row.settle_expect_amount, today, ref,
                          f"{_WORKBENCH_URL}?link_id={link_id}")
    return _exception("UNLINKED", "수집 전 주문(링크 없음)", day,
                      row.settle_expect_amount, today, ref, _INGEST_URL)


def _unmatched_exceptions(session: Any, channel: str, date_from: datetime.date,
                          date_to: datetime.date, today: datetime.date) -> list[dict]:
    """FOMS 주문에 붙지 않은 상품주문 행 두 갈래(v1.2 F1). 배송비·기타비용(NA) 행은 대상이 아니다.

    - ``UNMATCHED``: 링크는 있는데 주문이 아직 없다(워크벤치에서 주문 생성 대기) → 그 집을 연다.
    - ``UNLINKED``: 링크 자체가 없다(수집이 닿기 전 주문) → 수집 운영 화면.

    갈래마다 상한을 따로 둔다 — 한 상한을 나누면 많은 쪽(운영 실측 2026-09-03: 1,321 vs 32)이
    적은 쪽을 표에서 밀어내 그 갈래가 있다는 사실 자체가 안 보인다. 전체 건수는 KPI
    (``unmatched_pending_count``·``unmatched_unlinked_count``)가 말한다.
    """
    pending = _unmatched_rows(session, channel, date_from, date_to, linked=True)
    unlinked = _unmatched_rows(session, channel, date_from, date_to, linked=False)
    return ([_unmatched_exception(row, today, linked=True) for row in pending]
            + [_unmatched_exception(row, today, linked=False) for row in unlinked])


def _retro_exceptions(run: Any, today: datetime.date) -> list[dict]:
    """마지막 실행이 남긴 소급 변경(RETRO) **전부** — 상한은 :func:`_build_exceptions` 가 건다.

    소급 변경 금액은 **우리가 적재한 두 스냅샷의 차**다(네이버 값을 다시 계산한 것이 아니다).
    dict 가 아닌 항목(옛 형식)은 건너뛴다.

    Args:
        run: :func:`_latest_run` 결과(None 가능).
        today: KST 오늘(경과일 계산 기준).

    Returns:
        RETRO 예외 목록(상한 없음).
    """
    found: list[dict] = []
    stats = getattr(run, "stats", None) if run is not None else None
    for change in (stats or {}).get("retro_changes") or []:
        if not isinstance(change, dict):
            continue
        delta = _dec(change.get("new_total")) - _dec(change.get("old_total"))
        found.append(_exception("RETRO", "소급 변경(확정 후 값 변동)", change.get("date"),
                                delta, today, dict(change)))
    return found


def _mismatch_exceptions(reconcile: dict, today: datetime.date) -> list[dict]:
    """일별↔건별 합 불일치(COUNT_MISMATCH) 0/1행 — 차이를 감추지 않는다(적재 누락·소급 변경 신호).

    Args:
        reconcile: :func:`_build_reconcile` 결과.
        today: KST 오늘.

    Returns:
        불일치가 있으면 예외 1행, 없으면 빈 목록.
    """
    if not reconcile["diff"]:
        return []
    return [_exception("COUNT_MISMATCH", "일별↔건별 합계 불일치", None, reconcile["diff"],
                       today, {"daily_total": reconcile["daily_total"],
                               "case_total": reconcile["case_total"]})]


# ---------------------------------------------------------------------------
# 원장
# ---------------------------------------------------------------------------


def _ledger_axis(model: Any, kind: str, basis: str) -> tuple[Any, str, bool]:
    """원장의 날짜 축 식 + 실제 적용된 basis + 지원 여부 — 프론트 ``rowDateOf`` 와 같은 규칙.

    - 예정일 축만 조회일로 되돌린다(예정일이 아직 안 잡힌 미확정 건이 조용히 빠지지 않게).
    - 완료일·기준일·결제일 축은 **되돌리지 않는다.** 완료일이 없는 미완료 행을 예정일에 얹으면
      "완료일 기준" 표가 예정일 표와 같아져 셀렉트가 죽은 것처럼 보였다(2026-09-03 스테이징 실측:
      21그룹·487건 동일). 빠진 행은 :func:`_build_ledger` 가 세어 ``axis.excluded`` 로 낸다.
    - 표에 없는 축은 그 표의 기본 축으로 가되 ``supported=False`` 를 돌려 화면이 되돌림을 말하게 한다.

    Args:
        model: 원장 모델. kind: case|commission|vat_case. basis: 사용자가 고른 축.

    Returns:
        (SQL 축 식, 적용된 basis, 지원 여부).
    """
    allowed = _LEDGER_BASES[kind]
    supported = basis in allowed
    effective = basis if supported else allowed[0]
    if kind == "vat_case":
        return model.settle_basis_date, effective, supported
    if effective == "expect":
        return func.coalesce(model.settle_expect_date, model.search_date), effective, supported
    return getattr(model, _BASIS_COLUMN[effective]), effective, supported


def _expect_window(model: Any) -> Any:
    """예정일 창 식 — ``excluded``·``shifted_out`` 두 계수가 **같은 모집단**을 세게 하는 단일 정본.

    두 계수가 각자 coalesce 를 적으면 한쪽만 고쳐졌을 때 표 머리의 두 문장이 서로 다른
    집합을 말한다(리뷰 MINOR-2, 2026-09-03).

    Args:
        model: 원장 모델(``settle_expect_date``·``search_date`` 를 가진다).

    Returns:
        SQLAlchemy 식 ``coalesce(settle_expect_date, search_date)``.
    """
    return func.coalesce(model.settle_expect_date, model.search_date)


def _axis_gap_counts(session: Any, model: Any, axis: Any, scope_filters: list,
                     channel: str, date_from: datetime.date,
                     date_to: datetime.date) -> tuple[int, int]:
    """예정일 창 안인데 이 축 때문에 표에서 빠진 두 몫을 **한 번의 스캔**으로 센다.

    축을 바꾸면 표가 조용히 줄어드는 것이 결함이었다 — 줄어든 몫이 "날짜가 없어서"(``excluded``)
    인지 "다른 기간으로 옮겨 가서"(``shifted_out``)인지 화면이 말하지 못했다.

    반환 두 값은 **서로소**다: 축 날짜가 ``NULL`` 인 행(``excluded``)과 ``NOT NULL`` 이면서
    창 밖인 행(``shifted_out``)이라 한 행이 두 수에 겹쳐 세어지지 않는다(그래서 둘을 합쳐
    세지 않는다). 술어(유형·검색)는 :func:`_ledger_filters` 가 만든 것을 그대로 받는다 —
    화면 표와 같은 모집단이어야 두 수가 같은 질문의 답이다. 두 몫이 같은 창·같은 술어 위에서
    나오도록 조건부 집계 한 쿼리로 묶었다(리뷰 MINOR-1, 2026-09-03).

    Args:
        session: SQLAlchemy Session.
        model: 원장 모델.
        axis: 이 표의 날짜 축 식.
        scope_filters: 유형·검색 술어(``_ledger_filters`` 결과 그대로).
        channel: 채널 코드.
        date_from: 시작일(포함).
        date_to: 종료일(포함).

    Returns:
        ``(excluded, shifted_out)`` — 축 날짜가 빈 행 수와 창 밖으로 밀려난 행 수.
    """
    window = _expect_window(model)
    row = (session.query(
        func.count(case((axis.is_(None), model.id))),
        func.count(case((and_(axis.isnot(None),
                              or_(axis < date_from, axis > date_to)), model.id))),
    ).filter(model.channel == channel, window >= date_from, window <= date_to,
             *scope_filters).one())
    return int(row[0] or 0), int(row[1] or 0)


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
    axis, effective, supported = _ledger_axis(model, kind, basis)
    extra_filters = _ledger_filters(model, spec, filters)
    scope = [model.channel == channel, axis >= date_from, axis <= date_to]
    scope.extend(extra_filters)
    excluded = shifted_out = 0
    if effective != "expect" and kind != "vat_case":
        excluded, shifted_out = _axis_gap_counts(session, model, axis, extra_filters,
                                                 channel, date_from, date_to)
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
        "groups": _ledger_groups(groups),
        "rows": [_serialize_ledger_row(row, fields) for row in rows],
        "pagination": {"page": page, "per_page": per_page, "total": total,
                       "pages": pages},
        "totals": _ledger_totals(groups, total, kind, amount_column),
        # 표에 실제로 적용된 축. 화면은 위쪽 집계(늘 예정일)와 이 표의 축을 따로 말한다.
        "axis": {"basis": effective, "label": BASIS_LABELS[effective],
                 "supported": supported, "excluded": excluded,
                 "shifted_out": shifted_out},
    }


def _ledger_groups(groups: list[tuple]) -> list[dict]:
    """날짜 그룹 ``(축 날짜, 건수, 금액 합)`` → 계약 §5 ``ledger.groups``(기간 전체)."""
    return [{"date": _day(day_value), "count": int(count or 0),
             "amount": _money(total_amount, default=0)}
            for day_value, count, total_amount in groups]


def _ledger_totals(groups: list[tuple], total: int, kind: str, amount_column: str) -> dict:
    """같은 술어(유형·검색·축·기간)의 합계 — 이미 뽑은 그룹 합을 더할 뿐 질의를 더하지 않는다.

    화면이 날짜 그룹을 손으로 더하던 결함(감사 C-02)을 서버 숫자 한 줄로 대신한다.

    Args:
        groups: :func:`_build_ledger` 의 날짜 그룹 질의 결과.
        total: 그룹 건수 합(페이지네이션과 같은 수).
        kind: case|commission|vat_case.
        amount_column: 합산한 금액 컬럼 이름.

    Returns:
        ``count``·``amount``·``amount_column``·``amount_label``.
    """
    amount_total = sum((_dec(total_amount) for _day_value, _count, total_amount in groups), _ZERO)
    return {"count": total, "amount": _money(amount_total, default=0),
            "amount_column": amount_column, "amount_label": _LEDGER_AMOUNT_LABELS[kind]}


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


def _exception_totals(case_stats: dict[str, Any], uncapped: list[dict]) -> dict[str, int]:
    """예외 kind 별 **모집단**(상한 전) + ``total``. 7키 고정, 없으면 0.

    미연결 두 갈래는 목록이 아니라 group-by 통계에서 센다(목록은 갈래당 상한까지만 읽는다).
    나머지 다섯 kind 는 상한을 자르기 전 목록을 센다 — 추가 질의 0(감사 D-02).

    Args:
        case_stats: :func:`_build_case_stats` 결과.
        uncapped: 일별 3종·RETRO·COUNT_MISMATCH 의 상한 전 목록.

    Returns:
        ``{kind: 건수, ..., "total": 합}``.
    """
    totals = {kind: 0 for kind in _EXCEPTION_KINDS}
    totals["UNMATCHED"] = int(case_stats["unmatched_pending"])
    totals["UNLINKED"] = int(case_stats["unmatched_unlinked"])
    for item in uncapped:
        kind = str(item.get("kind") or "")
        if kind in totals:
            totals[kind] += 1
    totals["total"] = sum(totals[kind] for kind in _EXCEPTION_KINDS)
    return totals


def _build_exceptions(session: Any, channel: str, date_from: datetime.date,
                      date_to: datetime.date, rows: list[Any], case_stats: dict[str, Any],
                      reconcile: dict, today: datetime.date) -> tuple[list[dict], dict[str, int]]:
    """예외 큐 — 미매칭·보류·한도·음수·소급 변경·합계 불일치를 한 목록으로 잇고 모집단을 함께 낸다.

    순서가 곧 조치 우선순위다(사람이 붙일 것 → 돈이 묶인 것 → 값이 바뀐 것). 목록은 갈래
    (미연결 2갈래·일별 3종 합·RETRO)마다 :data:`_EXCEPTION_CAP` 까지만 싣고, 상한 전 건수는
    두 번째 반환값이 말한다 — 스트립·배지가 목록 길이를 세면 모집단이 8~34배 가려졌다(감사 D-02).

    Args:
        session: SQLAlchemy Session.
        channel: 채널 코드.
        date_from: 시작일.
        date_to: 종료일(포함).
        rows: :func:`_daily_rows` 결과(다시 조회하지 않는다).
        case_stats: :func:`_build_case_stats` 결과(미연결 모집단).
        reconcile: :func:`_build_reconcile` 결과.
        today: KST 오늘(경과일 계산 기준).

    Returns:
        ``(계약 §5 의 exceptions 목록, kind 별 모집단 + total)``.
    """
    unmatched = _unmatched_exceptions(session, channel, date_from, date_to, today)
    daily_all, retro_all, mismatch = _uncapped_exception_pool(session, channel, rows,
                                                              reconcile, today)
    listed = unmatched + daily_all[:_EXCEPTION_CAP] + retro_all[:_EXCEPTION_CAP] + mismatch
    return listed, _exception_totals(case_stats, daily_all + retro_all + mismatch)


def _uncapped_exception_pool(session: Any, channel: str, rows: list[Any], reconcile: dict,
                             today: datetime.date) -> tuple[list[dict], list[dict], list[dict]]:
    """상한 전 예외 세 갈래 — 일별 3종·RETRO·COUNT_MISMATCH(미연결은 목록이 아니라 통계로 센다).

    스트립은 여기까지만 쓴다: 미연결 목록 질의 2개(갈래별 50행)는 탭 화면에만 필요하고 모집단은
    ``case_stats`` 가 이미 갖고 있다 — 요약 탭마다 도는 경로라 질의를 아낀다.

    Args:
        session: SQLAlchemy Session.
        channel: 채널 코드.
        rows: :func:`_daily_rows` 결과.
        reconcile: :func:`_build_reconcile` 결과.
        today: KST 오늘(경과일 계산 기준).

    Returns:
        ``(일별 3종 전부, RETRO 전부, COUNT_MISMATCH 0/1행)``.
    """
    return (_daily_exceptions(rows, today),
            _retro_exceptions(_latest_run(session, channel), today),
            _mismatch_exceptions(reconcile, today))


def _range_block(date_from: datetime.date, date_to: datetime.date,
                 prev_from: datetime.date, prev_to: datetime.date) -> dict:
    """응답 ``range`` — 현재 구간과, ``kpi.prev``·``daily_prev`` 가 실제로 본 직전 구간.

    직전 구간을 응답에 싣는 이유: 화면이 "전기(MM-DD~MM-DD) 대비"라고 구간을 찍어야
    같은 일수 규칙과 달력 월 규칙이 섞인 것을 회계팀이 알아본다(감사 C-01).
    """
    return {"from": date_from.isoformat(), "to": date_to.isoformat(),
            "prev": {"from": prev_from.isoformat(), "to": prev_to.isoformat()}}


def _core(session: Any, channel: str, date_from: datetime.date,
          date_to: datetime.date, prev_from: datetime.date,
          prev_to: datetime.date, today: datetime.date) -> tuple:
    """현재·직전 구간을 한 번씩만 읽어 KPI·대사·예외 큐가 나눠 쓸 한 벌을 만든다.

    같은 행을 블록마다 다시 조회하지 않기 위한 지점이다(일별 2회 + 건별 집계 2회로 끝난다).

    Args:
        session: SQLAlchemy Session.
        channel: 채널 코드.
        date_from: 현재 구간 시작.
        date_to: 현재 구간 끝(포함).
        prev_from: 직전 구간 시작.
        prev_to: 직전 구간 끝(포함).
        today: KST 오늘(미매칭 경과 구간 기준일 — 전기 블록도 같은 오늘로 잰다).

    Returns:
        ``(현재 일별 행, 직전 일별 행, 현재 합계, kpi(prev 포함), 현재 건별 통계, reconcile)``.
    """
    rows = _daily_rows(session, channel, date_from, date_to)
    prev_rows = _daily_rows(session, channel, prev_from, prev_to)
    totals, prev_totals = _daily_totals(rows), _daily_totals(prev_rows)
    case_stats = _build_case_stats(session, channel, date_from, date_to, today)
    kpi = _kpi_block(totals, case_stats)
    kpi["prev"] = _kpi_block(prev_totals,
                             _build_case_stats(session, channel, prev_from, prev_to, today))
    return rows, prev_rows, totals, kpi, case_stats, _build_reconcile(totals, case_stats)


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
    # kpi.prev 와 daily_prev 가 **같은 구간**을 본다 — 월 단위 꽉 찬 달은 달력 전월(감사 C-01).
    prev_from, prev_to = _previous_range(date_from, date_to, granularity)
    rows, prev_rows, totals, kpi, case_stats, reconcile = _core(
        session, channel, date_from, date_to, prev_from, prev_to, today)
    exceptions, exception_totals = _build_exceptions(
        session, channel, date_from, date_to, rows, case_stats, reconcile, today)
    return {
        "channel": channel, "basis": basis,
        "basis_label": BASIS_LABELS[basis],
        "range": _range_block(date_from, date_to, prev_from, prev_to),
        "granularity": granularity,
        "sync": _build_sync(session, today),
        "kpi": kpi,
        "daily": _build_daily(rows, date_from, date_to, granularity),
        "daily_prev": _build_daily(prev_rows, prev_from, prev_to, granularity),
        "waterfall": _build_waterfall(totals),
        "deposit_channels": _build_deposit_channels(rows),
        "reconcile": reconcile,
        "holdback": _build_holdback(rows),
        "commission": _build_commission(session, channel, date_from, date_to),
        "vat": _build_vat(session, channel, date_from, date_to, today),
        "exceptions": exceptions,
        # 상한 전 모집단(kind 별 + total)과 갈래별 상한 — 화면이 "N건 중 M건 표시"를 말한다.
        "exception_totals": exception_totals,
        "exception_cap": _EXCEPTION_CAP,
        "ledger": _build_ledger(session, channel, ledger, basis, date_from, date_to,
                                page, per_page, filters),
    }


# ---------------------------------------------------------------------------
# 요약 탭 크로스 스트립(S11) — 같은 헬퍼에서 뽑은 스칼라 3개
# ---------------------------------------------------------------------------


def build_channel_strip(session: Any, *, channel: str = "NAVER",
                        date_from: datetime.date, date_to: datetime.date,
                        today: Optional[datetime.date] = None) -> dict:
    """요약 탭 크로스 스트립 1줄이 필요한 최소 한 벌(읽기 전용).

    :func:`build_channel_dashboard` 와 **같은 헬퍼**(:func:`_daily_rows` →
    :func:`_daily_totals` → :func:`_build_case_stats` → :func:`_kpi_block`)를 그대로
    통과시킨다. 숫자를 여기서 다시 정의하면 요약 스트립과 채널 탭이 조용히 갈린다.

    전기 구간·원장·수수료·부가세·미연결 **목록**은 조회하지 않는다(질의 4개: 일별 1 +
    건별 group-by 1 + 최근 run 1 + 워터마크 1). 미연결 모집단은 group-by 통계가 이미 갖고 있다.

    Args:
        session: SQLAlchemy Session.
        channel: 채널 코드(현재 ``NAVER`` 만 적재된다).
        date_from: 조회 시작일(포함).
        date_to: 조회 종료일(포함).
        today: KST 오늘(테스트가 고정할 수 있게 인자로 받는다).

    Returns:
        ``channel``·``basis``·``basis_label``·``range``·``sync``·``strip`` dict.
        ``strip`` = ``settled_amount``·``expected_amount``·``exception_count``(상한 **전**
        모집단 = 탭의 ``exception_totals.total``)·``unmatched_count``·``tab_key``.

    Raises:
        ValueError: 시작일이 종료일보다 뒤이거나 구간 폭이 상한을 넘을 때.
    """
    # 축은 언제나 정산 예정일이다(스트립에는 축 셀렉터가 없다). 구간 폭·역전 검사만 재사용.
    _validated(DEFAULT_BASIS, DEFAULT_GRANULARITY, DEFAULT_LEDGER, date_from, date_to)
    today = today or datetime.date.today()
    rows = _daily_rows(session, channel, date_from, date_to)
    totals = _daily_totals(rows)
    case_stats = _build_case_stats(session, channel, date_from, date_to, today)
    kpi = _kpi_block(totals, case_stats)
    daily_all, retro_all, mismatch = _uncapped_exception_pool(
        session, channel, rows, _build_reconcile(totals, case_stats), today)
    exception_totals = _exception_totals(case_stats, daily_all + retro_all + mismatch)
    return {
        "channel": channel,
        "basis": DEFAULT_BASIS,
        "basis_label": BASIS_LABELS[DEFAULT_BASIS],
        "range": {"from": date_from.isoformat(), "to": date_to.isoformat()},
        "sync": _build_sync(session, today),
        "strip": {
            "settled_amount": kpi["settled_amount"],
            "expected_amount": kpi["expected_amount"],
            "exception_count": exception_totals["total"],
            "unmatched_count": kpi["unmatched_count"],
            "tab_key": STRIP_TAB_KEY,
        },
    }
