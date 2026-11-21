"""CS · 완료 문지기 — 남은 제품 시공이 있으면 막는다 (제품마다 '시공 끝' 2단계 7절).

설계: ``docs/specs/2026-11-21-item-construction-done_SPEC.md`` §7 · 결정 N4 · N7.

판정: 스위치(:func:`is_item_construction_done_enabled`)가 켜져 있고, 목표가 CS · 완료이고, 주문이
**부분 시공 중**(:func:`is_partial_open` — '시공 끝' 제품도 남은 제품도 있다)이면 막는다. 오류 코드
``ITEMS_CONSTRUCTION_OPEN``, 글은 :func:`blocked_message` ("11/17 부엌가구 시공이 남아 있어요").

관리자 강제 변경(N4)만 ``close_remaining_items: true`` + 사유로 남은 제품을 ``admin_override`` 로 찍고
넘긴다(:func:`close_remaining_items`). 관리자 뚫기(``admin_override``)로는 이 문을 뚫지 못한다.

이 모듈은 잎(leaf)이다 — 전이 엔진(``order_transition_service``)과 강제 변경 서비스(``stage_override``)가
함께 import 하므로 그 둘(과 그 둘을 import 하는 모듈)을 import 하지 않는다.
"""
from __future__ import annotations

import copy
from typing import Any, Optional

from flask import jsonify
from sqlalchemy.orm.attributes import flag_modified

from foms.services.datetime_kst import get_today_kst, now_kst
from foms.services.feature_flags import is_item_construction_done_enabled
from foms.services.orders.erp_policy_constants import STAGE_NAME_TO_CODE
from foms.services.orders.item_construction_done import (
    SOURCE_ADMIN_OVERRIDE,
    apply_done_marks,
    blocked_message,
    is_partial_open,
    remaining_lines,
    remaining_summary,
)
from models import SecurityLog

__all__ = [
    "CLOSING_STAGES",
    "ITEMS_CONSTRUCTION_OPEN",
    "ItemsConstructionOpen",
    "close_remaining_items",
    "closing_stage_code",
    "items_gate_blocks",
    "items_gate_message",
    "items_open_body",
    "items_open_error",
    "items_open_response",
]

ITEMS_CONSTRUCTION_OPEN = "ITEMS_CONSTRUCTION_OPEN"

#: 문지기가 지키는 목표 단계 — 여기로 가는 쓰기는 남은 제품이 있으면 막힌다.
CLOSING_STAGES = frozenset({"CS", "COMPLETED"})


class ItemsConstructionOpen(Exception):
    """부분 시공 중인 주문을 CS · 완료로 옮기려 했다(409 ``ITEMS_CONSTRUCTION_OPEN``).

    전이 엔진은 이 클래스와 ``TransitionError`` 를 함께 이은 하위 클래스를 던진다 — 엔진 예외를
    받는 라우트들(``except TransitionError``)이 고치지 않고도 같은 코드 · 같은 상태로 답한다.
    """

    status_code = 409
    error_code = ITEMS_CONSTRUCTION_OPEN

    def __init__(self, message: str, *, order_id: Optional[int] = None, remaining: str = ""):
        super().__init__(message)
        self.order_id = order_id
        self.remaining = remaining


def closing_stage_code(target: Any) -> Optional[str]:
    """목표 글(코드 · 한글 라벨)이 CS · 완료면 그 코드, 아니면 None."""
    text = str(target or "").strip()
    code = text if text in CLOSING_STAGES else STAGE_NAME_TO_CODE.get(text)
    return code if code in CLOSING_STAGES else None


def items_gate_blocks(structured_data: Any, target: Any, *, current: Any = None) -> bool:
    """이 목표로 가는 쓰기를 막아야 하나 — 스위치 켜짐 + 목표 CS · 완료 + 부분 시공 중.

    ``current`` (지금 단계 · 상태 글)가 목표와 같으면 옮기는 쓰기가 아니므로 막지 않는다.
    """
    code = closing_stage_code(target)
    if code is None or closing_stage_code(current) == code:
        return False
    if not is_item_construction_done_enabled():
        return False
    return is_partial_open(structured_data)


def items_gate_message(structured_data: Any, from_value: Any, to_value: Any) -> Optional[str]:
    """전이 엔진용 판정 — 막히면 오류 글, 아니면 None. 제자리 전이(from == to)는 막지 않는다."""
    if items_gate_blocks(structured_data, to_value, current=from_value):
        return blocked_message(structured_data)
    return None


def items_open_error(order: Any) -> ItemsConstructionOpen:
    """주문 하나의 문지기 예외(글 · 주문 번호 · 남은 제품 한 줄)."""
    sd = getattr(order, "structured_data", None)
    return ItemsConstructionOpen(
        blocked_message(sd), order_id=getattr(order, "id", None), remaining=remaining_summary(sd),
    )


def _body(message: str, order_id: Optional[int], remaining: str, bulk: bool) -> dict[str, Any]:
    if bulk and order_id is not None:
        message = f"#{order_id} {message}"
    return {
        "success": False,
        "code": ITEMS_CONSTRUCTION_OPEN,
        "message": message,
        "error": message,
        "data": {"order_id": order_id, "remaining_summary": remaining},
    }


def items_open_body(order: Any, *, bulk: bool = False) -> dict[str, Any]:
    """문지기 거부 본문 — ``error`` 와 ``message`` 를 둘 다 싣는다(라우트마다 읽는 키가 다르다)."""
    exc = items_open_error(order)
    return _body(str(exc), exc.order_id, exc.remaining, bulk)


def items_open_response(exc: ItemsConstructionOpen, *, bulk: bool = False):
    """잡은 :class:`ItemsConstructionOpen` 을 라우트 응답 ``(json, 409)`` 로 바꾼다."""
    return jsonify(_body(str(exc), exc.order_id, exc.remaining, bulk)), exc.status_code


def close_remaining_items(order: Any, *, user_id: Any, user_name: str, reason: str = "",
                          db: Any = None) -> list[str]:
    """남은 제품 전부를 ``admin_override`` 로 '시공 끝' 찍는다(관리자 강제 변경 N4).

    ``copy.deepcopy`` → 찍기 → 재대입 → ``flag_modified`` 다. 커밋하지 않는다 — 부르는 쪽 전이와 같은
    거래에 실린다(전이가 실패해 되감기면 찍기도 함께 사라진다). ``db`` 를 주면 같은 거래에 감사행
    한 줄을 싣는다. 찍은 uid 목록을 돌려준다.
    """
    sd = copy.deepcopy(order.structured_data if isinstance(order.structured_data, dict) else {})
    lines = remaining_lines(sd)
    refs = [line.ref for line in lines]
    if not refs:
        return []
    try:
        actor_id = int(user_id) if user_id is not None else None
    except (TypeError, ValueError):
        actor_id = None
    marked = apply_done_marks(
        sd, refs,
        day_iso=get_today_kst().isoformat(),
        at_iso=now_kst().isoformat(timespec="seconds"),
        user_id=actor_id,
        user_name=str(user_name or ""),
        source=SOURCE_ADMIN_OVERRIDE,
        attempt_id=None,
    )
    if marked:
        order.structured_data = sd
        flag_modified(order, "structured_data")
        if db is not None:
            names = " · ".join(line.name for line in lines)
            db.add(SecurityLog(
                user_id=actor_id,
                message=f"주문 #{order.id} 남은 제품 시공 끝 처리(관리자 강제 변경): {names} ({reason})",
            ))
    return marked
