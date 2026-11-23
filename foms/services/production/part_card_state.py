"""파트 카드 한 장의 3판 상태 — 막힘 · 손 체크 · 밤 넘김 · 바뀐 기록 · 내 담당 꼬리 · 판 순서(설계서 2026-11-23 §4-6 · §4-9 ·
§4-11 · §8-1). 순수 계산 · 쿼리 0 — :mod:`foms.services.production.part_board` 가 이미 읽은 행 · 표시 줄을 넘긴다.

막는 판정은 쓰기 API 와 같은 함수(:mod:`foms.services.production.part_mark_gates`)를 그대로 부르고 그 글을 까닭 말풍선에
쓴다 — 화면 글과 서버 거절 글이 늘 같다. 지금 화면 글(``[내가 엣지]`` · "박엣지 맡음" · "작업 필요 · 김재단" 등)은 여기서
만들지 않는다(템플릿 그대로, 승인 때 고친 것 1). 여기 글은 새 칸의 글뿐이다.
"""

from __future__ import annotations

import datetime
from typing import Any, Optional

from foms.services.orders.confirm_drawing_gate import drawing_revision_in_progress
from foms.services.production.part_constants import PART_INSPECT, PRODUCTION_PART_LABELS
from foms.services.production.part_holders import handed_text, since_text
from foms.services.production.part_mark_gates import (
    DRAWING_REVISING,
    HOLD_ACTIVE,
    REVISING_MESSAGE,
    HOLD_MESSAGE,
    hand_step_gate,
    inspect_gate,
)
from foms.services.production.part_mark_rules import MarkSnapshot
from foms.services.production.part_progress import inspect_left

#: 막힌 칸 종류 → CSS 꼴(``.fph-wi.pp-st-*``).
BLOCK_HOLD = "hold"
BLOCK_REVISE = "revise"
BLOCK_PRE = "pre"


def _hold_reason(sd: Any) -> str:
    production = sd.get("production") if isinstance(sd, dict) else None
    hold = production.get("hold") if isinstance(production, dict) else None
    reason = hold.get("reason") if isinstance(hold, dict) else None
    return reason.strip() if isinstance(reason, str) else ""


def order_block(row: dict[str, Any]) -> Optional[dict[str, str]]:
    """주문 전체가 막혔는지(B4) — 보류 · 도면 고치는 중. 칸 글 · 까닭 글 · 서버 코드.

    Args:
        row: 첫 화면 행(``hold_active`` · ``structured_data``).

    Returns:
        ``{kind, text, why, code}`` 또는 None. 보류 글은 "보류 · 자재 기다림"(사유 없으면 "보류").
    """
    sd = row.get("structured_data") or {}
    if row.get("hold_active"):
        reason = _hold_reason(sd)
        return {"kind": BLOCK_HOLD, "text": f"보류 · {reason}" if reason else "보류", "why": HOLD_MESSAGE,
                "code": HOLD_ACTIVE}
    if drawing_revision_in_progress(sd):
        return {"kind": BLOCK_REVISE, "text": "도면 고치는 중", "why": REVISING_MESSAGE, "code": DRAWING_REVISING}
    return None


def inspect_block(sd: Any, marks: list[Any], key: str) -> Optional[dict[str, str]]:
    """검수 카드가 아직 못 열리는지(B11) — 그 장 재단 · 엣지 · 조립 중 미완료가 있으면 "엣지 · 조립 미완료".

    까닭 글은 쓰기 API 의 거절 글 그대로(:func:`inspect_gate`).
    """
    left = inspect_left(sd, marks, key)
    if not left:
        return None
    gate = inspect_gate(sd, marks, key, PART_INSPECT, "take")
    text = " · ".join(item["label"] for item in left) + " 미완료"
    return {"kind": BLOCK_PRE, "text": text, "why": gate.message if gate else "", "code": gate.code if gate else ""}


def hand_cell(sd: Any, marks: list[Any], part: str) -> Optional[dict[str, str]]:
    """카드를 한 장도 안 쓴 파트의 공정 칸이 손으로 체크돼 있으면 그 파트 모든 장이 완료(B5′ 왼쪽).

    Returns:
        ``{text: "재단 완료 · 박반장", name, why}`` 또는 None. 까닭 글은 쓰기 API 거절 글 그대로(:func:`hand_step_gate`).
    """
    gate = hand_step_gate(sd, marks, part)
    if gate is None:
        return None
    name = str(gate.extra.get("checked_by") or "")
    label = PRODUCTION_PART_LABELS[part]
    return {"text": f"{label} 완료 · {name}" if name else f"{label} 완료", "name": name, "why": gate.message}


def claim_notes(snap: MarkSnapshot, today: datetime.date, *, mine: bool) -> dict[str, Any]:
    """밤 넘김 · 바뀐 기록 글(B3 · B12) — 남의 담당 칸 둘째 줄과 내 카드 다른 파트 줄 꼬리.

    Args:
        snap: 그 장 · 그 파트 표시 모습.
        today: KST 오늘.
        mine: 내가 담당인 장인지(꼬리 "내 담당 …").

    Returns:
        ``{old, handed, held_note, tag}`` — ``held_note`` = 남의 담당 칸 둘째 줄("김민준에서 바뀜 14:20" · "어제부터"),
        ``tag`` = 내 카드 꼬리 ``{old, chg, aria}``(내 담당이 아니면 None).
    """
    need = snap.seen_key == "need"
    old = since_text(snap.picked_at, today) if need else ""
    handed = handed_text(snap.handed_from_name, snap.handed_at, today) if snap.handed_from_name else ""
    tag = None
    if mine and need:
        chg = f"{snap.handed_from_name}에서 바뀜" if snap.handed_from_name else ""
        tag = {"old": old if not chg else "", "chg": chg,
               "aria": " · ".join(p for p in ("내 담당", old, handed) if p)}
    return {"old": old, "handed": handed, "held_note": (handed or old) if need else "", "tag": tag}


def sort_rank(card: dict[str, Any], part: str) -> int:
    """판 순서(§8-1 '판 순서') — 모든 파트 남은 일 앞 · 완료 뒤.

    재단 · 엣지 · 조립: 미정 → 담당 → 완료. 검수: 검수 할 수 있음(미정) → 담당 → 검수 전(앞 파트 미완료) → 완료.
    """
    state = card["state"]
    if state in ("done", "basic", "hand"):
        return 3
    if state == "need":
        return 1
    if part == PART_INSPECT and card.get("block") and card["block"]["kind"] == BLOCK_PRE:
        return 2
    return 0


__all__ = ["BLOCK_HOLD", "BLOCK_PRE", "BLOCK_REVISE", "claim_notes", "hand_cell", "inspect_block", "order_block",
           "sort_rank"]
