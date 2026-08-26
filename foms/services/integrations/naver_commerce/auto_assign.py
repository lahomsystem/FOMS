"""수집 주문 담당자 자동 배정 — ERP '주문담당자' 입력을 배정 원장으로 옮긴다.

수집 주문은 실존 영업사원이 없으니 보류함 계정(:data:`constants.OWNER_USERNAME`)을 SALES
owner 로 달고 들어온다. 그런데 현장은 워크벤치의 '담당자 지정' 버튼 대신 ERP 상세의
**주문담당자 입력칸**(``structured_data.parties.manager.name``)에 이름을 타이핑한다
(운영 실측 2026-08-26: 수집 주문 11건 전부 보류함 owner, 사람 owner 0건).

그래서 화면에는 담당자가 있는데 배정 원장은 여전히 "주인 없음"이었다. 그 간극이 실제로
문제를 낳는 곳이 취소·반품 알림이다 — :mod:`claim_watch` 는 SALES owner 로 수신자를
정하므로, 이름을 적어 둔 담당자는 알림을 못 받았다.

여기서는 **이름이 사람 계정 1명으로 확정될 때만** 배정을 옮긴다:

* 현재 SALES owner 가 보류함 계정일 때만 발동한다. 사람이 이미 owner 면 손대지 않는다 —
  자유 텍스트 한 줄로 실제 배정을 갈아치우면 사유 없는 교체가 원장에 쌓인다.
* 이름이 **활성 사용자 정확히 1명**과 일치할 때만 옮긴다. 0명(외부인·오타)이나 2명 이상
  (동명이인)이면 아무것도 하지 않고 로그만 남긴다.
* 저장 트랜잭션을 절대 깨지 않는다. 실패는 삼키고 로그로 남긴다 — 담당자 이름 저장이
  배정 실패 때문에 롤백되면 사용자는 이유를 알 수 없다.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Optional

from sqlalchemy.orm import Session

from foms.services.integrations.naver_commerce.constants import OWNER_USERNAME
from models import OrderAssignment, User

logger = logging.getLogger(__name__)

#: 자동 배정으로 남기는 교체 사유. 원장에서 사람 지정과 구분하려고 문구를 고정한다.
AUTO_ASSIGN_REASON = "ERP 주문담당자 입력에 따른 자동 배정"


def _manager_name(structured_data: Any) -> str:
    """``structured_data`` 에서 주문담당자 이름을 꺼낸다(없으면 빈 문자열)."""
    if not isinstance(structured_data, dict):
        return ""
    parties = structured_data.get("parties")
    if not isinstance(parties, dict):
        return ""
    manager = parties.get("manager")
    if not isinstance(manager, dict):
        return ""
    return str(manager.get("name") or "").strip()


def _holdbox_owns(session: Session, order_id: int) -> bool:
    """현재 active SALES owner 가 보류함 계정인지."""
    row = (
        session.query(OrderAssignment.user_id)
        .join(User, User.id == OrderAssignment.user_id)
        .filter(
            OrderAssignment.order_id == int(order_id),
            OrderAssignment.domain == "SALES",
            OrderAssignment.active.is_(True),
            User.username == OWNER_USERNAME,
        )
        .first()
    )
    return row is not None


def _resolve_single_user(session: Session, name: str) -> Optional[User]:
    """이름과 정확히 일치하는 **활성 사용자 1명**을 찾는다(0명·2명 이상이면 None).

    보류함 계정은 사람이 아니므로 후보에서 뺀다. 동명이인은 자동으로 고르지 않는다 —
    잘못 고르면 남의 주문이 남의 알림이 된다.
    """
    candidates = (
        session.query(User)
        .filter(
            User.name == name,
            User.is_active.is_(True),
            User.username != OWNER_USERNAME,
        )
        .limit(2)
        .all()
    )
    return candidates[0] if len(candidates) == 1 else None


def auto_assign_sales_owner_from_manager(
    session: Session, *, order_id: int, structured_data: Any, actor_user_id: Optional[int],
    now: Optional[datetime] = None,
) -> Optional[int]:
    """보류함이 owner 인 주문의 SALES owner 를 주문담당자 이름의 주인으로 옮긴다.

    ERP 저장 경로(전체 저장 PUT · 인라인 PATCH)에서 **주문 저장과 같은 트랜잭션**으로
    부른다. 주문 행 락 안에서 부르는 것이 전제라 REV-00 mutation 을 새로 열지 않는다
    (:func:`~foms.services.orders.assignment.replace_sales_owner_in_tx`).

    Args:
        session: 저장 트랜잭션 세션(커밋은 호출자).
        order_id: 대상 주문 id.
        structured_data: 저장 직전 정본 structured_data.
        actor_user_id: 저장을 수행한 사용자 id(감사 원장 author). 없으면 배정 대상 본인.
        now: 시각 주입(테스트).

    Returns:
        새로 배정된 user id. 조건 미충족·실패면 ``None``(저장은 그대로 진행된다).
    """
    try:
        name = _manager_name(structured_data)
        if not name:
            return None
        if not _holdbox_owns(session, order_id):
            return None
        user = _resolve_single_user(session, name)
        if user is None:
            logger.info(
                "[NAVER] 담당자 자동 배정 보류 order=%s name=%r — 활성 사용자 1명 확정 실패",
                order_id, name,
            )
            return None

        from foms.services.orders.assignment import replace_sales_owner_in_tx

        # SAVEPOINT: 배정 쓰기가 실패해도 바깥 저장 트랜잭션은 살아 있어야 한다.
        # 예외만 삼키고 SAVEPOINT 를 안 쓰면 PostgreSQL 은 트랜잭션 전체를 abort 상태로
        # 만들어, 이어지는 주문 저장 커밋이 통째로 죽는다.
        with session.begin_nested():
            replace_sales_owner_in_tx(
                session, order_id=int(order_id), user_id=int(user.id),
                actor_user_id=int(actor_user_id or user.id),
                reason=AUTO_ASSIGN_REASON, now=now,
            )
        logger.warning("[NAVER] 담당자 자동 배정 order=%s user=%s(%s)",
                       order_id, user.id, name)
        return int(user.id)
    except Exception:  # noqa: BLE001 - 저장을 막지 않는다(부수효과 계약)
        logger.exception("[NAVER] 담당자 자동 배정 실패 order=%s", order_id)
        return None


__all__ = ["AUTO_ASSIGN_REASON", "auto_assign_sales_owner_from_manager"]
