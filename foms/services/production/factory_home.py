"""생산 첫 화면 줄의 2공장 칸 — 날짜 줄 · PC 줄 도면 칸 · 남의 공장 줄 · 내 공장 완료 · 'N공장 제작 완료만 남음'(설계서 2026-11-23
§4-13 · §4-14 · §8-2 · §8-4).

**순수 계산 · 쿼리 0** — 이미 읽은 첫 화면 행의 주문 JSON(장의 공장 · 공장 완료 표지)과 날짜 탭이 이미 읽은 표시 줄만 쓴다.
2공장 그림이 꺼진 화면(:func:`~foms.services.production.factory_scope.scene_on` 거짓)에서는 부르지 않는다 — 행에 아무 칸도 안
생겨 화면이 지금과 같다.

행에 다는 칸(없으면 안 단다):

* ``fac_dw`` — 섞인 주문(2공장 장이 있는 주문)의 도면 칸: ``{lines: [{label, n, done, me}], pc}``. 보는 공장 줄이 위
  (``me`` 굵게), 공장 완료 표지가 살아 있으면 ``done``. PC 는 한 줄 "1공장 3장 · 2공장 2장 완료".
* ``fac_elsewhere`` — 한 공장 계정에게 남의 공장 장만 있는 줄(만들 것 묶음 끝 작은 머리 "2공장 작업" 아래로, §4-13). 값 = 남의
  공장 이름("2공장").
* ``fac_done`` — 한 공장 계정의 공장 완료가 살아 있는 섞인 주문(그날 장 '제작 완료' 작은 칸 묶음으로, 꼬리 글 — §4-14).
* ``fac_stage`` — 한 공장 계정의 공장 장이 네 파트 모두 완료됐는데 공장 완료를 아직 안 누른 섞인 주문의 단계 글
  "2공장 제작 완료만 남음"(§4-4 [나중에]).
"""

from __future__ import annotations

from typing import Any, Iterable, Optional

from foms.services.orders.drawing_factory import current_factories, factory_done_entry, has_second_factory
from foms.services.production.factory_constants import FACTORIES, factory_label
from foms.services.production.part_constants import PRODUCTION_PART_KEYS
from foms.services.production.part_progress import part_done


def factory_finished(sd: Any, marks: Iterable[Any], factory: int) -> bool:
    """그 공장 장이 네 파트 모두 완료인지(카드 안 쓴 파트는 주문 칸 체크) — 아무 일도 안 한 주문은 거짓(§4-4 물음 · 단계 글)."""
    marks = list(marks)
    keys = [entry["key"] for entry, f in current_factories(sd) if f == factory]
    return bool(keys) and all(part_done(sd, marks, part, factory=factory) for part in PRODUCTION_PART_KEYS)


def factory_counts(sd: Any) -> dict[int, int]:
    """공장 → 지금 장 수(장이 없는 공장은 0)."""
    counts = {f: 0 for f in FACTORIES}
    for _entry, factory in current_factories(sd):
        counts[factory] += 1
    return counts


def drawing_cell(sd: Any, viewer: int) -> Optional[dict[str, Any]]:
    """섞인 주문의 도면 칸(§8-2 · §8-4) — 2공장 장이 없으면 None(지금 "도면 n장" 그대로).

    Args:
        sd: 주문 ``structured_data``.
        viewer: 보는 공장(그 줄이 위 · 굵게).

    Returns:
        ``{lines: [{label, n, done, me}], pc: "1공장 3장 · 2공장 2장 완료"}``.
    """
    if not has_second_factory(sd):
        return None
    counts = factory_counts(sd)
    order = sorted((f for f in FACTORIES if counts[f]), key=lambda f: (f != viewer, f))
    lines = [{"label": factory_label(f), "n": counts[f], "done": factory_done_entry(sd, f) is not None, "me": f == viewer}
             for f in order]
    pc = " · ".join(f"{line['label']} {line['n']}장" + (" 완료" if line["done"] else "") for line in lines)
    return {"lines": lines, "pc": pc}


def _done_tail(sd: Any, factory: int, counts: dict[int, int]) -> str:
    """'제작 완료' 작은 칸 꼬리 — "2공장 완료 · 1공장 제작 중"."""
    rest = [f"{factory_label(f)} {'완료' if factory_done_entry(sd, f) is not None else '제작 중'}"
            for f in FACTORIES if f != factory and counts[f]]
    return " · ".join([f"{factory_label(factory)} 완료", *rest])


def attach_factory_rows(rows: Iterable[dict[str, Any]], *, viewer: int, group: Optional[int]) -> None:
    """만들 것 행(생산 단계)에 2공장 칸을 단다 — 2공장 그림이 켜진 화면에서만 부른다.

    Args:
        rows: 첫 화면 행.
        viewer: 도면 칸 줄 순서를 정할 공장(관리자 · 보기만 = 계정 값 또는 1공장).
        group: 한 공장 계정의 공장(남의 공장 줄 · 내 공장 완료 묶음) — 관리자 · 보기만 · PC 는 None(두 공장 합침).
    """
    for row in rows:
        if row.get("home_view") != "prod":
            continue
        sd = row.get("structured_data") or {}
        cell = drawing_cell(sd, viewer)
        if cell is not None:
            row["fac_dw"] = cell
        if group is None:
            continue
        counts = factory_counts(sd)
        if not any(counts.values()):
            continue
        if not counts.get(group):
            row["fac_elsewhere"] = factory_label(next(f for f in FACTORIES if f != group))  # 묶음 머리 "2공장 작업"
        elif cell is not None and factory_done_entry(sd, group) is not None:
            row["fac_done"] = _done_tail(sd, group, counts)


def attach_factory_stage(rows: Iterable[dict[str, Any]], marks: Iterable[Any], group: int) -> None:
    """한 공장 계정의 섞인 주문 줄 — 그 공장 장이 다 완료됐는데 공장 완료가 아직이면 단계 글 "2공장 제작 완료만 남음".

    Args:
        rows: 그리는 만들 것 행(``fac_dw`` 가 있는 줄만 본다).
        marks: 그 주문들 표시 줄(날짜 탭이 이미 읽은 줄 — 쿼리 0).
        group: 보는 사람 공장.
    """
    by_order: dict[int, list[Any]] = {}
    for mark in marks:
        by_order.setdefault(int(mark.order_id), []).append(mark)
    for row in rows:
        sd = row.get("structured_data") or {}
        if not row.get("fac_dw") or row.get("fac_done") or not row.get("home_has_run"):
            continue
        if factory_done_entry(sd, group) is None and factory_finished(sd, by_order.get(int(row["id"]), []), group):
            row["fac_stage"] = f"{factory_label(group)} 제작 완료만 남음"


__all__ = ["attach_factory_rows", "attach_factory_stage", "drawing_cell", "factory_counts", "factory_finished"]
