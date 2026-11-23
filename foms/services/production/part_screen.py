"""생산 첫 화면이 파트 3판 칸을 위해 읽는 것 — 칸 아래 이름의 표시 줄 한 번 · 아침 칩 한 번(설계서 2026-11-23 §4-9 · §4-10 · §12).

* 표시 줄은 그리는 줄(날짜 장의 만들 것 · PC 찾기의 생산 줄) 중 확정 도면이 있는 주문만 ``order_id IN`` 한 번 읽는다
  (도면이 없는 주문은 카드 · 장이 없어 칸 아래 이름이 공정 칸만으로 정해진다 — 그런 줄만 있으면 쿼리 0). 파트 판도 같은 줄을
  다시 쓴다(판이 따로 읽지 않는다).
* 아침 칩 = 파트 계정 · 전체 페이지에서만, 내가 맡은 NEED 줄 중 맡은 때가 오늘 KST 0시 전(쿼리 1). 날 조각에는 없다.
  여러 파트 계정은 내 파트 전부를 센다(고른 파트만이 아니다) — 펼친 목록 줄에 파트 이름 · [보기]는 그 파트 · 그 날(§4-12).
"""

from __future__ import annotations

import datetime
from typing import Any, Iterable, Optional

from foms.services.datetime_kst import to_utc_naive
from foms.services.drawing_confirm_cleanup import resolve_final_drawing_files
from foms.services.production.part_holders import attach_part_holders
from foms.services.production.part_constants import PRODUCTION_PART_KEYS, PRODUCTION_PART_LABELS
from foms.services.production.part_marks_query import my_old_claims
from models import ProductionPartMark

_WEEKDAY_KO = "월화수목금토일"


def drawn_order_ids(rows: Iterable[dict[str, Any]]) -> list[int]:
    """확정 도면이 1장 이상인 주문 id(화면 순서) — 표시 줄을 읽을 주문."""
    return [int(r["id"]) for r in rows if resolve_final_drawing_files(r.get("structured_data") or {})]


def read_screen_marks(db: Any, rows: list[dict[str, Any]], today: datetime.date) -> list[Any]:
    """그리는 줄의 표시 줄을 한 번 읽고 칸 아래 이름을 단다. 읽은 줄을 돌려준다(파트 판이 다시 쓴다).

    Args:
        db: 세션.
        rows: 칸 아래 이름을 달 첫 화면 행(생산 줄만 단다).
        today: KST 오늘.

    Returns:
        읽은 ``ProductionPartMark`` 줄 목록(도면 있는 주문이 없으면 빈 목록 · 쿼리 0).
    """
    ids = drawn_order_ids(r for r in rows if r.get("home_view") == "prod")
    marks = db.query(ProductionPartMark).filter(ProductionPartMark.order_id.in_(ids)).all() if ids else []
    by_order: dict[int, list[Any]] = {}
    for mark in marks:
        by_order.setdefault(int(mark.order_id), []).append(mark)
    attach_part_holders(rows, by_order, today)
    return marks


def _day_label(day_key: str) -> str:
    try:
        day = datetime.date.fromisoformat(day_key)
    except (TypeError, ValueError):
        return "시공일 없음"
    return f"시공 {day.month}/{day.day} ({_WEEKDAY_KO[day.weekday()]})"


def morning_chip(db: Any, user: Any, parts: Any, rows: list[dict[str, Any]],
                 today: datetime.date) -> Optional[dict[str, Any]]:
    """아침 칩 "어제부터 내 담당 2장" — 시공일마다 몇 장인지(작은 창 [보기] 링크용).

    지금 확정 도면 장(옛 판 key 는 뺀다) · 생산 줄만 센다. 하나도 없으면 None(칩을 안 그린다). 칩 숫자 = 내 파트 전부의 합.
    파트가 여럿이면 줄을 시공일 · 파트마다 나누고 줄에 파트 이름(``part_label``)과 그 파트(``part``)를 싣는다 — [보기]가 그 파트
    판으로 간다. 파트 하나인 계정의 줄은 지금 그대로(``part`` · ``part_label`` 없음).

    Args:
        db: 세션.
        user: 보는 사람(파트 계정).
        parts: 내 파트들(정의 순서) — 파트 key 글 하나도 받는다.
        rows: 첫 화면 행 전부.
        today: KST 오늘.

    Returns:
        ``{count, days: [{key, label, count, part, part_label}]}`` 또는 None.
    """
    parts = (parts,) if isinstance(parts, str) else tuple(parts)
    prod = [r for r in rows if r.get("home_view") == "prod"]
    midnight = to_utc_naive(datetime.datetime.combine(today, datetime.time(0, 0)), assume_utc_if_naive=False)
    claims = my_old_claims(db, getattr(user, "id", 0), parts, (r["id"] for r in prod), midnight)
    if not claims:
        return None
    by_id = {int(r["id"]): r for r in prod}
    split = len(parts) > 1
    counts: dict[tuple[str, str], int] = {}
    for mark in claims:
        row = by_id.get(int(mark.order_id))
        keys = {e["key"] for e in resolve_final_drawing_files((row or {}).get("structured_data") or {})}
        if row is None or mark.drawing_key not in keys:
            continue
        slot = (row.get("day_key") or "", str(mark.part) if split else "")
        counts[slot] = counts.get(slot, 0) + 1
    if not counts:
        return None
    order = {key: i for i, key in enumerate(PRODUCTION_PART_KEYS)}
    days = [{"key": key, "label": _day_label(key), "count": n, "part": part or None,
             "part_label": PRODUCTION_PART_LABELS.get(part) if part else None}
            for (key, part), n in sorted(counts.items(), key=lambda kv: (kv[0][0], order.get(kv[0][1], -1)))]
    return {"count": sum(counts.values()), "days": days}


__all__ = ["drawn_order_ids", "morning_chip", "read_screen_marks"]
