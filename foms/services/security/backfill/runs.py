"""``maintenance_backfill_runs`` state machine + OPS-APPROVAL 소비 (§7.3 line 1255-1259).

resume run 정본(run/checkpoint/append-only approval)의 공용 라이브러리. **메커니즘만**
제공한다 — 실제 domain business write 는 호출자가 넘기는 ``batch_business_write`` 콜러블
이 수행하고, 이 모듈은 run_id 결정성, lease/heartbeat, batch 진행 원장, fingerprint drift
정지, OPS-APPROVAL(BACKFILL_APPLY/REAUTHORIZE) 소비만 책임진다.

계약(§7.3):

* ``run_id = SHA256(LP(packet_id,phase,manifest_sha256,mapping_sha256))`` — 결정적 resume id.
* lease token 은 raw 저장 0(``lease_token_hash`` = sha256(raw)). 60초 lease/10초 heartbeat.
  **expired lease 만** 동일 artifact/mapping + active approval 로 reclaim 한다.
* 각 batch = business write + checkpoint + completed_rows + heartbeat 를 target DB **한 tx**
  (호출자가 commit)로 묶는다. run 별 ``pg_advisory_xact_lock`` 으로 동시 writer 를 직렬화.
* source fingerprint drift → write 전에 ``STOPPED_DRIFT``, business mutation 0.
* 최초 apply 는 BACKFILL_APPLY approval 을 소비해 seq1 을 만들고, REAUTHORIZE 는 seq 를
  append-only 로 추가하며 run row_version CAS 로만 진행한다.
"""
from __future__ import annotations

import datetime
import hashlib
import os
from dataclasses import dataclass
from typing import Any, Callable, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from foms.services.datetime_kst import now_utc_naive
from foms.services.security.ops_approval import consume_same_db
from foms.services.security.backfill.crypto import lp
from foms.services.security.backfill.manifest import (
    BACKFILL_APPLY_OPERATION_ID,
    compute_approval_scope_sha256,
)
from models import (
    MaintenanceBackfillApproval,
    MaintenanceBackfillCheckpoint,
    MaintenanceBackfillRun,
)

LEASE_TTL_SECONDS = 60
HEARTBEAT_INTERVAL_SECONDS = 10
BACKFILL_REAUTHORIZE_OPERATION_ID = "BACKFILL_REAUTHORIZE"

_TERMINAL_STATES = frozenset({"DONE", "STOPPED_DRIFT"})


class BackfillRunError(RuntimeError):
    """run 존재/상태/정합성 계약 위반."""


class BackfillLeaseError(BackfillRunError):
    """lease 미보유/만료/타 소유자 재획득 시도."""


class BackfillDriftError(BackfillRunError):
    """source fingerprint drift(호출자는 STOPPED_DRIFT 상태를 commit)."""


@dataclass(frozen=True)
class BatchOutcome:
    """batch write 결과. drift 정지는 예외가 아니라 상태로 보고(호출자가 commit)."""

    applied: bool
    stopped_drift: bool
    completed_rows: int


def compute_run_id(packet_id: str, phase: str, manifest_sha256: str, mapping_sha256: str) -> str:
    """결정적 resume run id = ``SHA256(LP(packet_id,phase,manifest_sha256,mapping_sha256))``."""
    return hashlib.sha256(lp(packet_id, phase, manifest_sha256, mapping_sha256)).hexdigest()


def owner_hash(owner_identity: str) -> str:
    """lease owner 식별자의 sha256(원문 저장 0)."""
    return hashlib.sha256(owner_identity.encode("utf-8")).hexdigest()


def new_lease_token() -> tuple[bytes, str]:
    """새 lease token 생성 → ``(raw 32-byte token, sha256 hash)``. raw 는 저장 금지."""
    raw = os.urandom(32)
    return raw, _lease_token_hash(raw)


def _lease_token_hash(raw_token: bytes) -> str:
    return hashlib.sha256(raw_token).hexdigest()


def _advisory_lock(session: Session, run_id: str) -> None:
    """run 별 xact advisory lock — 동시 writer 직렬화(호출자 tx 종료 시 자동 해제)."""
    session.execute(text("SELECT pg_advisory_xact_lock(hashtext(:k))"), {"k": run_id})


def _lock_run(session: Session, run_id: str) -> Optional[MaintenanceBackfillRun]:
    return (
        session.query(MaintenanceBackfillRun)
        .filter(MaintenanceBackfillRun.run_id == run_id)
        .with_for_update()
        .one_or_none()
    )


def _lease_held(run: MaintenanceBackfillRun, raw_token: bytes, now: datetime.datetime) -> bool:
    """run lease 가 이 token 으로 보유되고 아직 만료되지 않았는가."""
    return (
        run.lease_token_hash == _lease_token_hash(raw_token)
        and run.lease_expires_at is not None
        and run.lease_expires_at > now
    )


def ensure_run(
    session: Session,
    *,
    packet_id: str,
    phase: str,
    db_instance_id: str,
    manifest_sha256: str,
    mapping_sha256: str,
    total_rows: int = 0,
    now: Optional[datetime.datetime] = None,
) -> MaintenanceBackfillRun:
    """run row 를 결정적 run_id 로 확보(없으면 PENDING insert, 있으면 identity 재확인).

    :raises BackfillRunError: 같은 run_id 인데 manifest/mapping 이 다르다(불가능한 정합성
        위반 — 방어).
    """
    now = now or now_utc_naive()
    run_id = compute_run_id(packet_id, phase, manifest_sha256, mapping_sha256)
    _advisory_lock(session, run_id)
    run = _lock_run(session, run_id)
    if run is None:
        run = MaintenanceBackfillRun(
            run_id=run_id,
            packet_id=packet_id,
            phase=phase,
            db_instance_id=db_instance_id,
            manifest_sha256=manifest_sha256,
            mapping_sha256=mapping_sha256,
            current_approval_seq=0,
            state="PENDING",
            total_rows=total_rows,
            completed_rows=0,
            row_version=1,
        )
        session.add(run)
        session.flush()
        return run
    if run.manifest_sha256 != manifest_sha256 or run.mapping_sha256 != mapping_sha256:
        raise BackfillRunError("run identity drift (manifest/mapping mismatch for run_id).")
    return run


def acquire_lease(
    session: Session,
    run_id: str,
    *,
    owner_identity_hash: str,
    raw_token: bytes,
    now: Optional[datetime.datetime] = None,
    require_active_approval: bool = True,
) -> MaintenanceBackfillRun:
    """write lease 를 획득/reclaim. active·미만료 lease 를 다른 token 으로 재획득하면 거부.

    expired lease 만 reclaim 하며, reclaim/획득은 동일 artifact/mapping(run_id 로 보장) +
    active approval(seq>=1)을 요구한다.

    :raises BackfillLeaseError: active lease 재획득 시도 / active approval 부재.
    :raises BackfillRunError: run 부재.
    """
    now = now or now_utc_naive()
    _advisory_lock(session, run_id)
    run = _lock_run(session, run_id)
    if run is None:
        raise BackfillRunError("run not found; call ensure_run first.")

    token_hash = _lease_token_hash(raw_token)
    lease_active = run.lease_expires_at is not None and run.lease_expires_at > now
    if lease_active and run.lease_token_hash != token_hash:
        raise BackfillLeaseError("run lease is held and unexpired (cannot reacquire).")
    if require_active_approval and (run.current_approval_seq or 0) < 1:
        raise BackfillLeaseError(
            "cannot lease run for apply without an active approval (seq>=1)."
        )

    run.lease_owner_hash = owner_identity_hash
    run.lease_token_hash = token_hash
    run.lease_expires_at = now + datetime.timedelta(seconds=LEASE_TTL_SECONDS)
    run.heartbeat_at = now
    if run.started_at is None:
        run.started_at = now
    if run.state == "PENDING":
        run.state = "RUNNING"
    run.row_version = (run.row_version or 1) + 1
    session.flush()
    return run


def heartbeat(
    session: Session,
    run_id: str,
    *,
    raw_token: bytes,
    now: Optional[datetime.datetime] = None,
) -> MaintenanceBackfillRun:
    """lease 를 보유한 writer 가 heartbeat 를 찍고 lease 를 갱신(row_version 불변)."""
    now = now or now_utc_naive()
    run = _lock_run(session, run_id)
    if run is None:
        raise BackfillRunError("run not found.")
    if not _lease_held(run, raw_token, now):
        raise BackfillLeaseError("heartbeat without a held, unexpired lease.")
    run.heartbeat_at = now
    run.lease_expires_at = now + datetime.timedelta(seconds=LEASE_TTL_SECONDS)
    session.flush()
    return run


def write_batch(
    session: Session,
    run_id: str,
    *,
    raw_token: bytes,
    expected_fingerprint: str,
    live_fingerprint: str,
    batch_business_write: Callable[[Session], Any],
    completed_delta: int,
    batch_seq: int,
    checkpoint_sha256: str,
    now: Optional[datetime.datetime] = None,
) -> BatchOutcome:
    """business write + checkpoint + completed_rows + heartbeat 를 **한 tx**로 기록(미commit).

    fingerprint drift 면 business write 전에 ``STOPPED_DRIFT`` 로 정지하고 business mutation
    을 실행하지 않는다(호출자는 이 상태를 commit). lease 미보유/만료/terminal 상태는 예외다.

    :returns: :class:`BatchOutcome` — ``stopped_drift`` 이면 business write 미실행.
    :raises BackfillLeaseError: lease 미보유/만료.
    :raises BackfillRunError: run 부재 / terminal 상태 / active approval 부재.
    """
    now = now or now_utc_naive()
    _advisory_lock(session, run_id)
    run = _lock_run(session, run_id)
    if run is None:
        raise BackfillRunError("run not found.")
    if not _lease_held(run, raw_token, now):
        raise BackfillLeaseError("batch write without a held, unexpired lease.")
    if run.state in _TERMINAL_STATES:
        raise BackfillRunError(f"run is terminal ({run.state}); no further batch writes.")

    # fingerprint drift → business mutation 0, STOPPED_DRIFT (호출자가 commit).
    if live_fingerprint != expected_fingerprint:
        run.state = "STOPPED_DRIFT"
        run.last_error_code = "FINGERPRINT_DRIFT"
        run.row_version = (run.row_version or 1) + 1
        session.flush()
        return BatchOutcome(applied=False, stopped_drift=True, completed_rows=run.completed_rows or 0)

    if (run.current_approval_seq or 0) < 1:
        raise BackfillRunError("batch write requires an active approval (seq>=1).")

    # domain business write(호출자 콜러블) + 진행 원장 — 모두 같은 session/tx.
    batch_business_write(session)
    new_completed = (run.completed_rows or 0) + completed_delta
    session.add(
        MaintenanceBackfillCheckpoint(
            run_id=run_id,
            batch_seq=batch_seq,
            completed_rows=new_completed,
            checkpoint_sha256=checkpoint_sha256,
            created_at=now,
        )
    )
    run.completed_rows = new_completed
    run.heartbeat_at = now
    run.lease_expires_at = now + datetime.timedelta(seconds=LEASE_TTL_SECONDS)
    if run.state == "PENDING":
        run.state = "RUNNING"
    run.row_version = (run.row_version or 1) + 1
    session.flush()
    return BatchOutcome(applied=True, stopped_drift=False, completed_rows=new_completed)


def complete_run(
    session: Session,
    run_id: str,
    *,
    raw_token: bytes,
    now: Optional[datetime.datetime] = None,
) -> MaintenanceBackfillRun:
    """coverage 100% 를 확인하고 ``DONE`` 으로 종료(lease 보유 필요).

    :raises BackfillRunError: coverage < 100% / STOPPED_DRIFT / run 부재.
    :raises BackfillLeaseError: lease 미보유.
    """
    now = now or now_utc_naive()
    _advisory_lock(session, run_id)
    run = _lock_run(session, run_id)
    if run is None:
        raise BackfillRunError("run not found.")
    if not _lease_held(run, raw_token, now):
        raise BackfillLeaseError("complete without a held, unexpired lease.")
    if run.state == "STOPPED_DRIFT":
        raise BackfillRunError("cannot complete a STOPPED_DRIFT run.")
    if (run.completed_rows or 0) < (run.total_rows or 0):
        raise BackfillRunError("coverage < 100%; cannot mark DONE.")
    run.state = "DONE"
    run.completed_at = now
    run.row_version = (run.row_version or 1) + 1
    session.flush()
    return run


# --------------------------------------------------------------------------- #
# OPS-APPROVAL 소비 (BACKFILL_APPLY seq1 / BACKFILL_REAUTHORIZE append-only)
# --------------------------------------------------------------------------- #
def ops_scope_for_backfill(approval_scope: dict, operation_id: str) -> dict:
    """approval-scope.json → OPS-APPROVAL scope object(exact ``_SCOPE_FIELDS``) 매핑.

    전체 approval-scope 를 단일 sha256(``artifact_sha256``)로 커밋하므로 manifest/mapping/
    composite/expected_version drift 는 OPS consume 에서 거부된다. ``expected_version`` 은
    run row_version CAS(approval 생성 시점 snapshot)다.
    """
    return {
        "schema_version": 1,
        "operation_id": operation_id,
        "packet_id": approval_scope["packet_id"],
        "target_ids_or_family": [approval_scope["db_instance_id"]],
        "phase": approval_scope["phase"],
        "artifact_sha256": compute_approval_scope_sha256(approval_scope),
        "expected_version": approval_scope["expected_run_row_version"],
        "expected_generation": None,
    }


def _consume_and_append(
    session: Session,
    run_id: str,
    *,
    approval_scope: dict,
    operation_id: str,
    kind: str,
    approval_id: str,
    admin_principal_version: int,
    reason_code: Optional[str],
    raw_secret: bytes,
    now: Optional[datetime.datetime],
) -> tuple[int, str]:
    """OPS approval 을 소비하며 append-only approval seq 추가 + run CAS 갱신(미commit).

    seq append + run.current_approval_seq/row_version 갱신은 OPS consume 의 target_mutation
    안에서 이뤄져 approval 검증과 **한 tx** 로 원자적이다.
    """
    now = now or now_utc_naive()
    _advisory_lock(session, run_id)
    run = _lock_run(session, run_id)
    if run is None:
        raise BackfillRunError("run not found; call ensure_run first.")
    if run.state in _TERMINAL_STATES:
        raise BackfillRunError(f"run is terminal ({run.state}); no approval append.")

    next_seq = (run.current_approval_seq or 0) + 1
    if kind == "APPLY" and next_seq != 1:
        raise BackfillRunError("BACKFILL_APPLY must create approval seq 1 (already applied).")
    if kind == "REAUTHORIZE" and next_seq < 2:
        raise BackfillRunError("BACKFILL_REAUTHORIZE requires a prior APPLY (seq>=2).")

    expected_rv = approval_scope["expected_run_row_version"]
    if (run.row_version or 0) != expected_rv:
        raise BackfillRunError(
            f"run row_version CAS mismatch (expected {expected_rv}, got {run.row_version})."
        )

    ops_scope = ops_scope_for_backfill(approval_scope, operation_id)

    def _target_mutation(sess: Session) -> bytes:
        sess.add(
            MaintenanceBackfillApproval(
                run_id=run_id,
                seq=next_seq,
                approval_id=approval_id,
                kind=kind,
                admin_principal_version=admin_principal_version,
                composite_sha256=approval_scope["source_composite_sha256"],
                reason_code=reason_code,
                created_at=now,
            )
        )
        run.current_approval_seq = next_seq
        run.row_version = (run.row_version or 1) + 1
        sess.flush()
        return f"{run_id}:{kind}:{next_seq}".encode("utf-8")

    result_sha = consume_same_db(
        session,
        operation_id=operation_id,
        scope_obj=ops_scope,
        artifact_sha256=ops_scope["artifact_sha256"],
        expected_version=ops_scope["expected_version"],
        expected_generation=None,
        raw_secret=raw_secret,
        target_mutation=_target_mutation,
        now=now,
    )
    return next_seq, result_sha


def consume_backfill_apply(
    session: Session,
    run_id: str,
    *,
    approval_scope: dict,
    approval_id: str,
    admin_principal_version: int,
    raw_secret: bytes,
    now: Optional[datetime.datetime] = None,
) -> tuple[int, str]:
    """최초 apply: BACKFILL_APPLY approval 을 소비해 approval seq1 을 만든다(미commit).

    :returns: ``(seq, result_sha256)``.
    """
    if approval_scope.get("operation_id") != BACKFILL_APPLY_OPERATION_ID:
        raise BackfillRunError("approval_scope.operation_id must be BACKFILL_APPLY.")
    return _consume_and_append(
        session,
        run_id,
        approval_scope=approval_scope,
        operation_id=BACKFILL_APPLY_OPERATION_ID,
        kind="APPLY",
        approval_id=approval_id,
        admin_principal_version=admin_principal_version,
        reason_code=None,
        raw_secret=raw_secret,
        now=now,
    )


def reauthorize(
    session: Session,
    run_id: str,
    *,
    approval_scope: dict,
    approval_id: str,
    admin_principal_version: int,
    reason_code: str,
    raw_secret: bytes,
    now: Optional[datetime.datetime] = None,
) -> tuple[int, str]:
    """다른 active ADMIN 이 BACKFILL_REAUTHORIZE 로 approval seq 를 append-only 추가(미commit).

    동일 manifest/mapping/composite + 현재 run row_version CAS + previous seq 위에서만
    진행하며, 기존 approval row 는 append-only trigger 로 수정/삭제 불가다.

    :returns: ``(seq, result_sha256)``.
    """
    return _consume_and_append(
        session,
        run_id,
        approval_scope=approval_scope,
        operation_id=BACKFILL_REAUTHORIZE_OPERATION_ID,
        kind="REAUTHORIZE",
        approval_id=approval_id,
        admin_principal_version=admin_principal_version,
        reason_code=reason_code,
        raw_secret=raw_secret,
        now=now,
    )
