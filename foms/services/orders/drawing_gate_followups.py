"""도면 게이트(2a-2)의 뒤처리 — 고객확인 무효화·복원(M16)과 캐시 무효화.

도면 라우트(수정요청·수정요청 취소·전달·전달 취소)는 다른 갈래가 구조를 크게 바꾸는 중이라,
2a-2 는 라우트에 이 모듈 함수 호출 한두 줄만 더한다(합치기 쉽게).

* M16: 수정요청이 오면 ``blueprint.customer_confirmed`` 를 무효로 하고, 그 요청을 취소하면
  되살린다. 게이트는 ``drawing_status`` 를 보므로 막는 데 쓰지 않는다 — 감사·백필 도구가
  사실대로 읽게 하는 것이 목적이다. ``confirmed_at``·``confirmed_by`` 는 이력으로 둔다.
* 캐시: 화면(PC 그리드·생산 보드 배지)과 서버 게이트가 같은 답을 내려면, 도면 상태가 바뀐
  순간 CONFIRM·생산 단계 패널 캐시(300초)와 첨부 개수 캐시(120초)를 비워야 한다.
"""
from __future__ import annotations

from typing import Any, Optional

from foms.services.common.dashboard_cache import (
    ATTACHMENT_DASHBOARD_FAMILIES,
    DASHBOARD_FAMILY_CONSTRUCTION,
    DASHBOARD_FAMILY_DRAWING,
    DASHBOARD_FAMILY_PRODUCTION,
    invalidate_dashboard_families,
    invalidate_order_dashboard_families,
)
from foms.services.datetime_kst import now_utc_naive

__all__ = [
    "invalidate_after_drawing_revision",
    "invalidate_after_drawing_transfer",
    "invalidate_customer_confirmation",
    "restore_customer_confirmation",
]

_INVALIDATED_FLAG = "customer_confirmation_invalidated"


def invalidate_customer_confirmation(sd: dict, request_entry: dict) -> bool:
    """수정요청 순간 고객확인 표시를 무효로 한다(M16). 바꿨으면 True.

    ``sd`` 는 호출자가 deepcopy 한 dict 이고 ``request_entry`` 는 방금 이력에 붙인
    REQUEST_REVISION 항목이다(둘 다 제자리 수정 — 호출자가 재대입·flag_modified 한다).
    """
    blueprint = sd.get("blueprint")
    if not isinstance(blueprint, dict) or blueprint.get("customer_confirmed") is not True:
        return False
    blueprint = dict(blueprint)
    blueprint["customer_confirmed"] = False
    blueprint["invalidated_at"] = now_utc_naive().strftime("%Y-%m-%d %H:%M:%S")
    blueprint["invalidated_by_request_at"] = request_entry.get("at")
    sd["blueprint"] = blueprint
    request_entry[_INVALIDATED_FLAG] = True
    return True


def _has_open_revision(history: list) -> bool:
    """마지막 전달·수령 확정 뒤에 남은 수정요청이 있는가."""
    for entry in reversed(history or []):
        if not isinstance(entry, dict):
            continue
        action = entry.get("action")
        if action == "REQUEST_REVISION":
            return True
        if action in ("TRANSFER", "CONFIRM_RECEIPT"):
            return False
    return False


def restore_customer_confirmation(sd: dict, cancelled_entry: Optional[dict], remaining_history: list) -> bool:
    """취소한 수정요청이 무효로 만든 고객확인을 되살린다(M16). 바꿨으면 True.

    취소한 요청에 무효화 표시가 있고, 무효화가 그 요청 때문이며, 남은 열린 요청이 없을 때만.
    """
    if not isinstance(cancelled_entry, dict) or not cancelled_entry.get(_INVALIDATED_FLAG):
        return False
    blueprint = sd.get("blueprint")
    if not isinstance(blueprint, dict) or blueprint.get("customer_confirmed") is True:
        return False
    if blueprint.get("invalidated_by_request_at") != cancelled_entry.get("at"):
        return False
    if _has_open_revision(remaining_history):
        return False
    blueprint = {k: v for k, v in blueprint.items()
                 if k not in ("invalidated_at", "invalidated_by_request_at")}
    blueprint["customer_confirmed"] = True
    sd["blueprint"] = blueprint
    return True


def invalidate_after_drawing_revision(order: Any) -> None:
    """수정요청·수정요청 취소 커밋 뒤 — 주문 단계 family + 생산·시공 family 를 비운다."""
    invalidate_order_dashboard_families(
        order,
        extra=(DASHBOARD_FAMILY_DRAWING, DASHBOARD_FAMILY_PRODUCTION, DASHBOARD_FAMILY_CONSTRUCTION),
    )


def invalidate_after_drawing_transfer() -> None:
    """전달·전달 취소 커밋 뒤 — 첨부 행과 개수가 바뀌므로 첨부를 읽는 family 전부를 비운다."""
    invalidate_dashboard_families(*sorted(ATTACHMENT_DASHBOARD_FAMILIES))
