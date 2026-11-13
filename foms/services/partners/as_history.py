"""협력사 화면 AS 내역 — 건마다 접수 내역 · 완료 내역(사용자 2026-11-13: "AS 완료 시 완료 내역, 접수 시 접수 내역도").

보이는 것: 접수일 · 접수 글(고친 기록 포함 — 같은 건 재접수는 접수 줄을 하나 더 쌓는다) · 접수 사진 · 방문일 ·
완료일 · 처리 결과(몇 차에 완결 · 미결) · 처리 사진.
안 보이는 것(우리 몫): 판정 사유 · 완료 메모 · 통화 · 자재 · 메모 · 방안 글 · 비용 판정 · 분류. 자재 · 통화 줄에 붙은
사진도 뺀다(견적 · 영수증일 수 있다).
주소(URL)는 웹 층이 붙인다(services 는 api 를 부르지 않는다).
설계서: docs/specs/2026-11-13-partner-as-intake-edit-push_SPEC.md §8
"""
from __future__ import annotations

from typing import Any

from foms.services.as_content_safety import as_content_html_to_text
from foms.services.datetime_kst import format_datetime_kst
from foms.services.orders.as_cycle_service import AS_COMPLETED, AS_IN_PROGRESS, AS_RECEIVED, cycle_status
from foms.services.orders.as_cycle_view import cycle_ordinal
from foms.services.orders.as_log import AS_VERDICT_LABELS
from models import Order, OrderAttachment

_STATUS_LABELS = {AS_RECEIVED: "접수됨 · 저희 AS 팀 확인 중", AS_IN_PROGRESS: "진행 중", AS_COMPLETED: "완료"}
# 처리 사진으로 보여 줄 기록 줄 — 접수 줄은 접수 사진, 자재 · 통화 · 시스템 줄 사진은 뺀다.
_WORK_PHOTO_TYPES = frozenset({"verdict", "plan", "action", "memo"})


def _text(entry: dict) -> str:
    return as_content_html_to_text(entry.get("text"), already_sanitized=True).strip()


def _at(ts: Any) -> str:
    return (format_datetime_kst(ts, "%m-%d %H:%M") or "") if ts else ""


def _visit(cycle: dict) -> tuple[str, str]:
    """마지막 방문 일정(AS_SCHEDULE) — 취소(AS_UNSCHEDULE)가 뒤에 있으면 없음."""
    date = time = ""
    for t in cycle.get("transitions") or []:
        if not isinstance(t, dict):
            continue
        if t.get("command") == "AS_SCHEDULE":
            payload = t.get("payload") or {}
            date, time = str(payload.get("visit_date") or ""), str(payload.get("visit_time") or "")
        elif t.get("command") == "AS_UNSCHEDULE":
            date = time = ""
    return date, time


def _results(logs: list[dict]) -> list[dict]:
    """처리 결과 — 회차 판정(몇 차 완결 · 미결)만, 시간 순. 판정 사유 · 완료 메모 글은 우리 내부 글이라 싣지 않는다
    (2026-10-19 이력 탭 결정 — tests/security/test_partner_history.py 가 "부품비 우리 부담" 같은 완료 메모를 지킨다)."""
    return [{"label": f"{e.get('round') or 1}차 {AS_VERDICT_LABELS.get(e.get('verdict'), '판정')}", "at": _at(e.get("ts"))}
            for e in logs if e.get("type") == "verdict"]


def _photo(att: OrderAttachment) -> dict[str, Any]:
    return {"id": att.id, "filename": att.filename, "storage_key": att.storage_key,
            "thumbnail_key": att.thumbnail_key or att.storage_key, "is_image": (att.file_type or "") == "image"}


def as_history_for_partner(db, order: Order) -> list[dict[str, Any]]:
    """AS 건 목록(최근 건 먼저). 건이 없으면 빈 목록."""
    sd = order.structured_data if isinstance(order.structured_data, dict) else {}
    cycles = [c for c in ((sd.get("as_lifecycle") or {}).get("cycles") or []) if isinstance(c, dict)]
    if not cycles:
        return []
    logs = [e for e in ((sd.get("shipment") or {}).get("as_log") or [])
            if isinstance(e, dict) and e.get("deleted") is not True]
    type_of = {str(e.get("id")): e.get("type") for e in logs if e.get("id")}
    cycle_of = {str(e.get("id")): e.get("cycle_id") for e in logs if e.get("id")}
    rows = (db.query(OrderAttachment)
            .filter(OrderAttachment.order_id == order.id, OrderAttachment.category == "as",
                    OrderAttachment.as_log_id.in_(list(type_of) or [""]))
            .order_by(OrderAttachment.sort_order.asc(), OrderAttachment.id.asc()).all())
    out = []
    for cycle in reversed(cycles):
        cid = cycle.get("cycle_id")
        mine = [e for e in logs if e.get("cycle_id") == cid]
        receptions = [{"text": _text(e), "by": e.get("by") or "", "at": _at(e.get("ts"))}
                      for e in mine if e.get("type") == "reception" and _text(e)]
        photos = [a for a in rows if a.storage_key and cycle_of.get(a.as_log_id) == cid]
        status = cycle_status(cycle)
        visit_date, visit_time = _visit(cycle)
        out.append({
            "ordinal": cycle_ordinal(sd, cid),
            "is_open": status in (AS_RECEIVED, AS_IN_PROGRESS),
            "status_label": _STATUS_LABELS.get(status, "완료"),
            "received_date": str(cycle.get("received_date") or str(cycle.get("opened_at") or "")[:10]),
            "content": receptions[-1]["text"] if receptions else "",
            "edits": receptions[:-1],  # 고치기 전 글(같은 건 재접수 — 오래된 것부터)
            "visit_date": visit_date, "visit_time": visit_time,
            "completed_date": str(cycle.get("completed_date") or "") if status == AS_COMPLETED else "",
            "results": _results(mine),
            "reception_photos": [_photo(a) for a in photos if type_of.get(a.as_log_id) == "reception"],
            "work_photos": [_photo(a) for a in photos if type_of.get(a.as_log_id) in _WORK_PHOTO_TYPES],
        })
    return out
