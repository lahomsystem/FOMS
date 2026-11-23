"""생산 파트 진행 — 카드를 쓴 파트 · 파트 실제 완료 · 제작 완료 될 수 있나 · 검수 준비됨(설계서 2026-11-23 §4-1 ~ §4-3 · §4-7).

**순수 계산 · 쿼리 0** — 부르는 쪽이 그 주문의 표시 줄(``ProductionPartMark`` ORM 줄 또는 같은 모양 — ``part`` ·
``drawing_key`` · ``state`` · ``picked_by_name`` 을 읽는다)을 넘긴다. 제작 완료 API · 일반 단계 쓰기(단건 · 일괄 · 칸 고치기) ·
작업 시트 · 공정 API · 파트 카드 쓰기가 모두 이 모듈 하나로 판정한다(같은 주문에 같은 답).

낱말(§4-1):

* **카드를 쓴 파트** = 그 파트 표시 줄 중 상태가 NONE 이 아닌 줄이 하나라도 있다(옛 판 key 줄 포함). 맡았다 취소해
  NONE 만 남으면 안 쓴 것이다.
* **장이 완료됐다** = 재단은 DONE · BASIC, 그 밖 파트는 DONE.
* **파트가 실제로 완료됐다** = 카드를 쓴 파트면 지금 확정 도면 장이 모두 완료, 카드를 안 쓴 파트면 그 파트 공정 칸이
  체크됨. 지금 장이 0장이면 카드를 썼어도 칸이 기준이다(§4-3 끝).

``factory`` 인자는 3단계(2공장, §4-14)를 위해 자리만 둔다 — 지금은 한 공장 주문만 판정하고, 공장을 주면 바로 알린다.
"""

from __future__ import annotations

from typing import Any, Iterable, Optional

from foms.services.drawing_confirm_cleanup import resolve_final_drawing_files
from foms.services.production.part_constants import (
    BASIC_ALLOWED_PART,
    MARK_STATE_BASIC,
    MARK_STATE_DONE,
    MARK_STATE_NEED,
    MARK_STATE_NONE,
    PART_ASSEMBLE,
    PART_CUT,
    PART_EDGE,
    PRODUCTION_PART_KEYS,
    PRODUCTION_PART_LABELS,
)
from foms.services.production.steps import (
    PRODUCTION_STEP_DEFS,
    STEPS_INCOMPLETE_CODE,
    production_complete_block_body,
    production_steps_missing,
    step_done_map,
)

#: 검수 앞 파트(§4-7 — 그 장의 이 셋이 완료돼야 검수를 맡는다).
INSPECT_PREREQ_PARTS: tuple[str, ...] = (PART_CUT, PART_EDGE, PART_ASSEMBLE)
#: 카드를 쓴 주문의 막힘 글 머리(새 글, §4-3) — 뒤에 "재단 1장 · 검수 3장".
CARDS_LEFT_MESSAGE = "아직 미완료가 있어요"
#: 카드를 쓴 주문인데 지금 확정 도면이 0장(새 글, §4-3 끝) — 칸이 기준이다.
NO_DRAWINGS_MESSAGE = "도면이 없어요 — 공정 칸을 체크하거나 관리자에게 말해 주세요."


def _single_factory(factory: Optional[int]) -> None:
    """공장별 판정은 3단계에서 — 지금 공장을 넘기면 조용히 무시하지 않고 알린다."""
    if factory is not None:
        raise NotImplementedError("공장별 판정은 2공장 단계(P3)에서 연다 — 지금은 한 공장 주문만 판정한다.")


def mark_finished(part: str, state: Optional[str]) -> bool:
    """장 하나가 그 파트에서 완료인지 — 재단은 DONE · BASIC, 그 밖 파트는 DONE.

    Args:
        part: 파트 key.
        state: 표시 상태(None = 줄 없음).

    Returns:
        완료면 True.
    """
    if part == BASIC_ALLOWED_PART:
        return state in (MARK_STATE_DONE, MARK_STATE_BASIC)
    return state == MARK_STATE_DONE


def cards_used(marks: Iterable[Any]) -> set[str]:
    """카드를 쓴 파트들 — 상태가 NONE 이 아닌 표시 줄이 하나라도 있는 파트(옛 판 key 줄 포함).

    Args:
        marks: 한 주문의 표시 줄들.

    Returns:
        파트 key 집합.
    """
    return {str(getattr(m, "part", "")) for m in marks
            if getattr(m, "part", None) in PRODUCTION_PART_KEYS
            and str(getattr(m, "state", None) or MARK_STATE_NONE) != MARK_STATE_NONE}


def current_keys(sd: Any, *, factory: Optional[int] = None) -> list[str]:
    """지금 확정 도면 장 key 들(화면 순서) — :func:`resolve_final_drawing_files` 하나."""
    _single_factory(factory)
    return [entry["key"] for entry in resolve_final_drawing_files(sd if isinstance(sd, dict) else {})]


def marks_by_part(marks: Iterable[Any]) -> dict[str, dict[str, Any]]:
    """파트 → (장 key → 표시 줄). 모르는 파트는 버린다."""
    out: dict[str, dict[str, Any]] = {}
    for mark in marks:
        part = getattr(mark, "part", None)
        if part in PRODUCTION_PART_KEYS:
            out.setdefault(str(part), {})[str(getattr(mark, "drawing_key", "") or "")] = mark
    return out


def _stored_step(sd: Any, part: str) -> dict[str, Any]:
    production = sd.get("production") if isinstance(sd, dict) else None
    steps = production.get("steps") if isinstance(production, dict) else None
    for step in steps if isinstance(steps, list) else []:
        if isinstance(step, dict) and step.get("key") == part:
            return step
    return {}


def part_progress(sd: Any, marks: Iterable[Any], part: str, *, factory: Optional[int] = None) -> dict[str, Any]:
    """한 파트의 진행 — 날짜 줄 "재단 3/5" · 작업 시트 "카드 3/5 · 2장 미완료" · 막힘 ``left`` 가 같은 값을 쓴다.

    Args:
        sd: 주문 ``structured_data``(읽기만).
        marks: 그 주문 표시 줄들(네 파트 섞여도 된다).
        part: 파트 key.
        factory: 3단계 자리(지금은 None 만).

    Returns:
        ``{uses_cards, done, done_n, total_n, left_keys, via}`` — ``via`` 는 저장된 공정 칸의 표지
        (``'sheet'`` · ``'part_marks'`` · 옛 칸이면 None). 카드를 안 쓴 파트는 칸이 체크됐으면 모든 장이 완료다.
    """
    marks = list(marks)
    keys = current_keys(sd, factory=factory)
    uses = part in cards_used(marks)
    step_on = step_done_map(sd).get(part, False)
    via = _stored_step(sd, part).get("via") if step_on else None
    if uses and keys:
        rows = marks_by_part(marks).get(part, {})
        left = [k for k in keys if not mark_finished(part, getattr(rows.get(k), "state", None))]
        done = not left
    else:  # 카드를 안 쓴 파트 · 지금 장 0장 = 칸이 기준
        left = [] if step_on else list(keys)
        done = step_on
    return {"uses_cards": uses, "done": done, "done_n": len(keys) - len(left), "total_n": len(keys),
            "left_keys": left, "via": via}


def part_done(sd: Any, marks: Iterable[Any], part: str, *, factory: Optional[int] = None) -> bool:
    """파트가 실제로 완료됐는지(§4-1) — 제작 완료 · 검수 순서 · 날짜 줄이 같이 쓰는 한 함수."""
    return bool(part_progress(sd, marks, part, factory=factory)["done"])


def complete_state(sd: Any, marks: Iterable[Any], *, factory: Optional[int] = None) -> dict[str, Any]:
    """[제작 완료]를 누를 수 있는지(§4-3 — 한 공장 주문).

    * 카드를 안 쓴 주문은 지금 규칙 그대로(:func:`production_steps_missing` — 칸을 하나도 안 켰으면 막지 않고,
      하나라도 켰으면 4칸 모두).
    * 카드를 쓴 주문은 네 파트가 모두 '실제 완료'여야 한다(카드 · 손 체크 섞여도 된다). 칸을 안 켜도 막는다.

    Args:
        sd: 주문 ``structured_data``(읽기만).
        marks: 그 주문 표시 줄들(없으면 빈 것 — 카드를 안 쓴 주문).
        factory: 3단계 자리(지금은 None 만).

    Returns:
        ``{ready, left: {part: 남은 장 수}, missing_steps: [{key, label}], uses_cards, sheets}``.
    """
    marks = list(marks)
    sheets = len(current_keys(sd, factory=factory))
    if not cards_used(marks):
        missing = production_steps_missing(sd)
        return {"ready": not missing, "left": {m["key"]: sheets for m in missing}, "missing_steps": missing,
                "uses_cards": False, "sheets": sheets}
    missing, left = [], {}
    for part, label in PRODUCTION_STEP_DEFS:
        progress = part_progress(sd, marks, part, factory=factory)
        if not progress["done"]:
            missing.append({"key": part, "label": label})
            left[part] = len(progress["left_keys"])
    return {"ready": not missing, "left": left, "missing_steps": missing, "uses_cards": True, "sheets": sheets}


def complete_ready(sd: Any, marks: Iterable[Any]) -> bool:
    """[제작 완료]를 누를 수 있는지 — 제작 완료 API · 일반 단계 쓰기 · 작업 시트 · 공정 API 가 같이 쓰는 한 판정."""
    return bool(complete_state(sd, marks)["ready"])


def complete_block_body(sd: Any, marks: Iterable[Any]) -> Optional[dict[str, Any]]:
    """[제작 완료]가 막히면 거절 본문(409 로 보낼 것), 되면 None — :func:`complete_state` 하나로.

    카드를 안 쓴 주문은 지금 글 · 꼴 그대로(:func:`~foms.services.production.steps.production_complete_block_body` 를
    부른다 — "검수까지 끝나야 … (남은 공정: …)"). 카드를 쓴 주문은 같은 꼴 ``{success, code, message, missing_steps}`` 에
    ``left`` 를 더하고 글은 "아직 미완료가 있어요 — 재단 1장 · 검수 3장", 확정 도면이 0장이면 "도면이 없어요 — …".

    Args:
        sd: 주문 ``structured_data``(읽기만).
        marks: 그 주문 표시 줄들(비면 카드를 안 쓴 주문).
    """
    marks = list(marks)
    state = complete_state(sd, marks)
    if state["ready"]:
        return None
    if not state["uses_cards"]:
        return production_complete_block_body(sd)
    missing = state["missing_steps"]
    if not state["sheets"]:
        message = NO_DRAWINGS_MESSAGE
    else:
        message = f"{CARDS_LEFT_MESSAGE} — " + " · ".join(f"{m['label']} {state['left'][m['key']]}장" for m in missing)
    return {"success": False, "code": STEPS_INCOMPLETE_CODE, "message": message, "missing_steps": missing,
            "left": state["left"]}


def inspect_left(sd: Any, marks: Iterable[Any], key: str) -> list[dict[str, Any]]:
    """장 ``key`` 의 검수 앞 파트 중 아직 미완료인 것(§4-7) — 비면 검수 준비됨.

    카드를 쓴 파트는 그 장의 표시로, 카드를 안 쓴 파트는 공정 칸 체크로 본다(칸이 체크됐으면 모든 장 완료).

    Returns:
        ``[{part, label, holder}]`` — ``holder`` 는 그 장 담당 이름(맡은 사람이 없으면 None = 미정).
    """
    marks = list(marks)
    used = cards_used(marks)
    rows = marks_by_part(marks)
    done = step_done_map(sd)
    out: list[dict[str, Any]] = []
    for part in INSPECT_PREREQ_PARTS:
        row = rows.get(part, {}).get(key)
        state = str(getattr(row, "state", None) or MARK_STATE_NONE)
        finished = mark_finished(part, state) if part in used else done.get(part, False)
        if not finished:
            holder = getattr(row, "picked_by_name", None) if state == MARK_STATE_NEED else None
            out.append({"part": part, "label": PRODUCTION_PART_LABELS[part], "holder": holder or None})
    return out


def inspect_ready(sd: Any, marks: Iterable[Any], key: str) -> bool:
    """장 ``key`` 를 검수할 수 있는지 — 재단 · 엣지 · 조립이 그 장에서 모두 완료(§4-7)."""
    return not inspect_left(sd, marks, key)


def parts_progress(sd: Any, marks: Iterable[Any]) -> dict[str, dict[str, Any]]:
    """네 파트 진행을 한 번에 — 공정 API · 작업 시트가 화면에 싣는 값(``left_keys`` 는 뺀 수만)."""
    marks = list(marks)
    out: dict[str, dict[str, Any]] = {}
    for part in PRODUCTION_PART_KEYS:
        progress = part_progress(sd, marks, part)
        out[part] = {k: progress[k] for k in ("uses_cards", "done", "done_n", "total_n", "via")}
        out[part]["left_n"] = len(progress["left_keys"])
    return out


def step_api_extras(sd: Any, marks: Iterable[Any]) -> dict[str, Any]:
    """공정 API · 작업 시트가 더 싣는 값 — 확정 도면 장 수(반장 손 체크 확인 창 "도면 5장이 모두 …") · 파트 진행.

    Returns:
        ``{sheets, parts: {part: {uses_cards, done, done_n, total_n, left_n, via}}}``.
    """
    marks = list(marks)
    return {"sheets": len(current_keys(sd)), "parts": parts_progress(sd, marks)}
