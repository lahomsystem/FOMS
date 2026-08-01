"""공용 ``STORAGE_DELETE`` side-effect handler (WIZ-DELETE-01 · task #44 해소).

SIDEFX outbox 의 ``STORAGE_DELETE`` 행을 처리하는 **단일 공용 handler** 다. 여러 도메인
(``WIZARD_PENDING`` · ``UPLOAD_TICKET`` · ``UPLOAD_DRAFT`` · ``ORDER_EVENT`` ·
``ORDER_IMPORT_ARTIFACT`` …)이 같은 effect_type 으로 R2 object 삭제를 예약하므로,
``source_domain`` 으로 분기해 공통 처리한다:

* **공통**: ``payload['object_key']`` 를 R2 에서 삭제한다(S3 DeleteObject 는 idempotent —
  중복 삭제 안전). 삭제 실패(ClientError → ``delete_file`` 이 ``False``)는 예외로 올려 worker
  가 재시도하게 한다(fail-closed — 삼키지 않음).
* ``WIZARD_PENDING``: object 삭제 뒤 ``drawing_wizard_pending`` child 를 ``DELETED`` 로 전이한다
  (이미 ``DELETED`` 면 재삭제 없이 즉시 반환 — retry idempotent, 중복 삭제 0). child 전이는
  outbox ``DONE`` 과 **같은 worker tx** 로 commit 된다(worker 는 Order JSON/version/event 를
  만들지 않는다 — child-only).
* **그 밖의 도메인**: child terminal 은 producer(각 도메인 cleanup)가 enqueue 시점에 이미
  마크했으므로 handler 는 ``object_key`` R2 삭제만 한다. ``object_key`` 가 없으면 안전 skip +
  로그(미지원 payload — DEAD 로 몰지 않음).

handler 는 자기 commit 을 하지 않는다 — :func:`foms.services.sidefx_worker.run_delivery_once`
가 dispatch 뒤 finalize 와 함께 commit 을 소유한다(원자성). worker 세션은
``Session.object_session(row)`` 로 얻는다.
"""
from __future__ import annotations

import logging
from typing import Optional

from sqlalchemy.orm import Session

from foms.services.orders.drawing_wizard_pending import get_pending, mark_deleted
from foms.services.storage import get_storage
from models import DomainSideEffectOutbox

_LOGGER = logging.getLogger("sidefx_storage_delete")

#: WIZARD_PENDING 도메인만 child(drawing_wizard_pending) terminal 전이를 handler 가 소유한다.
WIZARD_PENDING = "WIZARD_PENDING"


class StorageDeleteError(RuntimeError):
    """R2 object 삭제 실패(worker 가 attempts++/backoff/DEAD 로 재시도 처리)."""


def _object_key(row: DomainSideEffectOutbox) -> Optional[str]:
    """outbox payload 에서 server-derived ``object_key`` 를 꺼낸다(없으면 None)."""
    payload = row.payload if isinstance(row.payload, dict) else {}
    key = payload.get("object_key")
    if isinstance(key, str) and key.strip():
        return key.strip()
    return None


def _delete_object(object_key: str) -> None:
    """R2 object 1개를 삭제한다(idempotent). 실패면 :class:`StorageDeleteError`."""
    ok = get_storage().delete_file(object_key)
    if ok is False:
        raise StorageDeleteError(f"R2 delete failed for object_key {object_key!r}")


def handle_storage_delete(row: DomainSideEffectOutbox) -> None:
    """``STORAGE_DELETE`` outbox 행 1개를 공용 처리한다(source_domain 분기).

    Args:
        row: PROCESSING 으로 claim 된 ``effect_type=STORAGE_DELETE`` outbox 행(worker 세션에
            attach 됨). 성공하면 정상 반환, 실패하면 예외를 올려 worker 가 재시도한다.

    Raises:
        StorageDeleteError: R2 삭제 실패(재시도 대상) 또는 세션 미attach(방어).
        foms.services.orders.drawing_wizard_pending.DrawingWizardPendingError: WIZARD_PENDING
            child 전이가 state machine 계약을 위반(비정상 상태 — 재시도/DEAD 로 노출).
    """
    if row.source_domain == WIZARD_PENDING:
        _handle_wizard_pending(row)
        return
    object_key = _object_key(row)
    if object_key is None:
        _LOGGER.info(
            "[storage-delete] no object_key (domain=%s id=%s) — safe skip",
            row.source_domain, row.id)
        return
    _delete_object(object_key)


def _handle_wizard_pending(row: DomainSideEffectOutbox) -> None:
    """WIZARD_PENDING: R2 삭제 후 child 를 ``DELETED`` 로 전이(이미 DELETED 면 idempotent skip).

    child 전이(``mark_deleted``)는 worker 세션에 flush 만 하고, outbox ``DONE`` 과 같은 tx 로
    commit 된다(caller 소유). 이미 ``DELETED`` 면 R2 재삭제·전이 없이 반환한다(중복 삭제 0).
    """
    session = Session.object_session(row)
    if session is None:  # dispatch 는 항상 attach 된 row 를 준다 — 방어적 fail-closed.
        raise StorageDeleteError(f"outbox row {row.id} is not attached to a session")
    pending = get_pending(session, row.wizard_pending_id, for_update=True)
    if pending is None:
        _LOGGER.info(
            "[storage-delete] wizard_pending %s already gone (id=%s) — skip",
            row.wizard_pending_id, row.id)
        return
    if pending.state == "DELETED":
        return  # 이미 삭제 확인됨 — 중복 삭제 0(retry idempotent)
    _delete_object(pending.object_key)
    mark_deleted(session, pending, expected_row_version=pending.row_version)
