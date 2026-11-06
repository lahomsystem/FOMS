"""프리랜서 영업 수수료 탭 읽기 모델(FCOMM-01 §2.1 · §3 · §9 — 플랜 T5).

정산 화면 "영업 수수료" 탭이 프리랜서 한 명 · 달 하나의 줄을 받는다. 계산 규칙은 전부
:mod:`foms.services.sales_commission.calc`(순수 함수)에 있고, 여기서는 주문을 읽어 그 함수에 넘기기만 한다.

조회 수는 요청 한 번에 고정이다 — 후보 주문 1번 · 네이버 링크 1번 · 시공비 입력 1번 · 본인 수정 기록 1번
(+ 설정 1번). 줄마다 따로 묻지 않는다. 후보는 평탄 칸(``erp_stage_code`` · ``erp_construction_date`` ·
``erp_measurement_date``)으로 SQL 에서 먼저 좁히고, 주인 판정(발주사 · 대표 담당 이름)은 파이썬에서 한다 —
발주사 이름은 평탄 칸이 없어서다. ``structured_data`` 는 계산이 읽는 경로만 남긴 얇은 문서로 싣는다
(:func:`foms.services.settlement_source.fetch_settlement_rows`, 나무 :data:`COMMISSION_SD_SPEC`).

모집단(설계서 §3.1 · §8.1): ERP 주문 · 초안/삭제 아님(``Order.active_filter``) · 협력사 주문 아님.
- 시공 완료 기준(``basis="completion"``): 메인 단계 CS/COMPLETED · 시공 완료 달 ≤ 고른 달 · 아직 어느
  마감에도 없음(:func:`closed_order_ids`). 지난달에 시공비가 없어 빠진 주문도 다시 나온다.
- 실측일 기준(``basis="measurement"``): 실측일(없으면 접수일 · 생성일) 달 = 고른 달. 단계 조건 없음 —
  시공 완료 전 줄은 "예상"(``FORECAST``).
"""
from __future__ import annotations

import re
from typing import Any, Iterable, Optional

from sqlalchemy import or_, select

from foms.services.datetime_kst import format_datetime_kst
from foms.services.erp_display import _ensure_dict
from foms.services.orders.drawing_confirm_partial import drop_cancelled
from foms.services.sales_commission import calc
from foms.services.sales_commission.names import normalize_name
from foms.services.sales_commission.settings import FreelancerConfig, active_freelancers
from foms.services.settlement_deductions import valid_deductions
from foms.services.settlement_source import ARRAY_ITEMS, fetch_settlement_rows
from models import ExternalOrderLink, Order, OrderFieldChange, SalesCommissionClosing, SalesCommissionInput

__all__ = [
    "BASIS_COMPLETION",
    "BASIS_MEASUREMENT",
    "BASES",
    "COMMISSION_SD_SPEC",
    "SELF_EDIT_PATHS",
    "STATES",
    "closed_order_ids",
    "commission_row_for_order",
    "commission_rows",
    "input_payload",
]

BASIS_COMPLETION = "completion"
BASIS_MEASUREMENT = "measurement"
BASES = (BASIS_COMPLETION, BASIS_MEASUREMENT)

STATE_WAIT_COST = "WAIT_COST"  # 시공비가 아직 없다 — 계산 안 함, 합계 · 마감에서 빠짐
STATE_WAIT_RATE = "WAIT_RATE"  # 요율이 없다(숨고 · 직접 입력 발주사는 회계팀이 고른다)
STATE_DONE = "DONE"
STATE_FORECAST = "FORECAST"    # 실측일 기준 화면의 시공 완료 전 줄(예상)
STATES = (STATE_WAIT_COST, STATE_WAIT_RATE, STATE_DONE, STATE_FORECAST)

#: "본인 수정" 표시(§2.1-6) — 프리랜서 본인이 바꾸면 수수료가 달라지는 칸.
SELF_EDIT_PATHS = (
    "parties.orderer.name",
    "schedule.measurement.date",
    "schedule.construction.date",
    "totals.shipping_price",
)

NEAR_MISS_LIMIT = 20
_NEAR_MISS_MIN_LEN = 2  # 한 글자 이름이 맞출 이름 안에 들어가는 것은 경고하지 않는다(소음)
_NAVER_CHANNEL = "NAVER"
_MONTH_RE = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")

#: 계산이 읽는 ``structured_data`` 경로만 남긴 나무(:mod:`foms.services.settlement_source` 규약).
#: 출고가(품목 단가 · 취소 표시 · totals · payment/payments) · 이름 3칸 · 날짜 2칸 · 차감(settlement) · 품명.
COMMISSION_SD_SPEC: dict[str, Any] = {
    "items": {ARRAY_ITEMS: {"price": None, "product_name": None, "cancel": None}},
    "totals": None,
    "payment": None,
    "payments": None,
    "parties": {"manager": {"name": None}, "customer": {"name": None}, "orderer": {"name": None}},
    "schedule": {"construction": {"date": None}, "measurement": {"date": None}},
    "settlement": None,
}

_ORDER_COLUMNS = (
    Order.id,
    Order.customer_name,
    Order.erp_stage_code,
    Order.received_date,
    Order.created_at,
)


# --------------------------------------------------------------------------
# 작은 도우미
# --------------------------------------------------------------------------
def closed_order_ids(db, user_id: Optional[int] = None) -> set[int]:
    """마감에 이미 들어간 주문 번호(줄 스냅샷 ``lines[].order_id``).

    ``user_id`` 가 없으면 **모든 프리랜서**의 마감을 본다 — 시공 완료 기준 줄은 이것으로 거른다(J9: 한 번 F 의
    마감에 들어간 주문은 뒤에 대표 담당 · 발주사가 바뀌어도 누구의 일반 줄에도 다시 나오지 않는다. 그 뒤 차액은
    굳힌 주인의 조정 줄 몫이다 — T12). ``user_id`` 를 주면 그 프리랜서의 마감만 본다(조정 줄 다시 계산용).
    마감 표는 프리랜서 수 × 달 수 줄이라 작다 — ``lines`` 칸만 읽는다.
    """
    query = db.query(SalesCommissionClosing.lines)
    if user_id is not None:
        query = query.filter(SalesCommissionClosing.user_id == int(user_id))
    out: set[int] = set()
    for (lines,) in query.all():
        for line in lines if isinstance(lines, list) else []:
            order_id = calc._as_int(line.get("order_id")) if isinstance(line, dict) else None
            if order_id is not None:
                out.add(order_id)
    return out


def _next_month(month: str) -> str:
    year, mon = int(month[:4]), int(month[5:7])
    return f"{year + 1:04d}-01" if mon == 12 else f"{year:04d}-{mon + 1:02d}"


def _date_text(value: Any) -> Optional[str]:
    """날짜 칸 원본을 화면용 글자로(여러 날 글자는 그대로 둔다). 비었으면 None."""
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _customer_name(sd: dict, order: Any) -> str:
    """고객명 — 정산 실무 탭과 같은 순서(``parties.customer.name`` → ``orders.customer_name``)."""
    customer = calc._nested(sd, "parties", "customer")
    if isinstance(customer, dict):
        name = str(customer.get("name") or "").strip()
        if name:
            return name
    return str(getattr(order, "customer_name", "") or "").strip() or "-"


def _product_summary(sd: dict) -> str:
    """품명 요약 — 주문 목록 ``product`` 칸과 같은 규칙(취소 품목 빼고 품명을 ", " 로 잇는다)."""
    names = []
    for item in drop_cancelled(sd.get("items") or []):
        if not isinstance(item, dict):
            continue
        name = item.get("product_name")
        if isinstance(name, str) and name.strip():
            names.append(name.strip())
    return ", ".join(names)


def _sales_deductions(sd: dict, user_id: int) -> list[dict[str, Any]]:
    """이 프리랜서에게 붙은 유효 영업 차감 목록 — :func:`calc.sales_deduction_total` 과 같은 거름."""
    out: list[dict[str, Any]] = []
    for entry in valid_deductions(sd):
        if str(entry.get("department") or "").strip().upper() != "SALES":
            continue
        if calc._as_int(entry.get("charge_to_user_id")) != user_id:
            continue
        amount = calc._as_int(entry.get("amount"))
        if amount is None:
            continue
        out.append({
            "id": entry.get("id"),
            "amount": abs(amount),
            "reason": str(entry.get("reason") or ""),
            "created_at": entry.get("created_at"),
            "created_by": entry.get("created_by"),
        })
    return out


def input_payload(order_id: int, row: Optional[SalesCommissionInput]) -> dict[str, Any]:
    """시공비 입력 한 줄을 응답 모양으로. 줄이 없으면 version 0 · 빈 값."""
    return {
        "order_id": int(order_id),
        "install_cost": int(row.install_cost) if row is not None and row.install_cost is not None else None,
        "rate_override_bp": (int(row.rate_override_bp)
                             if row is not None and row.rate_override_bp is not None else None),
        "note": (row.note or "") if row is not None else "",
        "version": int(row.version or 1) if row is not None else 0,
    }


# --------------------------------------------------------------------------
# 묶음 조회(요청당 한 번씩)
# --------------------------------------------------------------------------
def _naver_ids(db, criteria: tuple) -> set[int]:
    """후보 주문 중 네이버 주문 번호 — 정산 대시보드 ``_channel_map`` 과 같은 규칙.

    한 주문에 링크가 여럿이면 가장 먼저 만들어진 링크의 채널을 쓴다. 후보 술어를 하위 조회로 넘겨 번호
    목록을 IN 으로 길게 싣지 않는다.
    """
    rows = (
        db.query(ExternalOrderLink.order_id, ExternalOrderLink.channel)
        .filter(ExternalOrderLink.order_id.in_(select(Order.id).where(*criteria)))
        .order_by(ExternalOrderLink.id.asc())
        .all()
    )
    first: dict[int, str] = {}
    for order_id, channel in rows:
        if order_id is not None:
            first.setdefault(int(order_id), str(channel or "").strip().upper())
    return {oid for oid, channel in first.items() if channel == _NAVER_CHANNEL}


def _inputs(db, order_ids: Iterable[int]) -> dict[int, SalesCommissionInput]:
    ids = list(order_ids)
    if not ids:
        return {}
    rows = db.query(SalesCommissionInput).filter(SalesCommissionInput.order_id.in_(ids)).all()
    return {int(r.order_id): r for r in rows}


def _self_edits(db, order_ids: Iterable[int], user_id: int) -> dict[int, list[dict[str, Any]]]:
    """프리랜서 본인이 수수료에 닿는 칸을 바꾼 기록(``order_field_changes``) — 주문별 ``[{field, at}]``."""
    ids = list(order_ids)
    if not ids:
        return {}
    rows = (
        db.query(OrderFieldChange.order_id, OrderFieldChange.path_template, OrderFieldChange.created_at)
        .filter(
            OrderFieldChange.order_id.in_(ids),
            OrderFieldChange.actor_user_id == user_id,
            OrderFieldChange.path_template.in_(SELF_EDIT_PATHS),
        )
        .order_by(OrderFieldChange.created_at.asc(), OrderFieldChange.id.asc())
        .all()
    )
    out: dict[int, list[dict[str, Any]]] = {}
    for order_id, field, created_at in rows:
        out.setdefault(int(order_id), []).append(
            {"field": field, "at": format_datetime_kst(created_at, "%Y-%m-%d %H:%M")})
    return out


# --------------------------------------------------------------------------
# 줄 만들기
# --------------------------------------------------------------------------
def _scope_filters() -> tuple:
    """모든 기준 공통 — ERP 주문 · 초안/삭제 아님 · 협력사 주문 아님(§3.1 제외 규칙)."""
    return (
        Order.active_filter(),
        Order.is_erp_order.is_(True),
        Order.partner_org_id.is_(None),
    )


def _window_filters(month: str, basis: str, start_month: str) -> tuple:
    """기준별 SQL 좁히기(평탄 칸). 넓게 잡고 정확한 판정은 파이썬(calc)이 한다."""
    start_day = f"{start_month}-01" if _MONTH_RE.match(start_month or "") else ""
    measured_on_or_after_start = or_(
        Order.erp_measurement_date.is_(None),
        Order.erp_measurement_date == "",
        Order.erp_measurement_date >= start_day,
    )
    if basis == BASIS_MEASUREMENT:
        return (or_(
            Order.erp_measurement_date.is_(None),
            Order.erp_measurement_date == "",
            Order.erp_measurement_date.like(f"{month}-%"),
        ),)
    return (
        Order.erp_stage_code.in_(tuple(calc.COMPLETED_STAGES)),
        Order.erp_construction_date.isnot(None),
        Order.erp_construction_date != "",
        Order.erp_construction_date < f"{_next_month(month)}-01",
        measured_on_or_after_start,
    )


def _build_row(order: Any, sd: dict, fields: dict[str, Any], *, cfg: FreelancerConfig, deal_type: str,
               basis: str, input_row: Optional[SalesCommissionInput],
               self_edits: list[dict[str, Any]]) -> dict[str, Any]:
    """주문 한 건 → 수수료 줄(쿼리 없음)."""
    done_month = calc.completion_month(order.erp_stage_code, fields["construction_date"])
    measured_month = calc.measurement_month(fields["measurement_date"], order.received_date, order.created_at)
    shipping = calc.commission_shipping_price(sd)
    deduction_total = calc.sales_deduction_total(sd, cfg.user_id)
    install_cost = (int(input_row.install_cost)
                    if input_row is not None and input_row.install_cost is not None else None)
    override = (int(input_row.rate_override_bp)
                if input_row is not None and input_row.rate_override_bp is not None else None)
    # 요율은 시공 완료 달 기준(§3.4). 아직 완료 전(실측일 기준 예상 줄)이면 실측 달로 어림한다.
    rate_month = done_month or measured_month
    rate_bp = calc.rate_bp_for([r.as_dict() for r in cfg.rates], rate_month, deal_type, override)
    commission = calc.line_commission(shipping, install_cost, deduction_total, rate_bp)
    if done_month is None:
        state = STATE_FORECAST
    elif install_cost is None:
        state = STATE_WAIT_COST
    elif rate_bp is None:
        state = STATE_WAIT_RATE
    else:
        state = STATE_DONE
    return {
        "order_id": int(order.id),
        "customer_name": _customer_name(sd, order),
        "product_summary": _product_summary(sd),
        "construction_date": _date_text(fields["construction_date"]),
        "measurement_date": _date_text(fields["measurement_date"]),
        "completion_month": done_month,
        "measurement_month": measured_month,
        "deal_type": deal_type,
        "shipping_price": shipping,
        "install_cost": install_cost,
        "rate_override_bp": override,
        "note": (input_row.note or "") if input_row is not None else "",
        "input_version": int(input_row.version or 1) if input_row is not None else 0,
        "deduction_total": deduction_total,
        "deductions": _sales_deductions(sd, cfg.user_id),
        "rate_bp": rate_bp,
        "commission": commission,
        "state": state,
        "self_edits": self_edits,
        "basis": basis,
    }


def _near_miss_name(match_name: str, fields: dict[str, Any]) -> Optional[str]:
    """맞출 이름과 완전히 같지는 않지만 비슷한(한쪽이 다른 쪽을 품는) 이름 칸 값. 없으면 None."""
    target = match_name.replace(" ", "")
    if not target:
        return None
    for seen in (fields["manager_name"], fields["orderer_name"]):
        seen = normalize_name(seen)
        if not seen or seen == match_name:
            continue
        compact = seen.replace(" ", "")
        if target in compact or (len(compact) >= _NEAR_MISS_MIN_LEN and compact in target):
            return seen
    return None


def _sort_key(row: dict[str, Any]) -> tuple:
    date = row.get("construction_date") or ""
    return (date == "", date, row["order_id"])


def _summary(rows: list[dict[str, Any]], month: str, basis: str) -> dict[str, Any]:
    counts = {state: 0 for state in STATES}
    for row in rows:
        counts[row["state"]] += 1
    total = sum(int(row["commission"] or 0) for row in rows if row["state"] == STATE_DONE)
    return {"month": month, "basis": basis, "total_commission": total, "counts": counts, "row_count": len(rows)}


def commission_rows(db, user_id: int, month: str, basis: str = BASIS_COMPLETION) -> dict[str, Any]:
    """프리랜서 한 명 · 달 하나의 수수료 줄.

    Args:
        db: SQLAlchemy Session.
        user_id: 켜진 프리랜서 사용자 id.
        month: ``YYYY-MM``. 시공 완료 기준이면 "이 달까지"(누적 · 미마감), 실측일 기준이면 "이 달".
        basis: :data:`BASES` 중 하나.

    Returns:
        ``{"freelancer", "rows", "summary", "near_misses"}``.

    Raises:
        ValueError: 달 · 기준 형식이 틀렸거나 켜진 프리랜서가 아니다.
    """
    if not _MONTH_RE.match(str(month or "")):
        raise ValueError("month")
    if basis not in BASES:
        raise ValueError("basis")
    configs = active_freelancers(db)
    cfg = configs.get(int(user_id))
    if cfg is None:
        raise ValueError("freelancer")
    match_map = {c.match_name: uid for uid, c in configs.items() if c.match_name}

    criteria = _scope_filters() + _window_filters(month, basis, cfg.start_month)
    closed = closed_order_ids(db) if basis == BASIS_COMPLETION else set()  # 모든 프리랜서의 마감(J9)
    if closed:
        criteria = criteria + (Order.id.notin_(sorted(closed)),)
    orders = fetch_settlement_rows(db, _ORDER_COLUMNS, criteria, COMMISSION_SD_SPEC)
    naver = _naver_ids(db, criteria) if orders else set()

    owned: list[tuple[Any, dict, dict, str]] = []
    near_misses: list[dict[str, Any]] = []
    for order in orders:
        sd = _ensure_dict(order.structured_data)
        fields = calc.extract_order_fields(sd)
        if not calc.is_eligible(fields["measurement_date"], order.received_date, order.created_at, cfg.start_month):
            continue
        if basis == BASIS_COMPLETION:
            done_month = calc.completion_month(order.erp_stage_code, fields["construction_date"])
            if done_month is None or done_month > month:
                continue
        elif calc.measurement_month(fields["measurement_date"], order.received_date, order.created_at) != month:
            continue
        owner, deal_type = calc.resolve_owner(fields["orderer_name"], fields["manager_name"],
                                              is_naver=int(order.id) in naver, match_map=match_map)
        if owner == cfg.user_id:
            owned.append((order, sd, fields, deal_type))
        elif owner is None and len(near_misses) < NEAR_MISS_LIMIT:
            seen = _near_miss_name(cfg.match_name, fields)
            if seen is not None:
                near_misses.append({"order_id": int(order.id), "customer_name": _customer_name(sd, order),
                                    "name_seen": seen})

    owned_ids = [int(order.id) for order, *_rest in owned]
    inputs = _inputs(db, owned_ids)
    edits = _self_edits(db, owned_ids, cfg.user_id)
    rows = [
        _build_row(order, sd, fields, cfg=cfg, deal_type=deal_type, basis=basis,
                   input_row=inputs.get(int(order.id)), self_edits=edits.get(int(order.id), []))
        for order, sd, fields, deal_type in owned
    ]
    rows.sort(key=_sort_key)
    near_misses.sort(key=lambda item: item["order_id"])
    return {
        "freelancer": {"user_id": cfg.user_id, "match_name": cfg.match_name, "start_month": cfg.start_month,
                       "tax_type": cfg.tax_type},
        "rows": rows,
        "summary": _summary(rows, month, basis),
        "near_misses": near_misses,
    }


def commission_row_for_order(db, order_id: int) -> Optional[dict[str, Any]]:
    """주문 한 건의 수수료 줄(시공비 저장 뒤 다시 그릴 때). 주인이 켜진 프리랜서가 아니거나 대상이 아니면 None.

    주인은 설정의 맞출 이름으로 정한다(§3.1). 기준은 시공 완료 — 아직 완료 전이면 ``FORECAST`` 줄이다.
    """
    configs = active_freelancers(db)
    if not configs:
        return None
    match_map = {c.match_name: uid for uid, c in configs.items() if c.match_name}
    criteria = _scope_filters() + (Order.id == int(order_id),)
    found = fetch_settlement_rows(db, _ORDER_COLUMNS, criteria, COMMISSION_SD_SPEC)
    if not found:
        return None
    order = found[0]
    sd = _ensure_dict(order.structured_data)
    fields = calc.extract_order_fields(sd)
    owner, deal_type = calc.resolve_owner(fields["orderer_name"], fields["manager_name"],
                                          is_naver=bool(_naver_ids(db, criteria)), match_map=match_map)
    cfg = configs.get(owner) if owner is not None else None
    if cfg is None or not calc.is_eligible(fields["measurement_date"], order.received_date, order.created_at,
                                           cfg.start_month):
        return None
    input_row = _inputs(db, [int(order.id)]).get(int(order.id))
    edits = _self_edits(db, [int(order.id)], cfg.user_id).get(int(order.id), [])
    return _build_row(order, sd, fields, cfg=cfg, deal_type=deal_type, basis=BASIS_COMPLETION,
                      input_row=input_row, self_edits=edits)
