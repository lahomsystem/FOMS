"""도면 작업실 '생산 중' 칸 줄 값 · 정렬 · 공장 진행 요약 + 상세 '공장 진행' 칸 값(설계서 2026-11-25 §2-1 · §2-2 · §10, D3).

* 목록 줄(:func:`production_row_fields`) — 이미 든 주문 JSON 만 본다(쿼리 0): 요청 표시("수정 요청 · 영업" · "수정 요청 · 공장") · 고치는
  중 표시 · 다음 액션 · 대상 번호 · 단계 낱말("생산" · "시공 대기") · 정렬 열쇠(① 열린 요청, 요청 시각 오래된 것 먼저 ② 고치는 도면이 있는
  주문 ③ 나머지 시공일 빠른 순, 시공일 없음은 맨 뒤). 공장 요청은 ``drawing_fix.requests`` 중 ``state == "open"`` 만 읽는다(만드는 길은 D4).
* 공장 진행 요약(:func:`attach_progress_lines`) — 한 쪽(25줄) 주문의 파트 표시를 한 번에 읽는다(``marks_by_order`` — 쿼리 1, N+1 없음).
  파트마다 완료(완료 · 기본 · 손 처리 · 그 공장 제작 완료) 장 수 / 장 수, 2공장 장이 있으면 공장마다 한 줄. 시공 대기는 "제작 완료".
* 상세 '공장 진행' 칸(:func:`fix_progress_view`) — 생산 · 시공 단계에서만(그 밖 None, 쿼리 0). 진행은 D2 의 도면별 진행 함수
  (``drawing_fix_progress.drawings_progress`` — R1 과 같은 값)를 부른다. 생산 단계만 표시 1번. 시공 대기는 줄마다 "제작 완료", [수정 시작] 없음.
"""

from __future__ import annotations

from typing import Any, Iterable, Optional

from foms.services.datetime_kst import format_datetime_kst, parse_datetime_utc
from foms.services.drawing_confirm_cleanup import resolve_final_drawing_files
from foms.services.drawing_fix_progress import BASIC, DONE, WORKING, drawings_progress, entry_parts, progress_context
from foms.services.orders.confirm_drawing_gate import effective_drawing_status, last_revision_request
from foms.services.orders.drawing_factory import DRAWING_FIX_KEY, current_factories, factory_made, has_second_factory
from foms.services.orders.drawing_fix import REQUEST_OPEN, blocked, fix_ident, numbers_text, request_left
from foms.services.orders.drawing_fix_marks import confirm_text, fixing_rows
from foms.services.orders.drawing_fix_transfer import can_fix_production_drawing, load_marks
from foms.services.orders.state_axes import read_main_stage
from foms.services.production.factory_constants import FACTORIES, factory_label
from foms.services.production.part_constants import PRODUCTION_PART_KEYS, PRODUCTION_PART_LABELS
from foms.services.production.part_marks_query import marks_by_order

#: 칸 값(``?status=PRODUCTION``) — 프로세스 맵 '생산 중' 칸 · 상태 거르개.
PRODUCTION_TAB_STATUS = "PRODUCTION"
STAGE_PRODUCTION = "PRODUCTION"
STAGE_CONSTRUCTION = "CONSTRUCTION"
_STAGE_BY_MIRROR = {"PRODUCTION": STAGE_PRODUCTION, "생산": STAGE_PRODUCTION, "CONSTRUCTION": STAGE_CONSTRUCTION,
                    "시공": STAGE_CONSTRUCTION}
#: 새 글(§10).
STAGE_WORDS = {STAGE_PRODUCTION: "생산", STAGE_CONSTRUCTION: "시공 대기"}
MADE_TEXT = "제작 완료"
MARK_SALES = "수정 요청 · 영업"
MARK_FACTORY = "수정 요청 · 공장"
MARK_FIXING = "도면 고치는 중"
HAND_TAIL = "(작업 시트)"
_FAR = float("inf")


# --------------------------------------------------------------------------- #
# 목록 줄
# --------------------------------------------------------------------------- #
def tab_stage(order: Any) -> str:
    """목록 줄의 단계(미러 컬럼 — 모집단 SQL 과 같은 축) — ``PRODUCTION`` · ``CONSTRUCTION``(그 밖은 빈 글)."""
    return _STAGE_BY_MIRROR.get(str(getattr(order, "erp_stage_code", None) or ""), "")


def _ts(raw: Any) -> float:
    parsed = parse_datetime_utc(raw) if raw else None
    return parsed.timestamp() if parsed is not None else _FAR


def _current_numbers(sd: Any) -> dict[str, int]:
    return {fix_ident(entry): no for no, entry in enumerate(resolve_final_drawing_files(sd), 1)}


def _stored_numbers(request: dict[str, Any], left: list[str]) -> list[int]:
    """지금 도면으로 못 센 남은 열쇠의 번호 — 요청 ``numbers`` 가 ``targets`` 와 짝일 때만 그 열쇠 몫(짝이 아니면 빈 목록)."""
    targets, numbers = request.get("targets") or [], request.get("numbers") or []
    if len(targets) != len(numbers):
        return []
    wanted = set(left)
    return sorted({n for t, n in zip(targets, numbers) if t in wanted and isinstance(n, int) and not isinstance(n, bool)})


def open_factory_requests(sd: Any, numbers: dict[str, int]) -> list[dict[str, Any]]:
    """아직 막는 공장 요청(``state == "open"`` 이고 남은 열쇠가 있음) — ``[{name, at, numbers}]`` 요청 시각 순.

    번호는 **남은** 열쇠(``drawing_fix.request_left`` = targets − resolved — 수정본이 간 도면은 빠진다, D2 지휘 N)를 지금 도면으로
    다시 센다(못 세면 적힌 번호 중 그 열쇠 몫). 남은 열쇠가 없는 요청은 막지 않으므로 뺀다.
    """
    table = sd.get(DRAWING_FIX_KEY) if isinstance(sd, dict) else None
    requests = table.get("requests") if isinstance(table, dict) else None
    out = []
    for request in requests if isinstance(requests, list) else []:
        if not isinstance(request, dict) or request.get("state") != REQUEST_OPEN:
            continue
        left = request_left(request)
        if not left:
            continue
        nos = sorted({numbers[t] for t in left if t in numbers}) or _stored_numbers(request, left)
        out.append({"name": str(request.get("by_name") or "").strip(), "at": request.get("at"), "numbers": nos})
    return sorted(out, key=lambda r: _ts(r["at"]))


def _sales_request(sd: Any) -> Optional[dict[str, Any]]:
    """열린 영업 수정 요청(RETURNED) — ``{name, at}``, 없으면 None."""
    if effective_drawing_status(sd) != "RETURNED":
        return None
    request = last_revision_request(sd) or {}
    return {"name": str(request.get("by_user_name") or "").strip(), "at": request.get("at") or request.get("transferred_at")}


def _join(*parts: str) -> str:
    return " · ".join(p for p in parts if p)


def _next_action(sales: Optional[dict[str, Any]], factory: list[dict[str, Any]], fixing: list[dict[str, Any]]) -> str:
    """다음 액션(§10) — 열린 요청 중 오래된 것, 없으면 고치는 중. 아무것도 없으면 빈 글(지금 글 그대로)."""
    asks = ([(_ts(sales["at"]), _join("영업 수정 요청", sales["name"]))] if sales else []) + [
        (_ts(r["at"]), _join("공장 수정 요청", r["name"], f"도면 {numbers_text(r['numbers'])}" if r["numbers"] else ""))
        for r in factory]
    if asks:
        return min(asks, key=lambda pair: pair[0])[1]
    if fixing:
        nos = [r["no"] for r in fixing if isinstance(r["no"], int)]
        names = list(dict.fromkeys(r["by_name"] for r in fixing if r["by_name"]))
        return _join(f"도면 {numbers_text(nos)} 고치는 중" if nos else MARK_FIXING, ", ".join(names))
    return ""


def production_row_fields(order: Any, sd: Any) -> dict[str, Any]:
    """'생산 중' 칸 줄에만 더하는 값(쿼리 0) — 템플릿은 ``in_production_tab`` 줄에서만 그린다(다른 칸 · 기본 목록은 그대로).

    Returns:
        ``in_production_tab`` · ``prod_stage_word`` · ``prod_is_made`` · ``prod_markers``(``[{text, tone}]``) · ``prod_next_action`` ·
        ``prod_targets``("도면 2 · 3", 없으면 빈 글) · ``prod_row_class`` · ``prod_sort``.
    """
    numbers = _current_numbers(sd)
    sales, factory, fixing = _sales_request(sd), open_factory_requests(sd, numbers), fixing_rows(sd)
    block = blocked(sd)
    targets = sorted({numbers[ident] for ident in block.idents if ident in numbers})
    markers = ([{"text": MARK_SALES, "tone": "revision"}] if sales else []) + (
        [{"text": MARK_FACTORY, "tone": "order-change"}] if factory else []) + (
        [{"text": MARK_FIXING, "tone": "transfer"}] if fixing else [])
    ask_times = ([_ts(sales["at"])] if sales else []) + [_ts(r["at"]) for r in factory]
    group = 0 if ask_times else (1 if fixing else 2)
    row_class = ("dw-req-row" + ("" if sales else " is-factory")) if group == 0 else ("dw-fix-row" if group == 1 else "")
    date = str(getattr(order, "erp_construction_date", None) or "")
    stage = tab_stage(order)
    return {
        "in_production_tab": True,
        "prod_stage_word": STAGE_WORDS.get(stage, ""),
        "prod_is_made": stage == STAGE_CONSTRUCTION,
        "prod_markers": markers,
        "prod_next_action": _next_action(sales, factory, fixing),
        "prod_targets": f"도면 {numbers_text(targets)}" if targets else "",
        "prod_row_class": row_class,
        "prod_sort": (group, min(ask_times) if ask_times else 0.0, 0 if date else 1, date, int(order.id)),
        "prod_progress": [],
    }


def production_sort_key(row: dict[str, Any]) -> tuple:
    """'생산 중' 칸 기본 정렬(``sort=`` 가 없을 때) — :func:`production_row_fields` 의 ``prod_sort``."""
    return row.get("prod_sort") or (9, 0.0, 1, "", -int(row.get("id") or 0))


# --------------------------------------------------------------------------- #
# 공장 진행 요약(목록 상태 칸)
# --------------------------------------------------------------------------- #
def progress_lines(sd: Any, marks: Iterable[Any], *, made: bool) -> list[dict[str, Any]]:
    """상태 칸 공장 진행 요약 — 시공 대기면 ``[{made: True}]``, 생산이면 공장마다 ``{label, parts: [{label, done, total, full}]}``.

    공장 칩(``label``)은 2공장 장이 있을 때만(1공장뿐 주문은 지금처럼 공장 표시 없음).
    """
    if made:
        return [{"made": True}]
    ctx = progress_context(sd, marks)
    by_factory: dict[int, list[dict[str, Any]]] = {}
    for entry, factory in current_factories(sd):
        by_factory.setdefault(factory, []).append(entry_parts(sd, entry, ctx))
    two = len(by_factory) > 1 or 2 in by_factory
    lines = []
    for factory in (f for f in FACTORIES if f in by_factory):
        rows = by_factory[factory]
        parts = []
        for part in PRODUCTION_PART_KEYS:
            done = sum(1 for parts_of in rows if parts_of[part]["state"] in (DONE, BASIC))
            parts.append({"label": PRODUCTION_PART_LABELS[part], "done": done, "total": len(rows), "full": done == len(rows)})
        lines.append({"made": False, "label": factory_label(factory) if two else "", "parts": parts})
    return lines


def attach_progress_lines(db: Any, page_rows: list[dict[str, Any]], sd_by_id: dict[int, Any]) -> None:
    """한 쪽 줄 중 '생산 중' 칸 줄에 공장 진행 요약을 붙인다(제자리) — 생산 단계 주문의 표시를 한 번에(쿼리 1, 없으면 0)."""
    rows = [r for r in page_rows if r.get("in_production_tab")]
    ids = [int(r["id"]) for r in rows if not r.get("prod_is_made")]
    marks = marks_by_order(db, ids) if ids else {}
    for row in rows:
        row["prod_progress"] = progress_lines(sd_by_id.get(int(row["id"])) or {}, marks.get(int(row["id"]), []),
                                              made=bool(row.get("prod_is_made")))


# --------------------------------------------------------------------------- #
# 상세 '공장 진행' 칸
# --------------------------------------------------------------------------- #
def _md_hm(raw: Any) -> str:
    text = format_datetime_kst(raw, "%m/%d %H:%M") if raw else None
    if not text:
        return ""
    month, rest = text.split("/", 1)
    day, hm = rest.split(" ", 1)
    return f"{int(month)}/{int(day)} {hm}"


def _cell(part: str, info: dict[str, Any]) -> dict[str, str]:
    """파트 칸 하나(§10) — 완료 초록 · 작업 중 분홍 · 미정 점선(무채색 없음)."""
    label, name, state = PRODUCTION_PART_LABELS[part], str(info.get("name") or "").strip(), info.get("state")
    if state == DONE:
        tail = f" · {name}{HAND_TAIL}" if info.get("hand") and name else (f" · {name}" if name else "")
        return {"text": f"{label} 완료{tail}", "tone": "done"}
    if state == BASIC:
        return {"text": f"{label} 기본", "tone": "done"}
    if state == WORKING:
        return {"text": _join(f"{label} 작업 중", name), "tone": "taken"}
    return {"text": f"{label} 미정", "tone": "none"}


def _detail_row(sd: Any, row: dict[str, Any], *, entry: dict[str, Any], fixing: dict[str, dict[str, Any]], made: bool,
                two: bool, can_fix: bool, whole_sales: bool) -> dict[str, Any]:
    fix = fixing.get(row["ident"])
    # requests = 그 도면을 막는 열린 요청 ``[{id, from, checked, left}]``(D2 drawings_progress — 공장 · 영업)
    sources = {str(r.get("from") or "") for r in row["requests"] if isinstance(r, dict)}
    asks = ([MARK_SALES] if whole_sales or "sales" in sources else []) + ([MARK_FACTORY] if "factory" in sources else [])
    factory = row["factory"]
    return {
        "no": row["no"], "sheet_id": str(entry.get("sheet_id") or ""), "key": "" if entry.get("sheet_id") else row["key"],
        "factory": factory, "factory_label": factory_label(factory) if two else "",
        "cells": [] if made else [_cell(part, row["parts"][part]) for part in PRODUCTION_PART_KEYS],
        "made_text": f"{factory_label(factory)} {MADE_TEXT}" if not made and factory_made(sd, factory) else "",
        "fixing_text": _join(MARK_FIXING, fix["by_name"], _md_hm(fix["at"])) if fix else "",
        "requests": asks, "blocked": bool(fix or asks),
        # [수정 시작]은 생산 단계만(시공 대기 없음 — 지휘 풀이), [수정 취소]는 고치는 중인 도면이면 시공 대기에도(사장님 답 "둘 다")
        "can_start": can_fix and not made and not fix, "can_stop": can_fix and bool(fix),
        "confirm_start": confirm_text([row["no"]], starting=True), "confirm_stop": confirm_text([row["no"]], starting=False),
    }


def fix_progress_view(db: Any, order: Any, sd: Any, user: Any) -> Optional[dict[str, Any]]:
    """상세 '공장 진행' 칸 값 — 생산 · 시공 단계에 지금 확정 도면이 있을 때만(그 밖 None · 쿼리 0). 생산 단계만 표시 1번.

    Returns:
        ``{order_id, made, count, two_factories, can_fix, parts: [파트 이름], rows: [...]}``. 단추는 ``can_fix_production_drawing``
        (도면팀 누구나 + 관리자 — 서버와 같은 술어)일 때만: [수정 시작]은 생산 단계만, [수정 취소]는 고치는 중인 도면이면 시공 대기에도
        (옛 표시가 남은 시공 대기 주문을 풀 길 — 사장님 답 "둘 다"). ``can_fix`` = 단추가 하나라도 있는지(확인 창 JS 를 싣는다).
    """
    stage = read_main_stage(order)
    entries = resolve_final_drawing_files(sd)
    if stage not in (STAGE_PRODUCTION, STAGE_CONSTRUCTION) or not entries:
        return None
    made = stage == STAGE_CONSTRUCTION
    progress = drawings_progress(sd, [] if made else load_marks(db, order.id), entries)
    fixing = {r["ident"]: r for r in fixing_rows(sd)}
    two = has_second_factory(sd)
    can_fix = can_fix_production_drawing(user, order)
    whole_sales = blocked(sd).whole and effective_drawing_status(sd) == "RETURNED"
    rows = [_detail_row(sd, row, entry=entry, fixing=fixing, made=made, two=two, can_fix=can_fix, whole_sales=whole_sales)
            for row, entry in zip(progress, entries)]
    return {"order_id": int(order.id), "made": made, "count": len(rows), "two_factories": two,
            "can_fix": any(r["can_start"] or r["can_stop"] for r in rows),
            "parts": [PRODUCTION_PART_LABELS[p] for p in PRODUCTION_PART_KEYS], "made_text": MADE_TEXT, "rows": rows}


__all__ = [
    "HAND_TAIL", "MADE_TEXT", "MARK_FACTORY", "MARK_FIXING", "MARK_SALES", "PRODUCTION_TAB_STATUS", "STAGE_WORDS",
    "attach_progress_lines", "fix_progress_view", "open_factory_requests", "production_row_fields", "production_sort_key",
    "progress_lines", "tab_stage",
]
