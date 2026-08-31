"""정산 대시보드 집계 서비스 — SETTLE-DASH-01 M1 (읽기 전용).

완료 대시보드(:mod:`foms.web.cs.completion_dashboard`)는 무검색 브라우즈 200건 캡이
있어 월별 합계를 낼 수 없다. 이 모듈은 **같은 모집단·같은 파생 규칙**을 캡 없이 전량으로
읽고 기간 버킷·미수 aging·채널·정산 현황·단계별 물린 금액을 집계한다.

파리티 원칙: 금액(출고가·예약금·잔금·과입금)·미수·현금영수증·정산 청구 판정은 완료
대시보드/erp_display/estimate_service 의 SSOT 헬퍼를 **직접 import 해서** 쓴다. 같은
규칙을 두 번 적어 두면 같은 주문의 잔금이 화면마다 갈린다(완료 대시보드 `_completion_row`
주석의 같은 이유).

성능(SPEC §4.1): **날짜 술어를 SQL 에 걸지 않는다.** 미수·aging 이 기간 무관 지표라
어차피 전량이 필요하고, 운영 실측 모집단이 2,168행/1.9MB·파이썬 커널 0.016초라 전량
로드가 저렴하다. 기간은 파이썬 버킷 단계에서만 적용한다. 로드 컬럼은
``id/status/structured_data`` 로 최소화하고 ``apply_erp_display_fields``(행마다 User
쿼리 = N+1)는 부르지 않는다.

이 모듈은 읽기 전용이다 — 커밋·flag_modified·Order 속성 대입을 하지 않는다.
"""

from __future__ import annotations

import calendar
import datetime
import re
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
    "aggregate_settlement",
    "aging_bucket",
    "completion_day_key",
    "completion_month_key",
    "week_key",
]

_MONTH_RE = re.compile(r"^\d{4}-\d{2}$")
_GRANULARITIES = ("day", "week", "month")
# 성능 가드(SPEC §4.2): 한 번에 12개월까지만. prev 구간까지 하면 최대 24개월 스캔이다.
_MAX_RANGE_MONTHS = 12
# 링크 없는 주문의 채널 표기. 네이버 등 외부 수집분만 링크가 붙는다.
_DEFAULT_CHANNEL = "일반"
# 단계 카드에서 빼는 완료 계열 stage code(SPEC §4.4).
_COMPLETED_STAGE_CODES = ("COMPLETED", "AS_COMPLETED")

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
        order: ``id/status/structured_data`` 만 실린 결과 행.
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
    return {
        "id": order.id,
        "status": order.status,
        "channel": channel,
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
        "as_billing_paid": _as_billing_paid_amount(
            shipment.get("as_billing") if isinstance(shipment, dict) else None
        ),
    }


def _is_receivable(row: dict) -> bool:
    """미수 여부 — 완료 대시보드 KPI(`_compute_completion_kpis`)와 같은 술어."""
    balance = row["balance"]
    return not row["paid"] and isinstance(balance, int) and balance > 0


def _row_month(row: dict) -> str:
    """행의 기간 귀속 월. 일 키가 없으면 "" (= 완료일 미상)."""
    return row["day_key"][:7]


# ---------------------------------------------------------------------------
# 모집단 로드
# ---------------------------------------------------------------------------


def _population_filters() -> tuple:
    """주 모집단 3조건 — 완료 대시보드 ``_completion_base_query`` 와 정확히 동일.

    ``Order.dashboard_active_filter()`` 를 쓰지 않는다 — 완료 60일 경과분을 잘라
    과거 월이 통째로 증발한다.
    """
    return (
        Order.active_filter(),
        Order.is_erp_order.is_(True),
        Order.status.in_(ORDER_SETTLEMENT_ALERT_TARGET_STATUSES),
    )


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
        .filter(*_population_filters())
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
    """모집단 전량을 파생 행 리스트로 읽는다(날짜 술어 없음).

    Args:
        db: SQLAlchemy Session.

    Returns:
        ``_settlement_row`` 파생 dict 리스트.
    """
    channels = _channel_map(db)
    orders = (
        db.query(Order.id, Order.status, Order.structured_data)
        .filter(*_population_filters())
        .all()
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


def _enumerate_bucket_keys(months: list[str], granularity: str) -> list[str]:
    """기간 내 모든 버킷 키(빈 구간 0 채우기용, 시간순).

    Args:
        months: 대상 월 키 목록(오름차순).
        granularity: "day" | "week" | "month".

    Returns:
        버킷 키 목록(시간 오름차순).
    """
    if granularity == "month":
        return list(months)
    keys: list[str] = []
    for month in months:
        year, mon = int(month[0:4]), int(month[5:7])
        last_day = calendar.monthrange(year, mon)[1]
        if granularity == "day":
            keys.extend(f"{month}-{d:02d}" for d in range(1, last_day + 1))
            continue
        last_week = int(week_key(f"{month}-{last_day:02d}").rsplit("W", 1)[1])
        keys.extend(f"{month}-W{n}" for n in range(1, last_week + 1))
    return keys


def _bucket_label(key: str, granularity: str) -> str:
    """버킷 키 → 화면 라벨("7/1" / "7월 1주" / "7월")."""
    month_no = int(key[5:7])
    if granularity == "day":
        return f"{month_no}/{int(key[8:10])}"
    if granularity == "week":
        return f"{month_no}월 {key.rsplit('W', 1)[1]}주"
    return f"{month_no}월"


def _build_buckets(rows: list[dict], months: list[str], granularity: str) -> list[dict]:
    """기간 내 행을 시계열 버킷으로 집계한다(빈 구간도 0 으로 채운다).

    Args:
        rows: 기간 내 파생 행(이미 월로 걸러진 것).
        months: 대상 월 키 목록(오름차순).
        granularity: "day" | "week" | "month".

    Returns:
        [{"key", "label", "revenue", "count"}] 시간 오름차순.
    """
    buckets = {
        key: {"key": key, "label": _bucket_label(key, granularity), "revenue": 0, "count": 0}
        for key in _enumerate_bucket_keys(months, granularity)
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


def _build_kpi(in_period: list[dict], all_rows: list[dict]) -> dict:
    """상단 KPI. 매출·건수·수금·과입금은 기간 내, 미수는 **기간 무관 모집단 전체**.

    Args:
        in_period: 기간 내 파생 행.
        all_rows: 모집단 전체 파생 행.

    Returns:
        반환 스키마의 ``kpi`` dict.
    """
    revenue = sum(
        row["shipping_price"] for row in in_period
        if isinstance(row["shipping_price"], int)
    )
    count = len(in_period)
    # 수금 근사: 완료월에 귀속된 예약금 + 잔금 확인(balance_confirmed)된 건의 잔금.
    collected = sum(row["deposit"] or 0 for row in in_period)
    collected += sum(
        row["balance"] for row in in_period
        if row["paid"] and isinstance(row["balance"], int)
    )
    receivable = [row for row in all_rows if _is_receivable(row)]
    return {
        "revenue": revenue,
        "completed_count": count,
        "avg_shipping_price": revenue // count if count else 0,
        "receivable_total": sum(row["balance"] for row in receivable),
        "receivable_count": len(receivable),
        "collected_approx": collected,
        "overpaid_total": sum(row["overpaid"] for row in in_period),
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


def _build_settlement_status(in_period: list[dict]) -> dict:
    """정산 현황(기간 내): 청구 여부·현금영수증·AS 유상 확정·부서별 차감.

    Args:
        in_period: 기간 내 파생 행.

    Returns:
        반환 스키마의 ``settlement_status`` dict.
    """
    issued = sum(1 for row in in_period if row["settlement_issued"])
    dept_amount = {code: 0 for code, _ in SETTLEMENT_DEPARTMENT_OPTIONS}
    dept_count = {code: 0 for code, _ in SETTLEMENT_DEPARTMENT_OPTIONS}
    as_paid_count = as_paid_amount = 0
    for row in in_period:
        for department, amount in row["deductions"]:
            if department in dept_amount:
                dept_amount[department] += amount
                dept_count[department] += 1
        if row["as_billing_paid"] is not None:
            as_paid_count += 1
            as_paid_amount += row["as_billing_paid"]
    return {
        "issued_count": issued,
        "pending_count": len(in_period) - issued,
        "cash_receipt_requested": sum(
            1 for row in in_period if row["cash_receipt_state"] == "requested"
        ),
        "cash_receipt_issued": sum(1 for row in in_period if row["cash_receipt_issued"]),
        "as_billing_paid_count": as_paid_count,
        "as_billing_paid_amount": as_paid_amount,
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
    rows = (
        db.query(Order.erp_stage_code, Order.structured_data)
        .filter(
            Order.active_filter(),
            Order.is_erp_order.is_(True),
            Order.erp_stage_code.isnot(None),
            ~Order.erp_stage_code.in_(_COMPLETED_STAGE_CODES),
        )
        .all()
    )
    stats: dict[str, dict] = {}
    for stage_code, structured_data in rows:
        code = str(stage_code)
        entry = stats.setdefault(
            code,
            {"stage": code, "label": STAGE_LABELS.get(code, code), "count": 0, "amount": 0},
        )
        entry["count"] += 1
        price = erp_shipping_price_from_structured(_ensure_dict(structured_data))
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
    month_from: str,
    month_to: str,
    granularity: str = "month",
) -> dict:
    """정산 대시보드 집계 — 완료 대시보드 200건 캡과 무관한 전량 집계.

    Args:
        db: SQLAlchemy Session.
        month_from: 조회 시작 월 "YYYY-MM"(포함).
        month_to: 조회 종료 월 "YYYY-MM"(포함).
        granularity: "day" | "week" | "month".

    Returns:
        range/kpi/buckets/prev_buckets/aging/aging_unknown/channels/
        settlement_status/stages/unknown_completion 키를 가진 dict.

    Raises:
        ValueError: month 형식 오류, granularity 미지원, 범위 역전, 12개월 초과.
    """
    if granularity not in _GRANULARITIES:
        raise ValueError(
            f"granularity 는 {'|'.join(_GRANULARITIES)} 중 하나여야 합니다: {granularity!r}"
        )
    months = _month_range(month_from, month_to)
    prev_months = _previous_month_range(months)
    current, previous = set(months), set(prev_months)
    all_rows = _load_rows(db)
    in_period = [row for row in all_rows if _row_month(row) in current]
    prev_period = [row for row in all_rows if _row_month(row) in previous]
    aging, aging_unknown = _build_aging(all_rows, get_today_kst())
    return {
        "range": {
            "month_from": month_from,
            "month_to": month_to,
            "granularity": granularity,
        },
        "kpi": _build_kpi(in_period, all_rows),
        "buckets": _build_buckets(in_period, months, granularity),
        "prev_buckets": _build_buckets(prev_period, prev_months, granularity),
        "aging": aging,
        "aging_unknown": aging_unknown,
        "channels": _build_channels(in_period),
        "settlement_status": _build_settlement_status(in_period),
        "stages": _build_stages(db),
        "unknown_completion": _build_unknown_completion(all_rows),
    }
