"""PC 공정 칸 → 도면 목록 창 자료(사장님 2026-11-24 "PC 에서도 도면별로 체크, PC 는 감독 성격이 강해 세세한 정보를").

설계서 ``docs/specs/2026-11-23-production-self-claim-and-factory2_SPEC.md`` §4-2(손 체크 두 경우) · §4-5 · §4-6 · §4-7 ·
§4-11 · §5 · §8-4 에 PC 창을 더한다. **순수 계산 · 쿼리 0** — API(``foms/api/production/part_sheet.py``)가 주문 · 표시 줄을
한 번씩 읽어 넘긴다.

* 줄 = 확정 도면 한 장(:func:`resolve_final_drawing_files` 순서 — 도면 판 카드 · 작업 시트와 같은 번호).
* 상태 낱말(2026-11-25 multi-holder §8-2 37 · §8-1): 재단 "안 봄" · 그 밖 "아직" · "작업 필요" · 같이 작업 중 일부 완료 "재단 1/2 완료"
  (+ 작은 글 "김재단 작업 중" — 아직인 사람 모두, Q10 "PC 도면별 창은 모두") · 모두 완료 "재단 완료"(옛 "재단 끝", K4) · "기본" · 손 체크
  "재단 완료 · 박반장" + "작업 시트에서 완료". "1/2 완료" 낱말은 감사 글과 같은 함수(``part_mark_notes.state_words``) 하나. 막힘 글 · 안내 글은 서버
  판정 함수의 글 그대로(:mod:`~foms.services.production.part_card_state` · :mod:`~foms.services.production.part_mark_gates`).
* 줄 글(``lines``)은 서버가 사람마다 만든다(K6) — 작업하는 사람마다 "작업 시작 이시영 · 11/25 08:10", 그 사람 몫을 완료했으면 바로 뒤에
  "완료 이시영 · 11/25 11:30"(대신 완료면 누른 반장 이름). 사람 없는 줄은 지금 글 그대로("담당 미정" — K2 · 기본 · 풀어 쓴 완료 · 손 체크는
  "완료 …"). PC 는 감독용이라 시작한 때 · 완료한 때 · 바뀐 때를 숨기지 않는다("M/D HH:MM", KST) — 태블릿 글은 건드리지 않는다.
* 누름 종류(``act``): 미완료 장 = ``check``([완료 처리] — 쓰기 action ``check`` 한 요청, 빈 장 = 시작 + 완료 · 남이 작업 중 = 남은 사람 몫을
  한 번에 대신 완료, 판결 2), 완료 · 기본 장 = ``uncheck``([완료 취소]), 손으로 통째 체크한 파트는 줄 단추 없이 창 머리 한 단추([모두 완료
  취소] — 공정 칸 끄기 길). 보류 · 도면 고치는 중 · 검수 순서로 막힌 미완료 장은 ``act`` 없음(서버가 늘 409 — 태블릿 판처럼 막힌 표시만,
  2026-11-24 셋째 판). 완료 취소는 막힌 중에도 되므로 그대로. 화면은 이 값만 따른다.
* ``undo_releases``: [완료 취소]가 완료 취소 뒤 시작 취소까지 이을지 — 작업하는 사람이 보는 사람 하나뿐이고 그 몫을 스스로 완료했고 시작한
  때 → 완료한 때가 :data:`UNDO_RELEASE_WINDOW` 안(PC [완료 처리]가 빈 장을 시작 + 완료한 흔적, 서버 UTC 로 견줌)일 때만. 그 밖은 완료 취소만.
"""

from __future__ import annotations

import datetime
from typing import Any, Optional

from foms.services.datetime_kst import parse_datetime_utc
from foms.services.drawing_confirm_cleanup import resolve_final_drawing_files
from foms.services.orders.drawing_factory import has_second_factory, sheet_factory
from foms.services.orders.drawing_fix import blocked
from foms.services.production import mark_crew as mc
from foms.services.production.factory_constants import FACTORIES, factory_label
from foms.services.production.part_board import card_item_text, is_part_thumb_image, other_part_word
from foms.services.production.part_card_state import hand_cell, inspect_block, order_block
from foms.services.production.part_constants import PART_INSPECT, PRODUCTION_PART_LABELS
from foms.services.production.part_holders import HOLDER_NONE
from foms.services.production.part_mark_gates import PART_USES_CARDS_MESSAGE
from foms.services.production.part_mark_notes import state_words
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
#: 제작 회차가 없는 주문(첫 도면을 체크하면 제작 시작도 같이 됨, 설계서 §4-8)의 창 머리 한 줄 — 태블릿 도면 판 확인 창의 지금 글
#: (foms-production-parts-modal.js firstLine)과 같은 글 하나로 쓴다(새 글 안 만듦).
START_NOTE = "이 주문 첫 도면이라 제작 시작도 같이 돼요."
#: [완료 취소]가 시작 취소까지 잇는 문턱 — 같은 사람이 시작한 뒤 이 안에 완료했으면 PC [완료 처리](빈 장 = 시작 + 완료)의 흔적으로 본다(셋째 판 4).
UNDO_RELEASE_WINDOW = datetime.timedelta(minutes=2)


def stamp(value: Any) -> str:
    """DB UTC 시각(naive · ISO 글) → 'M/D HH:MM'(KST). 없거나 못 읽으면 빈 글."""
    aware = parse_datetime_utc(value) if value is not None else None
    return format_step_at_kst(aware.isoformat()) if aware is not None else ""


def _who(head: str, name: Optional[str], at: Any) -> str:
    """'작업 시작 김재단 · 11/24 08:16' · '완료 박반장 · 11/24 15:02'(시각이 없으면 이름까지)."""
    text = f"{head} {(name or '').strip() or '-'}"
    when = stamp(at)
    return f"{text} · {when}" if when else text


def state_word(part: str, state: str, hand: Optional[dict[str, Any]], crew: Any = ()) -> str:
    """상태 칸 글 — 손 체크 "재단 완료 · 박반장" · "작업 필요" · 같이 작업 중 일부 완료 "재단 1/2 완료" · "재단 완료" · "기본" ·
    재단 "안 봄" · 그 밖 "아직"(작업 필요 · 완료 · 기본 낱말은 감사 글과 같은 함수)."""
    if hand:
        return str(hand["text"])
    if state in ("need", "done", "basic"):
        return state_words(part, state.upper(), crew)
    return other_part_word(part, "none")["word"]


def pending_note(state: str, crew: Any) -> Optional[str]:
    """상태 칸 아래 작은 글 — 같이 작업 중 일부만 완료한 장의 아직인 사람 모두("김재단 작업 중" — PC 창은 이름을 다 보인다, Q10)."""
    crew = list(crew)
    left = mc.names(m for m in crew if not mc.is_done(m))
    if state != "need" or not left or len(left) == len(crew):
        return None
    return f"{' · '.join(left)} 작업 중"


def _fallback_row(sd: dict[str, Any]) -> dict[str, str]:
    """도면과 품목을 못 이을 때 쓰는 큰 줄 글(첫 화면 행의 ``v3_product_label`` · ``v3_spec_display`` 와 같은 함수)."""
    first, items = _production_first_item(sd)
    return {"v3_product_label": _production_product_label(items), "v3_spec_display": _production_spec_display(first)}


def _people(crew: Any) -> list[str]:
    """사람마다 한 조각씩(시작한 차례) — "작업 시작 이시영 · 11/25 08:10", 그 사람 몫을 완료했으면 바로 뒤 "완료 이시영 · 11/25 11:30"."""
    out: list[str] = []
    for item in crew:
        out.append(_who("작업 시작", item.get("name"), item.get("at")))
        if mc.is_done(item):
            out.append(_who("완료", item.get("done_name"), item.get("done_at")))
    return out


def _lines(state: str, snap: MarkSnapshot, row: Any, hand: Optional[dict[str, Any]], step_at: Any) -> dict[str, Any]:
    """줄 글(사람마다 — 시각 포함) · 바뀐 기록 줄. 사람 없는 줄은 지금 글("담당 미정" · "완료 …")."""
    if state == "hand":
        lines = [_who("완료", hand.get("name") if hand else None, step_at)]
    elif state == "none":
        lines = [f"담당 {HOLDER_NONE}"]
    elif snap.crew:
        lines = _people(snap.crew)
    elif state in ("done", "basic"):
        lines = [_who("완료", snap.done_by_name, getattr(row, "done_at", None))]
    else:
        lines = []
    handed = None
    if snap.handed_from_name and state != "hand":
        when = stamp(snap.handed_at)
        handed = f"{snap.handed_from_name}에서 바뀜" + (f" {when}" if when else "")
    return {"lines": lines, "handed": handed}


def undo_releases(state: str, snap: MarkSnapshot, viewer_id: Any) -> bool:
    """[완료 취소] 뒤 시작 취소까지 할지 — 작업하는 사람이 보는 사람 하나뿐이고 그 몫을 스스로 완료했고, 시작한 때 → 완료한 때가 2분 안
    (서버 UTC). 같이 작업한 장 · 남이 시작한 장 · 대신 완료한 장은 완료 취소만."""
    crew = snap.crew
    if state != "done" or viewer_id is None or len(crew) != 1:
        return False
    item = crew[0]
    if item.get("uid") != viewer_id or item.get("done_uid") != viewer_id:
        return False
    picked, done = parse_datetime_utc(item.get("at")), parse_datetime_utc(item.get("done_at"))
    return picked is not None and done is not None and datetime.timedelta(0) <= done - picked <= UNDO_RELEASE_WINDOW


def sheet_row(sd: dict[str, Any], entry: dict[str, Any], no: int, of: int, ctx: dict[str, Any]) -> dict[str, Any]:
    """도면 한 장 줄.

    Args:
        sd: 주문 ``structured_data``.
        entry: 확정 도면 항목.
        no: 장 번호(1부터).
        of: 장 수.
        ctx: ``{part, rows(장 key → 그 파트 표시 줄), marks(네 파트), hand, order_block(주문 통째), block_row, fix(도면별 막힘),
            step_at, fallback, viewer_id}``.

    Returns:
        ``{key, no, of, label, item, image, filename, view_url, state, word, note, lines, handed, block, act, seen,
        undo_releases}`` — ``lines`` = 줄 글(사람마다), ``note`` = 상태 칸 아래 작은 글("작업 시트에서 완료" · "김재단 작업 중"),
        ``block`` 은 ``{kind, text, why}``(보류 · 도면 고치는 중 · 검수 전) 또는 None. 막힌 미완료 장은 ``act`` 가 None(단추 없음 —
        막힌 표시만). ``seen`` = 화면이 본 상태([완료 처리] · [완료 취소]가 그대로 보낸다).
    """
    part, key = ctx["part"], entry["key"]
    row = ctx["rows"].get(key)
    snap = MarkSnapshot.from_row(row)
    hand = ctx["hand"]
    state = "hand" if hand else snap.seen_key
    block = None
    if state in ("none", "need"):  # 도면별 막힘(2026-11-25 설계서 §3-3)은 그 장만 — 판 카드와 같은 판정
        block = (ctx["order_block"] or order_block(ctx["block_row"], entry, fix=ctx["fix"])
                 or (inspect_block(sd, ctx["marks"], key) if part == PART_INSPECT else None))
    name, spec = card_item_text(sd, entry, ctx["fallback"])
    act = None if state == "hand" or block else (ACT_UNCHECK if state in ("done", "basic") else ACT_CHECK)
    return {
        "key": key, "no": no, "of": of, "label": f"도면 {no}/{of}",
        "item": f"{name or '품목 없음'}{f' · {spec}' if spec else ''}",
        "image": is_part_thumb_image(entry), "filename": entry.get("filename") or "", "view_url": entry.get("view_url") or "",
        "state": state, "word": state_word(part, state, hand, snap.crew),
        "note": "작업 시트에서 완료" if state == "hand" else pending_note(state, snap.crew),
        **_lines(state, snap, row, hand, ctx["step_at"]),
        "block": {k: block[k] for k in ("kind", "text", "why")} if block else None,
        "act": act, "seen": snap.seen_key, "undo_releases": undo_releases(state, snap, ctx["viewer_id"]),
    }


def _step_at(sd: dict[str, Any], part: str) -> Any:
    production = sd.get("production") if isinstance(sd.get("production"), dict) else {}
    for step in production.get("steps") if isinstance(production.get("steps"), list) else []:
        if isinstance(step, dict) and step.get("key") == part:
            return step.get("at")
    return None


def _factory_rows(sd: dict[str, Any], entries: list[dict[str, Any]], rows: list[dict[str, Any]],
                  writable: tuple[int, ...]) -> None:
    """2공장(설계서 2026-11-23 §4-13 · §8-4) — 섞인 주문은 줄마다 공장(``factory`` · ``factory_label``), 쓸 수 없는 공장 줄은 단추 없음.

    PC 는 감독용이라 두 공장 줄을 모두 자세히 보인다(작업 시작 · 완료 · 바뀜 그대로). 2공장 장이 없고 쓸 수 있는 공장 장뿐이면 아무 칸도
    안 더한다(지금 응답 그대로).
    """
    mixed = has_second_factory(sd)
    for row, entry in zip(rows, entries):
        factory = sheet_factory(sd, entry)
        if mixed:
            row["factory"], row["factory_label"] = factory, factory_label(factory)
        if factory not in writable:
            row["act"], row["other_factory"] = None, True


def build_part_sheet(sd: Any, marks: list[Any], part: str, *, hold_active: bool, viewer_id: Any = None,
                     writable: tuple[int, ...] = FACTORIES) -> dict[str, Any]:
    """한 주문 · 한 파트의 도면 목록 창 자료.

    Args:
        sd: 주문 ``structured_data``(읽기만).
        marks: 그 주문 표시 줄 전부(네 파트 — 검수 순서 판정이 같이 본다).
        part: 파트 key.
        hold_active: 보류 중인지(첫 화면 행과 같은 판정 — ``production.hold.active``).
        viewer_id: 보는 사람 id(``undo_releases`` 판정 — 없으면 늘 거짓).
        writable: 보는 사람이 쓸 수 있는 공장(3단계 — 남의 공장 줄은 ``act`` 없음). 기본 두 공장(지금 그대로).

    Returns:
        ``{part, label, total, done_n, uses_cards, notice, all, hand_off, hand, rows, keys}`` —
        ``notice`` = 카드를 쓴 파트에 남은 장이 있을 때의 안내(공정 칸 체크 거절 글 그대로, 승인 때 고친 것 2),
        ``all`` = [모두 완료 처리]를 보일지(아무도 시작하거나 완료하지 않은 파트 · 칸이 꺼짐 · 장 1장 이상 · 보류 · 도면 고치는 중
        아님), ``hand_off`` = 손으로 통째 체크한 파트(창 머리 한 단추 [모두 완료 취소]로 끈다).
    """
    sd = sd if isinstance(sd, dict) else {}
    entries = resolve_final_drawing_files(sd)
    progress = part_progress(sd, marks, part)
    hand = hand_cell(sd, marks, part)
    left = len(progress["left_keys"])
    block_row = {"hold_active": hold_active, "structured_data": sd}
    ctx = {"part": part, "rows": marks_by_part(marks).get(part, {}), "marks": marks, "hand": hand,
           "order_block": order_block(block_row), "block_row": block_row, "fix": blocked(sd),
           "step_at": _step_at(sd, part), "fallback": _fallback_row(sd), "viewer_id": viewer_id}
    rows = [sheet_row(sd, entry, i + 1, len(entries), ctx) for i, entry in enumerate(entries)]
    _factory_rows(sd, entries, rows, writable)
    return {
        "part": part, "label": PRODUCTION_PART_LABELS[part], "total": len(entries), "done_n": progress["done_n"],
        "uses_cards": progress["uses_cards"],
        "notice": PART_USES_CARDS_MESSAGE.format(left=left) if progress["uses_cards"] and entries and left else None,
        # 보류 · 도면 고치는 중에는 통째 작업(공정 칸 켜기)을 서버가 막는다(사장님 2026-11-24 · 11-25) — [모두 완료 처리]를 안 보인다.
        # [모두 완료 취소](hand_off, 끄기)는 둘 다 된다(서버 step_cell_gate 와 같은 규칙). 도면별 막힘이면 보인다 — 같은 API 가
        # 막힌 장을 빼고 처리한다(2026-11-25 설계서 §3-6 ①)
        "all": bool(entries) and not progress["uses_cards"] and not progress["done"] and not ctx["order_block"],
        "hand_off": bool(hand), "hand": hand["text"] if hand else None,
        "rows": rows, "keys": [entry["key"] for entry in entries],
    }


__all__ = ["ACT_CHECK", "ACT_UNCHECK", "START_NOTE", "UNDO_RELEASE_WINDOW", "build_part_sheet", "pending_note", "sheet_row", "stamp",
           "state_word", "undo_releases"]
