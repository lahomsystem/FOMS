"""도면별 공장 진행 · 보내기 전 경고 글(설계서 2026-11-25 §2-3 · R1 — D2 가 만들고 D3 작업실 상세가 부른다). 순수 계산(쿼리 0).

* 파트마다 상태(:func:`drawing_parts`) — 표시 줄 ``DONE`` → 완료, 재단 ``BASIC`` → 기본, ``NEED`` + 작업하는 사람 → 작업 중, 손 처리
  (카드 0장 · 공정 칸 켜짐 — ``drawing_factory.hand_checked_parts``) → 완료(이름 = 칸을 켠 사람), 그 도면 공장이 제작 완료면 남은 파트도
  완료로 본다(``drawing_factory.factory_made`` — 시공 대기 뒤는 모든 공장 완료).
* "작업이 닿음"(§2-3) = 완료 · 기본 · 작업 중 파트가 하나라도 있거나 그 도면 공장이 제작 완료.
* 경고 글(§10 '보내기 전 확인 창'): 완료가 있으면 완료 문장 하나(풀이 §11-7), 아니면 작업 중 문장 — 그 아래 진행 줄
  "도면 2 · 재단 완료 · 엣지 작업 중". 같이 작업하면 이름은 둘까지 + "외 n"("박엣지 · 최엣지 외 1" — 2026-11-25 multi-holder Q20).
"""

from __future__ import annotations

from typing import Any, Iterable, Optional

from foms.services.orders.drawing_factory import factory_made, hand_checked_parts, sheet_factory
from foms.services.orders.drawing_fix import (
    REQUEST_OPEN,
    WHY_FIXING,
    WHY_SALES,
    blocked,
    fix_ident,
    number_topic,
    request_checked,
    request_left,
)
from foms.services.production import mark_crew as mc
from foms.services.production.part_constants import (
    MARK_STATE_BASIC,
    MARK_STATE_DONE,
    MARK_STATE_NEED,
    PRODUCTION_PART_KEYS,
    PRODUCTION_PART_LABELS,
)
from foms.services.production.part_mark_rules import subject_particle
from foms.services.production.part_progress import marks_by_part

#: 파트 상태 낱말(R1 자료 · 화면이 읽는다).
DONE, BASIC, WORKING, NONE = "done", "basic", "working", "none"
AGAIN = "보내면 공장에서 다시 작업해야 합니다."
ORDER_MADE_TEXT = "이미 제작 완료된 주문입니다. 보내면 공장에 도면 바뀜 알림이 갑니다."
ORDER_MADE_LINE = "주문은 시공 대기 그대로예요."


def _step_names(sd: Any) -> dict[str, Optional[str]]:
    production = sd.get("production") if isinstance(sd, dict) else None
    steps = production.get("steps") if isinstance(production, dict) else None
    return {str(s.get("key")): s.get("by_name") for s in steps or [] if isinstance(s, dict)}


def drawing_parts(entry: dict[str, Any], rows: dict[str, dict[str, Any]], *, hand_parts: Iterable[str],
                  step_names: dict[str, Optional[str]], made: bool) -> dict[str, dict[str, Any]]:
    """도면 한 장의 파트마다 ``{state, name}``(``state`` ∈ done · basic · working · none, ``name`` = 이름 줄 — 같이 작업하면
    "박엣지 · 최엣지 외 1", 완료는 완료한 사람들).

    Args:
        entry: 확정 도면 항목. rows: :func:`~foms.services.production.part_progress.marks_by_part` 값.
        hand_parts: 손 처리한 파트. step_names: 공정 칸을 켠 사람 이름. made: 그 도면 공장이 제작 완료인지.
    """
    hands = set(hand_parts)
    out = {}
    for part in PRODUCTION_PART_KEYS:
        row = rows.get(part, {}).get(entry["key"])
        state = getattr(row, "state", None)
        crew = mc.crew_of(row)
        if state == MARK_STATE_DONE:
            name = mc.name_line(mc.done_names(crew)) or row.done_by_name or mc.name_line(mc.names(crew))
            out[part] = {"state": DONE, "name": name or row.picked_by_name or ""}
        elif state == MARK_STATE_BASIC:
            out[part] = {"state": BASIC, "name": row.done_by_name or ""}
        elif state == MARK_STATE_NEED and any(m.get("uid") is not None for m in crew):
            out[part] = {"state": WORKING, "name": mc.name_line(mc.names(crew)) or row.picked_by_name or ""}
        elif part in hands:
            out[part] = {"state": DONE, "name": step_names.get(part) or "", "hand": True}
        else:
            out[part] = {"state": DONE if made else NONE, "name": ""}
    return out


def is_worked(parts: dict[str, dict[str, Any]]) -> bool:
    """작업이 닿은 도면인지(§2-3)."""
    return any(p["state"] != NONE for p in parts.values())


def progress_line(no: int, parts: dict[str, dict[str, Any]]) -> str:
    """진행 줄 "도면 2 · 재단 완료 · 엣지 작업 중"(재단 기본은 "재단 기본")."""
    words = []
    for part, info in parts.items():
        label = PRODUCTION_PART_LABELS[part]
        if info["state"] == DONE:
            words.append(f"{label} 완료")
        elif info["state"] == BASIC:
            words.append(f"{label} 기본")
        elif info["state"] == WORKING:
            words.append(f"{label} 작업 중")
    return " · ".join([f"도면 {no}", *words])


def worked_sentence(no: int, parts: dict[str, dict[str, Any]]) -> str:
    """경고 한 문장(§2-3) — 완료가 있으면 완료 문장, 아니면 작업 중 문장(작업이 안 닿았으면 빈 글)."""
    finished = [PRODUCTION_PART_LABELS[p] for p, info in parts.items() if info["state"] in (DONE, BASIC)]
    head = f"도면 {no}{number_topic(no)}"
    if finished:
        return f"{head} {subject_particle(' · '.join(finished))} 완료된 도면입니다. {AGAIN}"
    working = next(((p, info) for p, info in parts.items() if info["state"] == WORKING), None)
    if working is None:
        return ""
    who = subject_particle(working[1]["name"])
    return f"{head} {who + ' ' if who else ''}{PRODUCTION_PART_LABELS[working[0]]} 작업 중인 도면입니다. {AGAIN}"


def progress_context(sd: Any, marks: Iterable[Any]) -> dict[str, Any]:
    """도면마다 진행을 계산할 재료(한 번만) — 파트별 줄 · 손 처리 파트 · 칸 이름."""
    marks = list(marks)
    return {"rows": marks_by_part(marks), "hand_parts": hand_checked_parts(sd, marks), "step_names": _step_names(sd)}


def entry_parts(sd: Any, entry: dict[str, Any], ctx: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """도면 한 장의 파트 상태(:func:`drawing_parts` 를 주문 JSON · 재료로)."""
    return drawing_parts(entry, ctx["rows"], hand_parts=ctx["hand_parts"], step_names=ctx["step_names"],
                         made=factory_made(sd, sheet_factory(sd, entry)))


def worked_warnings(sd: Any, marks: Iterable[Any], changed: Iterable[tuple[int, dict[str, Any]]]) -> list[dict[str, Any]]:
    """바뀌거나 빠지는 옛 도면 중 작업이 닿은 것의 경고 ``[{no, ident, text, line}]``(옛 번호 순 — 409 ``WORKED_DRAWING`` 자료).

    ``ident`` 는 화면이 [그래도 보내기] 뒤 ``ack_worked`` 목록으로 돌려보내는 열쇠다(물어본 도면만 지나간다 — D2 검토 I).
    """
    ctx = progress_context(sd, marks)
    out = []
    for no, entry in changed:
        parts = entry_parts(sd, entry, ctx)
        if is_worked(parts):
            out.append({"no": no, "ident": fix_ident(entry), "text": worked_sentence(no, parts),
                        "line": progress_line(no, parts)})
    return out


def order_made_warning() -> list[dict[str, Any]]:
    """시공 대기 주문 경고(§2-3 답 7 — 409 ``ORDER_MADE`` 자료). ``order_made`` 표지 = 화면이 ``ack_order_made`` 로 돌려보낸다."""
    return [{"no": None, "ident": None, "order_made": True, "text": ORDER_MADE_TEXT, "line": ORDER_MADE_LINE}]


def _open_requests_by_ident(sd: Any) -> dict[str, list[dict[str, Any]]]:
    """열린 공장 요청(``state == 'open'`` — 막는 요청)을 **남은 대상** 열쇠마다 ``{id, from, checked, left}``(R1).

    ``left`` = 아직 막는 열쇠(``targets`` − ``resolved`` — 수정본이 간 열쇠는 빠진다, 지휘 N). 풀린 도면에는 그 요청이 안 붙는다.
    """
    table = sd.get("drawing_fix") if isinstance(sd, dict) else None
    out: dict[str, list[dict[str, Any]]] = {}
    for request in (table.get("requests") if isinstance(table, dict) else None) or []:
        if isinstance(request, dict) and request.get("state") == REQUEST_OPEN:
            left = request_left(request)
            row = {"id": request.get("id"), "from": request.get("from") or "factory", "checked": request_checked(request),
                   "left": left}
            for ident in left:
                out.setdefault(ident, []).append(row)
    return out


def drawings_progress(sd: Any, marks: Iterable[Any], entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """R1 자료 — 지금 확정 도면마다 ``{no, ident, key, factory, parts, worked, line, fixing, requests}``.

    ``requests`` = 그 도면을 막는 열린 요청(공장 요청 ``{id, from: 'factory', checked}`` — [반영 완료]여도 수정본이 갈 때까지 열린 채
    · 영업 요청 ``{from: 'sales'}``).
    """
    ctx = progress_context(sd, marks)
    block = blocked(sd)
    factory = _open_requests_by_ident(sd)
    out = []
    for no, entry in enumerate(entries, 1):
        parts = entry_parts(sd, entry, ctx)
        ident = fix_ident(entry)
        reasons = block.why.get(ident, ())
        requests = factory.get(ident, []) + ([{"id": None, "from": "sales", "checked": None}] if WHY_SALES in reasons else [])
        out.append({"no": no, "ident": ident, "key": entry["key"], "factory": sheet_factory(sd, entry), "parts": parts,
                    "worked": is_worked(parts), "line": progress_line(no, parts),
                    "fixing": WHY_FIXING in reasons, "requests": requests})
    return out


__all__ = [
    "AGAIN", "ORDER_MADE_LINE", "ORDER_MADE_TEXT", "drawing_parts", "drawings_progress", "entry_parts", "is_worked",
    "order_made_warning", "progress_context", "progress_line", "worked_sentence", "worked_warnings",
]
