"""STARTUP-BACKFILL-01 — SAFE 주문 flat 컬럼 재동기 backfill(runs 인프라 wrap).

:mod:`~foms.services.orders.erp_flat_audit` 가 ``SAFE`` 로 분류한 주문만 라이브 라우트와
동일한 :func:`foms.services.erp_sync_columns.sync_erp_flat_columns` 로 flat 컬럼을 재동기한다
(structured_data 가 SSOT — 파생 재동기만·역방향 금지). ambiguous/clean 은 손대지 않는다.

대량 apply 는 BACKFILL 공용 인프라 :mod:`foms.services.security.backfill.runs`
(lease/heartbeat/checkpoint/coverage/STOPPED_DRIFT)로 wrap 한다 — batch(기본 500) 별
business write + checkpoint + heartbeat 를 한 tx 로 묶고, source fingerprint drift 면 write
전에 정지한다. 최초 apply 는 active OPS approval(BACKFILL_APPLY seq≥1)이 선행돼야 하며,
이 모듈은 그 활성화를 ``activate_approval`` 훅으로 주입받는다(운영은
``runs.consume_backfill_apply``, bare ``--apply`` 는 CLI 가 거부).

resume: 중단 후 재실행하면 결정적 ``run_id`` 로 기존 run 을 이어받아 이미 완료된 앞
batch 를 건너뛰고 남은 주문만 처리한다(DB checkpoint resume). flat 재동기는 idempotent
이므로 재적용도 안전하지만, ``completed_rows`` 이중 계산을 막으려 앞 batch 를 skip 한다.
"""
from __future__ import annotations

import datetime
import hashlib
import json
from dataclasses import dataclass
from typing import Any, Callable, List, Optional, Sequence, Tuple

from sqlalchemy.orm import Session

from foms.services.datetime_kst import now_utc_naive
from foms.services.erp_sync_columns import sync_erp_flat_columns
from foms.services.orders.erp_flat_audit import (
    PACKET_ID,
    PHASE,
    source_sha,
)
from foms.services.security.backfill import runs

DEFAULT_BATCH_SIZE = 500


class ApplyAuthorizationError(RuntimeError):
    """bare ``--apply``(approval-token 부재) 등 apply 권한 계약 위반."""


def resolve_apply_mode(
    *, apply: bool, dry_run: bool, approval_token_file: Optional[str]
) -> bool:
    """apply/dry-run 인자를 검증해 apply 여부를 결정한다(bare ``--apply`` 거부).

    Args:
        apply: ``--apply`` 플래그.
        dry_run: ``--dry-run`` 플래그.
        approval_token_file: ``--approval-token-file`` 경로(없으면 None).

    Returns:
        ``True`` = apply, ``False`` = dry-run(기본).

    Raises:
        ApplyAuthorizationError: apply·dry-run 동시 지정, 또는 approval-token 없는 apply.
    """
    if apply and dry_run:
        raise ApplyAuthorizationError("--apply and --dry-run are mutually exclusive.")
    if not apply:
        return False
    if not approval_token_file:
        raise ApplyAuthorizationError(
            "--apply requires --approval-token-file (bare --apply is refused; operation-bound "
            "approval is mandatory)."
        )
    return True


@dataclass
class BackfillReport:
    """backfill apply 결과 요약."""

    run_id: str = ""
    state: str = ""
    total_rows: int = 0
    completed_rows: int = 0
    resynced_orders: int = 0
    batches: int = 0
    stopped_drift: bool = False


def _chunks(items: Sequence[Any], size: int) -> List[Sequence[Any]]:
    return [items[i : i + size] for i in range(0, len(items), size)]


def _batch_fingerprint(pairs: Sequence[Tuple[int, str]]) -> str:
    """(order_id, src_sha) 목록의 결정적 fingerprint(batch drift 비교용)."""
    payload = json.dumps(sorted(pairs), ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _live_source_sha(session: Session, order_id: int) -> str:
    """현재 DB 주문 structured_data 의 소스 fingerprint(audit 시점 대비 drift 감지)."""
    from models import Order

    sd = session.query(Order.structured_data).filter(Order.id == order_id).scalar()
    return source_sha(sd)


def _resync_batch(session: Session, order_ids: Sequence[int], report: BackfillReport) -> None:
    """batch 내 SAFE 주문의 flat 컬럼을 재동기(runs.write_batch business write 콜백)."""
    from models import Order

    for order_id in order_ids:
        order = session.get(Order, order_id)
        if order is None or order.structured_data is None:
            continue
        if not isinstance(order.structured_data, dict):
            continue
        sync_erp_flat_columns(order, order.structured_data)
        report.resynced_orders += 1


def run_backfill(
    session: Session,
    *,
    db_instance_id: str,
    owner_identity: str,
    safe_targets: Sequence[Tuple[int, str]],
    manifest_sha256: str,
    mapping_sha256: str,
    batch_size: int = DEFAULT_BATCH_SIZE,
    now: Optional[datetime.datetime] = None,
    activate_approval: Optional[Callable[[Session, Any], None]] = None,
) -> BackfillReport:
    """SAFE 주문을 BACKFILL 인프라로 wrap 해 flat 컬럼을 재동기하고 DONE 처리한다.

    Args:
        session: SQLAlchemy Session(호출자가 batch 마다 commit).
        db_instance_id: run identity 의 target DB 식별자.
        owner_identity: lease owner 식별자(원문 저장 안 됨 — hash 만).
        safe_targets: SAFE 주문 ``(order_id, expected_src_sha)`` 목록(audit/artifact 산출).
        manifest_sha256: run identity manifest sha(approval-scope 와 일치해야 함).
        mapping_sha256: run identity mapping sha.
        batch_size: batch 당 주문 수(기본 500).
        now: 결정적 타임스탬프(테스트·resume 주입용).
        activate_approval: seq<1 일 때 approval seq≥1 을 활성화하는 훅(운영은
            ``runs.consume_backfill_apply``; 없으면 acquire_lease 가 거부).

    Returns:
        :class:`BackfillReport` — run 상태·coverage·재동기 수.
    """
    now = now or now_utc_naive()
    targets = sorted(safe_targets, key=lambda t: t[0])

    run = runs.ensure_run(
        session,
        packet_id=PACKET_ID,
        phase=PHASE,
        db_instance_id=db_instance_id,
        manifest_sha256=manifest_sha256,
        mapping_sha256=mapping_sha256,
        total_rows=len(targets),
        now=now,
    )
    run_id = run.run_id

    # 최초 apply 만 approval 소비(seq1). resume 는 이미 seq≥1 이라 재소비하지 않는다.
    if (run.current_approval_seq or 0) < 1 and activate_approval is not None:
        activate_approval(session, run)
        session.commit()

    report = BackfillReport(run_id=run_id, total_rows=len(targets))
    raw_token, _ = runs.new_lease_token()
    runs.acquire_lease(
        session,
        run_id,
        owner_identity_hash=runs.owner_hash(owner_identity),
        raw_token=raw_token,
        now=now,
    )
    session.commit()

    already = run.completed_rows or 0
    remaining = targets[already:]
    base_seq = already // batch_size

    for offset, batch in enumerate(_chunks(remaining, batch_size), start=1):
        seq = base_seq + offset
        expected_fp = _batch_fingerprint(list(batch))
        live_fp = _batch_fingerprint([(oid, _live_source_sha(session, oid)) for oid, _ in batch])
        checkpoint = hashlib.sha256(
            f"{run_id}:{seq}:{sorted(oid for oid, _ in batch)}".encode("utf-8")
        ).hexdigest()
        order_ids = [oid for oid, _ in batch]
        outcome = runs.write_batch(
            session,
            run_id,
            raw_token=raw_token,
            expected_fingerprint=expected_fp,
            live_fingerprint=live_fp,
            batch_business_write=lambda s, ids=order_ids: _resync_batch(s, ids, report),
            completed_delta=len(batch),
            batch_seq=seq,
            checkpoint_sha256=checkpoint,
            now=now,
        )
        session.commit()
        report.batches += 1
        if outcome.stopped_drift:
            report.stopped_drift = True
            report.state = "STOPPED_DRIFT"
            report.completed_rows = outcome.completed_rows
            return report

    completed = runs.complete_run(session, run_id, raw_token=raw_token, now=now)
    session.commit()
    report.state = completed.state
    report.completed_rows = completed.completed_rows or 0
    return report


def count_flat_drift(session: Session, order_ids: Sequence[int]) -> int:
    """주어진 주문 중 flat 컬럼 drift 가 남은 수(before/after verify).

    Args:
        session: SQLAlchemy Session(read-only).
        order_ids: 검사할 주문 id 목록.

    Returns:
        여전히 SAFE/AMBIGUOUS drift 인 주문 수(CLEAN 은 0 으로 셈).
    """
    from models import Order
    from foms.services.orders.erp_flat_audit import CLEAN, classify_order

    drifting = 0
    for order_id in order_ids:
        order = session.get(Order, order_id)
        if order is None:
            continue
        result = classify_order(order)
        if result is not None and result.classification != CLEAN:
            drifting += 1
    return drifting


__all__ = [
    "DEFAULT_BATCH_SIZE",
    "ApplyAuthorizationError",
    "BackfillReport",
    "resolve_apply_mode",
    "run_backfill",
    "count_flat_drift",
]
