"""UPLOAD-02: 만료·orphan 업로드 ticket/draft 의 bounded cleanup provider.

만료(900s 초과)되거나 아이템 은퇴로 orphan 이 된 ISSUED :class:`~models.UploadTicket` 과
만료(24h 초과) DRAFT :class:`~models.UploadDraft` 를 **bounded scan** 으로 claim 해
terminal 로 전이하고, 각각의 server-derived object key 에 대해 ``STORAGE_DELETE`` side-effect
outbox 행(SIDEFX-00)을 만든다. 실 R2 삭제는 outbox delivery worker + STORAGE_DELETE handler
(하류) 몫이며 이 provider 는 삭제를 예약만 한다.

**별도 scheduler/cleanup loop 를 만들지 않는다.** 이 provider(:func:`run_upload_expiry_scan_once`)
는 SIDEFX worker(:mod:`foms.services.sidefx_worker`)의 300s expiry scan 이 호출한다
(:func:`~foms.services.sidefx_worker.run_expiry_scan_once` 가 등록된 provider 로 dispatch).

경계·불변식:

* **bounded**: 티켓/드래프트 각각 최대 ``limit`` 행만 처리한다(한 scan 이 무한히 돌지 않음).
* **advisory lock**: PostgreSQL 에서 ``pg_try_advisory_lock`` 으로 replica 간 scan 을
  직렬화한다(못 잡으면 benign skip). 비-PG(테스트 SQLite lane)에서는 lock/SKIP LOCKED 를
  생략하고 로직만 수행한다.
* **retry idempotent**: 한 scan 은 claim(state 전이) + enqueue 를 **한 트랜잭션**으로
  commit 하므로, 재호출은 이미 terminal 인 행을 다시 집지 않는다(중복 STORAGE_DELETE 0).
  ``dedupe_key`` 가 DB 레벨 2차 방어다.
* **item-retire PG race**: 만료 전이라도 item identity 가 은퇴(``is_active=False``)한 ISSUED
  티켓을 함께 claim 한다. ``FOR UPDATE SKIP LOCKED`` 로 동시 complete 와 배타 처리한다.
"""
from __future__ import annotations

import datetime
from typing import Callable, Optional

from sqlalchemy import or_, select, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from foms.services.datetime_kst import now_utc_naive
from foms.services.sidefx_outbox import enqueue_side_effect
from models import OrderItemIdentity, UploadDraft, UploadTicket

_UPLOAD_EXPIRY_LOCK_KEY = "foms:upload_expiry_scan"
_STORAGE_DELETE = "STORAGE_DELETE"
DEFAULT_SCAN_LIMIT = 100


def _is_pg(engine: Engine) -> bool:
    """엔진 dialect 가 PostgreSQL 인지(advisory lock/SKIP LOCKED 적용 여부)."""
    return engine.dialect.name == "postgresql"


def _claim_expired_tickets(session: Session, *, now: datetime.datetime, limit: int,
                           pg: bool) -> int:
    """만료·item-은퇴 ISSUED 티켓을 EXPIRED 로 claim 하고 STORAGE_DELETE 를 enqueue.

    Returns:
        전이·enqueue 한 티켓 수.
    """
    retired_ids = select(OrderItemIdentity.id).where(
        OrderItemIdentity.is_active.is_(False))
    query = session.query(UploadTicket).filter(
        UploadTicket.state == "ISSUED",
        or_(
            UploadTicket.expires_at < now,
            UploadTicket.item_id.in_(retired_ids),
        ),
    ).order_by(UploadTicket.expires_at.asc()).limit(limit)
    if pg:
        query = query.with_for_update(skip_locked=True)

    tickets = query.all()
    for ticket in tickets:
        ticket.state = "EXPIRED"
        ticket.row_version = (ticket.row_version or 0) + 1
        enqueue_side_effect(
            session,
            source_domain="UPLOAD_TICKET",
            source_id=ticket.id,
            effect_type=_STORAGE_DELETE,
            payload={"object_key": ticket.object_key, "order_id": ticket.order_id},
            dedupe_key=f"upload_ticket:{ticket.id}",
            provider_idempotency_key=f"upload_ticket:{ticket.id}",
            now=now,
        )
    return len(tickets)


def _claim_expired_drafts(session: Session, *, now: datetime.datetime, limit: int,
                          pg: bool) -> tuple[int, int]:
    """만료 DRAFT 를 CANCELLED 로 claim 하고 object_key 별 STORAGE_DELETE 를 enqueue.

    Returns:
        ``(전이한 draft 수, enqueue 한 STORAGE_DELETE 수)``.
    """
    query = session.query(UploadDraft).filter(
        UploadDraft.state == "DRAFT",
        UploadDraft.expires_at < now,
    ).order_by(UploadDraft.expires_at.asc()).limit(limit)
    if pg:
        query = query.with_for_update(skip_locked=True)

    drafts = query.all()
    deletes = 0
    for draft in drafts:
        for object_key in (draft.object_keys or []):
            enqueue_side_effect(
                session,
                source_domain="UPLOAD_DRAFT",
                source_id=draft.id,
                effect_type=_STORAGE_DELETE,
                payload={"object_key": object_key, "order_id": draft.order_id},
                dedupe_key=f"upload_draft:{draft.id}:{object_key}",
                provider_idempotency_key=f"upload_draft:{draft.id}:{object_key}",
                now=now,
            )
            deletes += 1
        # terminal 전이로 재-scan 을 막는다(만료 DRAFT 는 finalize 불가라 정리 안전).
        draft.state = "CANCELLED"
        draft.row_version = (draft.row_version or 0) + 1
    return len(drafts), deletes


def run_upload_expiry_scan_once(
    engine: Engine,
    *,
    limit: int = DEFAULT_SCAN_LIMIT,
    now_fn: Callable[[], datetime.datetime] = now_utc_naive,
) -> dict:
    """만료·orphan ticket/draft 를 bounded scan 으로 정리한다(SIDEFX worker 300s scan 이 호출).

    advisory lock 으로 replica 간 직렬화(못 잡으면 skip)하고, 티켓/드래프트 각각 최대
    ``limit`` 행을 claim → terminal 전이 + ``STORAGE_DELETE`` outbox enqueue 를 **한
    트랜잭션**으로 commit 한다(재호출 idempotent).

    Args:
        engine: 대상 DB 엔진(worker 소유).
        limit: 티켓/드래프트 각각 이번 scan 에서 처리할 최대 행 수(bounded).
        now_fn: 기준 시각 factory(테스트 주입용).

    Returns:
        ``{"skipped", "tickets_expired", "drafts_expired", "storage_deletes"}``. lock 을
        못 잡으면 ``{"skipped": 1, ...0}``.
    """
    pg = _is_pg(engine)
    session_local = sessionmaker(bind=engine)
    s = session_local()
    try:
        if pg:
            got = s.execute(
                text("SELECT pg_try_advisory_lock(hashtext(:k))"),
                {"k": _UPLOAD_EXPIRY_LOCK_KEY},
            ).scalar()
            if not got:
                return {"skipped": 1, "tickets_expired": 0,
                        "drafts_expired": 0, "storage_deletes": 0}
        try:
            now = now_fn()
            tickets = _claim_expired_tickets(s, now=now, limit=limit, pg=pg)
            drafts, draft_deletes = _claim_expired_drafts(s, now=now, limit=limit, pg=pg)
            s.commit()
            return {
                "skipped": 0,
                "tickets_expired": tickets,
                "drafts_expired": drafts,
                "storage_deletes": tickets + draft_deletes,
            }
        finally:
            if pg:
                s.execute(
                    text("SELECT pg_advisory_unlock(hashtext(:k))"),
                    {"k": _UPLOAD_EXPIRY_LOCK_KEY},
                )
                s.commit()
    finally:
        s.close()
