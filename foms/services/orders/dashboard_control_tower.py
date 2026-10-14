"""모바일 홈 '오퍼레이션 컨트롤 타워' 페이로드 빌더.

설계 의도: 단계별 개수(인벤토리/funnel)가 아니라 사용자가 매일 아침 던지는
실제 질문에 답하는 read-model을 만든다.
  ① 이번 달·그날 나갈 현장(실측·시공·AS)과 시공 출고가는? 할 일이 남았나? (calendar / field-ops)
  ② 약속일 펑크날 위험(시퀀스 위반)은? (risk_groups)
  ③ 내 담당 진행중 / 신규 유입은? (mine_open_count / inbound_count)

모든 신호는 기존 데이터 계약을 재사용한다:
  Order.erp_measurement_date / erp_construction_date (약속일, 인덱스 컬럼)
  Order.erp_stage_code (현재 단계)  · erp_stage_updated_at (도면 48h 정체)
  OrderAttachment / structured_data.pricing.balance (잔금)  · _erp_alerts D-day 규칙
반환값은 전부 JSON 직렬화 가능한 primitive (dashboard micro-cache 호환).
"""

from __future__ import annotations

import datetime
from typing import Any

from sqlalchemy import and_, distinct, false, func, or_

from models import Order, OrderScheduleDate
from foms.services.orders.erp_policy_constants import STAGE_LABELS, STAGE_NAME_TO_CODE
from foms.services.erp_display import (
    _ensure_dict,
    _erp_get_stage,
    erp_payment_amount_from_structured,
    erp_shipping_price_from_structured,
    get_today_kst,
    manager_display_name,
)
from foms.services.datetime_kst import now_utc_naive
from foms.services.common.business_calendar import business_days_until, get_holidays_kr
from foms.services.erp_permissions import build_mine_sql_filter, mine_membership_clause
from foms.services.measurement_time import measurement_glance_time_key
from foms.services.orders.calendar_amount_colors import DEFAULT_COLORS, load_colors, tone_for
from foms.services.orders.calendar_month_photos import month_photo
from foms.services.integrations.kma.seoul_daily_weather import load_days as load_weather_days
from foms.services.shipment_dashboard_helpers import AS_SHIPMENT_STATUSES

__all__ = [
    "build_mobile_control_tower",
    "build_field_ops_for_day",
    "build_month_calendar",
    "build_risk_order_ids",
    "build_risk_frame",
    "risk_row_cta_meta",
    "RISK_KEYS",
]

DOW_KR = ["월", "화", "수", "목", "금", "토", "일"]
# 시공 단계 이후(=출고/설치 완료로 간주)면 '시공 준비'가 끝난 것으로 본다.
_INSTALL_READY_CODES = ("CONSTRUCTION", "COMPLETED", "AS", "AS_RECEIVED", "AS_COMPLETED")
_DONE_CODES = ("COMPLETED", "AS_COMPLETED")
# 'AS 출고' = AS 상태 주문의 as_visit 일정. 출고 대시보드(foms.web.shipment.dashboard)와
# 동일 술어(status ∈ AS_* + OrderScheduleDate.kind=='as_visit')를 써서 두 화면 카운트를 정합시킨다.

# 복수 일정 SSOT: 실측/시공일은 콤마 복수(예: '2026-07-24, 2026-08-12')일 수 있는데
# erp_measurement_date/erp_construction_date 싱크 컬럼은 첫 날짜만 담는다.
# 날짜 술어는 전 날짜를 행으로 펼친 order_schedule_dates EXISTS/조인이 정본 —
# 실측 대시보드 패널과 날짜별 카운트가 정합된다(운영 8/6 25vs23 불일치 근본 수정).


def _sched_any(kind: str, dates: list[str]):
    """order_schedule_dates(kind)가 dates 중 하나에 걸리는 주문 EXISTS 술어.

    Args:
        kind: 일정 종류('measurement'|'construction' 등).
        dates: 'YYYY-MM-DD' 문자열 목록.

    Returns:
        SQLAlchemy EXISTS 술어(복수 일정 주문도 각 날짜에 모두 걸린다).
    """
    return Order.schedule_dates.any(
        and_(OrderScheduleDate.kind == kind, OrderScheduleDate.date.in_(list(dates)))
    )


# 자가실측 4체크 완료 = 실측 집계 제외/시공 집계 포함
# (erp_display.self_measurement_four_checks_done의 SQL판 — 실측 대시보드 패널과 동일 제외).
_SELF_MEASURE_DONE_SQL = and_(
    Order.is_self_measurement.is_(True),
    Order.measurement_completed.is_(True),
    Order.regional_sales_order_upload.is_(True),
    Order.regional_blueprint_sent.is_(True),
    Order.regional_order_upload.is_(True),
)


def _measure_on(dates: list[str]):
    """실측일 술어: 복수 일정 포함 + 자가실측 4체크 완료 주문 제외.

    Args:
        dates: 'YYYY-MM-DD' 문자열 목록.

    Returns:
        SQLAlchemy 술어(실측 대시보드 패널 카운트와 동일 모집단).
    """
    return and_(_sched_any('measurement', dates), ~_SELF_MEASURE_DONE_SQL)


# ───────── 작은 순수 헬퍼 ─────────

def _to_int(value: Any) -> int | None:
    """'1,410,000원' 같은 문자열/숫자를 int로. 실패 시 None."""
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    try:
        return int(float(str(value).replace(",", "").replace("원", "").strip()))
    except (TypeError, ValueError):
        return None


def _balance_remaining(sd: dict) -> int | None:
    """잔금(원). pricing/totals.balance 우선, 없으면 품목합-계약금."""
    pricing = sd.get("pricing") if isinstance(sd.get("pricing"), dict) else {}
    totals = sd.get("totals") if isinstance(sd.get("totals"), dict) else {}
    for raw in (totals.get("final_amount"), totals.get("balance_amount"), pricing.get("balance"), totals.get("balance"), sd.get("balance")):
        n = _to_int(raw)
        if n is not None:
            return n
    items_total = erp_payment_amount_from_structured(sd)
    deposit = _to_int(totals.get("deposit_amount") or totals.get("deposit") or pricing.get("deposit"))
    if items_total is not None and deposit is not None:
        from foms.services.estimate_service import _extract_discount_amount, _extract_free_input_amount

        free_input = _extract_free_input_amount(sd)
        discount = _extract_discount_amount(sd)
        return max(0, items_total + free_input - deposit - discount)
    return None


def _measure_assigned(order: Any, sd: dict) -> bool:
    """실측 담당이 배정됐는지 (영업 배정 user_ids 또는 담당자명)."""
    assignments = sd.get("assignments") or {}
    if assignments.get("sales_assignee_user_ids"):
        return True
    manager = manager_display_name(sd.get("parties")) or getattr(order, "manager_name", None)
    return bool(str(manager or "").strip())


def _stage_code_of(order: Any, sd: dict) -> str:
    code = getattr(order, "erp_stage_code", None)
    if code:
        return str(code)
    stage = _erp_get_stage(order, sd)
    return STAGE_NAME_TO_CODE.get(stage, stage or "")


def _cust_name(order: Any, sd: dict) -> str:
    return ((sd.get("parties") or {}).get("customer") or {}).get("name") or f"#{order.id}"


def _measure_readiness(order: Any, sd: dict) -> tuple[str, str]:
    """실측 칩: 담당이 없을 때만 '담당 미배정'. 배정됐으면 칩 없음(빈 라벨) — 전 행 '준비완료'는 정보가 없다."""
    if _measure_assigned(order, sd):
        return ("ok", "")
    return ("warn", "담당 미배정")


def _construction_readiness(order: Any, sd: dict, *, day_offset: int = 0) -> tuple[str, str]:
    """시공 칩 — 할 일이 있을 때만 붙인다.

    Args:
        order: Order.
        sd: structured_data.
        day_offset: 시공일 − 오늘(일). 지난 날(<0)은 칩 없음. 출고 전 단계(설치 단계 미도달)는
            오늘·내일(0·1)만 '출고 전'(위험) — 먼 날짜의 출고 전은 정상 진행이다.

    Returns:
        (상태, 라벨). 출고된 주문에 잔금이 남았으면 ('warn', '잔금 48만'). 할 일 없으면 ('ok', '').
    """
    if day_offset < 0:
        return ("ok", "")
    if _stage_code_of(order, sd) not in _INSTALL_READY_CODES:
        return ("risk", "출고 전") if day_offset <= 1 else ("ok", "")
    balance = _balance_remaining(sd) or 0
    if balance > 0:
        return ("warn", f"잔금 {_man_label(balance)}")
    return ("ok", "")


def _business_window_dates(today: datetime.date, *, max_business_days: int, window_days: int) -> list[str]:
    """오늘부터 window_days 안에서 영업일 기준 D-max 이하인 날짜 iso 목록.

    규칙 출처(SSOT)는 business_days_until(=대시보드 alert 엔진). foms.web.orders.dashboard의
    _business_alert_date_values와 동일 규칙을 의도적으로 따른다(타워/큐 카운트 정합).
    """
    out: list[str] = []
    for offset in range(window_days + 1):
        day = today + datetime.timedelta(days=offset)
        bd = business_days_until(day.isoformat(), today=today)
        if bd is not None and 0 <= bd <= max_business_days:
            out.append(day.isoformat())
    return out


# ───────── 섹션 빌더 ─────────

def _tower_base_query(db: Any, current_user: Any):
    """대시보드와 동일: 최근 60일 활성 ERP 주문. 시공팀은 본인 담당만."""
    q = db.query(Order).filter(Order.dashboard_active_filter(days=60), Order.is_erp_order.is_(True))
    if current_user and (getattr(current_user, "team", None) or "") == "CONSTRUCTION":
        conds = build_mine_sql_filter(current_user)
        if conds:
            q = q.filter(mine_membership_clause(conds, scope_conds=[q.whereclause]))
    return q


def _day_counts(base: Any, date_strs: list[str]) -> tuple[dict, dict, dict]:
    """날짜별 (실측, 시공, AS 방문) 주문 수. 복수 일정 주문은 각 날짜에 모두 잡힌다.

    order_schedule_dates 조인 집계 — 실측 대시보드 패널·출고 대시보드와 같은 모집단.

    Args:
        base: 타워 base 쿼리.
        date_strs: 'YYYY-MM-DD' 목록.

    Returns:
        ({날짜: 실측 수}, {날짜: 시공 수}, {날짜: AS 수}).
    """
    if not date_strs:
        return {}, {}, {}

    def _count_by(*conds):
        return dict(
            base.join(OrderScheduleDate, OrderScheduleDate.order_id == Order.id)
            .filter(OrderScheduleDate.date.in_(date_strs), *conds)
            .with_entities(OrderScheduleDate.date, func.count(distinct(Order.id)))
            .group_by(OrderScheduleDate.date)
            .all()
        )

    meas_by = _count_by(OrderScheduleDate.kind == 'measurement', ~_SELF_MEASURE_DONE_SQL)
    cons_by = _count_by(OrderScheduleDate.kind == 'construction')
    as_by = _count_by(Order.status.in_(AS_SHIPMENT_STATUSES), OrderScheduleDate.kind == "as_visit")
    return meas_by, cons_by, as_by


def _unshipped_construction_by(base: Any, date_strs: list[str]) -> dict:
    """날짜별 '출고 전' 시공 수 — 시공 일정은 있는데 단계가 시공 준비 완료 전인 주문."""
    if not date_strs:
        return {}
    return dict(
        base.join(OrderScheduleDate, OrderScheduleDate.order_id == Order.id)
        .filter(
            OrderScheduleDate.kind == 'construction',
            OrderScheduleDate.date.in_(date_strs),
            or_(Order.erp_stage_code.is_(None), Order.erp_stage_code.notin_(_INSTALL_READY_CODES)),
        )
        .with_entities(OrderScheduleDate.date, func.count(distinct(Order.id)))
        .group_by(OrderScheduleDate.date)
        .all()
    )


def _construction_amounts(base: Any, date_strs: list[str]) -> tuple[dict[str, int], int]:
    """날짜별 시공 출고가 합과 기간 합계(주문당 한 번).

    출고가는 정산 '예상 매출'·모바일 상세와 같은 식(`erp_shipping_price_from_structured`).
    산출 불가(None) 주문은 금액에서만 빠진다. 복수 시공일 주문은 날짜 칸마다 들어가지만
    기간 합계에는 한 번만 들어간다.

    Returns:
        ({날짜: 원}, 기간 합계 원).
    """
    if not date_strs:
        return {}, 0
    rows = (
        base.join(OrderScheduleDate, OrderScheduleDate.order_id == Order.id)
        .filter(OrderScheduleDate.kind == 'construction', OrderScheduleDate.date.in_(date_strs))
        .with_entities(OrderScheduleDate.date, Order.id, Order.structured_data)
        .all()
    )
    price_of: dict[int, int] = {}
    by_date: dict[str, int] = {}
    seen: set[tuple[str, int]] = set()
    for date_str, order_id, sd in rows:
        key = (str(date_str), int(order_id))
        if key in seen:
            continue
        seen.add(key)
        if key[1] not in price_of:
            price_of[key[1]] = erp_shipping_price_from_structured(_ensure_dict(sd)) or 0
        by_date[key[0]] = by_date.get(key[0], 0) + price_of[key[1]]
    return by_date, sum(price_of.values())


def _man_label(won: int | None) -> str:
    """원 → '3,470만' / '1억 2,300만'(만 원 반올림). 0·None 은 빈 문자열."""
    if not won or won <= 0:
        return ""
    man = int(round(won / 10000))
    if man <= 0:
        return f"{won:,}원"
    eok, rest = divmod(man, 10000)
    if not eok:
        return f"{man:,}만"
    return f"{eok}억 {rest:,}만" if rest else f"{eok}억"


def _pill_label(won: int | None) -> str:
    """달력 칸 출고가 알약용 짧은 글 — 1억 이상은 '1.23억'(폭 40px 폰 칸에서 '1억 2,300만' 이 넘친다)."""
    if won and won >= 100_000_000:
        return f"{won / 100_000_000:.2f}".rstrip("0").rstrip(".") + "억"
    return _man_label(won)


_CAL_DOW = ["일", "월", "화", "수", "목", "금", "토"]
# 달 이동 범위(오늘 기준 앞뒤 개월). 모집단이 '완료 60일 이내'라 먼 과거는 숫자가 줄어든다.
_CAL_MONTH_SPAN = 12


def _month_gap(a: datetime.date, b: datetime.date) -> int:
    return (a.year - b.year) * 12 + (a.month - b.month)


def _shift_month(first: datetime.date, delta: int) -> datetime.date:
    index = first.year * 12 + (first.month - 1) + delta
    return datetime.date(index // 12, index % 12 + 1, 1)


def _month_first(month: str | None, today: datetime.date) -> datetime.date:
    """'YYYY-MM' → 그 달 1일. 형식 오류·오늘 기준 ±12개월 밖이면 이번 달."""
    this_month = today.replace(day=1)
    try:
        year, mon = (int(part) for part in str(month or "").split("-"))
        first = datetime.date(year, mon, 1)
    except (TypeError, ValueError):
        return this_month
    return first if abs(_month_gap(first, this_month)) <= _CAL_MONTH_SPAN else this_month


def _month_calendar(
    base: Any, today: datetime.date, first: datetime.date, colors: dict[str, Any] | None = None,
    weather: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """월간 현장 달력: 일요일 시작 주 격자 + 날짜별 실측/시공/AS 수·시공 출고가 합.

    빨간 점(출고 전 시공)은 오늘·내일 칸에만 — 먼 날짜의 출고 전은 정상 상태다.
    colors: 시공 금액별 기준(`calendar_amount_colors`) — 출고가 알약 색. None 이면 기본값.
    weather: `seoul_daily_weather.load_days` 결과. 칸마다 날씨 종류(wx)·최고기온·움직임 여부(wx_live).
      자료 없는 날은 wx="" (띠는 회백색). 움직임은 오늘~6일 뒤 7칸만(휴대폰 성능, 설계서 §2.4).
    """
    wx_days = (weather or {}).get("days") or {}
    live_last = today + datetime.timedelta(days=WEATHER_LIVE_DAYS - 1)
    colors = colors if colors is not None else dict(DEFAULT_COLORS)
    next_first = _shift_month(first, 1)
    last = next_first - datetime.timedelta(days=1)
    grid_start = first - datetime.timedelta(days=(first.weekday() + 1) % 7)
    grid_end = last + datetime.timedelta(days=(5 - last.weekday()) % 7)
    month_dates = [(first + datetime.timedelta(days=i)).isoformat() for i in range(last.day)]
    soon_dates = [
        d.isoformat() for d in (today, today + datetime.timedelta(days=1)) if first <= d <= last
    ]

    meas_by, cons_by, as_by = _day_counts(base, month_dates)
    unshipped_by = _unshipped_construction_by(base, soon_dates)
    amount_by, month_amount = _construction_amounts(base, month_dates)
    holidays = get_holidays_kr(first.year)

    weeks: list[list[dict[str, Any]]] = []
    day = grid_start
    while day <= grid_end:
        week: list[dict[str, Any]] = []
        for col in range(7):
            iso = day.isoformat()
            in_month = first <= day <= last
            measure = int(meas_by.get(iso, 0) or 0) if in_month else 0
            construction = int(cons_by.get(iso, 0) or 0) if in_month else 0
            as_count = int(as_by.get(iso, 0) or 0) if in_month else 0
            unshipped = int(unshipped_by.get(iso, 0) or 0) if in_month else 0
            amount_won = int(amount_by.get(iso, 0) or 0) if in_month else 0
            amount_label = _man_label(amount_won)
            aria = f"{day.month}월 {day.day}일 {_CAL_DOW[col]}요일, 실측 {measure}건, 시공 {construction}건, AS {as_count}건"
            if amount_label:
                aria += f", 출고가 {amount_label}원"
            if unshipped:
                aria += f", 출고 전 시공 {unshipped}건"
            wx_day = wx_days.get(iso) if in_month else None
            wx = str(wx_day.get("kind") or "") if isinstance(wx_day, dict) else ""
            t_max = wx_day.get("t_max") if isinstance(wx_day, dict) else None
            t_min = wx_day.get("t_min") if isinstance(wx_day, dict) else None
            if wx:
                aria += f", 날씨 {WEATHER_LABELS.get(wx, '')}"
                if t_min is not None:
                    aria += f" 최저 {t_min}도"
                if t_max is not None:
                    aria += f" 최고 {t_max}도"
            week.append({
                "iso": iso,
                "day": day.day,
                "dow": col,
                "in_month": in_month,
                "is_today": day == today,
                "is_past": day < today,
                "is_holiday": iso in holidays,
                "measure": measure,
                "construction": construction,
                "as_count": as_count,
                "amount_label": amount_label,
                "amount_pill": _pill_label(amount_won),
                "tone": tone_for(amount_won, colors),
                "wx": wx,
                "t_max_label": f"{t_max}°" if wx and t_max is not None else "",
                "t_min_label": f"{t_min}°" if wx and t_min is not None else "",
                "wx_live": bool(wx) and today <= day <= live_last,
                "unshipped": unshipped,
                "aria": aria,
            })
            day += datetime.timedelta(days=1)
        _link_weather_neighbours(week)
        weeks.append(week)

    month_cells = [c for week in weeks for c in week if c["in_month"] and c["wx"]]
    this_month = today.replace(day=1)
    prev_first = _shift_month(first, -1)
    return {
        "month": first.strftime("%Y-%m"),
        "label": f"{first.year}년 {first.month}월",
        "is_this_month": first == this_month,
        "prev": prev_first.strftime("%Y-%m") if abs(_month_gap(prev_first, this_month)) <= _CAL_MONTH_SPAN else None,
        "next": next_first.strftime("%Y-%m") if abs(_month_gap(next_first, this_month)) <= _CAL_MONTH_SPAN else None,
        "weeks": weeks,
        "measure_total": sum(int(v or 0) for v in meas_by.values()),
        "construction_total": sum(int(v or 0) for v in cons_by.values()),
        "as_total": sum(int(v or 0) for v in as_by.values()),
        "amount_label": _man_label(month_amount) or "0원",
        "colors": colors,
        "photo": month_photo(first.month),
        # 그림 정의는 이 달에 쓰는 날씨만 싣는다(대시보드 전송 바이트 예산, perf-gate 2026-10-14).
        "wx_used": sorted({c["wx"] for c in month_cells}),
        "wx_still": sorted({c["wx"] for c in month_cells if not c["wx_live"]}),
        "yellow_label": _man_label((colors.get("yellow_from") or 0) * 10000),
        "pink_label": _man_label((colors.get("pink_from") or 0) * 10000),
    }


WEATHER_LIVE_DAYS = 7
WEATHER_LABELS = {"sun": "맑음", "cloud": "구름", "drizzle": "부슬비", "heavy": "장대비", "snow": "눈"}


def _link_weather_neighbours(week: list[dict[str, Any]]) -> None:
    """같은 주 띠 안에서 옆 날짜 날씨(wx_prev·wx_next)를 붙인다 — 칸 경계 색을 이음새 없이 섞는 데 쓴다.

    띠 끝(이 달 밖 칸과 닿는 쪽)은 제 날씨를 쓴다. 날씨 없는 날은 "none".
    """
    for i, cell in enumerate(week):
        if not cell["in_month"]:
            continue
        own = cell["wx"] or "none"
        left = week[i - 1] if i > 0 and week[i - 1]["in_month"] else None
        right = week[i + 1] if i < 6 and week[i + 1]["in_month"] else None
        cell["wx_prev"] = (left["wx"] or "none") if left else own
        cell["wx_next"] = (right["wx"] or "none") if right else own
        cell["band_start"] = left is None
        cell["band_end"] = right is None


def _weather_window(db: Any, first: datetime.date) -> dict[str, Any]:
    """달력 격자(앞뒤 한 주 여유)에 해당하는 날씨를 읽는다."""
    return load_weather_days(db, first - datetime.timedelta(days=7), _shift_month(first, 1) + datetime.timedelta(days=7))


def _as_visit_order_ids_for_date(base: Any, date_iso: str) -> list[int]:
    rows = (
        base.join(OrderScheduleDate, OrderScheduleDate.order_id == Order.id)
        .filter(
            Order.status.in_(AS_SHIPMENT_STATUSES),
            OrderScheduleDate.kind == "as_visit",
            OrderScheduleDate.date == date_iso,
        )
        .with_entities(distinct(Order.id))
        .all()
    )
    return [int(r[0]) for r in rows]


def _field_ops_for_date(
    base: Any,
    date_iso: str,
    *,
    field_type: str = "all",
    limit: int = 100,
    today: datetime.date | None = None,
) -> list[dict[str, Any]]:
    """특정 날짜의 실측/시공/AS 약속 + 준비도 신호등 (시공 우선, 시간순).

    field_type: 'measure'(실측만) | 'construction'(시공만) | 'as'(AS만) | 'all'(전부).
    limit는 한 날짜에 실무상 도달 불가능한 상한(=그날 전체 로딩 보장).
    """
    as_ids: list[int] = []
    if field_type == "measure":
        date_filter = _measure_on([date_iso])
    elif field_type == "construction":
        date_filter = _sched_any('construction', [date_iso])
    elif field_type == "as":
        as_ids = _as_visit_order_ids_for_date(base, date_iso)
        date_filter = Order.id.in_(as_ids)
    else:
        as_ids = _as_visit_order_ids_for_date(base, date_iso)
        date_filter = or_(
            _measure_on([date_iso]),
            _sched_any('construction', [date_iso]),
            Order.id.in_(as_ids) if as_ids else false(),
        )
    rows = (
        base.filter(date_filter)
        .order_by(Order.erp_construction_date.desc().nullslast(), Order.created_at.desc())
        .limit(limit)
        .all()
    )
    # 'all' 행 분류용 시공 id 집합 — 복수 시공일도 당일 여부를 정확 판정(컬럼 첫 날짜 비교 금지).
    cons_id_set: set[int] = set()
    if field_type == "all":
        cons_id_set = {
            int(r[0])
            for r in base.filter(_sched_any('construction', [date_iso])).with_entities(Order.id).all()
        }
    as_id_set = set(as_ids)
    try:
        day_offset = (datetime.date.fromisoformat(date_iso) - (today or get_today_kst())).days
    except ValueError:
        day_offset = 0
    out: list[dict[str, Any]] = []
    for order in rows:
        sd = _ensure_dict(getattr(order, "structured_data", None))
        order_id = int(getattr(order, "id", 0) or 0)
        is_as_visit = order_id in as_id_set
        is_as_only_visit = (
            field_type == "as"
            or (
                field_type == "all"
                and is_as_visit
                and order_id not in cons_id_set
            )
        )
        if field_type == "measure":
            is_cons = False
        elif field_type == "construction":
            is_cons = True
        elif field_type == "as":
            is_cons = True
        elif is_as_only_visit:
            is_cons = True
        else:
            is_cons = order_id in cons_id_set
        schedule_key = "as_visit" if is_as_only_visit else ("construction" if is_cons else "measurement")
        sched = (sd.get("schedule") or {}).get(schedule_key) or {}
        if is_as_only_visit:
            state, label = ("ok", "")
        elif is_cons:
            state, label = _construction_readiness(order, sd, day_offset=day_offset)
        else:
            state, label = _measure_readiness(order, sd)
        parties = sd.get("parties") or {}
        site = sd.get("site") or {}
        time_text = str(sched.get("time") or "").strip() or None
        amount = erp_shipping_price_from_structured(sd) if (is_cons and not is_as_only_visit) else None
        out.append({
            "id": order.id,
            "name": (parties.get("customer") or {}).get("name") or "-",
            "type": "AS" if is_as_only_visit else ("시공" if is_cons else "실측"),
            "type_code": "as" if is_as_only_visit else ("construction" if is_cons else "measure"),
            "time": time_text,
            "time_group": _time_group(time_text),
            "addr": site.get("address_full") or site.get("address_main") or "-",
            "manager": manager_display_name(parties) or getattr(order, "manager_name", None) or "-",
            "phone": str((parties.get("customer") or {}).get("phone") or "").strip(),
            "items_label": "" if (not is_cons and not is_as_only_visit) else _items_label(sd),
            "amount": amount,
            "amount_label": _man_label(amount),
            "readiness_state": state,
            "readiness_label": label,
        })
    out.sort(key=_field_ops_sort_key)
    return out


_FIELD_TYPE_ORDER = {"construction": 0, "measure": 1, "as": 2}
_FIELD_TYPE_TITLE = {"construction": "시공", "measure": "실측", "as": "AS"}


def _field_ops_sort_key(row: dict[str, Any]) -> tuple[int, tuple[int, int, int]]:
    """현장 목록 정렬: 시공 → 실측 → AS, 그 안에서 방문 시각 이른 순(시각 미정은 맨 뒤).

    시각은 자유 텍스트("오전", "2~3시 이후", None)라 문자열 비교를 하면 "99:99"(미정)가
    "오전"·"오후"보다 앞서고 "3~4시"가 "18:00" 뒤로 간다. 실측 체크리스트와 같은 키를 쓴다.
    """
    return (_FIELD_TYPE_ORDER.get(row["type_code"], 3), measurement_glance_time_key(row["time"]))


def _time_group(time_text: str | None) -> str:
    """방문 시각 원문 → 묶음 머리('오전'|'오후'|'종일'|'시간 미정'). 정렬 키와 같은 판정."""
    bucket, minutes, _ = measurement_glance_time_key(time_text)
    if bucket == 0:
        return "오전" if minutes < 12 * 60 else "오후"
    return {1: "오후", 2: "종일"}.get(bucket, "시간 미정")


def _items_label(sd: dict) -> str:
    """품목 요약: 첫 품목명 + ' 외 N'. 품목명이 없으면 빈 문자열."""
    names = [
        str(item.get("product_name") or "").strip()
        for item in (sd.get("items") or [])
        if isinstance(item, dict)
    ]
    names = [name for name in names if name]
    if not names:
        return ""
    return names[0] if len(names) == 1 else f"{names[0]} 외 {len(names) - 1}"


def _field_sections(rows: list[dict[str, Any]], day_offset: int) -> list[dict[str, Any]]:
    """정렬된 행 → 종류 묶음(시공·실측·AS) × 시간 묶음. 시공 묶음은 출고가 합·출고 전 띠를 싣는다."""
    sections: list[dict[str, Any]] = []
    for row in rows:
        if not sections or sections[-1]["type_code"] != row["type_code"]:
            sections.append({
                "type_code": row["type_code"],
                "title": _FIELD_TYPE_TITLE.get(row["type_code"], row["type"]),
                "count": 0,
                "amount": 0,
                "unshipped": 0,
                "groups": [],
            })
        section = sections[-1]
        section["count"] += 1
        section["amount"] += int(row.get("amount") or 0)
        if row["readiness_label"] == "출고 전":
            section["unshipped"] += 1
        if not section["groups"] or section["groups"][-1]["label"] != row["time_group"]:
            section["groups"].append({"label": row["time_group"], "rows": []})
        section["groups"][-1]["rows"].append(row)
    for section in sections:
        section["amount_label"] = _man_label(section.pop("amount"))
        section["unshipped_when"] = "오늘" if day_offset == 0 else ("내일" if day_offset == 1 else "")
    return sections


def _type_counts_for_date(base: Any, date_iso: str) -> tuple[int, int, int]:
    """(실측 건수, 시공 건수, AS 방문 건수) — 표시 limit과 무관한 정확 카운트(복수 일정 포함)."""
    measure = int(base.filter(_measure_on([date_iso])).count() or 0)
    construction = int(base.filter(_sched_any('construction', [date_iso])).count() or 0)
    as_count = len(_as_visit_order_ids_for_date(base, date_iso))
    return measure, construction, as_count


def _day_label(date_iso: str, today: datetime.date) -> str:
    """그날 목록 시트 제목 'M월 D일 (요일)'. 오늘 여부는 호출부가 is_today 배지로 따로 싣는다."""
    try:
        d = datetime.date.fromisoformat(date_iso)
    except (TypeError, ValueError):
        return "현장 일정"
    return f"{d.month}월 {d.day}일 ({DOW_KR[d.weekday()]})"


def _risk_group(key: str, icon: str, tone: str, title: str, why: str, count: int, filter_args: dict) -> dict[str, Any]:
    return {"key": key, "icon": icon, "tone": tone, "title": title, "why": why, "count": count, "filter": filter_args}


def _samples_names(orders: list, *, fallback: str) -> str:
    names = [_cust_name(o, _ensure_dict(getattr(o, "structured_data", None))) for o in orders]
    return " / ".join(names) if names else fallback


def _samples_construction(orders: list, today: datetime.date) -> str:
    parts = []
    for order in orders:
        sd = _ensure_dict(getattr(order, "structured_data", None))
        cons = getattr(order, "erp_construction_date", None)
        bd = business_days_until(cons, today=today) if cons else None
        dtxt = f"D-{bd}" if bd is not None else ""
        stage_label = STAGE_LABELS.get(_stage_code_of(order, sd), "")
        parts.append(" · ".join(p for p in (f"{_cust_name(order, sd)} {dtxt}".strip(), stage_label) if p))
    return " / ".join(parts)


def _samples_balance(orders: list) -> str:
    parts = []
    for order in orders:
        sd = _ensure_dict(getattr(order, "structured_data", None))
        parts.append(f"{_cust_name(order, sd)} 잔금 {(_balance_remaining(sd) or 0):,}원")
    return " / ".join(parts)


# 위험 후보 스캔 캡. JSONB(담당/잔금)은 SQL count가 어려워 후보를 메모리에서 거른다.
# 12일 윈도우에서 200건 초과는 실무상 비현실적이므로 정확 카운트를 보장하는 상한.
_RISK_CAND_LIMIT = 200


# ── 위험 모집단 id 집합 (SSOT) ──
# 카드 카운트·착지 칩·착지 리스트가 공유하는 단일 술어. build_risk_order_ids가 동일 함수를 재사용해
# '카드=칩=리스트' 3숫자 일치를 구조적으로 보장한다(연구 §8.1).

def _ids_construction_unready(base: Any, cons_dates: list[str]) -> list[int]:
    """시공 임박(D-3)인데 설치단계 미도달인 order id (순수 SQL, 복수 시공일 포함)."""
    rows = base.filter(
        _sched_any('construction', cons_dates),
        or_(Order.erp_stage_code.is_(None), Order.erp_stage_code.notin_(_INSTALL_READY_CODES)),
    ).with_entities(Order.id).all()
    return [int(r[0]) for r in rows]


def _ids_drawing_stalled(base: Any) -> list[int]:
    """도면/컨펌 48h+ 정체 order id (순수 SQL)."""
    cutoff = now_utc_naive() - datetime.timedelta(hours=48)
    rows = base.filter(
        Order.erp_stage_code.in_(["DRAWING", "CONFIRM"]),
        Order.erp_stage_updated_at.isnot(None),
        Order.erp_stage_updated_at <= cutoff,
    ).with_entities(Order.id).all()
    return [int(r[0]) for r in rows]


def _ids_measure_unassigned(base: Any, meas_dates: list[str]) -> list[int]:
    """실측 임박(D-4)인데 담당 미배정 order id (JSONB는 후보 200캡 메모리 필터, 복수 실측일 포함)."""
    cand = base.filter(_measure_on(meas_dates)).limit(_RISK_CAND_LIMIT).all()
    return [o.id for o in cand if not _measure_assigned(o, _ensure_dict(getattr(o, "structured_data", None)))]


def _ids_balance_due(base: Any, cons_dates: list[str]) -> list[int]:
    """잔금 미수 + 시공 임박 order id (JSONB는 후보 200캡 메모리 필터, 복수 시공일 포함)."""
    cand = base.filter(_sched_any('construction', cons_dates)).limit(_RISK_CAND_LIMIT).all()
    return [o.id for o in cand if (_balance_remaining(_ensure_dict(getattr(o, "structured_data", None))) or 0) > 0]


def _risk_construction_unready(base: Any, today: datetime.date, cons_dates: list[str]) -> dict[str, Any] | None:
    """시공 임박(D-3)인데 설치단계 미도달. 착지→risk=construction_unready(정확 동일 집합)."""
    ids = _ids_construction_unready(base, cons_dates)
    if not ids:
        return None
    samples = base.filter(Order.id.in_(ids)).order_by(Order.erp_construction_date.asc()).limit(2).all()
    why = _samples_construction(samples, today)
    return _risk_group("construction_unready", "🔨", "red", "시공 임박인데 미준비", why, len(ids), {"risk": "construction_unready"})


def _risk_drawing_stalled(base: Any) -> dict[str, Any] | None:
    """도면/컨펌 48h+ 정체. 착지→risk=drawing_stalled."""
    ids = _ids_drawing_stalled(base)
    if not ids:
        return None
    samples = base.filter(Order.id.in_(ids)).order_by(Order.erp_stage_updated_at.asc()).limit(2).all()
    why = _samples_names(samples, fallback="컨펌 지연")
    return _risk_group("drawing_stalled", "⏳", "amber", "도면 컨펌 48h+ 정체", why, len(ids), {"risk": "drawing_stalled"})


def _risk_measure_unassigned(base: Any, meas_dates: list[str]) -> dict[str, Any] | None:
    """실측 임박(D-4)인데 담당 미배정. 착지→risk=measure_unassigned(미배정만)."""
    ids = _ids_measure_unassigned(base, meas_dates)
    if not ids:
        return None
    samples = base.filter(Order.id.in_(ids[:2])).all()
    return _risk_group("measure_unassigned", "📐", "amber", "실측 예정 · 담당 미배정",
                       _samples_names(samples, fallback="담당 미배정"), len(ids), {"risk": "measure_unassigned"})


def _risk_balance_due(base: Any, cons_dates: list[str]) -> dict[str, Any] | None:
    """잔금 미수인데 시공 임박. 착지→risk=balance_due(잔금건만)."""
    ids = _ids_balance_due(base, cons_dates)
    if not ids:
        return None
    samples = base.filter(Order.id.in_(ids[:2])).all()
    return _risk_group("balance_due", "💰", "red", "잔금 미수 · 시공 임박",
                       _samples_balance(samples), len(ids), {"risk": "balance_due"})


def _risk_radar(base: Any, today: datetime.date) -> list[dict[str, Any]]:
    """돈/신뢰를 잃는 시퀀스 위반 예외만. 건수 0 그룹 제외. 각 탭→큐는 카운트 집합의 상위집합/정확."""
    cons_dates = _business_window_dates(today, max_business_days=3, window_days=10)
    meas_dates = _business_window_dates(today, max_business_days=4, window_days=12)
    candidates = [
        _risk_construction_unready(base, today, cons_dates),
        _risk_drawing_stalled(base),
        _risk_measure_unassigned(base, meas_dates),
        _risk_balance_due(base, cons_dates),
    ]
    return [g for g in candidates if g]


# ── 위험 착지(드릴다운) SSOT/프레임 ──
RISK_KEYS = ("construction_unready", "drawing_stalled", "measure_unassigned", "balance_due")

# 착지 상단 risk_frame 표시 메타(SSOT). 카드 제목/아이콘과 일치.
RISK_META: dict[str, dict[str, str]] = {
    "construction_unready": {"icon": "🔨", "tone": "red", "title": "시공 임박인데 미준비",
                             "defect": "시공 단계 미도달 — 출고 확인 필요", "cta": "생산/출고 독촉"},
    "balance_due": {"icon": "💰", "tone": "red", "title": "잔금 미수 · 시공 임박",
                    "defect": "시공 전 잔금 미수", "cta": "고객 연락 · 입금 확인"},
    "measure_unassigned": {"icon": "📐", "tone": "amber", "title": "실측 예정 · 담당 미배정",
                           "defect": "실측 담당자 미배정", "cta": "담당 배정"},
    "drawing_stalled": {"icon": "⏳", "tone": "amber", "title": "도면 컨펌 48h+ 정체",
                        "defect": "도면/컨펌 48시간+ 정체", "cta": "컨펌 독촉"},
}


def build_risk_order_ids(db: Any, current_user: Any, key: str, *, today: datetime.date | None = None) -> list[int]:
    """위험 key의 정확 order-id 집합 (착지 큐 SSOT). 카드 카운트와 동일 술어를 재사용한다.

    라우트가 이 집합으로 `_q`(칩/리스트/total)를 스코프하면 카드=칩=리스트 3숫자가 일치한다.
    """
    if key not in RISK_KEYS:
        return []
    today = today or get_today_kst()
    base = _tower_base_query(db, current_user)
    cons_dates = _business_window_dates(today, max_business_days=3, window_days=10)
    meas_dates = _business_window_dates(today, max_business_days=4, window_days=12)
    if key == "construction_unready":
        return _ids_construction_unready(base, cons_dates)
    if key == "drawing_stalled":
        return _ids_drawing_stalled(base)
    if key == "measure_unassigned":
        return _ids_measure_unassigned(base, meas_dates)
    if key == "balance_due":
        return _ids_balance_due(base, cons_dates)
    return []


# 행별 단일 지배 CTA 메타(P1). kind는 라우트가 href로 해석:
#   tel→고객 전화, edit→담당자 배정 필드 포커스, channel→채널톡 데스크 앱(담당자 연락).
RISK_ROW_CTA: dict[str, dict[str, str]] = {
    "construction_unready": {"label": "출고 확인", "icon": "fas fa-comments", "kind": "channel", "tone": "danger"},
    "balance_due": {"label": "전화", "icon": "fas fa-phone", "kind": "tel", "tone": "danger"},
    "measure_unassigned": {"label": "담당 배정", "icon": "fas fa-user-plus", "kind": "edit", "tone": "warning"},
    "drawing_stalled": {"label": "전화", "icon": "fas fa-phone", "kind": "tel", "tone": "warning"},
}


def risk_row_cta_meta(key: str) -> dict[str, str] | None:
    """위험 key의 행별 단일 CTA 메타(label/icon/kind/tone). 라우트가 href를 채운다."""
    return RISK_ROW_CTA.get(key)


def build_risk_frame(key: str, count: int, *, back_href: str = "/erp/dashboard") -> dict[str, Any] | None:
    """착지 상단 risk_frame 페이로드(카테고리·결함·CTA·뒤로=레이더)."""
    meta = RISK_META.get(key)
    if not meta:
        return None
    return {
        "key": key,
        "icon": meta["icon"],
        "tone": meta["tone"],
        "title": meta["title"],
        "defect": meta["defect"],
        "cta": meta["cta"],
        "count": int(count or 0),
        "back_href": back_href,
    }


def _today_total(base: Any, today_iso: str) -> int:
    """오늘 실측/시공/AS 약속 전체 건수 (표시 limit과 무관한 정확 카운트, 복수 일정 포함)."""
    as_ids = _as_visit_order_ids_for_date(base, today_iso)
    return int(
        base.filter(
            or_(
                _measure_on([today_iso]),
                _sched_any('construction', [today_iso]),
                Order.id.in_(as_ids) if as_ids else false(),
            )
        ).count()
        or 0
    )


def _inbound_count(base: Any) -> int:
    """신규 접수 대기 = ERP 단계 RECEIVED (큐 링크 stage=주문접수와 동일 기준)."""
    return int(base.filter(Order.erp_stage_code.in_(["RECEIVED"])).count() or 0)


def _mine_open_count(base: Any, current_user: Any) -> int:
    if not current_user:
        return 0
    conds = build_mine_sql_filter(current_user)
    if not conds:
        return 0
    # 단계 조건까지 먼저 붙인 범위를 갈래에 넣는다(HYBRID, 결과는 OR 과 같다)
    scoped = base.filter(or_(Order.erp_stage_code.is_(None), Order.erp_stage_code.notin_(_DONE_CODES)))
    return int(scoped.filter(mine_membership_clause(conds, scope_conds=[scoped.whereclause])).count() or 0)


def _apply_mine_only(base: Any, current_user: Any) -> Any:
    """내작업 토글 ON: 타워 base를 현재 사용자 담당분으로 축소."""
    if not current_user:
        return base
    conds = build_mine_sql_filter(current_user)
    if not conds:
        return base
    return base.filter(mine_membership_clause(conds, scope_conds=[base.whereclause]))


def build_field_ops_for_day(
    db: Any,
    current_user: Any,
    date_iso: str,
    *,
    field_type: str = "all",
    mine_only: bool = False,
    today: datetime.date | None = None,
) -> dict[str, Any]:
    """특정 날짜 현장 일정 페이로드 (인라인 탭/주간 타일 클릭 ajax용)."""
    today = today or get_today_kst()
    base = _tower_base_query(db, current_user)
    if mine_only:
        base = _apply_mine_only(base, current_user)
    rows = _field_ops_for_date(base, date_iso, field_type=field_type, today=today)
    measure_count, construction_count, as_count = _type_counts_for_date(base, date_iso)
    try:
        day_offset = (datetime.date.fromisoformat(date_iso) - today).days
    except ValueError:
        day_offset = 0
    if field_type == "measure":
        count = measure_count
    elif field_type == "construction":
        count = construction_count
    elif field_type == "as":
        count = as_count
    else:
        count = _today_total(base, date_iso)
    construction_amount = sum(int(r.get("amount") or 0) for r in rows if r["type_code"] == "construction")
    return {
        "rows": rows,
        "sections": _field_sections(rows, day_offset),
        "count": count,
        "measure_count": measure_count,
        "construction_count": construction_count,
        "as_count": as_count,
        "amount_label": _man_label(construction_amount) or "0원",
        "label": _day_label(date_iso, today),
        "iso": date_iso,
        "is_today": day_offset == 0,
    }


def build_month_calendar(
    db: Any,
    current_user: Any,
    month: str | None,
    *,
    mine_only: bool = False,
    today: datetime.date | None = None,
) -> dict[str, Any]:
    """월간 현장 달력 페이로드(달 이동 ajax용). month='YYYY-MM', 범위 밖·오류면 이번 달."""
    today = today or get_today_kst()
    base = _tower_base_query(db, current_user)
    if mine_only:
        base = _apply_mine_only(base, current_user)
    first = _month_first(month, today)
    return _month_calendar(base, today, first, load_colors(db), _weather_window(db, first))


def build_mobile_control_tower(
    db: Any, current_user: Any, *, today: datetime.date | None = None, mine_only: bool = False
) -> dict[str, Any]:
    """모바일 홈 컨트롤 타워 전체 페이로드 (JSON 직렬화 가능).

    mine_only=True면 '내작업' 토글 — 타워 전체를 현재 사용자 담당분으로 필터.
    """
    today = today or get_today_kst()
    today_iso = today.isoformat()
    base = _tower_base_query(db, current_user)
    if mine_only:
        base = _apply_mine_only(base, current_user)
    risk = _risk_radar(base, today)
    measure_count, construction_count, as_count = _type_counts_for_date(base, today_iso)
    first = today.replace(day=1)
    calendar = _month_calendar(base, today, first, load_colors(db), _weather_window(db, first))
    today_cell = next(
        (cell for week in calendar["weeks"] for cell in week if cell["iso"] == today_iso), {}
    )
    return {
        "calendar": calendar,
        "today_iso": today_iso,
        "today_label": _day_label(today_iso, today),
        "today_amount_label": today_cell.get("amount_label") or "0원",
        "today_unshipped": int(today_cell.get("unshipped") or 0),
        "today_count": _today_total(base, today_iso),
        "today_measure_count": measure_count,
        "today_construction_count": construction_count,
        "today_as_count": as_count,
        "risk_groups": risk,
        "risk_total": sum(g["count"] for g in risk),
        "inbound_count": _inbound_count(base),
        "mine_open_count": _mine_open_count(base, current_user),
    }
