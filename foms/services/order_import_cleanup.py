"""ORDER-IMPORT-01: 만료 import artifact 의 bounded cleanup provider.

24h 만료된 ``COMPLETED``/``FAILED`` :class:`~models.OrderImportArtifact` 를 **bounded scan**
으로 claim 해 ``EXPIRED`` 로 전이하고, 각 private object key(``source_object_key``·
``error_object_key``)에 대해 ``STORAGE_DELETE`` side-effect outbox 행(SIDEFX-00, source_domain
=``ORDER_IMPORT_ARTIFACT``)을 만든다. 실 R2 삭제는 outbox delivery worker + STORAGE_DELETE
handler(하류) 몫이며 이 provider 는 삭제를 예약만 한다.

**별도 scheduler/cleanup loop 를 만들지 않는다.** 이 provider(:func:`run_order_import_expiry_scan_once`)
는 SIDEFX worker(:mod:`foms.services.sidefx_worker`)의 300s expiry scan 이 호출한다
(:func:`~foms.services.sidefx_worker.run_expiry_scan_once` 가 등록된 provider 로 dispatch).
UPLOAD-02 :mod:`foms.services.upload_cleanup` 패턴을 미러한다.

경계·불변식:

* **bounded**: 한 scan 이 최대 ``limit`` artifact 만 처리한다(무한 scan 금지).
* **advisory lock**: PostgreSQL 에서 ``pg_try_advisory_lock`` 으로 replica 간 scan 을
  직렬화한다(못 잡으면 benign skip). 비-PG(테스트 SQLite lane)는 lock/SKIP LOCKED 생략.
* **retry idempotent**: claim(EXPIRED 전이) + enqueue 를 한 트랜잭션으로 commit 하므로,
  재호출은 이미 terminal(EXPIRED)인 행을 다시 집지 않는다(중복 STORAGE_DELETE 0).
  ``dedupe_key`` 가 DB 레벨 2차 방어다.
"""
from __future__ import annotations

import datetime
from typing import Callable

from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from foms.services.datetime_kst import now_utc_naive
from foms.services.sidefx_outbox import enqueue_side_effect
from models import OrderImportArtifact

_ORDER_IMPORT_EXPIRY_LOCK_KEY = "foms:order_import_expiry_scan"
_STORAGE_DELETE = "STORAGE_DELETE"
_SOURCE_DOMAIN = "ORDER_IMPORT_ARTIFACT"
DEFAULT_SCAN_LIMIT = 100


def _is_pg(engine: Engine) -> bool:
    """엔진 dialect 가 PostgreSQL 인지(advisory lock/SKIP LOCKED 적용 여부)."""
    return engine.dialect.name == "postgresql"


def _claim_expired_artifacts(session: Session, *, now: datetime.datetime, limit: int,
                             pg: bool) -> tuple[int, int]:
    """만료 COMPLETED/FAILED artifact 를 EXPIRED 로 claim 하고 key 별 STORAGE_DELETE enqueue.

    Returns:
        ``(전이한 artifact 수, enqueue 한 STORAGE_DELETE 수)``.
    """
    query = (
        session.query(OrderImportArtifact)
        .filter(OrderImportArtifact.state.in_(("COMPLETED", "FAILED")),
                OrderImportArtifact.expires_at < now)
        .order_by(OrderImportArtifact.expires_at.asc())
        .limit(limit)
    )
    if pg:
        query = query.with_for_update(skip_locked=True)

    artifacts = query.all()
    deletes = 0
    for artifact in artifacts:
        keys = [k for k in (artifact.source_object_key, artifact.error_object_key) if k]
        for object_key in keys:
            enqueue_side_effect(
                session,
                source_domain=_SOURCE_DOMAIN,
                source_id=artifact.id,
                effect_type=_STORAGE_DELETE,
                payload={"object_key": object_key, "artifact_id": artifact.id},
                dedupe_key=f"order_import_artifact:{artifact.id}:{object_key}",
                provider_idempotency_key=f"order_import_artifact:{artifact.id}:{object_key}",
                now=now,
            )
            deletes += 1
        # terminal 전이로 재-scan 을 막는다(만료 artifact 재claim 0).
        artifact.state = "EXPIRED"
    return len(artifacts), deletes


def run_order_import_expiry_scan_once(
    engine: Engine,
    *,
    limit: int = DEFAULT_SCAN_LIMIT,
    now_fn: Callable[[], datetime.datetime] = now_utc_naive,
) -> dict:
    """만료 import artifact 를 bounded scan 으로 정리한다(SIDEFX worker 300s scan 이 호출).

    advisory lock 으로 replica 간 직렬화(못 잡으면 skip)하고, 최대 ``limit`` artifact 를
    claim → EXPIRED 전이 + key 별 ``STORAGE_DELETE`` outbox enqueue 를 **한 트랜잭션**으로
    commit 한다(재호출 idempotent).

    Args:
        engine: 대상 DB 엔진(worker 소유).
        limit: 이번 scan 에서 처리할 최대 artifact 수(bounded).
        now_fn: 기준 시각 factory(테스트 주입용).

    Returns:
        ``{"skipped", "artifacts_expired", "storage_deletes"}``. lock 을 못 잡으면
        ``{"skipped": 1, ...0}``.
    """
    pg = _is_pg(engine)
    session_local = sessionmaker(bind=engine)
    s = session_local()
    try:
        if pg:
            got = s.execute(
                text("SELECT pg_try_advisory_lock(hashtext(:k))"),
                {"k": _ORDER_IMPORT_EXPIRY_LOCK_KEY},
            ).scalar()
            if not got:
                return {"skipped": 1, "artifacts_expired": 0, "storage_deletes": 0}
        try:
            now = now_fn()
            expired, deletes = _claim_expired_artifacts(s, now=now, limit=limit, pg=pg)
            s.commit()
            return {"skipped": 0, "artifacts_expired": expired, "storage_deletes": deletes}
        finally:
            if pg:
                s.execute(
                    text("SELECT pg_advisory_unlock(hashtext(:k))"),
                    {"k": _ORDER_IMPORT_EXPIRY_LOCK_KEY},
                )
                s.commit()
    finally:
        s.close()
