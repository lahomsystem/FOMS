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

from foms.services.orders.drawing_factory import (
    current_factories,
    factory_done_entry,
    has_second_factory,
    present_factories,
    sheet_factory,
)
from foms.services.production.factory_constants import FACTORIES, factory_label
from foms.services.production.part_access import can_finish_factory, can_revert_completed
from foms.services.production.part_constants import MARK_STATE_DONE, PART_INSPECT, PRODUCTION_PART_KEYS
from foms.services.production.part_progress import complete_state, part_done
from foms.services.production_home_read_model import format_step_at_kst


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


def factory_ready(sd: Any, entry: dict[str, Any], marks: Iterable[Any], user: Any, *, order_id: int, part: str,
                  target: Optional[str], stage: Optional[str], hold: bool) -> Optional[dict[str, Any]]:
    """검수 카드를 완료한 뒤 "2공장 제작 완료할까요?"를 물을지(§4-4 섞인 주문) — 쿼리 0(읽은 줄 · 잠근 주문).

    섞인 주문 · 검수 완료 쓰기 · 생산 단계 · 보류 아님(``hold`` = 보류 · 도면 고치는 중 — 제작 완료가 막힌 주문, 2026-11-25) · 그 장의
    공장 완료 표지가 아직 · 그 공장 장이 네 파트 모두 완료 · 누른 사람이
    그 공장 완료를 할 수 있을 때만. 한 공장 주문은 지금 ``order_ready`` 그대로(여기는 None).

    Returns:
        ``{order_id, factory, label, sheets, final, others, message}`` — ``final`` = 다른 있는 공장이 모두 이미 완료(이번이 마지막),
        ``message`` = 창 본문 뒤쪽("2공장 도면 2장이 모두 완료됐어요. 1공장은 아직 제작 중이에요.").
    """
    if part != PART_INSPECT or target != MARK_STATE_DONE or stage != "PRODUCTION" or hold or not has_second_factory(sd):
        return None
    factory = sheet_factory(sd, entry)
    if factory_done_entry(sd, factory) is not None or not can_finish_factory(user, factory):
        return None
    marks = list(marks)
    if not factory_finished(sd, marks, factory):
        return None
    others = [f for f in present_factories(sd) if f != factory]
    final = all(factory_done_entry(sd, f) is not None for f in others)
    names = " · ".join(factory_label(f) for f in others)
    tail = (f"{names}은 이미 완료했어요. 제작 완료하면 시공 대기로 넘어가요." if final
            else f"{names}은 아직 제작 중이에요.") if others else "제작 완료하면 시공 대기로 넘어가요."
    sheets = factory_counts(sd)[factory]
    return {"order_id": order_id, "factory": factory, "label": factory_label(factory), "sheets": sheets, "final": final,
            "others": [factory_label(f) for f in others],
            "message": f"{factory_label(factory)} 도면 {sheets}장이 모두 완료됐어요. {tail}"}


def factory_left_message(factory: int, state: dict[str, Any]) -> str:
    """그 공장에 남은 일 — "2공장에 미완료가 있어요 — 엣지 1장 · 검수 2장"(§4-14 작업 시트 · 공장 완료 거절 글)."""
    left = " · ".join(f"{m['label']} {state['left'].get(m['key'], 0)}장" for m in state["missing_steps"])
    return f"{factory_label(factory)}에 미완료가 있어요 — {left}"


def factory_step_fields(sd: Any, marks: Iterable[Any]) -> dict[str, Any]:
    """공정 API 응답에 더할 공장마다 준비 · 까닭(섞인 주문만 — 한 공장 주문은 빈 사전, 응답 그대로). 읽기 전용 · 쿼리 0.

    작업 시트가 공정 칸을 손 체크 · 해제한 뒤 [2공장 제작 완료] 단추 색 · 회색 까닭을 다시 그린다(그릴 때 한 번만 정하지 않게).

    Returns:
        ``{"factories": {"1": {ready, why, done}, "2": …}}`` 또는 ``{}``. ``ready`` = 공장 완료 API 와 같은 판정
        (:func:`complete_state` ``factory=``), ``done`` = 표지가 살아 있음.
    """
    if not has_second_factory(sd):
        return {}
    marks = list(marks)
    out: dict[str, Any] = {}
    for factory in present_factories(sd):
        state = complete_state(sd, marks, factory=factory)
        out[str(factory)] = {"ready": bool(state["ready"]), "why": "" if state["ready"] else factory_left_message(factory, state),
                             "done": factory_done_entry(sd, factory) is not None}
    return {"factories": out}


def _status_word(sd: Any, factory: int) -> str:
    entry = factory_done_entry(sd, factory)
    if entry is None:
        return f"{factory_label(factory)} 제작 중"
    who = " ".join(p for p in (str(entry.get("by_name") or "").strip(), format_step_at_kst(entry.get("at"))) if p)
    return f"{factory_label(factory)} 완료" + (f"({who})" if who else "")


def factory_sheet_view(sd: Any, marks: Iterable[Any], user: Any, *, stage_label: str) -> Optional[dict[str, Any]]:
    """작업 시트의 공장 줄 · 공장 단추(§4-14 '작업 시트 [제작 완료](섞인 주문)') — 한 공장 주문은 None(지금 시트 그대로).

    * 줄: "1공장 제작 중 · 2공장 완료(강검수 11/24 16:10)".
    * 제작중: 내가 완료할 수 있는 공장(:func:`can_finish_factory` — 관리자 두 공장 · 그 밖 계정 공장) 중 안 끝난 공장마다
      [2공장 제작 완료](그 공장 판정 — 안 되면 회색 + 까닭), 살아 있는 공장은 [2공장 완료 취소] — 반장 · 관리자만(사장님 2026-11-28,
      :func:`can_revert_completed` = 공장 완료 API 403 ``LEAD_REQUIRED`` 와 같은 함수). 파트 계정에게는 단추 없이 공장 줄의
      "2공장 완료(강검수 11/24 16:10)"로만 보인다. 안 끝난 공장이 내 공장 하나뿐이면
      지금 [제작 완료](마지막 — 남은 공장을 한꺼번에)를 그대로 보인다(``show_complete``).
    * 제작완료: 관리자는 [1공장 완료 취소] · [2공장 완료 취소](지금 [완료 취소] = 둘 다 — §19 여섯째).
    """
    if not has_second_factory(sd):
        return None
    marks = list(marks)
    present = present_factories(sd)
    mine = [f for f in present if can_finish_factory(user, f)]
    view = {"line": " · ".join(_status_word(sd, f) for f in present), "buttons": [], "show_complete": True, "reopen": []}
    if stage_label == "제작완료":
        view["reopen"] = [{"factory": f, "label": f"{factory_label(f)} 완료 취소"} for f in mine] if len(mine) > 1 else []
        return view
    if stage_label != "제작중":
        return view
    undone = [f for f in present if factory_done_entry(sd, f) is None]
    view["show_complete"] = bool(undone) and len(undone) == 1 and undone[0] in mine
    revert = can_revert_completed(user)
    for factory in mine:
        if factory not in undone:
            if revert:
                view["buttons"].append({"factory": factory, "done": False, "label": f"{factory_label(factory)} 완료 취소",
                                        "ready": True, "why": ""})
        elif not view["show_complete"]:
            state = complete_state(sd, marks, factory=factory)
            view["buttons"].append({"factory": factory, "done": True, "label": f"{factory_label(factory)} 제작 완료",
                                    "ready": bool(state["ready"]),
                                    "why": "" if state["ready"] else factory_left_message(factory, state)})
    return view


__all__ = ["attach_factory_rows", "attach_factory_stage", "drawing_cell", "factory_counts", "factory_finished", "factory_left_message",
           "factory_ready", "factory_sheet_view", "factory_step_fields"]
