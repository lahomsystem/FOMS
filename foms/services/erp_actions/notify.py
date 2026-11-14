"""새 ERP 할 일 제안 → 승인할 사람 폰 알림(설계서 2026-11-14-foms-graft 3.14 · D210 · D215).

:func:`proposal_created` 하나 — :func:`.lifecycle.propose` 가 **새 줄을 만든 때에만** 부른다(겹침 · 거절된 적 있음은 ``None`` 이라
부르지 않는다 — 같은 제안 알림이 두 번 가지 않는다).

- 스위치 ``FOMS_GRAFT_PUSH_ENABLED``(전역 — :func:`foms.services.graft_flags.enabled_global`)가 꺼져 있으면 아무것도 만들지 않는다.
- 받는 사람(:func:`recipients` — D215): 그 주문 담당(``parties.manager`` 이름에 이어진 켜진 계정, 프리랜서는 그 주문 연결 줄이 있을
  때만 — :func:`manager_name_recipient_ids`) 가운데 그 제안을 볼 · 승인할 수 있는 사람(:func:`.access.can_run` — 켜진 내부 계정 +
  ``actions`` 스위치 + ``policy_id`` 통과 + 주문 읽기 권한). 그런 담당이 없으면 할 일의 ``notify_team`` 팀 사람 가운데 같은 판정을
  지나는 사람. 한 제안에 :data:`MAX_RECIPIENTS` 명까지(번호 순). 0 명이면 아무것도 만들지 않는다(수 배지는 그대로).
- 사람마다 ``Notification`` 한 줄(``target_user_id``) + 받는 사람 상태(:func:`fan_out_new_notification`) — 저장점 안, 커밋은 부르는
  쪽. 폰 보내기는 **커밋 뒤에** 줄 세운다: 알림 번호를 세션 ``info`` 에 쌓아 두고, 세션의 진짜 커밋(저장점 풀기가 아니다) 뒤 듣개가
  꺼내 :func:`enqueue_push_for_notification` 한다. 되감기거나 커밋 없이 끝나면 버린다.
- 실패는 저장점만 되감고 경고 로그(제안 번호 · 예외 이름)만 남긴다 — 제안 만들기를 되돌리지 않는다.
- 잠금화면 글 · 주소는 :mod:`foms.services.notifications.erp_action_push`(손님 이름 · 날짜 없음).
"""

from __future__ import annotations

import logging
from typing import Any, Iterable

from sqlalchemy import event
from sqlalchemy.orm import Session

from foms.services.ai_staff.registry import agent_of
from foms.services.erp_actions.access import can_run
from foms.services.erp_actions.registry import ACTIONS, ActionSpec
from foms.services.graft_flags import enabled_global
from foms.services.notifications.erp_action_push import (
    ERP_ACTION_PROPOSAL_TYPE,
    ERP_ACTION_PUSH_TITLE,
    erp_action_message,
)
from foms.services.notifications.push_sender import enqueue_push_for_notification
from foms.services.notifications.recipients import (
    broad_recipient_ids,
    fan_out_new_notification,
    manager_name_recipient_ids,
    team_condition,
)
from foms.services.orders.manager_names import order_manager_names
from models import Notification, Order, User

logger = logging.getLogger(__name__)

__all__ = ["MAX_RECIPIENTS", "PENDING_KEY", "proposal_created", "recipients"]

MAX_RECIPIENTS = 20
#: 커밋 뒤 폰으로 보낼 알림 번호를 쌓아 두는 세션 ``info`` 열쇠.
PENDING_KEY = "foms_erp_action_push_pending"


# ── 받는 사람 ────────────────────────────────────────────────────────────
def _deciders(session: Any, ids: Iterable[int], spec: ActionSpec, order: Any) -> list[int]:
    """번호들 가운데 이 제안을 볼 · 승인할 수 있는 사람(번호 순) — 사용자 줄은 한 질의로 읽는다."""
    wanted = sorted({int(uid) for uid in ids})
    if not wanted:
        return []
    users = {int(user.id): user for user in session.query(User).filter(User.id.in_(wanted)).all()}
    return [uid for uid in wanted if uid in users and can_run(users[uid], spec, order)]


def recipients(session: Any, proposal: Any) -> list[int]:
    """폰 알림을 받을 사람 번호(D215) — 주문 담당 먼저, 그런 담당이 없으면 할 일의 팀. :data:`MAX_RECIPIENTS` 명까지.

    Args:
        session: DB 세션.
        proposal: 방금 만든 제안 줄(``action`` · ``order_id``).

    Returns:
        사용자 번호 목록(번호 순). 할 일 · 주문이 없거나 아무도 승인할 수 없으면 빈 목록.
    """
    spec = ACTIONS.get(getattr(proposal, "action", None))
    order = session.get(Order, proposal.order_id) if getattr(proposal, "order_id", None) is not None else None
    if spec is None or order is None:
        return []
    names = order_manager_names(order.structured_data, getattr(order, "manager_name", None))
    chosen = _deciders(session, manager_name_recipient_ids(session, names, order.id) if names else (), spec, order)
    condition = team_condition(spec.notify_team) if not chosen and spec.notify_team else None
    if condition is not None:
        chosen = _deciders(session, broad_recipient_ids(session, condition), spec, order)
    return chosen[:MAX_RECIPIENTS]


# ── 알림 줄 ──────────────────────────────────────────────────────────────
def _notify_one(session: Any, proposal: Any, spec: ActionSpec, user_id: int) -> int:
    """한 사람 몫 알림 줄 + 받는 사람 상태. 만든 알림 번호."""
    agent = agent_of(proposal.proposed_by)
    notif = Notification(
        notification_type=ERP_ACTION_PROPOSAL_TYPE, target_type="USER", target_user_id=int(user_id),
        order_id=proposal.order_id, is_urgent=False, title=ERP_ACTION_PUSH_TITLE,
        message=erp_action_message(spec.label, int(proposal.order_id), int(proposal.id)),
        created_by_user_id=None, created_by_name=agent.label if agent else None, is_read=False)
    session.add(notif)
    session.flush()
    fan_out_new_notification(session, notif)
    return int(notif.id)


def proposal_created(session: Any, proposal: Any) -> int:
    """새 제안 하나의 폰 알림 — 받는 사람마다 알림 줄을 만들고, 폰 보내기는 커밋 뒤로 미룬다(커밋은 부르는 쪽).

    Args:
        session: :func:`.lifecycle.propose` 의 세션.
        proposal: 방금 만든(flush 된) 제안 줄.

    Returns:
        만든 알림 줄 수 — 스위치 끔 · 받는 사람 0 명 · 실패면 0.
    """
    if not enabled_global("push"):
        return 0
    spec = ACTIONS.get(getattr(proposal, "action", None))
    try:
        with session.begin_nested():
            people = recipients(session, proposal) if spec is not None else []
            ids = [_notify_one(session, proposal, spec, uid) for uid in people]
    except Exception as exc:  # noqa: BLE001 — 알림 실패가 제안 만들기를 되돌리지 않는다(저장점만 되감긴다)
        logger.warning("[ERP-ACTION-PUSH] 알림 줄 못 만듦 proposal=%s error=%s",
                       getattr(proposal, "id", None), type(exc).__name__)
        return 0
    if ids:
        session.info.setdefault(PENDING_KEY, []).extend(ids)
    return len(ids)


# ── 커밋 뒤 폰 보내기 ────────────────────────────────────────────────────
def _send_pending(session: Session, ids: list[int]) -> None:
    """쌓인 알림 번호를 폰 보내기 줄에 세운다 — 큐가 없을 때 표시를 적는 일은 따로 연 세션이 한다(커밋 뒤라 이 세션은 쓰지 않는다)."""
    own = Session(bind=session.get_bind())
    try:
        for notification_id in ids:
            try:
                enqueue_push_for_notification(int(notification_id), db=own)
            except Exception as exc:  # noqa: BLE001 — 한 건 실패가 나머지를 막지 않는다(알림 줄은 이미 커밋됐다)
                own.rollback()
                logger.warning("[ERP-ACTION-PUSH] 폰 보내기 줄 세우기 실패 notification=%s error=%s",
                               notification_id, type(exc).__name__)
    finally:
        own.close()


@event.listens_for(Session, "after_commit")
def _after_commit(session: Session) -> None:
    """진짜 커밋 뒤에만 쌓인 알림을 보낸다 — 저장점 풀기(``begin_nested`` 끝)도 이 사건을 내므로 그때는 건너뛴다."""
    if session.in_nested_transaction():
        return
    ids = session.info.pop(PENDING_KEY, None)
    if ids:
        _send_pending(session, list(ids))


@event.listens_for(Session, "after_transaction_end")
def _after_transaction_end(session: Session, transaction: Any) -> None:
    """맨 바깥 트랜잭션이 커밋 없이 끝나면(되감기 · 닫기) 쌓인 알림 번호를 버린다(그 알림 줄은 없어졌다)."""
    if getattr(transaction, "parent", None) is None:
        session.info.pop(PENDING_KEY, None)
