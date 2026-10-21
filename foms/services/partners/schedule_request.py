"""PARTNER-FOMS 18-1: 협력사 실측 시간 · 희망 시공일 칸 정리와 출고팀 알림(등록 · 고치기가 같이 쓴다).

스펙 docs/specs/2026-10-19-partner-foms-mode_SPEC.md §18. 희망 시공일은 ``partner_intake.requested_construction``
에만 두고 우리 ``schedule.construction``(확정 시공일)은 건드리지 않는다.
"""
from __future__ import annotations

import datetime
import re
from typing import Any

from foms.services.notifications.recipients import fan_out_new_notification
from models import Notification

TIME_LIMIT = 20
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
