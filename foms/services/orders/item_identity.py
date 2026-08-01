"""주문 아이템 UUID identity registry 코어 (ITEM-ID-00, §5.2).

:class:`~models.OrderItemIdentity` 위의 얇은 서비스 계층이다. **identity 발급/은퇴**
(get-or-create·tombstone)과 **read-model**(item_id UUID 로 첨부/일정 조회)만 제공한다 —
authorization 판정이나 위치-인덱스 link 은 하지 않는다(그 경계는 §5.2).

계약:

* identity 는 (order_id, item_index) 슬롯당 활성 1개다(``uq_order_item_identity_active``
  partial unique). :func:`get_or_create_identity` 는 이 유일성 위에서 멱등하다.
* **immutable / no-reuse**: 발급 UUID 는 다른 아이템에 재발급하지 않는다. 아이템이 사라지면
  :func:`retire_identity` 로 tombstone(``is_active=False`` + ``retired_at``)하고, 같은 슬롯은
  **새 UUID** 로 다시 발급한다(은퇴 UUID 재활성화 금지).
* read-model 은 순수 조회다(쓰기 0).
"""
from __future__ import annotations

import uuid
from typing import List, Optional

from sqlalchemy.orm import Session

from foms.services.datetime_kst import now_utc_naive
from models import OrderAttachment, OrderItemIdentity, OrderScheduleDate


class ItemIdentityError(RuntimeError):
    """identity 존재/상태 계약 위반(없는 identity 은퇴 시도 등)."""


def get_or_create_identity(
    session: Session, order_id: int, item_index: int
) -> OrderItemIdentity:
    """(order_id, item_index) 슬롯의 활성 identity 를 반환, 없으면 새 UUID 를 발급한다.

    ``uq_order_item_identity_active`` partial unique 덕에 멱등하다 — 이미 활성 identity 가
    있으면 그대로 돌려주고, 없을 때만 새 UUID row 를 flush 한다.

    Args:
        session: DB 세션.
        order_id: identity 를 묶을 주문 id.
        item_index: 아이템 슬롯 좌표(발급 시점 provenance). 음수는 발급하지 않는다.

    Returns:
        활성 :class:`~models.OrderItemIdentity`.

    Raises:
        ItemIdentityError: ``item_index`` 가 음수(유효 슬롯 아님).
    """
    if item_index is None or item_index < 0:
        raise ItemIdentityError(
            f"cannot issue identity for non-slot item_index {item_index!r}."
        )
    existing = (
        session.query(OrderItemIdentity)
        .filter_by(order_id=order_id, item_index=item_index, is_active=True)
        .one_or_none()
    )
    if existing is not None:
        return existing
    identity = OrderItemIdentity(
        id=str(uuid.uuid4()),
        order_id=order_id,
        item_index=item_index,
        is_active=True,
        created_at=now_utc_naive(),
    )
    session.add(identity)
    session.flush()
    return identity


def retire_identity(session: Session, identity_id: str) -> OrderItemIdentity:
    """identity 를 tombstone 한다(``is_active=False`` + ``retired_at``). UUID 는 재활성화 안 함.

    Args:
        session: DB 세션.
        identity_id: 은퇴시킬 identity UUID.

    Returns:
        은퇴된 :class:`~models.OrderItemIdentity`.

    Raises:
        ItemIdentityError: identity 가 없다.
    """
    identity = session.get(OrderItemIdentity, identity_id)
    if identity is None:
        raise ItemIdentityError(f"identity {identity_id!r} not found.")
    if identity.is_active:
        identity.is_active = False
        identity.retired_at = now_utc_naive()
        session.flush()
    return identity


def resolve_active_item_id(
    session: Session, order_id: int, item_index: Optional[int]
) -> Optional[str]:
    """(order_id, item_index) 슬롯의 활성 identity UUID(없으면 None).

    date-sync 가 일정 row 를 rebuild 할 때, read-model 이 결합을 조회할 때 쓰는 lookup 이다.
    새 identity 를 발급하지 않는다(순수 조회) — 발급은 backfill/runtime write 소관이다.

    Args:
        session: DB 세션.
        order_id: 주문 id.
        item_index: 아이템 슬롯 좌표. ``None``(공통) 이면 즉시 None.

    Returns:
        활성 identity UUID 문자열, 또는 None.
    """
    if item_index is None:
        return None
    row = (
        session.query(OrderItemIdentity.id)
        .filter_by(order_id=order_id, item_index=item_index, is_active=True)
        .one_or_none()
    )
    return row[0] if row is not None else None


def attachments_for_item(session: Session, item_id: str) -> List[OrderAttachment]:
    """item_id UUID 에 결합된 첨부를 조회한다(위치 인덱스 아님·read-only)."""
    return (
        session.query(OrderAttachment)
        .filter(OrderAttachment.item_id == item_id)
        .order_by(OrderAttachment.id)
        .all()
    )


def schedule_dates_for_item(session: Session, item_id: str) -> List[OrderScheduleDate]:
    """item_id UUID 에 결합된 일정 row 를 조회한다(위치 인덱스 아님·read-only)."""
    return (
        session.query(OrderScheduleDate)
        .filter(OrderScheduleDate.item_id == item_id)
        .order_by(OrderScheduleDate.id)
        .all()
    )
