"""생산 파트 카드 · 공정 칸 쓰기를 막는 까닭 — 순수 판정(설계서 2026-11-23 §4-2 B5′ · §4-6 B4 · §4-7 B11).

쿼리 0 — 주문 ``structured_data`` 와 그 주문 표시 줄만 본다. 카드 쓰기 API(``part_mark_write``)와 공정 칸 API
(``POST /api/orders/<id>/production/steps``)가 같은 함수로 막고, 화면은 같은 글을 그대로 보인다.

=========================  =====  ====================================================================
코드                        상태   언제
=========================  =====  ====================================================================
``HOLD_ACTIVE``             409    보류 중 — 맡기 취소 · 완료 취소만 된다 · 공정 칸 손 작업 켜기도 막힘(끄기는 됨)
``DRAWING_REVISING``        409    도면 고치는 중(RETURNED · TRANSFERRED) — 같음(공정 칸 손 작업 켜기도 막힘, 사장님 2026-11-25).
                                   생산 단계 도면별 막힘(2026-11-25 설계서 §3-3)은 그 장 누름만 막고 ``numbers`` 를 싣는다
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

from foms.services.drawing_confirm_cleanup import resolve_final_drawing_files
from foms.services.orders.confirm_drawing_gate import drawing_revision_in_progress
from foms.services.orders.drawing_fix import blocked, entry_blocked
from foms.services.production.part_constants import MARK_STATE_DONE, PART_INSPECT, PRODUCTION_PART_LABELS
from foms.services.production import mark_crew as mc
from foms.services.production.part_mark_rules import (
    ACTION_CHECK,
    ACTION_DONE,
    ACTION_JOIN,
    ACTION_RELEASE,
    ACTION_REMOVE,
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
PART_USES_CARDS_MESSAGE = "도면 {left}장이 아직 미완료예요. 남은 도면을 완료하면 자동으로 작업 완료 처리돼요."
STEP_SET_BY_CARDS_MESSAGE = "도면을 모두 완료해서 작업 완료된 공정이에요. 취소하려면 그 파트 도면에서 [되돌리기]를 눌러 주세요."

#: 보류 · 도면 고치는 중에도 되는 누름(§4-6 '되는 것' — 시작 취소 · 완료 취소 · 반장의 남의 시작 취소, multi-holder §7-3 5).
ALLOWED_WHILE_BLOCKED: tuple[str, ...] = (ACTION_RELEASE, ACTION_UNDO, ACTION_REMOVE)
#: 검수 준비가 필요한 누름(§4-7 — 옛 검수 시작 취소 · 검수 완료 취소는 된다). 같이 작업 · PC [완료 처리]도(multi-holder §7-3 9).
INSPECT_READY_ACTIONS: tuple[str, ...] = (ACTION_TAKE, ACTION_DONE, ACTION_TAKEOVER, ACTION_JOIN, ACTION_CHECK)


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


def revising_gate(numbers: list[int], **extra: Any) -> Gate:
    """도면별 막힘 거절 — 지금 글 그대로(``REVISING_MESSAGE``) + 자료 ``numbers``(막힌 장 번호, 설계서 2026-11-25 §4-2)."""
    return Gate(409, DRAWING_REVISING, REVISING_MESSAGE, {**extra, "numbers": numbers})


def order_gate(sd: Any, action: str, entry: Optional[dict[str, Any]] = None) -> Optional[Gate]:
    """보류 · 도면 고치는 중이면 카드를 못 누른다(B4) — 맡기 취소 · 완료 취소는 된다.

    도면 고치는 중: 주문 통째(지금 규칙) 또는 생산 단계 도면별 막힘(2026-11-25 설계서 §3-3)이면 **그 장**(``entry``)만 —
    다른 장은 계속 작업한다(사장님 답 2). 도면별 거절은 자료에 ``numbers``(그 장 번호)를 싣는다.

    Args:
        sd: 잠근 주문의 ``structured_data``.
        action: 누름.
        entry: 누른 장(확정 도면 항목). None 이면 주문 통째 막힘만 본다.

    Returns:
        막히면 :class:`Gate`, 아니면 None.
    """
    if action in ALLOWED_WHILE_BLOCKED:
        return None
    if _hold_active(sd):
        return Gate(409, HOLD_ACTIVE, HOLD_MESSAGE)
    if drawing_revision_in_progress(sd):
        return Gate(409, DRAWING_REVISING, REVISING_MESSAGE)
    if entry is not None and entry_blocked(blocked(sd), entry):
        keys = [e["key"] for e in resolve_final_drawing_files(sd if isinstance(sd, dict) else {})]
        return revising_gate([keys.index(entry["key"]) + 1] if entry.get("key") in keys else [])
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
        message = f"{subject_particle(name)} 작업 시트에서 {label} 칸을 작업 완료 처리했어요. 다시 해야 하면 {name}에게 말해 주세요."
    else:
        message = f"작업 시트에서 {label} 칸이 작업 완료 처리돼 있어요. 다시 해야 하면 처리한 사람에게 말해 주세요."
    return Gate(409, STEP_SET_BY_HAND, message, {"part": part, "checked_by": name or None})


def _not_ready_message(left: list[dict[str, Any]]) -> str:
    """검수 막힘 글 — "재단(이시영 · 김재단 작업 중)" · "엣지(담당 미정)"(multi-holder §8-2 20 · '미정'은 K2 그대로)."""
    parts = " · ".join(f"{item['label']}({item['holder']} 작업 중)" if item["holder"] else f"{item['label']}(담당 미정)"
                       for item in left)
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

    * 검수 시작 · 같이 작업 · 완료 · 담당 바꾸기 · PC [완료 처리] = 그 장 재단 · 엣지 · 조립이 모두 완료여야(``INSPECT_NOT_READY`` +
      ``left``). 같이 작업하는 줄은 모두 완료여야 완료다("재단 1/2 완료" = 미완료 — Q14).
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
            done = mc.done_names(mc.crew_of(row)) or [str(getattr(row, "done_by_name", None) or "").strip()]
            inspector = mc.name_line(done)  # 여러 명이면 "강검수 · 윤검수"(Q20)
            return Gate(409, INSPECT_DONE_FIRST, _done_first_message(inspector, part, undo_basic),
                        {"inspected_by": inspector or None})
    return None


def step_cell_gate(sd: Any, marks: Iterable[Any], part: str, done: bool) -> Optional[Gate]:
    """공정 칸 손 체크(B5′ 오른쪽 — 카드를 쓴 파트는 카드가 기준).

    * 보류 · 도면 고치는 중에 켤 때: 409 ``HOLD_ACTIVE`` · ``DRAWING_REVISING``(사장님 2026-11-24 "보류 중에는 통째 작업도 막기" ·
      2026-11-25 "도면 고치는 중도 보류처럼" — 도면 누름 :func:`order_gate` 와 같은 차례 · 같은 글). 끄기(작업 취소)는 둘 다 된다
      (도면 쪽 :data:`ALLOWED_WHILE_BLOCKED` — 완료 취소 · 맡기 취소 — 와 같은 뜻). 여기 '도면 고치는 중'은 주문 **통째**만이다 —
      도면별 막힘은 막지 않고 공정 API 가 막힌 장을 빼고 풀어 적는다(2026-11-25 설계서 §3-6 ①, ``step_expand.expand_hand_step``).
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
    if done and _hold_active(sd):
        return Gate(409, HOLD_ACTIVE, HOLD_MESSAGE, {"part": part})
    if done and drawing_revision_in_progress(sd):
        return Gate(409, DRAWING_REVISING, REVISING_MESSAGE, {"part": part})
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
    "order_gate", "revising_gate", "step_cell_gate",
]
