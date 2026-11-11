"""도면 작업실 목록의 AS 도면 행 (설계서 ``docs/specs/2026-11-11-as-drawing-after-completion_SPEC.md`` §6.1).

새 칸·새 열을 만들지 않는다. 열린 AS 도면 차수가 있는 주문은 지금 칸(상태 · 다음 액션 · 시공일)에
들어가는 글만 바꾼다. 검색으로 찾은 완료 주문은 "AS 도면 시작할 수 있어요"로 보여 준다.
"""
from __future__ import annotations

from typing import Any, Mapping, Optional

from foms.services.as_content_safety import as_content_html_to_text
from foms.services.datetime_kst import format_datetime_kst
from foms.services.orders.as_cycle_service import current_cycle
from foms.services.orders.as_drawing import (
    STATUS_CANCELLED,
    STATUS_CONFIRMED,
    STATUS_IN_PROGRESS,
    STATUS_RETURNED,
    STATUS_TRANSFERRED,
    STATUS_WAITING,
    current_round,
    is_as_drawing_stage,
    open_as_cycle_id,
    room_push_round,
    round_no,
    round_sheet_ids,
    rounds,
)
from foms.services.orders.as_schedule_link import read_as_visit_date
from foms.services.orders.order_mutation_policy import POLICY_REGISTRY, evaluate_policy

__all__ = ["AS_SEARCH_HIT_BUCKET", "as_round_row_fields", "as_search_hit_row_fields", "build_as_drawing_detail"]

#: 검색으로 찾은 완료 주문 칸 — 열린 큐 네 칸 밖이라 타일 숫자에 섞이지 않는다.
AS_SEARCH_HIT_BUCKET = "AS_START"

_STATUS_LABELS = {
    STATUS_WAITING: "대기중",
    STATUS_IN_PROGRESS: "작업중",
    STATUS_RETURNED: "수정 요청됨",
    STATUS_TRANSFERRED: "확정 대기",
    STATUS_CONFIRMED: "확인함",
    STATUS_CANCELLED: "그만둠",
}


def _visit_text(sd: Mapping[str, Any]) -> str:
    raw = str(read_as_visit_date(dict(sd)) or "").strip()
    if len(raw) >= 10 and raw[4] == "-" and raw[7] == "-":
        return f"AS 방문 {raw[5:10]}"
    return f"AS 방문 {raw}" if raw else "AS 방문 미정"


def as_round_row_fields(sd: Mapping[str, Any], *, is_drawing_assignee: bool,
                        is_sales_owner: bool) -> Optional[dict[str, Any]]:
    """열린 AS 도면 차수가 있으면 목록 행에 덮어쓸 값, 없으면 None.

    Args:
        sd: 주문 structured_data.
        is_drawing_assignee: 보는 사람이 이 주문 도면 담당인가(내 할 일 판정).
        is_sales_owner: 보는 사람이 이 주문 영업 담당인가(확인 차례 판정).

    Returns:
        ``bucket``·``drawing_status_label``·``next_action``·``construction_date`` 등.
    """
    rnd = current_round(sd)
    if rnd is None:
        return None
    status = str(rnd.get("status") or "")
    no = round_no(sd, rnd)
    drawing_turn = status in (STATUS_WAITING, STATUS_IN_PROGRESS, STATUS_RETURNED)
    next_action = {
        STATUS_WAITING: f"AS 도면 그리기 · {no}차 부탁받음",
        STATUS_IN_PROGRESS: f"AS 도면 그리기 · {no}차",
        STATUS_RETURNED: f"AS 고쳐 달라고 함 · {no}차",
        STATUS_TRANSFERRED: f"AS 확인 기다림 · {no}차",
    }.get(status, f"AS 도면 · {no}차")
    wizard = sd.get("drawing_wizard") if isinstance(sd.get("drawing_wizard"), Mapping) else {}
    pending = wizard.get("pending") if isinstance(wizard.get("pending"), Mapping) else {}
    round_sheets = set(round_sheet_ids(sd, str(rnd.get("round_id") or "")))
    return {
        "as_round_no": no,
        "as_round_status": status,
        "bucket": status,
        "drawing_status_label": _STATUS_LABELS.get(status, status),
        "next_action": next_action,
        "next_action_tone": "mine" if drawing_turn else "other",
        "construction_date": _visit_text(sd),
        "construction_requested": "",
        "construction_badge_level": "info",
        "turn_label": "AS 도면 작업 차례" if drawing_turn else "AS 확인 차례",
        "turn_sub": f"AS {no}차 · 도면 {len(rnd.get('files') or [])}장",
        "turn_tone": "mine" if drawing_turn else "other",
        "primary_action_label": "AS 도면 그리기" if drawing_turn else "작업 열기",
        "primary_action_icon": "fa-magic" if drawing_turn else "fa-external-link-alt",
        "primary_action_query": "",
        "file_count": len(rnd.get("files") or []),
        "pending_count": len([sid for sid in pending if sid in round_sheets]),
        "my_todo": bool((drawing_turn and is_drawing_assignee)
                        or (status == STATUS_TRANSFERRED and is_sales_owner)),
        "post_drawing_receipt": False,
    }


def as_search_hit_row_fields() -> dict[str, Any]:
    """검색으로 찾은 완료 주문(열린 차수 없음) 행 값."""
    return {
        "bucket": AS_SEARCH_HIT_BUCKET,
        "drawing_status_label": "완료된 주문",
        "next_action": "AS 도면 시작할 수 있어요",
        "next_action_tone": "other",
        "my_todo": False,
        "post_drawing_receipt": False,
    }


def _files_view(files: Any) -> list[dict[str, str]]:
    out = []
    for f in files if isinstance(files, list) else []:
        key = str((f or {}).get("key") or "").strip() if isinstance(f, Mapping) else ""
        if not key:
            continue
        out.append({
            "name": str(f.get("name") or f.get("filename") or "AS 도면"),
            # 저장된 URL 은 믿지 않는다 — key 로만 같은 출처 주소를 만든다(작업실 갤러리와 같은 규칙).
            "view_url": "/api/files/view/" + key,
        })
    return out


def _round_brief(sd: Mapping[str, Any], rnd: Mapping[str, Any]) -> dict[str, Any]:
    status = str(rnd.get("status") or "")
    return {
        "round_id": rnd.get("round_id"),
        "no": round_no(sd, rnd),
        "status": status,
        "status_label": _STATUS_LABELS.get(status, status),
        "memo": rnd.get("memo") or "",
        "registered_as": bool(rnd.get("registered_as")),
        "opened_by_name": rnd.get("opened_by_name") or "",
        "opened_at": format_datetime_kst(rnd.get("opened_at"), "%m/%d %H:%M") or "",
        "files": _files_view(rnd.get("files")),
        "sent": any(isinstance(h, Mapping) and h.get("action") == "TRANSFER" for h in rnd.get("history") or []),
        "last_revision": next((str(h.get("note") or "") for h in reversed(rnd.get("history") or [])
                               if isinstance(h, Mapping) and h.get("action") == "REQUEST_REVISION"), ""),
    }


def build_as_drawing_detail(order: Any, sd: Mapping[str, Any], user: Any) -> dict[str, Any]:
    """실행판 AS 카드·맨 위 단추 값(조회 0 — 이미 읽은 structured_data 로만).

    Returns:
        ``as_stage``·``current``·``past``·``open_as``·``can_*`` 키가 늘 있는 dict.
    """
    sd = sd if isinstance(sd, Mapping) else {}
    as_stage = bool(is_as_drawing_stage(order))
    is_partner = bool(getattr(order, "partner_org_id", None))
    drawing_ok = bool(user) and evaluate_policy(POLICY_REGISTRY["DRAWING_TEAM"], user).allowed
    review_ok = bool(user) and evaluate_policy(POLICY_REGISTRY["ERP_EDIT"], user).allowed
    cur = current_round(sd)
    current = _round_brief(sd, cur) if cur else None
    open_as = None
    if open_as_cycle_id(dict(sd)):
        cycle = current_cycle(dict(sd)) or {}
        shipment = sd.get("shipment") if isinstance(sd.get("shipment"), Mapping) else {}
        open_as = {
            "received_date": str(cycle.get("received_date") or ""),
            "content": as_content_html_to_text(shipment.get("as_content") or "")[:300],
            "visit": _visit_text(sd),
        }
    pending_count = 0
    if cur:
        wizard = sd.get("drawing_wizard") if isinstance(sd.get("drawing_wizard"), Mapping) else {}
        pending = wizard.get("pending") if isinstance(wizard.get("pending"), Mapping) else {}
        sheets = set(round_sheet_ids(sd, str(cur.get("round_id") or "")))
        pending_count = len([sid for sid in pending if sid in sheets])
    status = (current or {}).get("status")
    push_as = sd.get("channeltalk_push_as") if isinstance(sd.get("channeltalk_push_as"), Mapping) else {}
    usable = as_stage and not is_partner
    return {
        "as_stage": as_stage,
        "show": bool(usable and (current or drawing_ok or rounds(sd))),
        "current": current,
        "past": [_round_brief(sd, r) for r in rounds(sd) if not cur or r.get("round_id") != cur.get("round_id")],
        "open_as": open_as,
        "pending_count": pending_count,
        "can_start": bool(usable and drawing_ok and cur is None),
        "can_draw": bool(usable and drawing_ok and cur is not None),
        "can_send": bool(usable and drawing_ok and status in (STATUS_IN_PROGRESS, STATUS_RETURNED, STATUS_TRANSFERRED)
                         and pending_count > 0),
        "can_cancel": bool(usable and drawing_ok and status in (STATUS_WAITING, STATUS_IN_PROGRESS)
                           and not (current or {}).get("sent")),
        "can_review": bool(usable and review_ok and status == STATUS_TRANSFERRED),
        "can_room_push": bool(usable and drawing_ok and room_push_round(sd) is not None),
        "can_channel_retry": bool(usable and drawing_ok and current and current.get("registered_as")
                                  and not push_as.get("pushed")),
    }

