"""도면 쪽 화면(마법사 · 작업실)에 내려 주는 장의 공장 값(설계서 2026-11-23 §8-5 · §5-1, 3단계 ④). 순수 함수 · 쿼리 0.

* 2공장 장이 하나도 없고 공장을 지정할 수도 없는 사람이면 ``None`` — 화면에 공장 그림이 하나도 생기지 않는다(지금 모습 그대로).
* 고르는 칸(``can_set``)은 도면팀 누구나 + 관리자(:func:`~foms.services.orders.erp_policy_permissions.can_set_sheet_factory`)
  이고, 주문이 아직 옮길 수 있는 단계(생산까지)일 때만이다. 시공 대기 이후는 서버가 막으므로(409 ``ORDER_DONE``) 표시만 보인다.
* 생산 단계에서 지금 확정 도면 장을 옮기면 확인 창을 먼저 띄운다(§4-13 표 둘째 줄) — 그 장의 시트 신원 · key 를 내려 준다.
  막을지는 서버가 정한다(일이 시작된 장 · 공장 완료 · 단계) — 화면은 서버 글을 그대로 보인다.
"""
from __future__ import annotations

from typing import Any, Optional

from foms.services.drawing_confirm_cleanup import resolve_final_drawing_files
from foms.services.orders.drawing_factory import current_factories, factory_by_key, factory_by_sheet, has_second_factory
from foms.services.orders.drawing_transfer import clean_sheet_id
from foms.services.orders.stage_override import STAGE_FORWARD_RANK
from foms.services.production.factory_constants import FACTORIES, factory_label

_PRODUCTION_RANK = STAGE_FORWARD_RANK["PRODUCTION"]


def _stage_rank(stage: Optional[str]) -> Optional[int]:
    return STAGE_FORWARD_RANK.get(str(stage or ""))


def can_move_stage(stage: Optional[str]) -> bool:
    """아직 장을 옮길 수 있는 단계인지 — 생산까지(단계를 모르면 서버 판정에 맡기고 참)."""
    rank = _stage_rank(stage)
    return rank is None or rank <= _PRODUCTION_RANK


def split_text(sd: Any) -> str:
    """지금 확정 도면의 공장별 장 수 "1공장 3장 · 2공장 2장" — 2공장 장이 없으면 빈 글(1공장은 표시 없음)."""
    if not has_second_factory(sd):
        return ""
    counts = {f: 0 for f in FACTORIES}
    for _entry, factory in current_factories(sd):
        counts[factory] += 1
    return " · ".join(f"{factory_label(f)} {counts[f]}장" for f in FACTORIES if counts[f])


def _production_sheet_ids(sd: Any, stage: Optional[str]) -> list[str]:
    """생산 단계 주문의 지금 확정 도면 시트 신원(옮기기 전에 확인 창) — 생산이 아니면 빈 목록."""
    if _stage_rank(stage) != _PRODUCTION_RANK:
        return []
    out: list[str] = []
    for entry in resolve_final_drawing_files(sd):
        sid = clean_sheet_id(entry.get("sheet_id"))
        if sid and sid not in out:
            out.append(sid)
    return out


def wizard_factory_view(sd: Any, *, can_set: bool, stage: Optional[str]) -> Optional[dict[str, Any]]:
    """마법사 페이지 설정 ``factory`` — 탭 앞 2공장 표시 · 도구 줄 공장 지정(§8-5 첫 두 줄).

    Args:
        sd: 주문 ``structured_data``(읽기만).
        can_set: 공장 지정 권한(도면팀 누구나 + 관리자).
        stage: 주문 큰 단계(``read_main_stage``).

    Returns:
        ``{can_set, by_sheet: {sheet_id: 2}, confirm_sheet_ids}`` 또는 None(2공장 시트가 없고 고를 수도 없음 — 화면 그대로).
    """
    by_sheet = factory_by_sheet(sd)
    can = bool(can_set and can_move_stage(stage))
    if not can and not by_sheet:
        return None
    return {"can_set": can, "by_sheet": by_sheet, "confirm_sheet_ids": _production_sheet_ids(sd, stage) if can else []}


def workbench_factory_view(sd: Any, *, order_id: int, can_set: bool, stage: Optional[str]) -> Optional[dict[str, Any]]:
    """작업실 '현재 버전' 타일 · 보낼 시트 칸 · 전달 창 한 줄(§8-5 셋째 · 넷째 줄)에 쓰는 값.

    Args:
        sd: 주문 ``structured_data``(읽기만).
        order_id: 주문 id(고르는 칸이 API 주소를 만든다).
        can_set: 공장 지정 권한(도면팀 누구나 + 관리자).
        stage: 주문 큰 단계(``read_main_stage``).

    Returns:
        ``{order_id, can_set, by_key, by_sheet, split_text, production, confirm_sheet_ids}`` 또는 None
        (2공장 장 · 시트가 없고 고를 수도 없음 — 화면 그대로).
    """
    by_key, by_sheet = factory_by_key(sd), factory_by_sheet(sd)
    can = bool(can_set and can_move_stage(stage))
    if not can and not by_key and not by_sheet:
        return None
    confirm_ids = _production_sheet_ids(sd, stage) if can else []
    return {"order_id": int(order_id), "can_set": can, "by_key": by_key, "by_sheet": by_sheet, "split_text": split_text(sd),
            "production": bool(can and _stage_rank(stage) == _PRODUCTION_RANK), "confirm_sheet_ids": confirm_ids}


def pending_split_text(pending: list[dict[str, Any]], by_sheet: dict[str, int]) -> str:
    """전달 창 한 줄 "보낼 도면 5장 — 1공장 3장 · 2공장 2장" — 보낼 시트에 2공장이 없으면 빈 글.

    Args:
        pending: 전달 대기 목록(``_pending_list`` — 시트마다 ``sheet_id``). 창을 열 때 모두 골라져 있다.
        by_sheet: :func:`~foms.services.orders.drawing_factory.factory_by_sheet` 값.
    """
    counts = {f: 0 for f in FACTORIES}
    for row in pending:
        counts[by_sheet.get(str(row.get("sheet_id") or ""), 1)] += 1
    if not counts[2]:
        return ""
    parts = " · ".join(f"{factory_label(f)} {counts[f]}장" for f in FACTORIES if counts[f])
    return f"보낼 도면 {len(pending)}장 — {parts}"
