"""모바일 홈 '오퍼레이션 컨트롤 타워' 페이로드 빌더.

설계 의도: 단계별 개수(인벤토리/funnel)가 아니라 사용자가 매일 아침 던지는
실제 질문에 답하는 read-model을 만든다.
  ① 이번주/오늘 나갈 현장(실측·시공)은? 각각 준비됐나? (week / today_field_ops)
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

from sqlalchemy import func, or_

from models import Order
from foms.services.orders.erp_policy_constants import STAGE_LABELS, STAGE_NAME_TO_CODE
from foms.services.erp_display import (
    _ensure_dict,
    _erp_get_stage,
    erp_payment_amount_from_structured,
)
from foms.services.common.business_calendar import business_days_until
from foms.services.erp_permissions import build_mine_sql_filter

__all__ = ["build_mobile_control_tower"]

DOW_KR = ["월", "화", "수", "목", "금", "토", "일"]
# 시공 단계 이후(=출고/설치 완료로 간주)면 '시공 준비'가 끝난 것으로 본다.
_INSTALL_READY_CODES = ("CONSTRUCTION", "COMPLETED", "AS", "AS_RECEIVED", "AS_COMPLETED")
_DONE_CODES = ("COMPLETED", "AS_COMPLETED")


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
    for raw in (pricing.get("balance"), totals.get("balance"), sd.get("balance")):
        n = _to_int(raw)
        if n is not None:
            return n
    items_total = erp_payment_amount_from_structured(sd)
    deposit = _to_int(totals.get("deposit_amount") or totals.get("deposit") or pricing.get("deposit"))
    if items_total is not None and deposit is not None:
        return max(0, items_total - deposit)
    return None


def _measure_assigned(order: Any, sd: dict) -> bool:
    """실측 담당이 배정됐는지 (영업 배정 user_ids 또는 담당자명)."""
    assignments = sd.get("assignments") or {}
    if assignments.get("sales_assignee_user_ids"):
        return True
    manager = (((sd.get("parties") or {}).get("manager") or {}).get("name")) or getattr(order, "manager_name", None)
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
    if _measure_assigned(order, sd):
        return ("ok", "준비완료")
    return ("warn", "담당 미배정")


def _construction_readiness(order: Any, sd: dict) -> tuple[str, str]:
    """시공 준비도: 설치단계 미도달=위험(출고 미확인), 잔금 남음=경고, 그 외 준비완료."""
    if _stage_code_of(order, sd) not in _INSTALL_READY_CODES:
        return ("risk", "출고 미확인")
    if (_balance_remaining(sd) or 0) > 0:
        return ("warn", "잔금 미수")
    return ("ok", "준비완료")


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
            q = q.filter(or_(*conds))
    return q


def _week_strip(base: Any, today: datetime.date) -> dict[str, Any]:
    """오늘부터 7일: 일자별 실측/시공 건수 + 시공 미준비 위험 표시."""
    dates = [today + datetime.timedelta(days=i) for i in range(7)]
    date_strs = [d.isoformat() for d in dates]
    meas_by = dict(
        base.with_entities(Order.erp_measurement_date, func.count(Order.id))
        .filter(Order.erp_measurement_date.in_(date_strs))
        .group_by(Order.erp_measurement_date)
        .all()
    )
    cons_by = dict(
        base.with_entities(Order.erp_construction_date, func.count(Order.id))
        .filter(Order.erp_construction_date.in_(date_strs))
        .group_by(Order.erp_construction_date)
        .all()
    )
    risk_by = dict(
        base.with_entities(Order.erp_construction_date, func.count(Order.id))
        .filter(
            Order.erp_construction_date.in_(date_strs),
            or_(Order.erp_stage_code.is_(None), Order.erp_stage_code.notin_(_INSTALL_READY_CODES)),
        )
        .group_by(Order.erp_construction_date)
        .all()
    )
    days = []
    for i, day in enumerate(dates):
        ds = day.isoformat()
        days.append({
            "date": day.day,
            "iso": ds,
            "dow": "오늘" if i == 0 else DOW_KR[day.weekday()],
            "is_today": i == 0,
            "measure": int(meas_by.get(ds, 0) or 0),
            "construction": int(cons_by.get(ds, 0) or 0),
            "has_risk": int(risk_by.get(ds, 0) or 0) > 0,
        })
    return {
        "days": days,
        "measure_total": sum(d["measure"] for d in days),
        "construction_total": sum(d["construction"] for d in days),
        "risk_total": sum(int(risk_by.get(d["iso"], 0) or 0) for d in days),
    }


def _today_field_ops(base: Any, today_iso: str, *, limit: int = 12) -> list[dict[str, Any]]:
    """오늘 실측/시공 약속 + 준비도 신호등 (시공 우선, 시간순)."""
    rows = (
        base.filter(or_(Order.erp_measurement_date == today_iso, Order.erp_construction_date == today_iso))
        .order_by(Order.erp_construction_date.desc().nullslast(), Order.created_at.desc())
        .limit(limit)
        .all()
    )
    out: list[dict[str, Any]] = []
    for order in rows:
        sd = _ensure_dict(getattr(order, "structured_data", None))
        is_cons = getattr(order, "erp_construction_date", None) == today_iso
        sched = (sd.get("schedule") or {}).get("construction" if is_cons else "measurement") or {}
        state, label = (_construction_readiness if is_cons else _measure_readiness)(order, sd)
        parties = sd.get("parties") or {}
        site = sd.get("site") or {}
        out.append({
            "id": order.id,
            "name": (parties.get("customer") or {}).get("name") or "-",
            "type": "시공" if is_cons else "실측",
            "type_code": "construction" if is_cons else "measure",
            "time": (str(sched.get("time") or "").strip() or None),
            "addr": site.get("address_full") or site.get("address_main") or "-",
            "manager": (parties.get("manager") or {}).get("name") or getattr(order, "manager_name", None) or "-",
            "readiness_state": state,
            "readiness_label": label,
        })
    out.sort(key=lambda r: (0 if r["type_code"] == "construction" else 1, r["time"] or "99:99"))
    return out


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


def _risk_construction_unready(base: Any, today: datetime.date, cons_dates: list[str]) -> dict[str, Any] | None:
    """시공 임박(D-3)인데 설치단계 미도달. 탭→construction_d3(임박 전체, 미준비 포함 상위집합)."""
    q = base.filter(
        Order.erp_construction_date.in_(cons_dates),
        or_(Order.erp_stage_code.is_(None), Order.erp_stage_code.notin_(_INSTALL_READY_CODES)),
    )
    count = int(q.count() or 0)
    if not count:
        return None
    why = _samples_construction(q.order_by(Order.erp_construction_date.asc()).limit(2).all(), today)
    return _risk_group("construction_unready", "🔨", "red", "시공 임박인데 미준비", why, count, {"alert_type": "construction_d3"})


def _risk_drawing_stalled(base: Any) -> dict[str, Any] | None:
    """도면/컨펌 48h+ 정체. 탭→drawing_overdue(DRAWING+CONFIRM 정체 정확 일치)."""
    cutoff = datetime.datetime.now() - datetime.timedelta(hours=48)
    q = base.filter(
        Order.erp_stage_code.in_(["DRAWING", "CONFIRM"]),
        Order.erp_stage_updated_at.isnot(None),
        Order.erp_stage_updated_at <= cutoff,
    )
    count = int(q.count() or 0)
    if not count:
        return None
    why = _samples_names(q.order_by(Order.erp_stage_updated_at.asc()).limit(2).all(), fallback="컨펌 지연")
    return _risk_group("drawing_stalled", "⏳", "amber", "도면 컨펌 48h+ 정체", why, count, {"alert_type": "drawing_overdue"})


def _risk_measure_unassigned(base: Any, meas_dates: list[str]) -> dict[str, Any] | None:
    """실측 임박(D-4)인데 담당 미배정. 탭→measurement_d4(임박 전체 상위집합)."""
    cand = base.filter(Order.erp_measurement_date.in_(meas_dates)).limit(_RISK_CAND_LIMIT).all()
    unassigned = [o for o in cand if not _measure_assigned(o, _ensure_dict(getattr(o, "structured_data", None)))]
    if not unassigned:
        return None
    return _risk_group("measure_unassigned", "📐", "amber", "실측 예정 · 담당 미배정",
                       _samples_names(unassigned[:2], fallback="담당 미배정"), len(unassigned), {"alert_type": "measurement_d4"})


def _risk_balance_due(base: Any, cons_dates: list[str]) -> dict[str, Any] | None:
    """잔금 미수인데 시공 임박. 탭→construction_d3(임박 전체, 잔금건 포함 상위집합)."""
    cand = base.filter(Order.erp_construction_date.in_(cons_dates)).limit(_RISK_CAND_LIMIT).all()
    due = [o for o in cand if (_balance_remaining(_ensure_dict(getattr(o, "structured_data", None))) or 0) > 0]
    if not due:
        return None
    return _risk_group("balance_due", "💰", "red", "잔금 미수 · 시공 임박",
                       _samples_balance(due[:2]), len(due), {"alert_type": "construction_d3"})


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


def _today_total(base: Any, today_iso: str) -> int:
    """오늘 실측 또는 시공 약속 전체 건수 (표시 limit과 무관한 정확 카운트)."""
    return int(
        base.filter(
            or_(Order.erp_measurement_date == today_iso, Order.erp_construction_date == today_iso)
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
    return int(
        base.filter(or_(*conds))
        .filter(or_(Order.erp_stage_code.is_(None), Order.erp_stage_code.notin_(_DONE_CODES)))
        .count()
        or 0
    )


def build_mobile_control_tower(db: Any, current_user: Any, *, today: datetime.date | None = None) -> dict[str, Any]:
    """모바일 홈 컨트롤 타워 전체 페이로드 (JSON 직렬화 가능)."""
    today = today or datetime.date.today()
    today_iso = today.isoformat()
    base = _tower_base_query(db, current_user)
    risk = _risk_radar(base, today)
    field_ops = _today_field_ops(base, today_iso)
    return {
        "week": _week_strip(base, today),
        "today_field_ops": field_ops,
        "today_count": _today_total(base, today_iso),
        "risk_groups": risk,
        "risk_total": sum(g["count"] for g in risk),
        "inbound_count": _inbound_count(base),
        "mine_open_count": _mine_open_count(base, current_user),
    }
