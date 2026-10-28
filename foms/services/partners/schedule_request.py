"""PARTNER-FOMS 18-1: 협력사 실측 시간 · 희망 시공일 칸 정리와 출고팀 알림(등록 · 고치기가 같이 쓴다).

스펙 docs/specs/2026-10-19-partner-foms-mode_SPEC.md §18. 희망 시공일은 ``partner_intake.requested_construction``
에만 두고 우리 ``schedule.construction``(확정 시공일)은 건드리지 않는다.

협력사는 주문 · 실측까지만 하고 도면 · 제작 · 시공 · AS 는 우리가 한다 — 확정 전 희망 시공일도 그날 우리 시공
건수에 넣는다(사용자 결정 2026-10-28, :func:`partner_request_on` · :func:`pending_request_counts`). 출고가도 그날
금액에 싣는다(2026-10-29, :func:`pending_request_rows`).
"""
from __future__ import annotations

import datetime
import re
from typing import Any

from sqlalchemy import and_, or_

from foms.services.notifications.recipients import fan_out_new_notification
from models import Notification, Order, OrderScheduleDate, PartnerOrg

TIME_LIMIT = 20
# 출고 화면 확정 대기 칸이 훑는 협력사 주문 수(최근 순) — 시공일 없는 시공 전 주문만이라 몇 건이다.
_SHIPMENT_SCAN_LIMIT = 200
_REQUEST_DATE_EXPR = Order.structured_data["partner_intake"]["requested_construction"]["date"].as_string()
_REQUEST_DATE = _REQUEST_DATE_EXPR.label("date")
_REQUEST_TIME = Order.structured_data["partner_intake"]["requested_construction"]["time"].as_string().label("time")
# 시공이 시작됐거나 끝난 단계 — 희망 시공일을 더 받지 않는다.
REQUEST_CLOSED_STAGES = frozenset({"CONSTRUCTION", "CS", "COMPLETED", "AS", "AS_RECEIVED", "AS_COMPLETED"})
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def clean_date(value: Any) -> str:
    """'YYYY-MM-DD' 이고 실제 날짜일 때만 그 값, 아니면 빈 문자열."""
    text = str(value if value is not None else "").strip()[:10]
    if not _DATE_RE.match(text):
        return ""
    try:
        datetime.date.fromisoformat(text)
    except ValueError:
        return ""
    return text


def clean_time(value: Any) -> str:
    """시간 칸 — 우리 화면처럼 오전 · 오후 · 종일 또는 직접 입력(예: 10:30). 길이만 자른다."""
    return str(value if value is not None else "").strip()[:TIME_LIMIT]


def clean_request(data: dict[str, Any]) -> dict[str, str] | None:
    """희망 시공일 묶음. 날짜 · 시간이 모두 비면 None."""
    date = clean_date(data.get("requested_construction_date"))
    time = clean_time(data.get("requested_construction_time"))
    return {"date": date, "time": time} if (date or time) else None


def request_text(request: dict[str, Any] | None) -> str:
    """'2026-10-30 오후' 처럼 한 줄(없으면 빈 문자열)."""
    if not isinstance(request, dict):
        return ""
    return " ".join(v for v in (str(request.get("date") or ""), str(request.get("time") or "")) if v)


def construction_confirmed(sd: dict[str, Any]) -> bool:
    """우리 시공일이 정해졌는가(정해지면 희망 시공일을 더 고치지 않는다)."""
    schedule = sd.get("schedule") if isinstance(sd.get("schedule"), dict) else {}
    construction = schedule.get("construction") if isinstance(schedule.get("construction"), dict) else {}
    return bool(str(construction.get("date") or "").strip())


def request_open(sd: dict[str, Any], stage: str) -> bool:
    """희망 시공일을 넣거나 고칠 수 있는가 — 우리 시공일이 아직 없고 시공 전 단계."""
    return not construction_confirmed(sd) and (stage or "").upper() not in REQUEST_CLOSED_STAGES


def notify_shipment_request(db, user: Any, order_id: int, customer: str, request: dict[str, Any]) -> None:
    """희망 시공일을 넣거나 바꿨을 때 출고팀 알림 1건(협의 후 시공일을 정하라는 안내). 호출자가 commit."""
    notification = Notification(
        order_id=order_id,
        notification_type="PARTNER_CONSTRUCTION_REQUESTED",
        target_team="SHIPMENT",
        title="협력사 희망 시공일",
        message=f"[협력사] 주문 #{order_id}" + (f" ({customer})" if customer else "")
        + f" 희망 시공일 {request_text(request)}. 협력사와 이야기한 뒤 시공일을 정해 주세요.",
        created_by_user_id=user.id,
        created_by_name=f"{user.name} (협력사)",
    )
    db.add(notification)
    db.flush()
    fan_out_new_notification(db, notification, actor_user_id=user.id)


def pending_request(sd: Any, stage: str) -> dict[str, Any] | None:
    """우리가 아직 확정하지 않은 희망 시공일 묶음(없으면 None) — 목록 · 대시보드 · 출고 화면 표시용."""
    if not isinstance(sd, dict) or not request_open(sd, stage):
        return None
    intake = sd.get("partner_intake") if isinstance(sd.get("partner_intake"), dict) else {}
    request = intake.get("requested_construction")
    return request if request_text(request) else None


def _unconfirmed_conds() -> tuple:
    """협력사 주문 중 우리 시공일이 없고 시공 전 단계인 것 — 평면 칸으로 먼저 줄인다(JSONB 는 남은 건만 읽는다)."""
    return (
        Order.partner_org_id.isnot(None),
        or_(Order.erp_construction_date.is_(None), Order.erp_construction_date == ""),
        or_(Order.erp_stage_code.is_(None), Order.erp_stage_code.notin_(REQUEST_CLOSED_STAGES)),
    )


def _unconfirmed_partner_orders(query):
    """확정 대기 협력사 주문(삭제 · 보관 제외)."""
    return query.filter(Order.active_filter(), *_unconfirmed_conds())


def partner_request_on(dates: list[str]):
    """희망 시공일이 dates 중 하나인 확정 대기 협력사 주문 술어 — 날짜별 시공 술어에 OR 로 붙인다.

    우리 시공 일정 행이 하나라도 있으면(품목별 시공일만 있는 경우 포함) 그 행으로 세므로 여기서 뺀다(두 번 세지 않게).
    """
    return and_(
        *_unconfirmed_conds(),
        ~Order.schedule_dates.any(OrderScheduleDate.kind == "construction"),
        _REQUEST_DATE_EXPR.in_(list(dates)),
    )


def pending_request_ids_by_date(query, dates: list[str]) -> dict[int, str]:
    """확정 대기 희망 시공 주문 번호 → 희망일(query 범위 안). 화면이 담당 거르기를 따로 할 때 쓴다."""
    if not dates:
        return {}
    rows = query.filter(partner_request_on(dates)).with_entities(Order.id, _REQUEST_DATE_EXPR).all()
    return {int(order_id): str(day) for order_id, day in rows if day}


def pending_request_counts(query, dates: list[str]) -> dict[str, int]:
    """날짜별 확정 대기 희망 시공 주문 수(query 가 정한 범위 안). 우리 시공 건수에 더한다.

    시공일 없는 협력사 주문이라 몇 건뿐이다 — 번호 · 날짜를 받아 여기서 센다(담당 거르기 경로와 같은 행).
    """
    counts: dict[str, int] = {}
    for day in pending_request_ids_by_date(query, dates).values():
        counts[day] = counts.get(day, 0) + 1
    return counts


def pending_request_rows(query, dates: list[str]) -> list[tuple[int, str, Any]]:
    """확정 대기 희망 시공 (주문 번호, 희망일, structured_data) — 그날 출고가를 더할 때 쓴다(사용자 결정 2026-10-29)."""
    if not dates:
        return []
    rows = (query.filter(partner_request_on(dates))
            .with_entities(Order.id, _REQUEST_DATE_EXPR, Order.structured_data).all())
    return [(int(order_id), str(day), sd) for order_id, day, sd in rows if day]


def pending_request_texts(db, order_ids: set[int]) -> dict[int, str]:
    """주문 번호별 확정 대기 희망 시공일 한 줄('2026-10-30 오후'). 대상이 아니면 빠진다."""
    if not order_ids:
        return {}
    rows = _unconfirmed_partner_orders(
        db.query(Order.id, _REQUEST_DATE, _REQUEST_TIME).filter(Order.id.in_(order_ids))
    ).all()
    texts = {r.id: request_text({"date": clean_date(r.date), "time": clean_time(r.time)}) for r in rows}
    return {order_id: text for order_id, text in texts.items() if text}


def shipment_pending_requests(db, limit: int = 30) -> list[dict[str, Any]]:
    """출고 화면 '협력사 희망 시공일 · 확정 대기' 칸 — 희망일이 이른 순(날짜 없는 건 뒤)."""
    rows = _unconfirmed_partner_orders(
        db.query(Order.id, Order.customer_name, PartnerOrg.name.label("partner_name"), _REQUEST_DATE, _REQUEST_TIME)
        .join(PartnerOrg, PartnerOrg.id == Order.partner_org_id)
    ).order_by(Order.id.desc()).limit(_SHIPMENT_SCAN_LIMIT).all()
    items = []
    for r in rows:
        request = {"date": clean_date(r.date), "time": clean_time(r.time)}
        text = request_text(request)
        if text:
            items.append({"id": r.id, "customer_name": r.customer_name or "", "partner_name": r.partner_name or "",
                          "date": request["date"], "text": text})
    items.sort(key=lambda item: (item["date"] == "", item["date"], item["id"]))
    return items[:limit]
