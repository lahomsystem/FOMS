"""생산 화면(PC 보드·모바일 카드·태블릿 칸반·태블릿 시트)의 도면 게이트 표시 — 2차 묶음 2a-2 (Q2).

생산팀이 도면 수정요청을 알 수 있게 카드에 "도면 수정 중" 배지를 달고, [제작 시작] 이 서버에서
막힐 주문은 버튼 대신(비관리자) 또는 버튼과 함께(관리자) 막힌 이유를 보인다.

판정은 서버 제작 시작 라우트와 **같은 함수**(``confirm_drawing_gate``)를 부른다(화면 == 서버).
생산 보드 행은 캐시 없이 매 요청 읽으므로 수령 확정 직후 배지·막힘이 바로 사라진다.
영업 담당 이름은 막힌 행이 있을 때만 한 번에 조회한다(쿼리 최대 1회).
"""
from __future__ import annotations

from typing import Any, Iterable, Mapping

from foms.services.erp_display import _ensure_dict
from foms.services.orders.confirm_drawing_gate import (
    production_block_reason,
    production_drawing_badge,
    production_start_block,
)
from foms.services.orders.erp_policy_permissions import get_assignee_ids

__all__ = ["attach_production_drawing_gate"]

_WAITING_LABEL = "제작대기"


def attach_production_drawing_gate(db: Any, rows: Iterable[dict[str, Any]], orders_by_id: Mapping[int, Any]) -> None:
    """행 dict 에 ``drawing_badge``·``production_start_blocked``·``production_start_block_reason`` 를 붙인다.

    ``rows`` 는 ``stage``(버킷 라벨)·``is_sales_approved``·``id`` 를 가진 생산 행이고,
    ``orders_by_id`` 는 그 행의 Order(단계 원문 ``erp_stage_code``·``structured_data`` 출처)다.
    배지는 대기·진행 중 모두, 막힘은 [제작 시작] 이 보이는 제작 대기(승인 끝) 행에만 단다.
    """
    pending: list[tuple[dict[str, Any], Any, list[int]]] = []
    for row in rows:
        order = orders_by_id.get(row.get("id"))
        sd = _ensure_dict(getattr(order, "structured_data", None)) if order is not None else {}
        row["drawing_badge"] = production_drawing_badge(sd)
        row["production_start_blocked"] = False
        row["production_start_block_reason"] = ""
        if order is None or row.get("stage") != _WAITING_LABEL or not row.get("is_sales_approved"):
            continue
        block = production_start_block(getattr(order, "erp_stage_code", None), sd)
        if block is not None:
            pending.append((row, block, get_assignee_ids(order, "SALES_DOMAIN")))
    if not pending:
        return
    names = _user_names(db, {uid for _row, _block, ids in pending for uid in ids})
    for row, block, ids in pending:
        row["production_start_blocked"] = True
        row["production_start_block_reason"] = production_block_reason(block, [names.get(i, "") for i in ids])


def _user_names(db: Any, user_ids: set[int]) -> dict[int, str]:
    """영업 담당 id → 이름(한 번에 조회). 없으면 빈 dict."""
    if not user_ids:
        return {}
    from models import User

    rows = db.query(User.id, User.name).filter(User.id.in_(sorted(user_ids))).limit(len(user_ids)).all()
    return {int(uid): str(name or "") for uid, name in rows}
