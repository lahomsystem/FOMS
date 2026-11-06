"""프리랜서 영업 수수료 계산 규칙 정본(FCOMM-01 §3).

설계서 ``docs/specs/2026-11-06-freelancer-sales-commission_SPEC.md`` §3 의 규칙을 순수 함수로 둔다.
DB · Flask 를 모른다 — 호출자가 주문 칸 값 · 설정값 · 시공비 입력을 꺼내 넘긴다.

- 주인과 거래구분(§3.1 · J8): :func:`resolve_owner`
- 대상 여부(§3.2 · D8 · D15): :func:`eligibility_date` · :func:`is_eligible`
- 달(§3.3 · D6 · J1): :func:`completion_month` · :func:`measurement_month`
- 금액(§3.4 · D1 · D2 · D18): :func:`commission_shipping_price` · :func:`sales_deduction_total`
  · :func:`rate_bp_for` · :func:`commission_amount` · :func:`line_commission`
- 세금(§3.5 · D11 · J3): :func:`tax_breakdown`

돈 계산은 정수식만 쓴다. 파이썬 ``round()`` 는 짝수 반올림이라 엑셀과 1원 어긋난다(J3).
"""

from __future__ import annotations

import datetime
import re
from typing import Any, Mapping, Sequence

from foms.services.erp_display import (
    _erp_coerce_item_price_krw,
    erp_payment_amount_from_structured,
    erp_shipping_price_from_structured,
)
from foms.services.orders.drawing_confirm_partial import is_item_cancelled
from foms.services.sales_commission.names import normalize_name

# 거래구분(§3.1). 요율 이력의 칸 이름은 :data:`RATE_FIELD_BY_DEAL` 이 정한다.
DEAL_LAHOM = "LAHOM"
DEAL_HAUD = "HAUD"
DEAL_PERSONAL = "PERSONAL"
DEAL_MANUAL = "MANUAL"  # 숨고 · 직접 입력 발주사 — 회계팀이 건마다 요율을 고른다(D4)
DEAL_TYPES = (DEAL_LAHOM, DEAL_HAUD, DEAL_PERSONAL, DEAL_MANUAL)

RATE_FIELD_BY_DEAL = {
    DEAL_LAHOM: "lahom_bp",
    DEAL_HAUD: "haud_bp",
    DEAL_PERSONAL: "personal_bp",
}

# 시공 완료 = 메인 단계(orders.erp_stage_code)가 이 값들(J1). order.status · AS 축은 보지 않는다.
COMPLETED_STAGES = frozenset({"CS", "COMPLETED"})

# 세금 방식(D11).
TAX_WITHHOLD_3_3 = "WITHHOLD_3_3"
TAX_VAT_10 = "VAT_10"
TAX_NONE = "NONE"
TAX_TYPES = (TAX_WITHHOLD_3_3, TAX_VAT_10, TAX_NONE)

# 발주사 글자 판정어 — 라홈은 정산 대시보드 brand_channel_of 와 같은 규칙(네이버 주문 포함).
_LAHOM_KEYWORD = "라홈"
_HAUD_KEYWORD = "하우드"

# 수수료 귀속 부서(차감 기록 department).
_SALES_DEPARTMENT = "SALES"

# 날짜 글자 맨 앞의 "YYYY-MM-DD"(구분자 - . / 허용, 월·일 한 자리 허용). 여러 날이면 첫 날만 잡힌다.
_DATE_PREFIX_RE = re.compile(r"^\s*(\d{4})[-./](\d{1,2})[-./](\d{1,2})")
_MONTH_RE = re.compile(r"^(\d{4})-(\d{2})$")


# ---------------------------------------------------------------------------
# 날짜 · 달
# ---------------------------------------------------------------------------


def _to_ymd(value: Any) -> str | None:
    """날짜 값 하나를 ``YYYY-MM-DD`` 로 바꾼다.

    Args:
        value: ``date`` · ``datetime`` 또는 ``"YYYY-MM-DD..."`` 로 시작하는 글자. 콤마 등으로 여러
            날을 이어 붙인 시공일(운영 예 ``"2026-05-27,2026-05-28"``)은 첫 날만 본다 — 정산
            대시보드 ``completion_month_key`` 와 같은 귀속.

    Returns:
        ``YYYY-MM-DD`` 글자. 비었거나 날짜로 읽을 수 없으면 None.
    """
    if isinstance(value, datetime.datetime):
        return value.date().isoformat()
    if isinstance(value, datetime.date):
        return value.isoformat()
    if not isinstance(value, str):
        return None
    match = _DATE_PREFIX_RE.match(value)
    if not match:
        return None
    try:
        return datetime.date(int(match.group(1)), int(match.group(2)), int(match.group(3))).isoformat()
    except ValueError:
        return None


def eligibility_date(measurement_date: Any, received_date: Any, created_at: Any) -> str | None:
    """대상 여부 · 실측일 기준 달의 기준 날짜(§3.2 · D15).

    Args:
        measurement_date: ``schedule.measurement.date`` 원본 값.
        received_date: ``orders.received_date``(글자 칸). 빈 글자면 다음으로 넘어간다.
        created_at: ``orders.created_at``(datetime). 호출자가 저장값을 그대로 넘긴다.

    Returns:
        실측일, 없으면 접수일, 없으면 생성일의 ``YYYY-MM-DD``. 셋 다 없으면 None.
    """
    for candidate in (measurement_date, received_date, created_at):
        ymd = _to_ymd(candidate)
        if ymd:
            return ymd
    return None


def is_eligible(measurement_date: Any, received_date: Any, created_at: Any, start_month: Any) -> bool:
    """프리랜서 시작 달 1일 이후 실측한 주문인가(D8 · D15).

    Args:
        measurement_date: 실측일 원본 값.
        received_date: 접수일 원본 값.
        created_at: 생성 시각.
        start_month: 프리랜서 설정의 시작 달 ``YYYY-MM``.

    Returns:
        기준 날짜 ≥ 시작 달 1일이면 True. 시작 달이 형식에 안 맞거나 기준 날짜가 없으면 False.
    """
    if not isinstance(start_month, str) or not _MONTH_RE.match(start_month.strip()):
        return False
    ymd = eligibility_date(measurement_date, received_date, created_at)
    if ymd is None:
        return False
    return ymd >= f"{start_month.strip()}-01"


def completion_month(stage_code: Any, construction_date: Any) -> str | None:
    """시공 완료 달(§3.3 · J1). 지급 기준 달이다.

    Args:
        stage_code: ``orders.erp_stage_code``.
        construction_date: ``schedule.construction.date`` 원본 값(여러 날이면 첫 날).

    Returns:
        메인 단계가 :data:`COMPLETED_STAGES` 이고 시공일을 읽을 수 있으면 ``YYYY-MM``, 아니면 None.
    """
    code = str(stage_code or "").strip().upper()
    if code not in COMPLETED_STAGES:
        return None
    ymd = _to_ymd(construction_date)
    return ymd[:7] if ymd else None


def measurement_month(measurement_date: Any, received_date: Any, created_at: Any) -> str | None:
    """실측일 기준 달(§3.3 · D7). 보기 전용이라 단계 조건이 없다.

    Args:
        measurement_date: 실측일 원본 값.
        received_date: 접수일 원본 값.
        created_at: 생성 시각.

    Returns:
        :func:`eligibility_date` 의 ``YYYY-MM``. 없으면 None.
    """
    ymd = eligibility_date(measurement_date, received_date, created_at)
    return ymd[:7] if ymd else None


# ---------------------------------------------------------------------------
# 주문 칸 꺼내기 · 주인
# ---------------------------------------------------------------------------


def _nested(sd: Any, *keys: str) -> Any:
    """dict 를 따라 내려가 값을 꺼낸다. 중간이 dict 가 아니면 None."""
    node = sd
    for key in keys:
        if not isinstance(node, dict):
            return None
        node = node.get(key)
    return node


def extract_order_fields(sd: Any) -> dict[str, Any]:
    """수수료 계산에 쓰는 structured_data 칸만 꺼낸다(경로를 한 곳에 둔다).

    Args:
        sd: 주문 structured_data. dict 가 아니면 모두 빈 값.

    Returns:
        ``orderer_name`` · ``manager_name``(정리한 이름), ``measurement_date`` ·
        ``construction_date``(원본 값) 키를 가진 dict.
    """
    return {
        "orderer_name": normalize_name(_nested(sd, "parties", "orderer", "name")),
        "manager_name": normalize_name(_nested(sd, "parties", "manager", "name")),
        "measurement_date": _nested(sd, "schedule", "measurement", "date"),
        "construction_date": _nested(sd, "schedule", "construction", "date"),
    }


def _normalized_match_map(match_map: Mapping[str, Any] | None) -> dict[str, int]:
    """맞출 이름 표의 열쇠를 정리하고 값을 정수로 맞춘다. 빈 이름 · 정수 아닌 값은 버린다."""
    result: dict[str, int] = {}
    for raw_name, raw_user_id in (match_map or {}).items():
        name = normalize_name(raw_name)
        if not name or isinstance(raw_user_id, bool):
            continue
        try:
            result[name] = int(raw_user_id)
        except (TypeError, ValueError):
            continue
    return result


def resolve_owner(
    orderer_name: Any,
    manager_name: Any,
    *,
    is_naver: bool,
    match_map: Mapping[str, Any] | None,
) -> tuple[int | None, str | None]:
    """수수료 주인과 거래구분(§3.1 · J8 · J10). 완전 일치만 인정한다.

    1. 발주사가 맞출 이름이면 → (그 프리랜서, 개인영업).
    2. 아니면 대표 담당자가 맞출 이름이면 → (그 프리랜서, 발주사로 정한 거래구분):
       '라홈' 포함 또는 네이버 주문 → 라홈, '하우드' 포함 → 하우드, 그 밖 → 회계팀 지정.
    3. 둘 다 아니면 (None, None).

    Args:
        orderer_name: ``parties.orderer.name``.
        manager_name: ``parties.manager.name``(대표 담당자).
        is_naver: 네이버 주문인가(외부 판매채널 NAVER).
        match_map: 활성 프리랜서의 ``{맞출 이름: user_id}``. 열쇠는 여기서 다시 정리한다.

    Returns:
        ``(user_id, 거래구분)`` 또는 ``(None, None)``.
    """
    names = _normalized_match_map(match_map)
    orderer = normalize_name(orderer_name)
    if orderer and orderer in names:
        return names[orderer], DEAL_PERSONAL
    manager = normalize_name(manager_name)
    if not manager or manager not in names:
        return None, None
    if is_naver or _LAHOM_KEYWORD in orderer:
        return names[manager], DEAL_LAHOM
    if _HAUD_KEYWORD in orderer:
        return names[manager], DEAL_HAUD
    return names[manager], DEAL_MANUAL


# ---------------------------------------------------------------------------
# 금액
# ---------------------------------------------------------------------------


def commission_shipping_price(sd: Any) -> int | None:
    """수수료용 출고가 = 주문 화면 출고가에서 취소 품목 값만 뺀 것(§3.4 · D2 · D18).

    공식과 예외 모양은 ``erp_shipping_price_from_structured`` 를 그대로 따른다(그 함수는 주문
    화면 숫자라 바꾸지 않는다). 취소 품목이 없으면 그 함수의 결과를 그대로 돌려준다.

    취소 품목이 있으면: 품목합(``erp_payment_amount_from_structured`` — 저장된
    ``totals.items_total`` 우선, 없으면 ``items[].price`` 합)에서 ``items[]`` 중 취소 품목 값을
    빼고(0 미만 없음) 자유 입력을 더하고 할인을 뺀다(0 미만 없음). 저장 ``items_total`` 은 서버가
    취소 품목까지 포함한 품목 값 합으로 다시 계산하므로(``recompute_totals``) 빼는 쪽이 맞다.
    ``items`` 가 없는 옛 모양(``totals`` 만 있음)은 취소를 알 길이 없어 화면 출고가와 같다.

    Args:
        sd: 주문 structured_data.

    Returns:
        출고가(원) 정수. 품목합을 낼 수 없으면 None.
    """
    items = sd.get("items") if isinstance(sd, dict) else None
    cancelled = [it for it in items if is_item_cancelled(it)] if isinstance(items, list) else []
    if not cancelled:
        return erp_shipping_price_from_structured(sd)
    items_total = erp_payment_amount_from_structured(sd)
    if items_total is None:
        return None
    cancelled_total = sum(_erp_coerce_item_price_krw(it) for it in cancelled)
    active_total = max(0, int(items_total) - cancelled_total)
    # 원본 함수와 같은 지역 import(모듈 로드 순환 방지 — erp_display 와 같은 이유).
    from foms.services.estimate_service import (
        _extract_discount_amount,
        _extract_free_input_amount,
    )
    free_input = int(_extract_free_input_amount(sd) or 0)
    discount = int(_extract_discount_amount(sd) or 0)
    return max(0, active_total + free_input - discount)


def _as_int(value: Any) -> int | None:
    """정수로 읽을 수 있으면 정수, 아니면 None(bool 은 거부)."""
    if isinstance(value, bool) or value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def sales_deduction_total(sd: Any, user_id: Any) -> int:
    """프리랜서 귀속 영업 차감 합(§3.4 · D13).

    ``settlement.deductions[]`` 중 부서 SALES · 귀속 사람 = ``user_id`` · 취소 표시(``voided_at``)
    없음인 기록의 금액 절대값을 더한다. 차감 금액은 음수로 저장된다.

    Args:
        sd: 주문 structured_data.
        user_id: 프리랜서 사용자 id(글자 id 도 정수로 맞춰 비교).

    Returns:
        차감 합(0 이상 원). 칸이 없거나 모양이 틀리면 0.
    """
    target = _as_int(user_id)
    deductions = _nested(sd, "settlement", "deductions")
    if target is None or not isinstance(deductions, list):
        return 0
    total = 0
    for entry in deductions:
        if not isinstance(entry, dict) or entry.get("voided_at"):
            continue
        if str(entry.get("department") or "").strip().upper() != _SALES_DEPARTMENT:
            continue
        if _as_int(entry.get("charge_to_user_id")) != target:
            continue
        amount = _as_int(entry.get("amount"))
        if amount is not None:
            total += abs(amount)
    return total


def rate_bp_for(
    rates: Sequence[Mapping[str, Any]] | None,
    month: Any,
    deal_type: str,
    override_bp: int | None,
) -> int | None:
    """그 줄에 적용할 요율(basis point, 100bp = 1%)(§3.4 · D4 · D16).

    Args:
        rates: 프리랜서 요율 이력. 줄마다 ``effective_month``(``YYYY-MM``) · ``lahom_bp`` ·
            ``haud_bp`` · ``personal_bp``. 순서는 상관없다.
        month: 시공 완료 달 ``YYYY-MM``.
        deal_type: 거래구분.
        override_bp: 회계팀 지정 요율(없으면 None).

    Returns:
        회계팀 지정 줄 → ``override_bp``(없으면 None). 그 밖 → ``override_bp`` 가 있으면 그 값,
        없으면 ``effective_month ≤ month`` 중 가장 늦은 줄의 거래구분 칸. 줄이 없으면 None.
    """
    override = _as_int(override_bp)
    if deal_type == DEAL_MANUAL:
        return override
    if override is not None:
        return override
    field = RATE_FIELD_BY_DEAL.get(deal_type)
    if field is None or not isinstance(month, str) or not _MONTH_RE.match(month.strip()):
        return None
    target_month = month.strip()
    best: Mapping[str, Any] | None = None
    best_month = ""
    for row in rates or ():
        if not isinstance(row, Mapping):
            continue
        effective = str(row.get("effective_month") or "").strip()
        if not _MONTH_RE.match(effective) or effective > target_month:
            continue
        if effective >= best_month:  # 같은 달이 둘이면 뒤의 줄(나중 저장)이 이긴다
            best, best_month = row, effective
    return _as_int(best.get(field)) if best is not None else None


def commission_amount(base: int, bp: int) -> int:
    """수수료 = 기준액 × 요율, 원 단위 반올림(J3).

    Args:
        base: 기준액(출고가 − 시공비 − 차감). 0 미만이면 0 으로 본다(D1).
        bp: 요율(basis point).

    Returns:
        ``(max(0, base) × bp + 5000) // 10000``.
    """
    return (max(0, int(base)) * int(bp) + 5000) // 10000


def line_commission(
    shipping_price: int | None,
    install_cost: int | None,
    deduction_total: int | None,
    bp: int | None,
) -> int | None:
    """주문 한 줄의 수수료(§3.4 · D1).

    Args:
        shipping_price: 수수료용 출고가(:func:`commission_shipping_price`).
        install_cost: 시공비. 없으면 "시공비 기다림"이라 계산하지 않는다.
        deduction_total: 영업 차감 합(:func:`sales_deduction_total`). None 은 0.
        bp: 적용 요율(:func:`rate_bp_for`).

    Returns:
        수수료(원). 출고가 · 시공비 · 요율 중 하나라도 없으면 None.
    """
    if shipping_price is None or install_cost is None or bp is None:
        return None
    base = int(shipping_price) - int(install_cost) - int(deduction_total or 0)
    return commission_amount(base, bp)


# ---------------------------------------------------------------------------
# 세금
# ---------------------------------------------------------------------------


def tax_breakdown(gross: int, tax_type: str) -> dict[str, int]:
    """마감 합계에 세금을 한 번 매긴다(§3.5 · D11 · J3).

    - 3.3% 원천징수: 소득세 = 합계 × 3% (10원 미만 버림), 지방소득세 = 소득세 × 10%
      (10원 미만 버림), 실지급 = 합계 − 둘.
    - 부가세 10%: 부가세 = 합계 × 10% (원 미만 버림), 실지급 = 합계 + 부가세.
    - 없음: 실지급 = 합계.

    Args:
        gross: 마감 합계(원).
        tax_type: :data:`TAX_TYPES` 중 하나.

    Returns:
        ``gross`` · ``tax_income`` · ``tax_local`` · ``vat`` · ``net`` 키의 dict.
        합계가 0 이하면 세금과 실지급 모두 0.

    Raises:
        ValueError: 모르는 세금 방식.
    """
    if tax_type not in TAX_TYPES:
        raise ValueError(f"unknown tax_type: {tax_type!r}")
    gross = int(gross)
    result = {"gross": gross, "tax_income": 0, "tax_local": 0, "vat": 0, "net": 0}
    if gross <= 0:
        return result
    if tax_type == TAX_WITHHOLD_3_3:
        tax_income = (gross * 3 // 100) // 10 * 10
        tax_local = (tax_income // 10) // 10 * 10
        result.update(tax_income=tax_income, tax_local=tax_local, net=gross - tax_income - tax_local)
    elif tax_type == TAX_VAT_10:
        vat = gross * 10 // 100
        result.update(vat=vat, net=gross + vat)
    else:
        result["net"] = gross
    return result
