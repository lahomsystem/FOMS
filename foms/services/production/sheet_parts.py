"""작업 시트의 파트 3판 칸 — 공정 칸 옆 진행 글 · [제작 완료] 까닭 · 손 체크 확인 창 자료(설계서 2026-11-23 §4-2 · §8-3).

순수 계산 · 쿼리 0 — 작업 시트 뷰(``production_sheet_view``)가 이미 읽은 그 주문 표시 줄을 넘긴다. 카드를 안 쓴 파트의 칸 옆 글은
지금 글("박반장 · 11/24 10:20") 그대로 두므로 여기서는 카드를 쓴 파트만 글을 만든다(승인 때 고친 것 1 — 새 칸에만 새 글).
"""

from __future__ import annotations

from typing import Any

from foms.services.drawing_confirm_cleanup import resolve_final_drawing_files
from foms.services.production.part_constants import PRODUCTION_PART_KEYS
from foms.services.production.part_progress import complete_block_body, marks_by_part, part_progress
from foms.services.production_home_read_model import format_step_at_kst


def _last_finisher(rows: list[Any]) -> tuple[str, str]:
    """가장 늦게 완료한 줄의 (이름, 'M/D HH:MM')."""
    done = [r for r in rows if getattr(r, "done_at", None) is not None]
    if not done:
        return "", ""
    last = max(done, key=lambda r: r.done_at)
    return str(last.done_by_name or "").strip(), format_step_at_kst(last.done_at.isoformat() + "+00:00")


def step_note(sd: Any, marks: list[Any], part: str) -> dict[str, str] | None:
    """공정 칸 옆 글 하나 — 카드를 쓴 파트만. 미완료 "카드 3/5 · 2장 미완료"(is-miss) · 모두 완료 "카드로 완료 · 김재단 11/24 15:02"(is-ok),
    담당이 바뀐 장이 있으면 끝에 " · 바뀜 n". 카드를 안 쓴 파트 · 확정 도면 0장은 None(지금 글 그대로).
    """
    progress = part_progress(sd, marks, part)
    if not progress["uses_cards"] or not progress["total_n"]:
        return None
    keys = [e["key"] for e in resolve_final_drawing_files(sd if isinstance(sd, dict) else {})]
    rows = [r for k, r in marks_by_part(marks).get(part, {}).items() if k in keys]
    handed = sum(1 for r in rows if getattr(r, "handed_from_name", None))
    tail = f" · 바뀜 {handed}" if handed else ""
    if progress["done"]:
        name, at = _last_finisher(rows)
        who = " ".join(p for p in (name, at) if p)
        return {"text": "카드로 완료" + (f" · {who}" if who else "") + tail, "cls": "is-ok"}
    left = len(progress["left_keys"])
    return {"text": f"카드 {progress['done_n']}/{progress['total_n']} · {left}장 미완료{tail}", "cls": "is-miss"}


def sheet_part_extras(sd: Any, marks: list[Any]) -> dict[str, Any]:
    """작업 시트가 더 그리는 값.

    Returns:
        ``{step_notes: {part: {text, cls}}, complete_why, uses_cards, current_keys}`` — ``complete_why`` 는 카드를 쓴 주문의
        [제작 완료] 막힘 글(서버 거절 글 그대로, 카드를 안 쓴 주문은 빈 글 — 지금 화면 글을 JS 가 그대로 쓴다),
        ``current_keys`` 는 바뀐 기록 목록의 "도면 n/m" 번호용.
    """
    marks = list(marks)
    notes = {part: note for part in PRODUCTION_PART_KEYS if (note := step_note(sd, marks, part))}
    uses = any(m.state != "NONE" for m in marks)
    block = complete_block_body(sd, marks) if uses else None
    return {
        "step_notes": notes,
        "complete_why": (block or {}).get("message", "") if uses else "",
        "uses_cards": uses,
        "current_keys": [e["key"] for e in resolve_final_drawing_files(sd if isinstance(sd, dict) else {})],
    }


__all__ = ["sheet_part_extras", "step_note"]
