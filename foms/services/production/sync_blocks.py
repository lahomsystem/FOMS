"""도면 카드 판의 주문 막힘 — 30초 받아 오기 · 제작 완료 뒤 카드 칸(비평 C06 · C09).

받아 오기(``GET /api/production/part-marks``)는 표시 줄과 같이 주문마다 **지금** 막힘을 싣고, 판 JS 는 카드를 이미 있는 막힌 칸으로
다시 그린다(그사이 보류 · 도면 고치는 중 · 제작 완료가 돼도 30초 안에 — 누르면 늘 거절되던 칸을 없앤다).

* 생산 단계 주문: 판이 그릴 때와 같은 :func:`~foms.services.production.part_card_state.order_block` — 보류 · 도면 고치는 중(주문 통째는
  ``all``, 생산 단계 도면별 막힘은 그 장만 ``keys``).
* 생산 단계가 아닌 주문(제작 완료 뒤 등 — 카드 쓰기는 모든 누름이 409 ``NOT_IN_PRODUCTION``): 단계 칸 하나(``all``) — 글 = 첫 화면 단계 글
  ("제작 완료" · "컨펌 기다림"), 까닭 = 그 거절 글 그대로. 생산 단계 판정은 카드 쓰기(``part_mark_write.check_order``)와 같은 함수.

순수 계산 · 쿼리 0 — 부르는 쪽이 주문 JSON 을 읽어 넘긴다.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, Optional

from foms.services.drawing_confirm_cleanup import resolve_final_drawing_files
from foms.services.orders.drawing_fix import blocked
from foms.services.orders.state_axes import read_main_stage
from foms.services.production.part_card_state import BLOCK_HOLD, order_block
from foms.services.production.part_mark_write import NOT_IN_PRODUCTION_MESSAGE
from foms.services.production_home_read_model import production_home_stage

#: 생산 단계가 아닌 주문의 막힘 코드 — 카드 쓰기 거절과 같은 코드(판 JS 는 이 코드면 모든 칸을 막는다).
NOT_IN_PRODUCTION = "NOT_IN_PRODUCTION"
#: 시공 단계(제작 완료) 칸은 완료 칸 색(``pp-st-done``), 그 밖 단계는 보류 칸 색.
_DONE_KIND = "done"
_PRODUCTION = "PRODUCTION"
_CONSTRUCTION = "CONSTRUCTION"


def stage_block(stage: Optional[str]) -> dict[str, str]:
    """생산 단계가 아닌 주문의 카드 칸 — 글 = 첫 화면 단계 글(시공 단계 = "제작 완료"), 까닭 = 카드 쓰기 거절 글 그대로."""
    return {"kind": _DONE_KIND if stage == _CONSTRUCTION else BLOCK_HOLD, "text": production_home_stage(stage, True, [], False)[0],
            "why": NOT_IN_PRODUCTION_MESSAGE, "code": NOT_IN_PRODUCTION}


#: 제작 완료(시공 단계) 칸 — 판 설정에 실어 제작 완료 성공 응답 때 판 JS 가 그 주문 카드에 그린다(C09).
DONE_BLOCK = stage_block(_CONSTRUCTION)


def _hold_on(sd: dict[str, Any]) -> bool:
    production = sd.get("production") if isinstance(sd.get("production"), dict) else {}
    hold = production.get("hold") if isinstance(production.get("hold"), dict) else {}
    return bool(hold.get("active"))


def order_sync_block(sd: Any, status: Any = None, flat_stage: Any = None) -> dict[str, Any]:
    """주문 하나의 지금 막힘 ``{all, keys}`` — ``all`` = 주문 통째 칸(없으면 None), ``keys`` = 그 장만 막힌 장 key → 칸.

    Args:
        sd: 주문 ``structured_data``.
        status: 주문 ``status``(단계 판정의 옛 값 — ``read_main_stage``).
        flat_stage: 주문 ``erp_stage_code``(단계를 못 읽는 옛 주문의 칸 글에만).
    """
    sd = sd if isinstance(sd, dict) else {}
    stage = read_main_stage(SimpleNamespace(structured_data=sd, status=status, is_erp_order=True))
    if stage != _PRODUCTION:
        return {"all": stage_block(stage or flat_stage), "keys": {}}
    row = {"hold_active": _hold_on(sd), "structured_data": sd}
    whole = order_block(row)
    if whole is not None:
        return {"all": whole, "keys": {}}
    fix = blocked(sd)
    keys = {}
    for entry in resolve_final_drawing_files(sd):
        block = order_block(row, entry, fix=fix)
        if block is not None:
            keys[entry["key"]] = block
    return {"all": None, "keys": keys}


__all__ = ["DONE_BLOCK", "NOT_IN_PRODUCTION", "order_sync_block", "stage_block"]
