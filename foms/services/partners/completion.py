"""PARTNER-FOMS 2단계: 협력사 화면의 완공 사진 · AS 진행 상황 · 완공 사진으로 AS 접수.

- 완공 사진 = 우리 시공팀이 올린 첨부 분류 ``construction``(시공 완료 대시보드와 같은 줄).
- AS 진행 = 현재 AS 건의 상태 · 방문일 · 방문시간 + 그 건의 AS 사진. 비용 판정 같은 내부 값은 넣지 않는다.
- AS 접수에 고른 완공 사진은 첨부를 복제하지 않고 id 목록으로만 남긴다(AS 첨부를 지울 때 시공 사진
  원본이 같이 지워지는 것을 막는다).
설계서: docs/specs/2026-10-19-partner-foms-mode_SPEC.md §3.6 · §4.6 · §4.7
"""
from __future__ import annotations

from typing import Any

from foms.services.orders.as_cycle_service import AS_IN_PROGRESS, AS_RECEIVED, project_current_as_cycle
from models import Order, OrderAttachment

CONSTRUCTION_CATEGORY = "construction"
MAX_REF_PHOTOS = 20

_AS_STATUS_LABELS = {AS_RECEIVED: "접수됨 · 우리 AS 팀 확인 중", AS_IN_PROGRESS: "진행 중"}


class CompletionPhotoError(ValueError):
    """고른 완공 사진이 이 주문의 것이 아닐 때 — 화면에 그대로 보여 줄 수 있는 문구."""


def _photo_view(att: OrderAttachment) -> dict[str, Any]:
    """사진 한 장 — 주소는 웹 층이 key 로 만든다(services 는 api 를 부르지 않는다: 층 의존 규칙)."""
    return {
        "id": att.id,
        "filename": att.filename,
        "storage_key": att.storage_key,
        "thumbnail_key": att.thumbnail_key or att.storage_key,
        "is_image": (att.file_type or "") == "image",
    }


def construction_photos_for_partner(db, order: Order) -> list[dict[str, Any]]:
    """완공 사진(시공팀 사진) 목록 — 올린 순서."""
    rows = (
        db.query(OrderAttachment)
        .filter(OrderAttachment.order_id == order.id, OrderAttachment.category == CONSTRUCTION_CATEGORY)
        .order_by(OrderAttachment.created_at.asc(), OrderAttachment.id.asc())
        .all()
    )
    return [_photo_view(a) for a in rows if a.storage_key]


def _current_cycle_log_ids(order: Order, cycle_id: Any) -> set[str]:
    logs = ((order.structured_data or {}).get("shipment") or {}).get("as_log") or []
    return {str(e.get("id")) for e in logs if isinstance(e, dict) and e.get("cycle_id") == cycle_id and e.get("id")}


def _visit(order: Order, cycle: dict[str, Any], is_open: bool) -> tuple[str, str]:
    """방문 예정 날짜 · 시간. AS 화면은 ``schedule.as_visit`` 에 바로 저장하고 ``AS_SCHEDULE`` 기록을 남기지
    않는다(``field_update`` ``as_visit_date``) — 진행 중인 AS 건이면 그 칸도 읽는다(PARTNER-FOMS 6 §1-8)."""
    date, time = cycle.get("visit_date") or "", cycle.get("visit_time") or ""
    if date or not is_open:
        return date, time
    sd = order.structured_data if isinstance(order.structured_data, dict) else {}
    visit = ((sd.get("schedule") or {}).get("as_visit") or {})
    return str(visit.get("date") or ""), str(visit.get("time") or "")


def as_progress_for_partner(db, order: Order) -> dict[str, Any] | None:
    """현재 AS 건 진행 상황. AS 건이 없으면 None."""
    cycle = project_current_as_cycle(order)
    if cycle is None:
        return None
    log_ids = _current_cycle_log_ids(order, cycle.get("cycle_id"))
    photos = []
    if log_ids:
        rows = (
            db.query(OrderAttachment)
            .filter(OrderAttachment.order_id == order.id, OrderAttachment.category == "as",
                    OrderAttachment.as_log_id.in_(log_ids))
            .order_by(OrderAttachment.id.asc())
            .all()
        )
        photos = [_photo_view(a) for a in rows if a.storage_key]
    status = cycle.get("status")
    is_open = status in (AS_RECEIVED, AS_IN_PROGRESS)
    visit_date, visit_time = _visit(order, cycle, is_open)
    return {
        "status": status,
        "status_label": _AS_STATUS_LABELS.get(status, "처리 완료"),
        "is_open": is_open,
        "visit_date": visit_date,
        "visit_time": visit_time,
        "opened_at": str(cycle.get("opened_at") or "")[:10],
        "photos": photos,
    }


def pick_construction_photos(db, order_id: int, raw_ids: list[Any]) -> list[tuple[int, str]]:
    """AS 접수에 붙일 완공 사진 id 들을 검사한다. 반환 ``[(id, filename)]``(고른 순서, 중복 제거).

    Raises:
        CompletionPhotoError: 숫자가 아니거나, 이 주문의 완공 사진이 아니거나, 너무 많을 때.
    """
    ids: list[int] = []
    for raw in raw_ids or []:
        try:
            value = int(str(raw).strip())
        except (TypeError, ValueError):
            raise CompletionPhotoError("고른 완공 사진이 올바르지 않습니다. 화면을 새로고침해 주세요.")
        if value not in ids:
            ids.append(value)
    if len(ids) > MAX_REF_PHOTOS:
        raise CompletionPhotoError(f"완공 사진은 {MAX_REF_PHOTOS}장까지 고를 수 있습니다.")
    if not ids:
        return []
    rows = (
        db.query(OrderAttachment.id, OrderAttachment.filename)
        .filter(OrderAttachment.id.in_(ids), OrderAttachment.order_id == order_id,
                OrderAttachment.category == CONSTRUCTION_CATEGORY)
        .all()
    )
    found = {r.id: r.filename for r in rows}
    if len(found) != len(ids):
        raise CompletionPhotoError("고른 완공 사진이 올바르지 않습니다. 화면을 새로고침해 주세요.")
    return [(i, found[i]) for i in ids]
