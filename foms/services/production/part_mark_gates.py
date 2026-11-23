"""생산 파트 카드 · 공정 칸 쓰기를 막는 까닭 — 순수 판정(설계서 2026-11-23 §4-2 B5′ · §4-6 B4 · §4-7 B11).

쿼리 0 — 주문 ``structured_data`` 와 그 주문 표시 줄만 본다. 카드 쓰기 API(``part_mark_write``)와 공정 칸 API
(``POST /api/orders/<id>/production/steps``)가 같은 함수로 막고, 화면은 같은 글을 그대로 보인다.

=========================  =====  ====================================================================
코드                        상태   언제
=========================  =====  ====================================================================
``HOLD_ACTIVE``             409    보류 중 — 맡기 취소 · 완료 취소만 된다
``DRAWING_REVISING``        409    도면 고치는 중(RETURNED · TRANSFERRED) — 같음
``STEP_SET_BY_HAND``        409    카드를 안 쓴 파트의 공정 칸이 손으로 체크됨 — 그 파트 카드 쓰기
``INSPECT_NOT_READY``       409    그 장 재단 · 엣지 · 조립이 아직 — 검수 맡기 · 완료 · 담당 바꾸기(``left``)
``INSPECT_DONE_FIRST``      409    그 장 검수가 완료 — 앞 파트 완료 취소 · 기본 취소
``PART_USES_CARDS``         409    카드를 쓴 파트에 미완료 장이 있는데 공정 칸 체크(``left``)
``STEP_SET_BY_CARDS``       409    카드로 모두 완료한 파트의 공정 칸 끄기
=========================  =====  ====================================================================

글은 새로 생긴 경우의 새 글이다(지금 화면 글은 그대로 — 승인 때 고친 것 1).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Optional

from foms.services.orders.confirm_drawing_gate import drawing_revision_in_progress
from foms.services.production.part_constants import MARK_STATE_DONE, PART_INSPECT, PRODUCTION_PART_LABELS
from foms.services.production.part_mark_rules import (
    ACTION_DONE,
    ACTION_RELEASE,
    ACTION_TAKE,
    ACTION_TAKEOVER,
    ACTION_UNDO,
    subject_particle,
)
from foms.services.production.part_progress import (
    INSPECT_PREREQ_PARTS,
    cards_used,
    inspect_left,
    marks_by_part,
    part_progress,
)

HOLD_ACTIVE = "HOLD_ACTIVE"
DRAWING_REVISING = "DRAWING_REVISING"
STEP_SET_BY_HAND = "STEP_SET_BY_HAND"
INSPECT_NOT_READY = "INSPECT_NOT_READY"
INSPECT_DONE_FIRST = "INSPECT_DONE_FIRST"
PART_USES_CARDS = "PART_USES_CARDS"
STEP_SET_BY_CARDS = "STEP_SET_BY_CARDS"

HOLD_MESSAGE = "보류된 주문이라 지금은 못 눌러요. 보류가 풀리면 다시 돼요."
REVISING_MESSAGE = "도면을 고치는 중이라 지금은 못 눌러요. 새 도면이 오면 다시 돼요."
#: 카드를 쓴 파트의 공정 칸 체크(승인 때 고친 것 2 — 글자 그대로, 숫자 = 남은 장).
PART_USES_CARDS_MESSAGE = "도면 {left}장이 아직 미완료예요. 남은 도면을 완료하면 자동으로 체크돼요."
STEP_SET_BY_CARDS_MESSAGE = "도면 카드로 완료한 칸이에요. 취소하려면 그 파트 카드에서 [완료 취소]를 눌러요."

#: 보류 · 도면 고치는 중에도 되는 누름(§4-6 '되는 것' — 맡기 취소 · 완료 취소).
ALLOWED_WHILE_BLOCKED: tuple[str, ...] = (ACTION_RELEASE, ACTION_UNDO)
#: 검수 준비가 필요한 누름(§4-7 — 옛 검수 맡기 취소 · 검수 완료 취소는 된다).
INSPECT_READY_ACTIONS: tuple[str, ...] = (ACTION_TAKE, ACTION_DONE, ACTION_TAKEOVER)


@dataclass(frozen=True)
class Gate:
    """막는 까닭 하나 — 응답 상태 · 코드 · 글 · 자료(``data`` 에 코드와 같이 싣는다)."""

    status: int
    code: str
    message: str
    extra: dict[str, Any] = field(default_factory=dict)

    def body(self) -> dict[str, Any]:
        """응답 본문 ``{success: False, data: {code, …extra}, error: 글}``(생산 API 공통 꼴)."""
        return {"success": False, "data": {"code": self.code, **self.extra}, "error": self.message}


class GateRefusal(Exception):
    """주문 쓰기 콜백 안에서 막을 때(잠금 아래 판정) — 부르는 쪽이 되감고 :meth:`Gate.body` 로 답한다."""

    def __init__(self, gate: Gate) -> None:
        super().__init__(gate.message)
        self.gate = gate


def _hold_active(sd: Any) -> bool:
    production = sd.get("production") if isinstance(sd, dict) else None
    hold = production.get("hold") if isinstance(production, dict) else None
    return bool(isinstance(hold, dict) and hold.get("active"))


def order_gate(sd: Any, action: str) -> Optional[Gate]:
    """보류 · 도면 고치는 중이면 카드를 못 누른다(B4) — 맡기 취소 · 완료 취소는 된다.

    Args:
        sd: 잠근 주문의 ``structured_data``.
        action: 누름.

    Returns:
        막히면 :class:`Gate`, 아니면 None.
    """
    if action in ALLOWED_WHILE_BLOCKED:
        return None
    if _hold_active(sd):
        return Gate(409, HOLD_ACTIVE, HOLD_MESSAGE)
    if drawing_revision_in_progress(sd):
        return Gate(409, DRAWING_REVISING, REVISING_MESSAGE)
    return None


def _step(sd: Any, part: str) -> dict[str, Any]:
    production = sd.get("production") if isinstance(sd, dict) else None
    steps = production.get("steps") if isinstance(production, dict) else None
    if not isinstance(steps, list):
        return {}
    return next((s for s in steps if isinstance(s, dict) and s.get("key") == part), {})


def hand_step_gate(sd: Any, marks: Iterable[Any], part: str) -> Optional[Gate]:
    """카드를 한 장도 안 쓴 파트의 공정 칸이 손으로 체크돼 있으면 그 파트 카드 쓰기를 막는다(B5′ 왼쪽 — 칸이 기준).

    Args:
        sd: 잠근 주문의 ``structured_data``.
        marks: 그 주문 표시 줄들(그 파트 줄이 들어 있어야 한다).
        part: 누른 파트.

    Returns:
        막히면 :class:`Gate`(``checked_by`` 를 싣는다), 아니면 None.
    """
    step = _step(sd, part)
    if not step.get("done") or part in cards_used(marks):
        return None
    name = str(step.get("by_name") or "").strip()
    label = PRODUCTION_PART_LABELS[part]
    if name:
        message = f"{subject_particle(name)} 작업 시트에서 {label} 칸을 체크했어요. 다시 해야 하면 {name}에게 말해 주세요."
    else:
        message = f"작업 시트에서 {label} 칸이 체크돼 있어요. 다시 해야 하면 칸을 체크한 사람에게 말해 주세요."
    return Gate(409, STEP_SET_BY_HAND, message, {"part": part, "checked_by": name or None})


def _not_ready_message(left: list[dict[str, Any]]) -> str:
    parts = " · ".join(f"{item['label']}(담당 {item['holder'] or '미정'})" for item in left)
    last = left[-1]["label"]
    particle = subject_particle(last)[len(last):]  # 괄호 앞 파트 이름에 맞춘 토씨(조립이 · 엣지가)
    return f"아직 검수할 수 없어요. {parts}{particle} 미완료예요. 완료되면 검수할 수 있어요."


def _done_first_message(inspector: str, part: str, basic: bool) -> str:
    what = "기본을" if basic else f"{PRODUCTION_PART_LABELS[part]} 완료를"  # 받침에 맞춘 토씨(기본을 · 완료를)
    if not inspector:
        return f"이 장은 검수가 완료됐어요. {what} 취소하려면 먼저 검수 완료를 취소해 주세요."
    return (f"{subject_particle(inspector)} 이 장 검수를 완료했어요. {what} 취소하려면 "
            f"{inspector}에게 검수 완료부터 취소해 달라고 해 주세요.")


def inspect_gate(sd: Any, marks: Iterable[Any], key: str, part: str, action: str, *,
                 undo_basic: bool = False) -> Optional[Gate]:
    """검수 순서(B11) — 장마다. 관리자 · 대신도 똑같이 막힌다.

    * 검수 맡기 · 완료 · 담당 바꾸기 = 그 장 재단 · 엣지 · 조립이 모두 완료여야(``INSPECT_NOT_READY`` + ``left``).
    * 재단 · 엣지 · 조립 완료 취소 · 기본 취소 = 그 장 검수가 완료면 막는다(``INSPECT_DONE_FIRST``).

    Args:
        sd: 잠근 주문의 ``structured_data``.
        marks: 그 주문 **네 파트** 표시 줄.
        key: 누른 장 key.
        part: 누른 파트.
        action: 누름.
        undo_basic: 되돌리기가 기본 취소(BASIC → NONE)인지(글만 가른다).

    Returns:
        막히면 :class:`Gate`, 아니면 None.
    """
    marks = list(marks)
    if part == PART_INSPECT and action in INSPECT_READY_ACTIONS:
        left = inspect_left(sd, marks, key)
        if left:
            return Gate(409, INSPECT_NOT_READY, _not_ready_message(left),
                        {"left": [{"part": item["part"], "holder": item["holder"]} for item in left]})
        return None
    if part in INSPECT_PREREQ_PARTS and action == ACTION_UNDO:
        row = marks_by_part(marks).get(PART_INSPECT, {}).get(key)
        if row is not None and str(getattr(row, "state", "")) == MARK_STATE_DONE:
            inspector = str(getattr(row, "done_by_name", None) or "").strip()
            return Gate(409, INSPECT_DONE_FIRST, _done_first_message(inspector, part, undo_basic),
                        {"inspected_by": inspector or None})
    return None


def step_cell_gate(sd: Any, marks: Iterable[Any], part: str, done: bool) -> Optional[Gate]:
    """공정 칸 손 체크(B5′ 오른쪽 — 카드를 쓴 파트는 카드가 기준).

    * 켤 때: 카드를 쓴 파트에 미완료 장이 1장 이상이면 409 ``PART_USES_CARDS`` + ``left``(쓰기 · 이벤트 없음).
      미완료 0장(확정 도면 0장 포함)이면 지금처럼 켜진다.
    * 끌 때: 카드를 쓴 파트의 지금 장이 모두 카드로 완료면 409 ``STEP_SET_BY_CARDS``(완료 취소는 카드에서).
    * 카드를 안 쓴 파트는 늘 지금 그대로.

    Args:
        sd: 잠근 주문의 ``structured_data``.
        marks: 그 주문 표시 줄들.
        part: 공정 칸 key(= 파트 key).
        done: 켬 여부.

    Returns:
        막히면 :class:`Gate`, 아니면 None.
    """
    progress = part_progress(sd, marks, part)
    if not progress["uses_cards"] or not progress["total_n"]:
        return None
    left = len(progress["left_keys"])
    if done and left:
        return Gate(409, PART_USES_CARDS, PART_USES_CARDS_MESSAGE.format(left=left),
                    {"part": part, "left": left, "total": progress["total_n"]})
    if not done and not left:
        return Gate(409, STEP_SET_BY_CARDS, STEP_SET_BY_CARDS_MESSAGE, {"part": part})
    return None


__all__ = [
    "ALLOWED_WHILE_BLOCKED", "DRAWING_REVISING", "Gate", "GateRefusal", "HOLD_ACTIVE", "INSPECT_DONE_FIRST",
    "INSPECT_NOT_READY", "PART_USES_CARDS", "STEP_SET_BY_CARDS", "STEP_SET_BY_HAND", "hand_step_gate", "inspect_gate",
    "order_gate", "step_cell_gate",
]
