"""PARTNER-FOMS 18-1: 협력사 실측 시간 · 희망 시공일 칸 정리와 출고팀 알림(등록 · 고치기가 같이 쓴다).

스펙 docs/specs/2026-10-19-partner-foms-mode_SPEC.md §18. 희망 시공일은 ``partner_intake.requested_construction``
에만 두고 우리 ``schedule.construction``(확정 시공일)은 건드리지 않는다.
"""
from __future__ import annotations

import datetime
import re
from typing import Any

from sqlalchemy import or_

from foms.services.notifications.recipients import fan_out_new_notification
from models import Notification, Order, PartnerOrg

TIME_LIMIT = 20
# 출고 화면 확정 대기 칸이 훑는 협력사 주문 수(최근 순) — 시공일 없는 시공 전 주문만이라 몇 건이다.
_SHIPMENT_SCAN_LIMIT = 200
_REQUEST_DATE = Order.structured_data["partner_intake"]["requested_construction"]["date"].as_string().label("date")
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


def _unconfirmed_partner_orders(query):
    """협력사 주문 중 우리 시공일이 없고 시공 전 단계인 것 — 평면 칸으로 먼저 줄인다(JSONB 는 남은 건만 읽는다)."""
    return query.filter(
        Order.partner_org_id.isnot(None),
        Order.active_filter(),
        or_(Order.erp_construction_date.is_(None), Order.erp_construction_date == ""),
        or_(Order.erp_stage_code.is_(None), Order.erp_stage_code.notin_(REQUEST_CLOSED_STAGES)),
    )


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
