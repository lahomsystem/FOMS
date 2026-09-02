"""채널(네이버) 정산 CSV 내보내기 커널 — SETTLE-CHANNEL v1.1 T14 (읽기 전용).

화면 원장(:mod:`foms.services.settlement_channel`)은 41필드만 낸다. 이 모듈은 **적재된 원본
전량**을 5종 CSV 로 흘려 보낸다(계약 "적재 100% · CSV 100% · 화면 41"). 화면 필드표를
재사용하지 않는 것은 게으름이 아니라 **의도적으로 다른 집합**이기 때문이다 — 두 표가 같은
모델 컬럼 이름을 쓰는지는 계약 테스트가 대조한다.

설계 제약(계약 §1.3, 전부 강제):

* **새 의존성 0.** 표준 라이브러리 :mod:`csv`·:mod:`io` 만 쓴다. 2026-09-01 에 떼어낸
  ``pandas``·``openpyxl`` 을 되붙이지 않는다. 이름에도 그 낱말을 쓰지 않는다(잔존 grep 0 계약).
* **UTF-8 BOM 1회 + 줄바꿈 CRLF.** 없으면 표 계산 프로그램이 한글을 깨서 연다.
* **회계 프로그램(더존·이카운트) import 친화**: 헤더 정확히 1줄, 금액은 부호 포함 평문
  (``-389000`` — 천단위 콤마·통화기호·괄호 음수 금지), 날짜는 ``YYYY-MM-DD``, 빈 값은 빈 칸.
  enum 은 **코드 열과 한글 라벨 열을 둘 다** 낸다(프로그램은 코드로, 사람은 라벨로 읽는다).
* **금액 재계산 금지.** 네이버가 준 부호를 그대로 옮긴다(v1 워터폴 부호 사고 재발 금지).
* **계좌번호는 CSV 에서도 마스킹**한다 — "화면은 가리고 파일은 다 준다"는 구멍을 만들지 않는다.
* **주문번호를 ``="..."`` 로 감싸지 않는다.** 지수표기를 막으려는 그 래핑을 더존·이카운트
  임포터가 리터럴로 읽어 오히려 깨진다. 원문 그대로 내고, 여는 법은 UI 안내가 맡는다.
* ``raw_snapshot``(JSON)은 넣지 않는다 — 셀 안 개행·콤마가 임포터를 깨뜨린다.

메모리 규율: 헤더를 먼저 ``yield`` 하고 데이터 행은 :meth:`~sqlalchemy.orm.Query.yield_per`
로 하나씩 흘린다. 첫 줄만 받아 가는 호출자에게는 조회가 **아직 일어나지 않는다**.

이 모듈은 읽기 전용이다 — 커밋·flag_modified·속성 대입을 하지 않는다.
"""

from __future__ import annotations

import csv
import datetime
import io
from decimal import Decimal, InvalidOperation
from typing import Any, Iterator, Mapping, Optional

from sqlalchemy import func, or_

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
from foms.services.settlement_channel import (
    DEFAULT_BASIS,
    MAX_RANGE_DAYS,
    mask_account_no,
)
from models import (
    NaverSettleCase,
    NaverSettleCommission,
    NaverSettleDaily,
    NaverVatCase,
    NaverVatDaily,
)

__all__ = [
    "CSV_COLUMNS",
    "CSV_KINDS",
    "EXPORT_KINDS",
    "FILTER_FIELDS",
    "build_export_rows",
    "csv_filename",
    "export_filename",
    "iter_csv_lines",
    "iter_settlement_csv",
    "normalize_kind",
]

#: CSV 종류 5종. 4종(건별 정산·수수료·부가세 일별·부가세 건별)만으로는 settle/daily 의
#: 13필드(정산 금액·지급 보류·입금 계좌 등)가 어느 파일에도 안 들어가 "CSV 100%" 약속이
#: 산술적으로 깨진다 — 그래서 ``settle_daily`` 가 다섯 번째다(사용자 승인 2026-09-02).
EXPORT_KINDS: tuple[str, ...] = (
    "settle_daily", "settle_case", "commission", "vat_daily", "vat_case",
)

#: 계약서 초안이 쓰던 짧은 이름. 라우트가 어느 쪽을 넘겨도 같은 파일이 나오게 편다.
_KIND_ALIASES: dict[str, str] = {"case": "settle_case", "daily": "settle_daily"}

#: 파일명 조각(ASCII). ``settle_case`` 가 ``naver_settle_settle_case`` 가 되지 않게 따로 둔다.
_FILENAME_SLUG: dict[str, str] = {
    "settle_daily": "daily", "settle_case": "case", "commission": "commission",
    "vat_daily": "vat_daily", "vat_case": "vat_case",
}

_MODELS: dict[str, Any] = {
    "settle_daily": NaverSettleDaily, "settle_case": NaverSettleCase,
    "commission": NaverSettleCommission, "vat_daily": NaverVatDaily,
    "vat_case": NaverVatCase,
}

#: ``basis`` -> 날짜 컬럼 이름. **조회 커널의 같은 이름 표와 한 글자도 달라선 안 된다**
#: (계약 테스트가 두 dict 를 정확 비교한다) — 두 곳이 다른 축을 고르면 화면에서 본 행이
#: 파일에 없다.
_BASIS_COLUMN: dict[str, str] = {
    "expect": "settle_expect_date",
    "complete": "settle_complete_date",
    "basis": "settle_basis_date",
    "pay": "pay_date",
}

#: kind -> 날짜 축 되돌림 순서(기준일 컬럼 뒤에 붙는다). 원장 커널 ``_ledger_date_expr`` 과
#: 같은 순서다.
_AXIS_FALLBACK: dict[str, tuple[str, ...]] = {
    "settle_daily": ("settle_expect_date",),
    "settle_case": ("settle_expect_date", "search_date"),
    "commission": ("settle_expect_date", "search_date"),
    "vat_daily": ("settle_basis_date",),
    "vat_case": ("settle_basis_date",),
}

#: ``basis`` 셀렉터가 뜻을 갖는 kind. 일자 단위 표는 축이 하나뿐이라 셀렉터를 무시한다.
_BASIS_AWARE: frozenset[str] = frozenset({"settle_case", "commission"})

#: kind -> (유형 필터 필드, 검색 필드). 원장 커널의 ``_LEDGER_SPEC`` 과 같은 필드다.
#: 빈 튜플인 kind 에 조건을 주면 :func:`build_export_rows` 가 거절한다 — 조건을 조용히
#: 버리면 화면과 다른 파일이 나간다.
FILTER_FIELDS: dict[str, tuple[tuple[str, ...], tuple[str, ...]]] = {
    "settle_daily": ((), ()),
    "settle_case": (("product_order_type", "settle_type"),
                    ("order_id", "product_order_id")),
    "commission": (("commission_type", "pay_means_type"),
                   ("order_no", "product_order_id")),
    "vat_daily": ((), ()),
    "vat_case": (("detail_type", "status"), ("order_id", "product_order_id")),
}

#: 컬럼 타입 태그.
_DATE, _MONEY, _TEXT, _INT, _BOOL = "date", "money", "text", "int", "bool"
#: enum 코드 열 / 그 옆 한글 라벨 열 / 마스킹 열.
_ENUM, _ENUM_LABEL, _ACCOUNT = "enum", "enum_label", "account"

#: 컬럼명 -> enum 카탈로그. 한글 라벨은 **여기 카탈로그에서만** 온다(이 파일에 한글 enum
#: 리터럴을 적지 않는다 — 네이버가 표기를 바꾸면 두 곳이 갈린다).
_ENUM_MAPS: dict[str, Mapping[str, str]] = {
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

#: 부가세 8금액 — 일자표·건별표가 같은 이름·같은 순서를 쓴다(합이 안 맞을 때 대조하려고).
_VAT_AMOUNT_COLUMNS: tuple[tuple[str, str, str], ...] = (
    ("총 매출 금액", "total_sales_amount", _MONEY),
    ("과세 매출 금액", "taxation_sales_amount", _MONEY),
    ("면세 매출 금액", "tax_exemption_sales_amount", _MONEY),
    ("신용카드 결제 금액", "credit_card_amount", _MONEY),
    ("현금영수증 소득공제 금액", "cash_income_deduction_amount", _MONEY),
    ("현금영수증 지출증빙 금액", "cash_outgoing_evidence_amount", _MONEY),
    ("현금영수증 발행제외 금액", "cash_exclusion_issuance_amount", _MONEY),
    ("기타 금액", "other_amount", _MONEY),
)

_SETTLE_DAILY_COLUMNS: tuple[tuple[str, str, str], ...] = (
    ("정산 기준 시작일", "settle_basis_start_date", _DATE),
    ("정산 기준 종료일", "settle_basis_end_date", _DATE),
    ("정산 예정일", "settle_expect_date", _DATE),
    ("정산 완료일", "settle_complete_date", _DATE),
    ("정산 금액", "settle_amount", _MONEY),
    ("결제 정산 금액", "pay_settle_amount", _MONEY),
    ("수수료 정산 합계", "commission_settle_amount", _MONEY),
    ("혜택 정산 금액", "benefit_settle_amount", _MONEY),
    ("공제 환급 합계", "deduction_restore_settle_amount", _MONEY),
    ("지급 보류 금액", "pay_holdback_amount", _MONEY),
    ("마이너스 충전금 상계", "minus_charge_amount", _MONEY),
    ("차액 정산 금액", "difference_settle_amount", _MONEY),
    ("반품안심케어 정산 금액", "return_care_settle_amount", _MONEY),
    ("일반정산 금액", "normal_settle_amount", _MONEY),
    ("빠른정산 금액", "quick_settle_amount", _MONEY),
    ("우대 수수료 환급", "preferential_commission_amount", _MONEY),
    ("한도 보류 금액", "settlement_limit_amount", _MONEY),
    ("정산 방식(settleMethodType)", "settle_method_type", _ENUM),
    ("정산 방식명", "settle_method_type", _ENUM_LABEL),
    ("은행(bankType)", "bank_type", _ENUM),
    ("은행명", "bank_type", _ENUM_LABEL),
    ("예금주명", "depositor_name", _TEXT),
    ("계좌번호(마스킹)", "account_no", _ACCOUNT),
    ("가맹점 ID", "merchant_id", _TEXT),
    ("가맹점명", "merchant_name", _TEXT),
)

_SETTLE_CASE_COLUMNS: tuple[tuple[str, str, str], ...] = (
    ("조회일", "search_date", _DATE),
    ("조회 기준(periodType)", "period_type", _ENUM),
    ("조회 기준명", "period_type", _ENUM_LABEL),
    ("정산 기준일", "settle_basis_date", _DATE),
    ("정산 예정일", "settle_expect_date", _DATE),
    ("정산 완료일", "settle_complete_date", _DATE),
    ("결제일", "pay_date", _DATE),
    ("주문번호(orderId)", "order_id", _TEXT),
    ("상품주문번호(productOrderId)", "product_order_id", _TEXT),
    ("정산 대상 구분(productOrderType)", "product_order_type", _ENUM),
    ("정산 대상 구분명", "product_order_type", _ENUM_LABEL),
    ("정산 구분(settleType)", "settle_type", _ENUM),
    ("정산 구분명", "settle_type", _ENUM_LABEL),
    ("상품번호", "product_id", _TEXT),
    ("상품명", "product_name", _TEXT),
    ("구매자명", "purchaser_name", _TEXT),
    ("결제 정산 금액", "pay_settle_amount", _MONEY),
    ("네이버페이 수수료 합계", "total_pay_commission_amount", _MONEY),
    ("무이자 할부 수수료", "free_installment_commission_amount", _MONEY),
    ("매출 연동 수수료", "selling_interlock_commission_amount", _MONEY),
    ("혜택 정산 금액", "benefit_settle_amount", _MONEY),
    ("정산 예정 금액", "settle_expect_amount", _MONEY),
    ("가맹점 ID", "merchant_id", _TEXT),
    ("가맹점명", "merchant_name", _TEXT),
    ("계약번호", "contract_no", _TEXT),
    ("FOMS 주문 ID", "foms_order_id", _INT),
    ("FOMS 연동 링크 ID", "link_id", _INT),
    ("주문 매칭 상태", "match_status", _TEXT),
)

_COMMISSION_COLUMNS: tuple[tuple[str, str, str], ...] = (
    ("조회일", "search_date", _DATE),
    ("조회 기준(periodType)", "period_type", _ENUM),
    ("조회 기준명", "period_type", _ENUM_LABEL),
    ("주문번호(orderNo)", "order_no", _TEXT),
    ("상품주문번호(productOrderId)", "product_order_id", _TEXT),
    ("정산 대상 구분(productOrderType)", "product_order_type", _ENUM),
    ("정산 대상 구분명", "product_order_type", _ENUM_LABEL),
    ("상품번호", "product_id", _TEXT),
    ("상품명", "product_name", _TEXT),
    ("가맹점 ID", "merchant_id", _TEXT),
    ("가맹점명", "merchant_name", _TEXT),
    ("구매자명", "purchaser_name", _TEXT),
    ("정산 구분(settleType)", "settle_type", _ENUM),
    ("정산 구분명", "settle_type", _ENUM_LABEL),
    ("정산 기준일", "settle_basis_date", _DATE),
    ("정산 예정일", "settle_expect_date", _DATE),
    ("정산 완료일", "settle_complete_date", _DATE),
    ("세금 신고 기준일", "tax_return_date", _DATE),
    ("수수료 기준 금액", "commission_basis_amount", _MONEY),
    ("수수료 유형(commissionType)", "commission_type", _ENUM),
    ("수수료 유형명", "commission_type", _ENUM_LABEL),
    ("결제 수단(payMeansType)", "pay_means_type", _ENUM),
    ("결제 수단명", "pay_means_type", _ENUM_LABEL),
    ("수수료 금액", "commission_amount", _MONEY),
    ("매출 연동 수수료 상한", "maximum_selling_interlock_commission_amount", _MONEY),
)

_VAT_DAILY_COLUMNS: tuple[tuple[str, str, str], ...] = (
    ("정산 기준일", "settle_basis_date", _DATE),
) + _VAT_AMOUNT_COLUMNS + (
    ("가맹점 ID", "merchant_id", _TEXT),
    ("가맹점명", "merchant_name", _TEXT),
    ("확정 여부", "is_final", _BOOL),
)

_VAT_CASE_COLUMNS: tuple[tuple[str, str, str], ...] = (
    ("정산 기준일", "settle_basis_date", _DATE),
    ("주문번호(orderId)", "order_id", _TEXT),
    ("상품주문번호(productOrderId)", "product_order_id", _TEXT),
    ("정산 대상 구분(productOrderType)", "product_order_type", _ENUM),
    ("정산 대상 구분명", "product_order_type", _ENUM_LABEL),
    ("부가세 상세 유형(detailType)", "detail_type", _ENUM),
    ("부가세 상세 유형명", "detail_type", _ENUM_LABEL),
    ("증빙 상태(status)", "status", _ENUM),
    ("증빙 상태명", "status", _ENUM_LABEL),
    ("상품명", "product_name", _TEXT),
) + _VAT_AMOUNT_COLUMNS + (
    ("가맹점 ID", "merchant_id", _TEXT),
    ("가맹점명", "merchant_name", _TEXT),
)

#: kind -> ((헤더 한글, 모델 컬럼명, 타입태그), ...). **열 순서가 계약**이다 — 회계
#: 프로그램의 import 매핑이 순서를 기억한다.
CSV_COLUMNS: dict[str, tuple[tuple[str, str, str], ...]] = {
    "settle_daily": _SETTLE_DAILY_COLUMNS,
    "settle_case": _SETTLE_CASE_COLUMNS,
    "commission": _COMMISSION_COLUMNS,
    "vat_daily": _VAT_DAILY_COLUMNS,
    "vat_case": _VAT_CASE_COLUMNS,
}

#: 계약서 초안이 쓰던 이름(별칭). 라우트가 어느 쪽을 import 해도 같은 값이다.
CSV_KINDS: tuple[str, ...] = EXPORT_KINDS

#: UTF-8 BOM 1회. 없으면 표 계산 프로그램이 한글을 깨서 연다.
_BOM = "\ufeff"
_CRLF = "\r\n"
#: 한 번에 물어 오는 행 수. 관측 규모(1,284행/월)에서 1년치도 30여 회 왕복이면 끝난다.
_CHUNK = 500


# ---------------------------------------------------------------------------
# 값 -> 셀 문자열 (변형 금지 — 부호·자릿수를 그대로 옮긴다)
# ---------------------------------------------------------------------------


def _fmt_text(value: Any) -> str:
    """아무 값이나 셀 문자열로. ``None`` 은 빈 칸(``-`` 를 쓰지 않는다)."""
    return "" if value is None else str(value)


def _fmt_date(value: Any) -> str:
    """날짜 -> ``YYYY-MM-DD``. SQLite 는 문자열로 돌려주므로 둘 다 받는다."""
    if value is None or value == "":
        return ""
    if isinstance(value, (datetime.date, datetime.datetime)):
        return value.isoformat()[:10]
    return str(value)[:10]


def _fmt_money(value: Any) -> str:
    """금액 -> 부호 포함 평문 문자열.

    천단위 콤마·통화기호·괄호 음수를 쓰지 않는다(더존·이카운트 파서가 오독한다).
    정수로 떨어지면 정수 문자열, 소수부가 있으면 그대로 남긴다(버림은 회계에서 손실이다).

    Args:
        value: ``Numeric``/숫자/문자열/``None``.

    Returns:
        예: ``"-389000"``, ``"1234.56"``. 빈 값은 빈 문자열.
    """
    if value is None or value == "":
        return ""
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return str(value)
    if amount == amount.to_integral_value():
        return str(int(amount))
    return format(amount.normalize(), "f")


def _fmt_bool(value: Any) -> str:
    """참/거짓 -> ``Y``/``N``. ``None`` 은 빈 칸(모름을 거짓으로 바꾸지 않는다)."""
    if value is None:
        return ""
    return "Y" if bool(value) else "N"


#: 타입 태그 -> 셀 변환 함수. :data:`_ENUM_LABEL` 만 카탈로그가 필요해 따로 분기한다.
_FORMATTERS = {
    _DATE: _fmt_date, _MONEY: _fmt_money, _TEXT: _fmt_text,
    _INT: _fmt_text, _BOOL: _fmt_bool, _ENUM: _fmt_text, _ACCOUNT: mask_account_no,
}


def _cell(row: Any, column: str, tag: str) -> str:
    """행 하나의 컬럼 한 칸을 셀 문자열로.

    Args:
        row: ORM 행.
        column: 모델 컬럼명.
        tag: :data:`_FORMATTERS` 의 타입 태그 또는 :data:`_ENUM_LABEL`.

    Returns:
        셀 문자열.
    """
    value = getattr(row, column, None)
    if tag == _ENUM_LABEL:
        return label(_ENUM_MAPS[column], _fmt_text(value))
    return _FORMATTERS[tag](value)


# ---------------------------------------------------------------------------
# 파라미터 검증 · 조회
# ---------------------------------------------------------------------------


def normalize_kind(kind: Any) -> str:
    """CSV 종류 이름을 정본으로 편다(별칭 허용).

    Args:
        kind: 요청이 준 종류 이름.

    Returns:
        :data:`EXPORT_KINDS` 안의 정본 이름.

    Raises:
        ValueError: 허용 집합 밖(사람이 읽는 한글 사유).
    """
    text = str(kind or "").strip()
    resolved = _KIND_ALIASES.get(text, text)
    if resolved not in EXPORT_KINDS:
        raise ValueError(f"kind 는 {'|'.join(EXPORT_KINDS)} 중 하나여야 합니다: {kind!r}")
    return resolved


def _validate_range(date_from: datetime.date, date_to: datetime.date) -> None:
    """구간 검사 — 조회 커널과 **같은 상한**(:data:`MAX_RANGE_DAYS`)을 쓴다.

    Args:
        date_from: 시작일(포함).
        date_to: 종료일(포함).

    Raises:
        ValueError: 역순 구간이거나 폭이 상한을 넘을 때(한글 사유).
    """
    if date_from > date_to:
        raise ValueError("조회 시작일이 종료일보다 뒤입니다.")
    if (date_to - date_from).days + 1 > MAX_RANGE_DAYS:
        raise ValueError(f"내보내기 구간은 최대 {MAX_RANGE_DAYS}일입니다.")


def _axis_expr(model: Any, kind: str, basis: str) -> Any:
    """날짜 축 식 — 원장 커널 ``_ledger_date_expr`` 과 **같은 되돌림 순서**다.

    Args:
        model: 대상 모델.
        kind: CSV 종류(정본 이름).
        basis: 기준일 축. 일자 단위 표에는 뜻이 없다.

    Returns:
        SQLAlchemy 컬럼 식(후보가 둘 이상이면 ``coalesce``).
    """
    names: tuple[str, ...] = _AXIS_FALLBACK[kind]
    if kind in _BASIS_AWARE:
        names = (_BASIS_COLUMN.get(basis, ""),) + names
    columns: list[Any] = []
    seen: set[str] = set()
    for name in names:
        column = getattr(model, name, None)
        if column is not None and name not in seen:
            seen.add(name)
            columns.append(column)
    return columns[0] if len(columns) == 1 else func.coalesce(*columns)


def _filter_clauses(model: Any, kind: str, filters: dict) -> list:
    """유형 필터·검색어 술어. 파라미터 바인딩만 쓴다(문자열 조립 금지).

    Args:
        model: 대상 모델.
        kind: CSV 종류(정본 이름).
        filters: ``{'type': 유형코드, 'q': 부분일치}``.

    Returns:
        ``where`` 절 목록.

    Raises:
        ValueError: 그 kind 가 받지 않는 조건을 줬을 때. 조용히 버리면 화면과 다른
            파일이 나간다.
    """
    type_fields, search_fields = FILTER_FIELDS[kind]
    clauses: list = []
    for key, fields in (("type", type_fields), ("q", search_fields)):
        wanted = str(filters.get(key) or "").strip()
        if not wanted:
            continue
        if not fields:
            raise ValueError(f"{kind} 내보내기는 {key} 조건을 받지 않습니다.")
        if key == "type":
            clauses.append(or_(*[getattr(model, name) == wanted for name in fields]))
        else:
            pattern = f"%{wanted}%"
            clauses.append(or_(*[getattr(model, name).ilike(pattern)
                                 for name in fields]))
    return clauses


def build_export_rows(session: Any, *, kind: str, date_from: datetime.date,
                      date_to: datetime.date, channel: str = "NAVER",
                      basis: str = DEFAULT_BASIS,
                      filters: Optional[dict] = None) -> Iterator[list[str]]:
    """CSV 데이터 행을 하나씩 흘린다(헤더 없음, 전량 적재 없음).

    Args:
        session: SQLAlchemy Session.
        kind: CSV 종류(:data:`EXPORT_KINDS` 또는 별칭).
        date_from: 시작일(포함).
        date_to: 종료일(포함).
        channel: 채널 코드(현재 ``NAVER`` 만 적재된다).
        basis: 기준일 축 — 건별 정산·수수료에만 뜻이 있다.
        filters: ``{'type': 유형코드, 'q': 부분일치}``.

    Returns:
        행마다 :data:`CSV_COLUMNS` 순서의 셀 문자열 목록을 내는 이터레이터.

    Raises:
        ValueError: 종류·구간·조건이 허용 밖일 때(**호출 시점에** 즉시).
    """
    resolved = normalize_kind(kind)
    _validate_range(date_from, date_to)
    model = _MODELS[resolved]
    axis = _axis_expr(model, resolved, basis)
    clauses = [model.channel == channel, axis >= date_from, axis <= date_to]
    clauses += _filter_clauses(model, resolved, dict(filters or {}))
    query = (session.query(model).filter(*clauses)
             .order_by(axis.asc(), model.id.asc()))
    return _stream_rows(query, CSV_COLUMNS[resolved])


def _stream_rows(query: Any, columns: tuple[tuple[str, str, str], ...]
                 ) -> Iterator[list[str]]:
    """조회 결과를 셀 목록으로 바꿔 하나씩 내보낸다(``yield_per`` 로 청크 조회).

    Args:
        query: 완성된 조회.
        columns: :data:`CSV_COLUMNS` 의 한 항목.

    Yields:
        셀 문자열 목록.
    """
    for row in query.yield_per(_CHUNK):
        yield [_cell(row, column, tag) for _header, column, tag in columns]


# ---------------------------------------------------------------------------
# CSV 직렬화 · 파일명
# ---------------------------------------------------------------------------


def _write_line(writer: Any, buffer: io.StringIO, cells: list[str]) -> str:
    """셀 목록 -> CSV 한 줄(CRLF 포함). 버퍼 하나를 계속 되쓴다.

    Args:
        writer: :func:`csv.writer`.
        buffer: 그 writer 가 쓰는 버퍼.
        cells: 한 줄의 셀 문자열.

    Returns:
        ``\\r\\n`` 로 끝나는 한 줄.
    """
    buffer.seek(0)
    buffer.truncate(0)
    writer.writerow(cells)
    return buffer.getvalue()


def _emit(kind: str, rows: Iterator[list[str]]) -> Iterator[str]:
    """BOM+헤더 1줄을 먼저 내고 데이터 줄을 하나씩 낸다.

    헤더를 ``yield`` 한 시점에는 **조회가 아직 일어나지 않는다** — 첫 줄만 받아 가는
    호출자(스트리밍 응답)가 전량을 끌어오지 않게 하기 위해서다.

    Args:
        kind: CSV 종류(정본 이름).
        rows: :func:`build_export_rows` 의 결과.

    Yields:
        CSV 한 줄씩.
    """
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator=_CRLF)
    headers = [header for header, _column, _tag in CSV_COLUMNS[kind]]
    yield _BOM + _write_line(writer, buffer, headers)
    for cells in rows:
        yield _write_line(writer, buffer, cells)


def iter_csv_lines(session: Any, *, kind: str, date_from: datetime.date,
                   date_to: datetime.date, channel: str = "NAVER",
                   basis: str = DEFAULT_BASIS,
                   filters: Optional[dict] = None) -> Iterator[str]:
    """CSV 본문을 줄 단위로 흘린다 — 첫 줄은 BOM+헤더, 그 뒤는 데이터 줄.

    Args:
        session: SQLAlchemy Session.
        kind: CSV 종류(:data:`EXPORT_KINDS` 또는 별칭).
        date_from: 시작일(포함).
        date_to: 종료일(포함).
        channel: 채널 코드.
        basis: 기준일 축.
        filters: 유형·검색 조건.

    Returns:
        ``\\r\\n`` 로 끝나는 줄을 내는 이터레이터(``Response`` 에 그대로 물린다).

    Raises:
        ValueError: 종류·구간·조건이 허용 밖일 때 — **호출 시점에** 던진다(스트림이
            시작된 뒤에 터지면 반쪽 파일이 내려간다).
    """
    resolved = normalize_kind(kind)
    rows = build_export_rows(session, kind=resolved, date_from=date_from,
                             date_to=date_to, channel=channel, basis=basis,
                             filters=filters)
    return _emit(resolved, rows)


def export_filename(kind: str, date_from: datetime.date,
                    date_to: datetime.date) -> str:
    """다운로드 파일명 — **ASCII 만** 쓴다(한글 파일명은 RFC 5987 함정에 걸린다).

    Args:
        kind: CSV 종류(:data:`EXPORT_KINDS` 또는 별칭).
        date_from: 시작일.
        date_to: 종료일.

    Returns:
        예: ``naver_settle_case_20260803_20260902.csv``.

    Raises:
        ValueError: 허용 밖 종류.
    """
    slug = _FILENAME_SLUG[normalize_kind(kind)]
    return (f"naver_settle_{slug}_{date_from.strftime('%Y%m%d')}"
            f"_{date_to.strftime('%Y%m%d')}.csv")


#: 계약서 초안이 쓰던 이름(별칭). 라우트가 어느 쪽을 import 해도 같은 함수다.
iter_settlement_csv = iter_csv_lines
csv_filename = export_filename
