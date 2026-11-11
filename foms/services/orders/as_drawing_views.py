"""완료 주문 AS 도면 — 화면·채널톡에 보여 줄 값(순수 계산, 조회 0).

규칙(차수 열기·잠금·전달·확인)은 :mod:`foms.services.orders.as_drawing` 가 정본이고, 이 모듈은 그 값을
마법사 설정 · 도면방 본문 · AS 화면 상태 글로 바꾼다. 설계서 ``docs/specs/2026-11-11-as-drawing-after-completion_SPEC.md``.
"""
from __future__ import annotations

from typing import Any, Mapping, Optional

from foms.services.orders.as_cycle_service import current_cycle
from foms.services.orders.as_drawing import (
    SHEET_ROUND_KEY,
    STATUS_CONFIRMED,
    STATUS_IN_PROGRESS,
    STATUS_RETURNED,
    STATUS_TRANSFERRED,
    STATUS_WAITING,
    _clean_text,
    _sheets,
    current_round,
    is_as_drawing_stage,
    open_as_cycle_id,
    round_no,
    rounds,
)

__all__ = ["ROOM_PUSH_HISTORY_KEY", "room_push_round", "room_push_text", "status_text", "wizard_config_view"]


def wizard_config_view(order: Any, sd: Mapping) -> Optional[dict]:
    """마법사 화면(wizard-as.js)이 쓰는 값. 시공이 끝난 주문이 아니면 None.

    ``locked_sheet_ids`` = 지금 저장돼 있는 시트 중 열린 차수 시트가 아닌 것(원래·지난 차수).
    열린 차수가 있으면 그 밖의 시트(새로 만든 시트 포함)는 AS 시트다 — 서버가 저장 때 표시를 붙인다.
    """
    if not is_as_drawing_stage(order):
        return None
    cur = current_round(sd)
    open_id = cur.get("round_id") if cur else None
    cycle = current_cycle(sd if isinstance(sd, dict) else {}) if open_as_cycle_id(sd) else None
    schedule = sd.get("schedule") if isinstance(sd.get("schedule"), Mapping) else {}
    construction = schedule.get("construction") if isinstance(schedule.get("construction"), Mapping) else {}
    return {
        "round": None if cur is None else {
            "round_id": open_id,
            "no": round_no(sd, cur),
            "status": cur.get("status"),
            "opened_at": str(cur.get("opened_at") or "")[:10],
            "memo": cur.get("memo") or "",
        },
        "as_received_date": str((cycle or {}).get("received_date") or ""),
        "original_construction_date": str(construction.get("date") or ""),
        "locked_sheet_ids": [str(s.get("id")) for s in _sheets(sd)
                             if s.get("id") and (not open_id or s.get(SHEET_ROUND_KEY) != open_id)],
    }


_STATUS_TEXT = {
    STATUS_WAITING: "도면팀 대기중",
    STATUS_IN_PROGRESS: "도면팀 작업중",
    STATUS_TRANSFERRED: "왔어요",
    STATUS_RETURNED: "고쳐 달라고 함",
    STATUS_CONFIRMED: "확인함",
}


def status_text(sd: Any) -> str:
    """AS 화면 'AS도면' 칸 옆 한 줄 — ``AS 도면 1차 · 왔어요``. 차수가 없거나 그만뒀으면 빈 글."""
    if not isinstance(sd, Mapping):
        return ""
    rnd = current_round(sd)
    if rnd is None:
        items = [r for r in rounds(sd) if r.get("status") == STATUS_CONFIRMED]
        rnd = items[-1] if items else None
    if rnd is None:
        return ""
    label = _STATUS_TEXT.get(str(rnd.get("status") or ""), "")
    return f"AS 도면 {round_no(sd, rnd)}차 · {label}" if label else ""


#: AS 도면 도면방 PUSH 이력 키 — 원래 도면 도면방 이력(``channeltalk_push_drawing_room``)과 섞지 않는다.
ROOM_PUSH_HISTORY_KEY = "channeltalk_push_as_drawing_room"


def room_push_round(sd: Mapping) -> Optional[dict]:
    """도면방으로 보낼 AS 차수 — 보낸 파일이 있는 열린 차수, 없으면 마지막 확인한 차수(D4)."""
    cur = current_round(sd)
    if cur is not None and cur.get("files"):
        return cur
    for rnd in reversed(rounds(sd)):
        if rnd.get("status") == STATUS_CONFIRMED and rnd.get("files"):
            return rnd
    return None


def room_push_text(customer_text: str, sd: Mapping, rnd: Mapping) -> str:
    """도면방 본문 — ``[AS] 고객 · AS 도면 N차`` 와 무엇을 그렸는지 한 줄(설계서 D4)."""
    head = f"[AS] {customer_text} · AS 도면 {round_no(sd, rnd)}차".strip()
    memo = _clean_text(rnd.get("memo"), 200)
    return "\n".join([head, memo]) if memo else head
