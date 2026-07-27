"""UPLOAD-INTENT-01: pre-file upload DRAFT lifecycle (create / cancel / finalize).

파일이 R2 에 도착하기 **전에** drawing revision / AS cycle 업로드 의도를 durable DRAFT
로 예약한다. :func:`create_upload_draft` 는 멱등(같은 intent 재요청은 기존 DRAFT 반환),
:func:`cancel_upload_draft` 는 terminal 마킹(멱등·no-op), :func:`finalize_upload_draft`
만 Order ``mutation_version`` 을 1회 bump 한다(REV-00). 만료는 24h **lazy** 판정이며
(scheduler 없음) EXPIRED 는 :func:`effective_state` 로 조회 시 계산한다.

경계(UPLOAD-INTENT-01): 만료 자동 정리 scheduler·R2 객체 삭제·upload_ticket/storage 는
이 모듈이 건드리지 않는다(UPLOAD-02 소관). 모든 함수는 ``flush`` 만 하고 ``commit`` 은
호출자가 소유한다.
"""
from __future__ import annotations

import datetime
from typing import Optional, Sequence

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from foms.services.datetime_kst import now_utc_naive
from models import (
    UPLOAD_DRAFT_KINDS,
    UPLOAD_DRAFT_TTL_HOURS,
    Order,
    UploadDraft,
)

__all__ = [
    "UploadDraftError",
    "cancel_upload_draft",
    "create_upload_draft",
    "effective_state",
    "finalize_upload_draft",
    "is_expired",
]

_TTL = datetime.timedelta(hours=UPLOAD_DRAFT_TTL_HOURS)


class UploadDraftError(ValueError):
    """UPLOAD-INTENT-01 계약 위반(알 수 없는 kind, 잘못된 전이, 부재 DRAFT 등)."""


def is_expired(draft: UploadDraft, now: Optional[datetime.datetime] = None) -> bool:
    """DRAFT 가 24h 만료를 지났는지 **lazy** 판정한다(상태 미기록, scheduler 없음).

    Args:
        draft: 판정 대상 DRAFT.
        now: 기준 시각(테스트 주입용). 기본 :func:`now_utc_naive`.

    Returns:
        ``now >= expires_at`` 이면 True.
    """
    now = now or now_utc_naive()
    return draft.expires_at is not None and now >= draft.expires_at


def effective_state(draft: UploadDraft, now: Optional[datetime.datetime] = None) -> str:
    """저장 state + lazy 만료를 합친 실효 state 를 돌려준다.

    저장된 ``state`` 가 ``DRAFT`` 이고 만료를 지났으면 ``EXPIRED`` 로 계산한다(DB 는 여전히
    ``DRAFT``). terminal(FINALIZED/CANCELLED)은 그대로 반환한다.

    Args:
        draft: 대상 DRAFT.
        now: 기준 시각(테스트 주입용).

    Returns:
        ``DRAFT`` | ``FINALIZED`` | ``CANCELLED`` | ``EXPIRED``.
    """
    if draft.state == "DRAFT" and is_expired(draft, now):
        return "EXPIRED"
    return draft.state


def _lookup_idem(
    session: Session, order_id: int, kind: str, idempotency_key: str
) -> Optional[UploadDraft]:
    """``(order_id, kind, idempotency_key)`` 로 기존 DRAFT 를 조회(없으면 None)."""
    return (
        session.query(UploadDraft)
        .filter(
            UploadDraft.order_id == order_id,
            UploadDraft.kind == kind,
            UploadDraft.idempotency_key == idempotency_key,
        )
        .one_or_none()
    )


def _get(session: Session, draft_id: int) -> UploadDraft:
    """DRAFT 를 id 로 로드하거나 :class:`UploadDraftError`."""
    draft = session.get(UploadDraft, draft_id)
    if draft is None:
        raise UploadDraftError(f"upload draft {draft_id} not found")
    return draft


def create_upload_draft(
    session: Session,
    *,
    order_id: int,
    kind: str,
    created_by_user_id: Optional[int] = None,
    idempotency_key: Optional[str] = None,
    object_keys: Optional[Sequence[str]] = None,
    now: Optional[datetime.datetime] = None,
) -> UploadDraft:
    """파일 업로드 전 DRAFT id 를 발급한다(멱등). **Order 는 불변**.

    같은 ``(order_id, kind, idempotency_key)`` 재요청은 기존 DRAFT 를 그대로 돌려주고 새
    행을 만들지 않는다(중복 생성 0). ``idempotency_key`` 가 None 이면 매 호출이 새 DRAFT.

    Args:
        session: business transaction 세션(호출자 소유·commit 미수행).
        order_id: 대상 주문 id.
        kind: ``drawing_revision`` | ``as_cycle``.
        created_by_user_id: 발급 actor(audit). None 허용.
        idempotency_key: 같은 intent dedupe 키(≤80자) 또는 None.
        object_keys: 초기 server-derived object key 목록(선택).
        now: 기준 시각(테스트 주입용).

    Returns:
        생성했거나 재사용한 :class:`UploadDraft`.

    Raises:
        UploadDraftError: 알 수 없는 kind.
    """
    if kind not in UPLOAD_DRAFT_KINDS:
        raise UploadDraftError(f"unknown upload draft kind: {kind!r}")
    now = now or now_utc_naive()

    if idempotency_key is not None:
        existing = _lookup_idem(session, order_id, kind, idempotency_key)
        if existing is not None:
            return existing  # 멱등: 같은 intent → 기존 DRAFT(중복 생성 0)

    draft = UploadDraft(
        order_id=order_id,
        kind=kind,
        created_by_user_id=created_by_user_id,
        state="DRAFT",
        object_keys=list(object_keys) if object_keys else [],
        idempotency_key=idempotency_key,
        row_version=1,
        created_at=now,
        expires_at=now + _TTL,
    )
    session.add(draft)
    try:
        session.flush()
    except IntegrityError:
        # 동시 same-key 경합 backstop: 진 쪽은 이긴 DRAFT 를 돌려준다(중복 생성 0).
        session.rollback()
        if idempotency_key is None:
            raise
        winner = _lookup_idem(session, order_id, kind, idempotency_key)
        if winner is None:
            raise
        return winner
    return draft


def cancel_upload_draft(session: Session, draft_id: int) -> UploadDraft:
    """DRAFT 를 CANCELLED(terminal)로 마크한다(멱등). **Order 는 불변**.

    이미 terminal(CANCELLED/FINALIZED)이면 상태를 바꾸지 않고 현재 행을 돌려준다(no-op).

    Args:
        session: business transaction 세션(호출자 소유).
        draft_id: 대상 DRAFT id.

    Returns:
        CANCELLED 로 마킹했거나 이미 terminal 인 :class:`UploadDraft`.

    Raises:
        UploadDraftError: 부재 DRAFT.
    """
    draft = _get(session, draft_id)
    if draft.state in ("CANCELLED", "FINALIZED"):
        return draft  # 이미 terminal → no-op(멱등)
    draft.state = "CANCELLED"
    draft.row_version = (draft.row_version or 0) + 1
    session.flush()
    return draft


def finalize_upload_draft(
    session: Session, draft_id: int, *, now: Optional[datetime.datetime] = None
) -> UploadDraft:
    """DRAFT 를 FINALIZED 로 확정하고 Order ``mutation_version`` 을 **1회 bump**(REV-00).

    create/cancel 는 Order 를 건드리지 않고 final command(finalize)만 version 을 올린다.
    이미 FINALIZED 면 no-op(추가 bump 0, 멱등). CANCELLED / 만료(EXPIRED) DRAFT 는 확정
    불가.

    Args:
        session: business transaction 세션(호출자 소유).
        draft_id: 대상 DRAFT id.
        now: 기준 시각(테스트 주입용).

    Returns:
        FINALIZED :class:`UploadDraft`.

    Raises:
        UploadDraftError: 부재 DRAFT, CANCELLED/EXPIRED 확정 시도, order 부재.
    """
    now = now or now_utc_naive()
    # DRAFT row 를 FOR UPDATE 로 잠근 뒤 state 를 판정한다. 동시 finalize 가 같은 DRAFT 를
    # 확정할 때 락-후-체크로 직렬화해 order version 이중 bump("1회" 불변식)을 막는다.
    draft = (
        session.query(UploadDraft)
        .filter(UploadDraft.id == draft_id)
        .with_for_update()
        .one_or_none()
    )
    if draft is None:
        raise UploadDraftError(f"upload draft {draft_id} not found")
    if draft.state == "FINALIZED":
        return draft  # 멱등 no-op — version 재bump 금지
    if draft.state == "CANCELLED":
        raise UploadDraftError(f"cannot finalize cancelled draft {draft_id}")
    if is_expired(draft, now):
        raise UploadDraftError(f"cannot finalize expired draft {draft_id}")

    # REV-00: final command 만 Order version 1회 bump. ID lock 으로 lost-update 직렬화.
    order = (
        session.query(Order)
        .filter(Order.id == draft.order_id)
        .with_for_update()
        .one_or_none()
    )
    if order is None:
        raise UploadDraftError(f"order {draft.order_id} not found for draft {draft_id}")
    order.mutation_version = (order.mutation_version or 0) + 1

    draft.state = "FINALIZED"
    draft.row_version = (draft.row_version or 0) + 1
    session.flush()
    return draft
