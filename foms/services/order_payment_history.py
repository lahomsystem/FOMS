"""예약금을 마지막으로 고친 사람·때 읽기 (2026-11-11).

``PAYMENT_CHANGED`` 쓰기는 :mod:`foms.services.order_payment_sync` 가 맡고, 이 모듈은
화면에 낼 읽기만 한다(쓰기 모듈은 파일 크기 래칫 500줄에 닿아 따로 둔다).
"""

from __future__ import annotations

from foms.services.datetime_kst import format_datetime_kst
from foms.services.order_payment_sync import PAYMENT_CHANGED_EVENT
from models import OrderEvent, User

__all__ = ["last_deposit_changes"]


def last_deposit_changes(session, order_ids: list[int]) -> dict[int, dict[str, str]]:
    """주문마다 예약금(``payment.deposit``)을 마지막으로 고친 사람과 때(KST)를 돌려준다.

    ``PAYMENT_CHANGED`` 는 :mod:`foms.services.order_payment_sync` 가 유일하게 남긴다(2026-11-11).
    네이버 관계 표·검색 표(화면 상한 수 건)와 주문 수정 화면(1건)이 같이 쓴다 —
    주문마다 따로 묻지 않고 한 번에 읽는다.

    Args:
        session: DB 세션.
        order_ids: 화면에 낼 주문 id.

    Returns:
        ``{order_id: {"by": 이름, "at": "MM-DD HH:MM"}}`` — 고친 기록이 없는 주문은 빠진다.
    """
    if not order_ids:
        return {}
    rows = (
        session.query(OrderEvent.order_id, OrderEvent.payload, OrderEvent.created_at, User.name)
        .outerjoin(User, User.id == OrderEvent.created_by_user_id)
        .filter(OrderEvent.order_id.in_(order_ids),
                OrderEvent.event_type == PAYMENT_CHANGED_EVENT)
        .order_by(OrderEvent.created_at.desc(), OrderEvent.id.desc())
        .all()
    )
    found: dict[int, dict[str, str]] = {}
    for order_id, payload, created_at, user_name in rows:
        if int(order_id) in found:
            continue
        if not isinstance(payload, dict) or payload.get("field") != "payment.deposit":
            continue
        found[int(order_id)] = {
            # 사람 없이 바뀐 기록(시스템 경로)은 '자동' 으로 말한다 — 빈칸이면 "모름"으로 읽힌다.
            "by": (user_name or "").strip() or "자동",
            "at": format_datetime_kst(created_at, "%m-%d %H:%M") or "",
        }
    return found
