"""PARTNER-FOMS 3-3: 협력사 주문 화면 "이력" 탭 — 협력사가 볼 일만 고른 줄(허용 목록 방식).

우리 내부 변경 이력과 다르다. 우리 직원 이름은 넣지 않고("저희 담당자" · "저희 도면팀"), 도면팀 메모 ·
우리 쪽이 낸 수정 요청 내용 · 단계 바꾼 사유 · AS 비용 판정은 넣지 않는다. 협력사 직원 이름과 협력사가 보낸
수정 요청 내용은 넣는다(자기 회사 일).
설계서: docs/specs/2026-10-19-partner-foms-mode_SPEC.md §3.7 · §15
"""
from __future__ import annotations

from typing import Any

from foms.services.datetime_kst import format_datetime_kst, parse_datetime_utc
from foms.services.order_timeline_v3 import _stage_reach_events
from models import Order, OrderEvent, User

OUR_STAFF = "저희 담당자"
OUR_DRAWING_TEAM = "저희 도면팀"
MAX_NOTE = 300

_AS_LINES = {
    "AS_REGISTER": "AS 접수",
    "AS_SCHEDULE": "AS 방문 예정",
    "AS_UNSCHEDULE": "AS 방문 일정 취소",
    "AS_START": "AS 처리 시작",
    "AS_COMPLETE": "AS 처리 끝",
    "AS_REOPEN": "AS 다시 열림",
}


def _line(at: Any, kind: str, title: str, who: str, detail: str = "") -> dict[str, Any] | None:
    """이력 한 줄. 시각을 읽을 수 없으면 버린다(순서를 정할 수 없다)."""
    when = parse_datetime_utc(at)
    if when is None:
        return None
    return {
        "sort": when,
        "at": format_datetime_kst(when, "%Y-%m-%d %H:%M"),
        "kind": kind,
        "title": title,
        "who": who,
        "detail": detail,
    }


def _partner_names(db, order: Order, user_ids: set[int]) -> dict[int, str]:
    """이 주문 협력사 직원만 이름을 돌려준다(그 밖은 우리 직원 — 이름을 내지 않는다)."""
    if not user_ids or not order.partner_org_id:
        return {}
    rows = (
        db.query(User.id, User.name)
        .filter(User.id.in_(user_ids), User.partner_org_id == order.partner_org_id)
        .all()
    )
    return {uid: name for uid, name in rows}


def _intake_lines(intake: dict[str, Any]) -> list[dict | None]:
    lines = [_line(intake.get("submitted_at"), "order", "주문 보냄", str(intake.get("submitted_by_name") or ""))]
    for edit in intake.get("item_edits") or []:
        if isinstance(edit, dict):
            lines.append(_line(edit.get("at"), "order", "품목 고침", str(edit.get("by_name") or "")))
    return lines


def _drawing_lines(history: list[dict], names: dict[int, str]) -> tuple[list[dict | None], list[tuple]]:
    """도면 올림 · 수정 요청 · 도면 확정. 두 번째 값은 (올린 시각, 회차) — 승인 줄의 회차를 정한다."""
    lines: list[dict | None] = []
    rounds: list[tuple] = []
    revisions = 0
    for h in history:
        action = h.get("action")
        if action == "TRANSFER":
            round_no = revisions + 1
            line = _line(h.get("transferred_at") or h.get("at"), "drawing", f"{round_no}차 도면 올라옴",
                         OUR_DRAWING_TEAM, f"파일 {int(h.get('files_count') or 0)}개")
            if line:
                rounds.append((line["sort"], round_no))
            lines.append(line)
        elif action == "REQUEST_REVISION":
            revisions += 1
            name = names.get(h.get("by_user_id"))
            note = str(h.get("note") or "").strip()[:MAX_NOTE] if name else ""
            lines.append(_line(h.get("at"), "revision", "수정 요청", name or OUR_STAFF, note))
        elif action == "CONFIRM_RECEIPT":
            lines.append(_line(h.get("at"), "drawing", "도면 확정 · 협력사 확인 차례", OUR_STAFF))
    return lines, rounds


def _approval_line(sd: dict[str, Any], rounds: list[tuple]) -> dict | None:
    blueprint = sd.get("blueprint") if isinstance(sd.get("blueprint"), dict) else {}
    if not blueprint.get("customer_confirmed"):
        return None
    by = str(blueprint.get("confirmed_by") or "")
    who = by[: -len(" (협력사)")] if by.endswith(" (협력사)") else OUR_STAFF
    line = _line(blueprint.get("confirmed_at"), "approve", "이대로 만들어 주세요", who)
    if line:
        before = [r for at, r in rounds if at <= line["sort"]]
        line["detail"] = f"{before[-1]}차 도면으로 제작" if before else ""
    return line


def _construction_date_line(ev: OrderEvent) -> dict | None:
    payload = ev.payload if isinstance(ev.payload, dict) else {}
    before, after = str(payload.get("from") or ""), str(payload.get("to") or "")
    if after and not before:
        return _line(ev.created_at, "schedule", "시공일 정해짐", OUR_STAFF, after)
    if after:
        return _line(ev.created_at, "schedule", "시공일 바뀜", OUR_STAFF, f"{before} → {after}")
    return _line(ev.created_at, "schedule", "시공일 취소", OUR_STAFF, before) if before else None


def _event_lines(events: list[OrderEvent]) -> list[dict | None]:
    lines: list[dict | None] = []
    drawing_start = _stage_reach_events(events).get("DRAWING")
    if drawing_start is not None:
        lines.append(_line(drawing_start.created_at, "order", "주문 확인 · 도면 작업 시작", OUR_STAFF))
    for ev in events:
        if ev.event_type == "CONSTRUCTION_DATE_CHANGED":
            lines.append(_construction_date_line(ev))
        elif ev.event_type == "CONSTRUCTION_COMPLETED":
            lines.append(_line(ev.created_at, "schedule", "시공 끝", OUR_STAFF, "완공 사진 탭에서 볼 수 있습니다."))
    return lines


def _as_lines(cycles: list[dict], names: dict[int, str]) -> list[dict | None]:
    lines: list[dict | None] = []
    for cycle in cycles:
        for tr in cycle.get("transitions") or []:
            title = _AS_LINES.get(tr.get("command")) if isinstance(tr, dict) else None
            if not title:
                continue
            detail = ""
            if tr.get("command") == "AS_SCHEDULE":
                payload = tr.get("payload") if isinstance(tr.get("payload"), dict) else {}
                detail = " ".join(str(payload.get(k) or "") for k in ("visit_date", "visit_time")).strip()
            lines.append(_line(tr.get("at"), "as", title, names.get(tr.get("actor_id")) or OUR_STAFF, detail))
    return lines


def _as_cycles(sd: dict[str, Any]) -> list[dict]:
    lifecycle = sd.get("as_lifecycle") if isinstance(sd.get("as_lifecycle"), dict) else {}
    return [c for c in lifecycle.get("cycles") or [] if isinstance(c, dict)]


def partner_order_history(db, order: Order) -> list[dict[str, Any]]:
    """협력사 이력 줄(최근이 위). 줄 = ``{at, kind, title, who, detail}`` — 시각은 KST."""
    sd = order.structured_data if isinstance(order.structured_data, dict) else {}
    drawing = [h for h in sd.get("drawing_transfer_history") or [] if isinstance(h, dict)]
    cycles = _as_cycles(sd)
    actor_ids = {h.get("by_user_id") for h in drawing if h.get("action") == "REQUEST_REVISION"}
    actor_ids |= {tr.get("actor_id") for c in cycles for tr in c.get("transitions") or [] if isinstance(tr, dict)}
    names = _partner_names(db, order, {i for i in actor_ids if isinstance(i, int)})
    events = (
        db.query(OrderEvent)
        .filter(OrderEvent.order_id == order.id)
        .order_by(OrderEvent.created_at, OrderEvent.id)
        .all()
    )
    intake = sd.get("partner_intake") if isinstance(sd.get("partner_intake"), dict) else {}
    drawing_lines, rounds = _drawing_lines(drawing, names)
    lines = [
        *_intake_lines(intake),
        *drawing_lines,
        _approval_line(sd, rounds),
        *_event_lines(events),
        *_as_lines(cycles, names),
    ]
    kept = sorted((x for x in lines if x), key=lambda x: x["sort"], reverse=True)
    return [{k: v for k, v in x.items() if k != "sort"} for x in kept]

