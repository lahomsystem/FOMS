"""WIZ-01-COMPLETION: drawing wizard transfer-pending 정본 store 서비스.

도면 마법사가 export 한 sheet PNG(전달 대기)를 :class:`~models.DrawingWizardPending`
child row 로 정본 관리하는 서비스다. 기존 ``structured_data['drawing_wizard']['pending']``
JSON 은 live bridge 로 유지되고(전면 rewire 는 후속), 이 서비스가 child 테이블을 canonical
로 삼아 state machine·collection ETag·row_version optimistic lock 을 강제한다.

WIZ-DELETE-01 은 이 서비스로 pending 을 ``DELETE_PENDING`` 으로 마크하고(한 tx 안에서
SIDEFX ``STORAGE_DELETE`` outbox enqueue), worker 확인 후 ``DELETED`` 로 전이한다 —
worker 는 Order JSON/version/event 를 만들지 않는다(child-only).

계약(§2.6 / master plan line 530):

* **server-derived key**: ``object_key`` 는 ``orders/<id>/drawing_wizard/exports/`` 접두만
  허용한다(클라이언트 임의 경로·traversal 거부). unique index 가 중복 export 를 차단한다.
* **state machine**: READY→CLAIMED / READY·CLAIMED→DELETE_PENDING→DELETED, invalid 는
  QUARANTINED 로 보존(삭제 금지). 불법 전이는 :class:`PendingStateError`.
* **optimistic lock**: 모든 전이는 ``row_version`` 을 1 bump 하고, 호출자가
  ``expected_row_version`` 을 주면 불일치 시 :class:`PendingConcurrencyError`.
* **collection ETag**: order 별 pending 집합의 (id, row_version, state) 로 유도한 ETag.

모든 함수는 ``flush`` 만 하고 ``commit`` 은 호출자가 소유한다(business tx 원자성).
"""
from __future__ import annotations

import datetime
import hashlib
from typing import Optional

from sqlalchemy.orm import Session

from foms.services.datetime_kst import now_utc_naive
from models import (
    DRAWING_WIZARD_PENDING_TTL_SECONDS,
    DrawingWizardPending,
)

__all__ = [
    "DrawingWizardPendingError",
    "PendingStateError",
    "PendingConcurrencyError",
    "record_pending",
    "get_pending",
    "list_pending",
    "transition",
    "mark_claimed",
    "mark_delete_pending",
    "mark_deleted",
    "quarantine",
    "collection_etag",
]

#: 허용 state 전이 그래프(§2.6 line 530). DELETED 는 terminal(빈 집합).
_TRANSITIONS: dict[str, frozenset[str]] = {
    "READY": frozenset({"CLAIMED", "DELETE_PENDING", "QUARANTINED"}),
    "CLAIMED": frozenset({"DELETE_PENDING", "DELETED", "QUARANTINED"}),
    "DELETE_PENDING": frozenset({"DELETED"}),
    "QUARANTINED": frozenset({"DELETE_PENDING"}),
    "DELETED": frozenset(),
}
#: 활성(비-terminal) pending 목록에서 기본 제외할 state.
_TERMINAL_STATES = frozenset({"DELETED"})


class DrawingWizardPendingError(ValueError):
    """WIZ pending 계약 위반(부재 pending, 잘못된 key, 불법 전이, 낙관적 충돌)."""


class PendingStateError(DrawingWizardPendingError):
    """허용되지 않은 state 전이 시도."""


class PendingConcurrencyError(DrawingWizardPendingError):
    """``expected_row_version`` 불일치(다른 트랜잭션이 먼저 전이함)."""


def _exports_prefix(order_id: int) -> str:
    """해당 주문의 server-derived export pending 접두사(끝에 ``/``)."""
    return f"orders/{order_id}/drawing_wizard/exports/"


def _validate_object_key(order_id: int, object_key: str) -> None:
    """object_key 가 해당 주문의 server-derived exports 경로인지 검증(traversal 거부)."""
    key = (object_key or "").strip()
    if not key or key.startswith("/") or ".." in key:
        raise DrawingWizardPendingError("pending object_key 가 올바르지 않습니다.")
    if not key.startswith(_exports_prefix(order_id)):
        raise DrawingWizardPendingError("pending object_key 경로가 올바르지 않습니다.")


def record_pending(
    session: Session,
    *,
    order_id: int,
    object_key: str,
    owner_user_id: Optional[int] = None,
    now: Optional[datetime.datetime] = None,
    ttl_seconds: int = DRAWING_WIZARD_PENDING_TTL_SECONDS,
) -> DrawingWizardPending:
    """export 된 sheet PNG 를 READY pending child row 로 기록한다(server-derived key).

    Args:
        session: business transaction 세션(호출자 소유·commit 미수행).
        order_id: 대상 주문 id.
        object_key: server-derived export key(``orders/<id>/drawing_wizard/exports/`` 접두).
        owner_user_id: export 를 소유한 도면 담당자 id(감사용, None 허용).
        now: 기준 시각(테스트 주입). 기본 :func:`now_utc_naive`.
        ttl_seconds: orphan cleanup 지평(초). 기본 7일.

    Returns:
        flush 된 READY :class:`~models.DrawingWizardPending`.

    Raises:
        DrawingWizardPendingError: object_key 가 server-derived exports 경로가 아님.
    """
    _validate_object_key(order_id, object_key)
    now = now or now_utc_naive()
    pending = DrawingWizardPending(
        order_id=order_id,
        owner_user_id=owner_user_id,
        object_key=object_key.strip(),
        state="READY",
        row_version=1,
        created_at=now,
        expires_at=now + datetime.timedelta(seconds=ttl_seconds),
    )
    session.add(pending)
    session.flush()
    return pending


def get_pending(
    session: Session, pending_id: int, *, for_update: bool = False
) -> Optional[DrawingWizardPending]:
    """pending 1건을 조회한다(``for_update`` 면 ``FOR UPDATE`` 락). 없으면 None."""
    query = session.query(DrawingWizardPending).filter(
        DrawingWizardPending.id == pending_id)
    if for_update:
        query = query.with_for_update()
    return query.one_or_none()


def list_pending(
    session: Session, order_id: int, *, include_terminal: bool = False
) -> list[DrawingWizardPending]:
    """주문의 pending 목록을 id 순으로 반환한다(기본 DELETED terminal 제외)."""
    query = session.query(DrawingWizardPending).filter(
        DrawingWizardPending.order_id == order_id)
    if not include_terminal:
        query = query.filter(DrawingWizardPending.state.notin_(list(_TERMINAL_STATES)))
    return query.order_by(DrawingWizardPending.id.asc()).all()


def transition(
    session: Session,
    pending: DrawingWizardPending,
    to_state: str,
    *,
    expected_row_version: Optional[int] = None,
    now: Optional[datetime.datetime] = None,
) -> DrawingWizardPending:
    """pending 을 ``to_state`` 로 전이한다(state machine + optimistic row_version bump).

    Args:
        session: business transaction 세션(호출자 소유).
        pending: 전이 대상 행(호출자가 ``get_pending(for_update=True)`` 로 잠그길 권장).
        to_state: 목표 state(:data:`models.DRAWING_WIZARD_PENDING_STATES` 중 하나).
        expected_row_version: 주면 현재 ``row_version`` 과 일치해야 한다(낙관적 잠금).
        now: 기준 시각(미사용 시각 주입 여지·현재는 예약).

    Returns:
        전이된(``row_version`` bump) pending.

    Raises:
        PendingStateError: 현재 state 에서 ``to_state`` 로의 전이가 허용되지 않음.
        PendingConcurrencyError: ``expected_row_version`` 불일치.
    """
    del now  # 시각 기록은 현재 컬럼 없음(예약 인자); 전이는 row_version 만 bump.
    allowed = _TRANSITIONS.get(pending.state, frozenset())
    if to_state not in allowed:
        raise PendingStateError(
            f"pending {pending.id}: {pending.state} → {to_state} 전이는 허용되지 않습니다.")
    if expected_row_version is not None and pending.row_version != expected_row_version:
        raise PendingConcurrencyError(
            f"pending {pending.id} row_version 불일치"
            f"(expected {expected_row_version}, actual {pending.row_version}).")
    pending.state = to_state
    pending.row_version = (pending.row_version or 0) + 1
    session.flush()
    return pending


def mark_claimed(session: Session, pending: DrawingWizardPending,
                 *, expected_row_version: Optional[int] = None) -> DrawingWizardPending:
    """READY pending 을 전달이 소비하며 CLAIMED 로 전이한다."""
    return transition(session, pending, "CLAIMED", expected_row_version=expected_row_version)


def mark_delete_pending(session: Session, pending: DrawingWizardPending,
                        *, expected_row_version: Optional[int] = None) -> DrawingWizardPending:
    """pending 을 DELETE_PENDING 으로 전이한다(WIZ-DELETE-01 이 STORAGE_DELETE enqueue 와 동 tx)."""
    return transition(session, pending, "DELETE_PENDING",
                      expected_row_version=expected_row_version)


def mark_deleted(session: Session, pending: DrawingWizardPending,
                 *, expected_row_version: Optional[int] = None) -> DrawingWizardPending:
    """DELETE_PENDING pending 을 worker 삭제 확인 후 DELETED terminal 로 전이한다."""
    return transition(session, pending, "DELETED", expected_row_version=expected_row_version)


def quarantine(session: Session, pending: DrawingWizardPending,
               *, expected_row_version: Optional[int] = None) -> DrawingWizardPending:
    """invalid pending 을 삭제하지 않고 QUARANTINED 로 보존한다(§2.6)."""
    return transition(session, pending, "QUARANTINED",
                      expected_row_version=expected_row_version)


def collection_etag(session: Session, order_id: int) -> str:
    """주문 pending 집합(terminal 포함)의 collection ETag 를 유도한다(전달/삭제 precondition).

    order 의 모든 pending 을 (id, row_version, state) 로 직렬화해 sha256 한 hex 다. 어떤
    pending 이든 전이(row_version bump)·추가되면 ETag 가 바뀐다. 비어 있으면 고정 sentinel.
    """
    rows = (
        session.query(
            DrawingWizardPending.id,
            DrawingWizardPending.row_version,
            DrawingWizardPending.state,
        )
        .filter(DrawingWizardPending.order_id == order_id)
        .order_by(DrawingWizardPending.id.asc())
        .all()
    )
    if not rows:
        return "empty"
    material = ";".join(f"{r_id}:{rv}:{st}" for r_id, rv, st in rows)
    return hashlib.sha256(material.encode("utf-8")).hexdigest()
