"""날짜 줄 · PC 줄 공정 네 칸 아래 이름(설계서 2026-11-23 §4-10 B8 · §4-11 B12) — 순수 계산, 쿼리 0.

부르는 쪽(``foms/web/production/home.py``)이 그날 만들 것 주문의 표시 줄을 한 번 읽어 넘긴다(파트 계정은 판이 읽은 줄을
다시 쓴다). 칸 하나의 값:

* 완료(카드) = 마지막으로 완료한 사람 + "외 n"(다른 완료한 사람 수). 완료(손 체크 · 카드 안 쓴 파트) = 체크한 사람.
* 하는 중 · 담당 있음 = 담당 중 맡은 때 이른 사람 + "외 n". 담당이 바뀐 장이 있으면 바꿔 맡은 사람 + "바뀜"("외 n" 대신).
  밤을 넘긴 담당은 ``old``(호박 글자 — "어제부터" 글은 ``aria`` · 마우스 글에만).
* 담당 없음 = "미정". 카드를 쓴 파트가 아직 미완료면 칸 이름이 "재단 3/5", 그 파트가 첫 미완 공정이면 단계 칸 둘째 줄
  "2장 미완료"(``row['part_miss']``).

``aria`` 는 태블릿 글(시각 없음 — 칸 아래 이름은 태블릿에서 시각을 안 보인다), ``tip`` 은 PC 마우스 글(시각 포함). 카드를 안 쓴
파트의 PC 마우스 글은 지금 글 그대로 두므로 ``tip`` 이 None 이다(:mod:`foms.services.production.pc_view` 가 지금 글을 쓴다).
"""

from __future__ import annotations

import datetime
from typing import Any, Iterable, Optional

from foms.services.datetime_kst import format_datetime_kst
from foms.services.production.part_constants import MARK_STATE_NEED, PRODUCTION_PART_LABELS
from foms.services.production.part_progress import current_keys, marks_by_part, part_progress

#: 칸 아래 이름이 없을 때(담당 없음) — 결정표 '미정'(답 ③).
HOLDER_NONE = "미정"


def kst_day(value: Optional[datetime.datetime]) -> Optional[datetime.date]:
    """DB UTC naive 시각 → KST 날짜(없으면 None)."""
    text = format_datetime_kst(value, "%Y-%m-%d") if value is not None else None
    return datetime.date.fromisoformat(text) if text else None


def since_text(picked_at: Optional[datetime.datetime], today: datetime.date) -> str:
    """밤 넘긴 담당 글 — 오늘 맡음 = 빈 글, 어제 = "어제부터", 그 전 = "11/20부터"(결정표 다)."""
    day = kst_day(picked_at)
    if day is None or day >= today:
        return ""
    if day == today - datetime.timedelta(days=1):
        return "어제부터"
    return f"{day.month}/{day.day}부터"


def handed_text(from_name: Optional[str], at: Optional[datetime.datetime], today: datetime.date, *,
                with_time: bool = True) -> str:
    """담당 바꾸기 요약 — "박엣지에서 바뀜 14:20"(오늘) · "박엣지에서 바뀜 · 어제" · "박엣지에서 바뀜 · 11/20".

    Args:
        from_name: 바꾸기 전 담당 이름(없으면 빈 글을 돌려준다).
        at: 바꾼 때(UTC naive).
        today: KST 오늘.
        with_time: 오늘 바뀐 것에 시각을 붙일지(태블릿 칸 아래 글은 시각을 안 붙인다).
    """
    name = (from_name or "").strip()
    if not name:
        return ""
    head = f"{name}에서 바뀜"
    day = kst_day(at)
    if day is None:
        return head
    if day >= today:
        return f"{head} {format_datetime_kst(at, '%H:%M')}" if with_time else head
    if day == today - datetime.timedelta(days=1):
        return f"{head} · 어제"
    return f"{head} · {day.month}/{day.day}"


def _names(rows: Iterable[Any], attr: str) -> list[str]:
    seen: list[str] = []
    for row in rows:
        name = str(getattr(row, attr, None) or "").strip()
        if name and name not in seen:
            seen.append(name)
    return seen


def _done_cell(keys: list[str], rows: dict[str, Any], progress: dict[str, Any], step: dict[str, Any]) -> dict[str, Any]:
    """완료 칸 — 카드로 완료면 마지막 완료한 사람 + 외 n, 손 체크면 체크한 사람."""
    if progress["uses_cards"] and progress["total_n"]:
        finished = [rows[k] for k in keys if k in rows]
        finished.sort(key=lambda r: (getattr(r, "done_at", None) is not None, getattr(r, "done_at", None)))
        names = _names(reversed(finished), "done_by_name")
        name, others = (names[0] if names else ""), names[1:]
    else:
        name, others = str(step.get("by") or "").strip(), []
    extra = [name] if name else []
    if others:
        extra.append("함께 완료한 사람 " + ", ".join(others))
    return {"kind": "done", "name": name, "tail": f"외 {len(others)}" if others else "", "old": False,
            "state": "완료", "extra": extra, "others": others}


def _held_cell(held: list[Any], today: datetime.date) -> dict[str, Any]:
    """하는 중 칸 — 담당(맡은 때 이른 사람, 담당이 바뀐 장이 있으면 바꿔 맡은 사람) · 외 n · 바뀜 · 밤 넘김."""
    held = sorted(held, key=lambda r: (getattr(r, "picked_at", None) is None, getattr(r, "picked_at", None)))
    handed = [r for r in held if getattr(r, "handed_from_name", None)]
    handed.sort(key=lambda r: (getattr(r, "handed_at", None) is not None, getattr(r, "handed_at", None)))
    lead = handed[-1] if handed else held[0]
    name = str(lead.picked_by_name or "").strip() or "다른 사람"
    others = [n for n in _names(held, "picked_by_name") if n != name]
    since = since_text(getattr(lead, "picked_at", None), today)
    change = handed_text(lead.handed_from_name, getattr(lead, "handed_at", None), today, with_time=False) if handed else ""
    extra = [f"담당 {name}"] + [p for p in (change or since,) if p]
    if others:
        extra.append("함께 하는 사람 " + ", ".join(others))
    return {"kind": "held", "name": name, "tail": "바뀜" if handed else (f"외 {len(others)}" if others else ""),
            "old": bool(since) and not handed, "state": "", "extra": extra, "others": others,
            "change_tip": handed_text(lead.handed_from_name, getattr(lead, "handed_at", None), today) if handed else ""}


def part_holder(sd: Any, marks: list[Any], part: str, step: dict[str, Any], today: datetime.date) -> dict[str, Any]:
    """공정 칸 하나 아래 이름.

    Args:
        sd: 주문 ``structured_data``.
        marks: 그 주문 표시 줄들(네 파트).
        part: 파트(= 공정 칸) key.
        step: 첫 화면 공정 칸(``home_steps`` 하나 — ``by`` 가 손 체크한 사람).
        today: KST 오늘.

    Returns:
        ``{kind: done|held|none, name, tail, old, label, aria, tip, progress}`` — ``label`` 은 칸 이름("재단" · "재단 3/5"),
        ``tip`` 은 카드를 쓴 파트의 PC 마우스 글(그 밖은 None).
    """
    label = PRODUCTION_PART_LABELS[part]
    progress = part_progress(sd, marks, part)
    keys = current_keys(sd)
    rows = marks_by_part(marks).get(part, {})
    partial = progress["uses_cards"] and progress["total_n"] and not progress["done"]
    cell_label = f"{label} {progress['done_n']}/{progress['total_n']}" if partial else label
    if progress["done"]:
        cell = _done_cell(keys, rows, progress, step)
    else:
        held = [rows[k] for k in keys if k in rows and rows[k].state == MARK_STATE_NEED]
        cell = _held_cell(held, today) if held else {"kind": "none", "name": HOLDER_NONE, "tail": "", "old": False,
                                                      "state": "", "extra": [f"담당 {HOLDER_NONE}"], "others": []}
    left = len(progress["left_keys"])
    head = f"{cell_label} · {left}장 미완료" if partial else (f"{label} {cell['state']}" if cell["state"] else label)
    cell.update(label=cell_label, progress=progress, aria=" · ".join([head] + cell.pop("extra")),
                tip=_pc_tip(cell, cell_label, left, partial))
    return cell


def _pc_tip(cell: dict[str, Any], label: str, left: int, partial: bool) -> Optional[str]:
    """PC 마우스 글 — 카드를 쓴 파트가 아직 미완료일 때만 새 글("재단 3/5 · 2장 미완료 · 담당 김재단"). 그 밖은 지금 글."""
    if not partial:
        return None
    who = f"담당 {cell['name']}" if cell["kind"] == "held" else f"담당 {HOLDER_NONE}"
    tip = f"{label} · {left}장 미완료 · {who}"
    if cell.get("change_tip"):
        tip += f" · {cell['change_tip']}"
    if cell.get("others"):
        tip += " · 함께 하는 사람 " + ", ".join(cell["others"])
    return tip


def stage_miss(row: dict[str, Any], holders: list[dict[str, Any]]) -> str:
    """단계 칸 둘째 줄 — 지금 공정("재단 중")이 카드를 쓴 파트이고 미완료 장이 있으면 "2장 미완료", 아니면 빈 글."""
    for step, cell in zip(row.get("home_steps") or [], holders):
        if step.get("done"):
            continue
        progress = cell["progress"]
        if row.get("home_stage") == f"{step['label']} 중" and progress["uses_cards"] and progress["left_keys"] \
                and progress["total_n"]:
            return f"{len(progress['left_keys'])}장 미완료"
        return ""
    return ""


def attach_part_holders(rows: Iterable[dict[str, Any]], marks_by_order: dict[int, list[Any]],
                        today: datetime.date) -> None:
    """행마다 ``part_holders``(공정 칸 넷과 같은 순서) · ``part_miss`` 를 단다 — 생산 단계 줄만(쿼리 0).

    Args:
        rows: 첫 화면 행들(``home_steps`` · ``structured_data`` · ``home_stage``).
        marks_by_order: 주문 → 표시 줄(:func:`foms.services.production.part_marks_query.marks_by_order` 꼴).
        today: KST 오늘.
    """
    for row in rows:
        if row.get("home_view") != "prod" or not row.get("home_steps"):
            continue
        sd = row.get("structured_data") or {}
        marks = list(marks_by_order.get(int(row["id"]), []))
        holders = [part_holder(sd, marks, step["key"], step, today) for step in row["home_steps"]]
        row["part_holders"] = holders
        row["part_miss"] = stage_miss(row, holders)


__all__ = ["HOLDER_NONE", "attach_part_holders", "handed_text", "kst_day", "part_holder", "since_text", "stage_miss"]
