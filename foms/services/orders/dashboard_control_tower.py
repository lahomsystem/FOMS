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
    get_today_kst,
)
from foms.services.common.business_calendar import business_days_until
from foms.services.erp_permissions import build_mine_sql_filter

__all__ = [
    "build_mobile_control_tower",
    "build_field_ops_for_day",
    "build_risk_order_ids",
    "build_risk_frame",
    "risk_row_cta_meta",
    "RISK_KEYS",
]

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


def _field_ops_for_date(base: Any, date_iso: str, *, field_type: str = "all", limit: int = 100) -> list[dict[str, Any]]:
    """특정 날짜의 실측/시공 약속 + 준비도 신호등 (시공 우선, 시간순).

    field_type: 'measure'(실측만) | 'construction'(시공만) | 'all'(둘 다).
    limit는 한 날짜에 실무상 도달 불가능한 상한(=그날 전체 로딩 보장).
    """
    if field_type == "measure":
        date_filter = Order.erp_measurement_date == date_iso
    elif field_type == "construction":
        date_filter = Order.erp_construction_date == date_iso
    else:
        date_filter = or_(Order.erp_measurement_date == date_iso, Order.erp_construction_date == date_iso)
    rows = (
        base.filter(date_filter)
        .order_by(Order.erp_construction_date.desc().nullslast(), Order.created_at.desc())
        .limit(limit)
        .all()
    )
    out: list[dict[str, Any]] = []
    for order in rows:
        sd = _ensure_dict(getattr(order, "structured_data", None))
        if field_type == "measure":
            is_cons = False
        elif field_type == "construction":
            is_cons = True
        else:
            is_cons = getattr(order, "erp_construction_date", None) == date_iso
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


def _type_counts_for_date(base: Any, date_iso: str) -> tuple[int, int]:
    """(실측 건수, 시공 건수) — 표시 limit과 무관한 정확 카운트."""
    measure = int(base.filter(Order.erp_measurement_date == date_iso).count() or 0)
    construction = int(base.filter(Order.erp_construction_date == date_iso).count() or 0)
    return measure, construction


def _day_label(date_iso: str, today: datetime.date) -> str:
    """섹션 제목용 날짜 라벨. 오늘이면 '오늘의 현장', 그 외 'M/D(요일) 현장'."""
    try:
        d = datetime.date.fromisoformat(date_iso)
    except (TypeError, ValueError):
        return "현장 일정"
    if d == today:
        return "오늘의 현장"
    return f"{d.month}/{d.day}({DOW_KR[d.weekday()]}) 현장"


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
    """시공 임박(D-3)인데 설치단계 미도달인 order id (순수 SQL)."""
    rows = base.filter(
        Order.erp_construction_date.in_(cons_dates),
        or_(Order.erp_stage_code.is_(None), Order.erp_stage_code.notin_(_INSTALL_READY_CODES)),
    ).with_entities(Order.id).all()
    return [int(r[0]) for r in rows]


def _ids_drawing_stalled(base: Any) -> list[int]:
    """도면/컨펌 48h+ 정체 order id (순수 SQL)."""
    cutoff = datetime.datetime.now() - datetime.timedelta(hours=48)
    rows = base.filter(
        Order.erp_stage_code.in_(["DRAWING", "CONFIRM"]),
        Order.erp_stage_updated_at.isnot(None),
        Order.erp_stage_updated_at <= cutoff,
    ).with_entities(Order.id).all()
    return [int(r[0]) for r in rows]


def _ids_measure_unassigned(base: Any, meas_dates: list[str]) -> list[int]:
    """실측 임박(D-4)인데 담당 미배정 order id (JSONB는 후보 200캡 메모리 필터)."""
    cand = base.filter(Order.erp_measurement_date.in_(meas_dates)).limit(_RISK_CAND_LIMIT).all()
    return [o.id for o in cand if not _measure_assigned(o, _ensure_dict(getattr(o, "structured_data", None)))]


def _ids_balance_due(base: Any, cons_dates: list[str]) -> list[int]:
    """잔금 미수 + 시공 임박 order id (JSONB는 후보 200캡 메모리 필터)."""
    cand = base.filter(Order.erp_construction_date.in_(cons_dates)).limit(_RISK_CAND_LIMIT).all()
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


def _apply_mine_only(base: Any, current_user: Any) -> Any:
    """내작업 토글 ON: 타워 base를 현재 사용자 담당분으로 축소."""
    if not current_user:
        return base
    conds = build_mine_sql_filter(current_user)
    return base.filter(or_(*conds)) if conds else base


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
    rows = _field_ops_for_date(base, date_iso, field_type=field_type)
    measure_count, construction_count = _type_counts_for_date(base, date_iso)
    if field_type == "measure":
        count = measure_count
    elif field_type == "construction":
        count = construction_count
    else:
        count = _today_total(base, date_iso)
    return {
        "rows": rows,
        "count": count,
        "measure_count": measure_count,
        "construction_count": construction_count,
        "label": _day_label(date_iso, today),
        "iso": date_iso,
    }


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
    field_ops = _field_ops_for_date(base, today_iso)
    measure_count, construction_count = _type_counts_for_date(base, today_iso)
    return {
        "week": _week_strip(base, today),
        "today_iso": today_iso,
        "today_field_ops": field_ops,
        "today_count": _today_total(base, today_iso),
        "today_measure_count": measure_count,
        "today_construction_count": construction_count,
        "risk_groups": risk,
        "risk_total": sum(g["count"] for g in risk),
        "inbound_count": _inbound_count(base),
        "mine_open_count": _mine_open_count(base, current_user),
    }
