"""PC 공정 칸 → 도면 목록 창 자료(사장님 2026-11-24 "PC 에서도 도면별로 체크, PC 는 감독 성격이 강해 세세한 정보를").

설계서 ``docs/specs/2026-11-23-production-self-claim-and-factory2_SPEC.md`` §4-2(손 체크 두 경우) · §4-5 · §4-6 · §4-7 ·
§4-11 · §5 · §8-4 에 PC 창을 더한다. **순수 계산 · 쿼리 0** — API(``foms/api/production/part_sheet.py``)가 주문 · 표시 줄을
한 번씩 읽어 넘긴다.

* 줄 = 확정 도면 한 장(:func:`resolve_final_drawing_files` 순서 — 도면 판 카드 · 작업 시트와 같은 번호).
* 상태 낱말은 도면 판이 쓰는 글 그대로(재단 "안 봄" · 그 밖 "아직" · "작업 필요" · "재단 끝" · "기본" · 손 체크 "재단 완료 · 박반장"
  + "작업 시트"). 막힘 글 · 안내 글도 서버 판정 함수의 글 그대로(:mod:`~foms.services.production.part_card_state` ·
  :mod:`~foms.services.production.part_mark_gates`). 새 글은 칸 이름 "담당" · "완료"(빈 담당 "미정")뿐이다.
* PC 는 감독용이라 맡은 때 · 완료한 때 · 바뀐 때를 숨기지 않는다("M/D HH:MM", KST) — 태블릿 글은 건드리지 않는다.
* 누름 종류(``act``): 미완료 장 = ``check``(완료로 처리), 완료 · 기본 장 = ``uncheck``(완료 취소), 손으로 통째 체크한 파트는
  줄 단추 없이 창 머리 한 단추(공정 칸 끄기 길). 쓸지 말지는 화면 · 서버가 정한다(여기는 자료만).
"""

from __future__ import annotations

from typing import Any, Optional

from foms.services.datetime_kst import parse_datetime_utc
from foms.services.drawing_confirm_cleanup import resolve_final_drawing_files
from foms.services.production.part_board import card_item_text, is_part_thumb_image, other_part_word
from foms.services.production.part_card_state import hand_cell, inspect_block, order_block
from foms.services.production.part_constants import PART_INSPECT, PRODUCTION_PART_LABELS
from foms.services.production.part_holders import HOLDER_NONE
from foms.services.production.part_mark_gates import PART_USES_CARDS_MESSAGE
from foms.services.production.part_mark_rules import MarkSnapshot
from foms.services.production.part_progress import marks_by_part, part_progress
from foms.services.production_dashboard_display import (
    _production_first_item,
    _production_product_label,
    _production_spec_display,
)
from foms.services.production_home_read_model import format_step_at_kst

#: 줄 단추 — 미완료 장을 완료로 처리 · 완료한 장 완료 취소.
ACT_CHECK = "check"
ACT_UNCHECK = "uncheck"


def stamp(value: Any) -> str:
    """DB UTC 시각(naive · ISO 글) → 'M/D HH:MM'(KST). 없거나 못 읽으면 빈 글."""
    aware = parse_datetime_utc(value) if value is not None else None
    return format_step_at_kst(aware.isoformat()) if aware is not None else ""


def _who(head: str, name: Optional[str], at: Any) -> str:
    """'담당 김재단 · 11/24 08:16' · '완료 박반장 · 11/24 15:02'(시각이 없으면 이름까지)."""
    text = f"{head} {(name or '').strip() or '-'}"
    when = stamp(at)
    return f"{text} · {when}" if when else text


def state_word(part: str, state: str, hand: Optional[dict[str, Any]]) -> str:
    """도면 판 글 그대로 — 손 체크 "재단 완료 · 박반장" · "작업 필요" · "재단 끝" · "기본" · 재단 "안 봄" · 그 밖 "아직"."""
    if hand:
        return str(hand["text"])
    if state == "need":
        return "작업 필요"
    if state == "done":
        return f"{PRODUCTION_PART_LABELS[part]} 끝"
    if state == "basic":
        return "기본"
    return other_part_word(part, "none")["word"]


def _fallback_row(sd: dict[str, Any]) -> dict[str, str]:
    """도면과 품목을 못 이을 때 쓰는 큰 줄 글(첫 화면 행의 ``v3_product_label`` · ``v3_spec_display`` 와 같은 함수)."""
    first, items = _production_first_item(sd)
    return {"v3_product_label": _production_product_label(items), "v3_spec_display": _production_spec_display(first)}


def _lines(state: str, snap: MarkSnapshot, row: Any, hand: Optional[dict[str, Any]], step_at: Any) -> dict[str, Any]:
    """담당 · 완료 · 바뀐 기록 줄(시각 포함)."""
    holder = None
    if state == "none":
        holder = f"담당 {HOLDER_NONE}"
    elif state in ("need", "done") and snap.picked_by_name:
        holder = _who("담당", snap.picked_by_name, snap.picked_at)
    done = None
    if state in ("done", "basic"):
        done = _who("완료", snap.done_by_name, getattr(row, "done_at", None))
    elif state == "hand":
        done = _who("완료", hand.get("name") if hand else None, step_at)
    handed = None
    if snap.handed_from_name and state != "hand":
        when = stamp(snap.handed_at)
        handed = f"{snap.handed_from_name}에서 바뀜" + (f" {when}" if when else "")
    return {"holder": holder, "done": done, "handed": handed}


def sheet_row(sd: dict[str, Any], entry: dict[str, Any], no: int, of: int, ctx: dict[str, Any]) -> dict[str, Any]:
    """도면 한 장 줄.

    Args:
        sd: 주문 ``structured_data``.
        entry: 확정 도면 항목.
        no: 장 번호(1부터).
        of: 장 수.
        ctx: ``{part, rows(장 key → 그 파트 표시 줄), marks(네 파트), hand, order_block, step_at, fallback}``.

    Returns:
        ``{key, no, of, label, item, image, filename, view_url, state, word, note, holder, done, handed, block, act, seen,
        seen_by}`` — ``block`` 은 ``{kind, text, why}``(보류 · 도면 고치는 중 · 검수 전) 또는 None.
    """
    part, key = ctx["part"], entry["key"]
    row = ctx["rows"].get(key)
    snap = MarkSnapshot.from_row(row)
    hand = ctx["hand"]
    state = "hand" if hand else snap.seen_key
    block = None
    if state in ("none", "need"):
        block = ctx["order_block"] or (inspect_block(sd, ctx["marks"], key) if part == PART_INSPECT else None)
    name, spec = card_item_text(sd, entry, ctx["fallback"])
    act = None if state == "hand" else (ACT_UNCHECK if state in ("done", "basic") else ACT_CHECK)
    return {
        "key": key, "no": no, "of": of, "label": f"도면 {no}/{of}",
        "item": f"{name or '품목 없음'}{f' · {spec}' if spec else ''}",
        "image": is_part_thumb_image(entry), "filename": entry.get("filename") or "", "view_url": entry.get("view_url") or "",
        "state": state, "word": state_word(part, state, hand), "note": "작업 시트" if state == "hand" else None,
        **_lines(state, snap, row, hand, ctx["step_at"]),
        "block": {k: block[k] for k in ("kind", "text", "why")} if block else None,
        "act": act, "seen": snap.seen_key, "seen_by": snap.picked_by_user_id,
    }


def _step_at(sd: dict[str, Any], part: str) -> Any:
    production = sd.get("production") if isinstance(sd.get("production"), dict) else {}
    for step in production.get("steps") if isinstance(production.get("steps"), list) else []:
        if isinstance(step, dict) and step.get("key") == part:
            return step.get("at")
    return None


def build_part_sheet(sd: Any, marks: list[Any], part: str, *, hold_active: bool) -> dict[str, Any]:
    """한 주문 · 한 파트의 도면 목록 창 자료.

    Args:
        sd: 주문 ``structured_data``(읽기만).
        marks: 그 주문 표시 줄 전부(네 파트 — 검수 순서 판정이 같이 본다).
        part: 파트 key.
        hold_active: 보류 중인지(첫 화면 행과 같은 판정 — ``production.hold.active``).

    Returns:
        ``{part, label, total, done_n, uses_cards, notice, all, hand_off, hand, rows, keys}`` —
        ``notice`` = 카드를 쓴 파트에 남은 장이 있을 때의 안내(공정 칸 체크 거절 글 그대로, 승인 때 고친 것 2),
        ``all`` = [모두 체크]를 보일지(아무도 맡거나 완료하지 않은 파트 · 칸이 꺼짐 · 장 1장 이상),
        ``hand_off`` = 손으로 통째 체크한 파트(창 머리 한 단추로 끈다).
    """
    sd = sd if isinstance(sd, dict) else {}
    entries = resolve_final_drawing_files(sd)
    progress = part_progress(sd, marks, part)
    hand = hand_cell(sd, marks, part)
    left = len(progress["left_keys"])
    ctx = {"part": part, "rows": marks_by_part(marks).get(part, {}), "marks": marks, "hand": hand,
           "order_block": order_block({"hold_active": hold_active, "structured_data": sd}),
           "step_at": _step_at(sd, part), "fallback": _fallback_row(sd)}
    rows = [sheet_row(sd, entry, i + 1, len(entries), ctx) for i, entry in enumerate(entries)]
    return {
        "part": part, "label": PRODUCTION_PART_LABELS[part], "total": len(entries), "done_n": progress["done_n"],
        "uses_cards": progress["uses_cards"],
        "notice": PART_USES_CARDS_MESSAGE.format(left=left) if progress["uses_cards"] and entries and left else None,
        "all": bool(entries) and not progress["uses_cards"] and not progress["done"],
        "hand_off": bool(hand), "hand": hand["text"] if hand else None,
        "rows": rows, "keys": [entry["key"] for entry in entries],
    }


__all__ = ["ACT_CHECK", "ACT_UNCHECK", "build_part_sheet", "sheet_row", "stamp", "state_word"]
