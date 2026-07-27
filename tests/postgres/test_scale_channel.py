"""SCALE-CHANNEL-01 — channel order pipeline scale · index · load artifact (PG lane).

This packet is **scale verification only** — it changes no CHANNEL logic (worker,
lease, state, max-attempt, auth, provider, constructor are untouched) and creates
no migration. It reuses the CHANNEL-INBOUND-ORDER-01 worker
(:mod:`foms.services.security.channel_order.worker`) and the
``channel_inbound_event_logs`` receipt pipeline verbatim.

What it locks in:

* **Load harness (7-day peak · STOP)**: :func:`compute_5min_peak` reads the prior
  7-day valid ingress (``received_at``) and returns the busiest 5-minute window
  count. With **no ingress it returns None and the harness STOPs** — it never
  fabricates a peak to soften the load (:func:`derived_rate_per_sec` raises
  :class:`StopLoadTest`). The drive rate is ``max(1 job/s, 2 × peak_rate)`` — the
  window/rate is never reduced.
* **N-worker SLA**: a burst backlog drained by N concurrent workers
  (real ``FOR UPDATE SKIP LOCKED`` contention) must hold
  **p95 receipt→DONE ≤ 10 s**, **backlog 0**, **duplicate Order 0**, **missing
  Order 0**, expired-lease/RECOVERY_REQUIRED 0, and **heartbeat ≤ 15 s**.
* **EXPLAIN index hit**: the worker claim hot path (:func:`worker._claimable_filter`
  + FIFO ``received_at`` LIMIT) and the oldest-lag query ride
  ``ix_channel_inbound_receipt_state`` with **no sequential scan** at
  production-like volume. Regression guard: goes red if that index is dropped or a
  Seq Scan creeps onto the claim path.
* **PII-0 artifact**: :func:`build_load_artifact` emits aggregate counts/metrics
  only — no customer name / phone / address / raw payload.

Index finding (반환): **no new index required (무변경 종료)**. The existing
``ix_channel_inbound_receipt_state (receipt_state, lease_expires_at)`` keeps both
worker hot paths off a Seq Scan at a selective (steady-state) ACCEPTED backlog,
which is exactly the regime the SLA enforces (oldest PENDING ≤ 60 s bounds the
claimable set). A ``(receipt_state, received_at)`` btree would only help stream the
FIFO LIMIT if the backlog were allowed to grow very large (a worker-down degraded
state, not steady state) — zero steady-state TTFB gain, so per the guardrail
"측정 전 index 금지·효과 없으면 무변경 종료" nothing is added. If a future migration
does add it, WIZ-01-COMPLETION owns that batch's migration slot (this packet must
not create one).

PG lane is opt-in via ``FOMS_TEST_DATABASE_URL`` (skips otherwise; the pure-function
tests below still run and give structural evidence). No credentials in source — the
DSN and owner id come from the environment (``tests/postgres/conftest.py``).
"""
from __future__ import annotations

import datetime
import json
import math
import threading
import time
import uuid
from typing import Optional

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import sessionmaker

import app  # noqa: F401  register every model on Base.metadata
from foms.services.datetime_kst import now_utc_naive
from foms.services.security.channel_order import creation, worker
from models import ChannelInboundEventLog, ChannelInboundWorkerHeartbeat, User

# --------------------------------------------------------------------------- #
# harness constants
# --------------------------------------------------------------------------- #
BUCKET_SECONDS = 300  # 5-minute ingress peak window
PROD_MIN_RATE_PER_SEC = 1.0  # floor of max(1 job/s, 2×peak) — never reduced
PROD_LOAD_DURATION_SECONDS = 900  # production config: 15-minute N-worker soak
SLA_P95_RECEIPT_TO_DONE_S = 10.0
SLA_OLDEST_PENDING_S = 60.0
SLA_HEARTBEAT_AGE_S = 15.0

# Scaled test profile (the production soak is 900 s; the lane proves the harness
# and the invariants under real concurrency without a 15-minute wall clock).
_TEST_DURATION_SECONDS = 20
_TEST_N_WORKERS = 3
_TEST_DRAIN_DEADLINE_S = 40.0
# Small claim chunk so the N workers contend over the burst via SKIP LOCKED
# (strictly more stressful than one big batch — never a rate/window softening).
_TEST_CLAIM_BATCH = 8

# Same well-formed payload the CHANNEL-INBOUND contract test parses into an order.
_VALID_TEXT = "고객명: 홍길동\n연락처: 010-1234-5678\n주소: 서울시 강남구\n수주제품: 소파"
_PII_STRINGS = ("홍길동", "010-1234-5678", "서울시 강남구", "소파")


class StopLoadTest(RuntimeError):
    """Prior 7-day valid ingress has no data — STOP (no fabricated load)."""


# --------------------------------------------------------------------------- #
# pure harness functions (run without a database — structural evidence)
# --------------------------------------------------------------------------- #
def bucket_5min_peak(timestamps: list[datetime.datetime]) -> Optional[int]:
    """Return the busiest 5-minute window's receipt count, or None if empty.

    Args:
        timestamps: ``received_at`` values of valid ingress in the lookback window.

    Returns:
        Peak count in any 300-second bucket, or None when there is no ingress
        (the STOP signal — the caller must not fabricate a peak).
    """
    if not timestamps:
        return None
    counts: dict[int, int] = {}
    for ts in timestamps:
        bucket = int(ts.timestamp()) // BUCKET_SECONDS
        counts[bucket] = counts.get(bucket, 0) + 1
    return max(counts.values())


def derived_rate_per_sec(peak_5min: Optional[int]) -> float:
    """Drive rate = ``max(1 job/s, 2 × peak_rate)`` — never reduced below observed.

    Args:
        peak_5min: busiest 5-minute window count from :func:`bucket_5min_peak`.

    Returns:
        Jobs/second to drive the load at (2× the observed peak arrival rate).

    Raises:
        StopLoadTest: peak is None (no prior ingress) — STOP, do not fabricate.
    """
    if peak_5min is None:
        raise StopLoadTest(
            "prior 7-day valid ingress has no data — STOP (no fabricated load)."
        )
    peak_rate = peak_5min / float(BUCKET_SECONDS)
    return max(PROD_MIN_RATE_PER_SEC, 2.0 * peak_rate)


def planned_receipt_count(rate_per_sec: float, duration_seconds: float) -> int:
    """Number of receipts a run of ``duration_seconds`` at ``rate_per_sec`` emits."""
    return max(1, round(rate_per_sec * duration_seconds))


def _percentile(values: list[float], pct: float) -> float:
    """Nearest-rank percentile of ``values`` (0.0 for an empty sample)."""
    if not values:
        return 0.0
    ordered = sorted(values)
    rank = max(0, math.ceil(pct / 100.0 * len(ordered)) - 1)
    return ordered[rank]


# --------------------------------------------------------------------------- #
# DB-backed harness (reuses the CHANNEL worker verbatim — no logic change)
# --------------------------------------------------------------------------- #
def compute_5min_peak(session, *, now: datetime.datetime) -> Optional[int]:
    """Peak 5-minute ingress over the prior 7 days from ``channel_inbound_event_logs``."""
    window_start = now - datetime.timedelta(days=7)
    rows = (
        session.query(ChannelInboundEventLog.received_at)
        .filter(
            ChannelInboundEventLog.received_at >= window_start,
            ChannelInboundEventLog.received_at <= now,
        )
        .all()
    )
    return bucket_5min_peak([r[0] for r in rows])


def _seed_backlog(engine, n: int, *, run_token: str, now: datetime.datetime) -> None:
    """Commit ``n`` ACCEPTED receipts (a burst) stamped ``received_at = now`` (UTC)."""
    session = sessionmaker(bind=engine)()
    try:
        for i in range(n):
            session.add(
                ChannelInboundEventLog(
                    dedupe_key=f"{run_token}-{i}",
                    creation_key=f"{run_token}-crt-{i}",
                    payload_hash="h",
                    status="accepted",
                    raw_payload={"entity": {"plainText": _VALID_TEXT}},
                    receipt_state="ACCEPTED",
                    received_at=now,
                )
            )
        session.commit()
    finally:
        session.close()


def _accepted_count(engine) -> int:
    """Live count of receipts still in ACCEPTED (leased-in-flight included)."""
    session = sessionmaker(bind=engine)()
    try:
        return int(
            session.query(func.count(ChannelInboundEventLog.id))
            .filter(ChannelInboundEventLog.receipt_state == "ACCEPTED")
            .scalar()
            or 0
        )
    finally:
        session.close()


def _worker_loop(engine, *, stop_at: float, owner_hash: str, batch_size: int) -> None:
    """One load worker: claim → create → heartbeat until backlog drains or deadline."""
    def _lease_token() -> str:
        return uuid.uuid4().hex

    while time.monotonic() < stop_at:
        result = worker.run_create_once(
            engine, owner_hash=owner_hash, lease_token_fn=_lease_token,
            batch_size=batch_size,
        )
        worker.upsert_heartbeat(engine)
        if result["claimed"] == 0:
            if _accepted_count(engine) == 0:
                return
            time.sleep(0.02)  # let another worker's in-flight receipt commit


def run_channel_load(
    engine, *, n_receipts: int, n_workers: int, run_token: str,
    batch_size: int = _TEST_CLAIM_BATCH,
    deadline_seconds: float = _TEST_DRAIN_DEADLINE_S,
) -> datetime.datetime:
    """Seed an ACCEPTED burst and drain it with N concurrent workers.

    Args:
        engine: PG-lane engine (multiple committing sessions for SKIP LOCKED).
        n_receipts: burst size (worst-case arrival — all at once).
        n_workers: number of concurrent claim workers.
        run_token: unique per-run dedupe prefix (isolates this run's receipts).
        batch_size: per-claim chunk (small → real N-worker SKIP LOCKED contention).
        deadline_seconds: hard cap so a stuck drain fails loudly instead of hanging.

    Returns:
        The UTC instant the burst was stamped (load start).
    """
    started = now_utc_naive()
    _seed_backlog(engine, n_receipts, run_token=run_token, now=started)
    stop_at = time.monotonic() + deadline_seconds
    threads = [
        threading.Thread(
            target=_worker_loop,
            kwargs={"engine": engine, "stop_at": stop_at, "batch_size": batch_size,
                    "owner_hash": f"load-{run_token[:8]}-{i}"},
        )
        for i in range(n_workers)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(deadline_seconds + 10)
    return started


def build_load_artifact(engine, *, run_token: str, now: datetime.datetime) -> dict:
    """PII-free scale/capacity artifact — aggregate counts and SLA metrics only."""
    session = sessionmaker(bind=engine)()
    try:
        mine = (
            session.query(ChannelInboundEventLog)
            .filter(ChannelInboundEventLog.dedupe_key.like(f"{run_token}-%"))
            .all()
        )
        created = [r for r in mine if r.receipt_state == "CREATED"]
        latencies = [
            (r.processed_at - r.received_at).total_seconds()
            for r in created if r.processed_at and r.received_at
        ]
        non_null = [r.created_order_id for r in created if r.created_order_id is not None]
        heartbeat = session.get(ChannelInboundWorkerHeartbeat, worker.WORKER_KIND)
        heartbeat_age = (
            None if heartbeat is None
            else max(0, int((now - heartbeat.last_heartbeat_at).total_seconds()))
        )
        return {
            "receipts_total": len(mine),
            "receipts_created": len(created),
            "backlog_remaining": sum(1 for r in mine if r.receipt_state == "ACCEPTED"),
            "expired_lease_accepted": sum(
                1 for r in mine if r.receipt_state == "ACCEPTED"
                and r.lease_expires_at and r.lease_expires_at < now
            ),
            "recovery_required": sum(
                1 for r in mine if r.receipt_state == "RECOVERY_REQUIRED"
            ),
            "distinct_orders": len(set(non_null)),
            "duplicate_orders": len(non_null) - len(set(non_null)),
            "missing_orders": len(created) - len(non_null),
            "p95_receipt_to_done_seconds": _percentile(latencies, 95),
            "max_receipt_to_done_seconds": max(latencies) if latencies else 0.0,
            "heartbeat_age_seconds": heartbeat_age,
            "oldest_pending_seconds": worker.oldest_accepted_lag_seconds(session, now=now),
        }
    finally:
        session.close()


def _explain_lines(session, stmt) -> list[str]:
    """Return the EXPLAIN plan for ``stmt`` (postgresql dialect) as text lines."""
    sql = str(
        stmt.compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    )
    return [row[0] for row in session.execute(text("EXPLAIN " + sql)).fetchall()]


def _seed_explain_volume(session, total: int = 12000) -> None:
    """Seed a production-like receipt mix (selective ACCEPTED slice), then ANALYZE.

    ~2% land on ACCEPTED (the claimable backlog), the rest on CREATED / other
    lifecycle states — the steady-state shape the SLA enforces. mod()/``||`` keep
    the SQL free of ``%``/``:`` so text() does not mistake them for bind markers.
    ``total`` is a module int constant, not user input.
    """
    session.execute(text(
        f"""
        INSERT INTO channel_inbound_event_logs
          (dedupe_key, payload_hash, status, received_at, receipt_state,
           create_attempts, legal_hold)
        SELECT 'exp-'||gs, 'h'||gs, 'received',
               TIMESTAMP '2025-01-01 00:00:00' + gs * interval '1 second',
               CASE
                 WHEN mod(gs, 50) = 0 THEN 'ACCEPTED'
                 WHEN mod(gs, 50) = 1 THEN 'RECOVERY_REQUIRED'
                 WHEN mod(gs, 50) = 2 THEN 'PAUSED_ACCEPTED'
                 ELSE 'CREATED'
               END,
               0, false
        FROM generate_series(1, {total}) gs
        """
    ))
    session.execute(text("ANALYZE channel_inbound_event_logs"))


def _assert_index_driven_no_seqscan(lines: list[str], label: str) -> None:
    """Assert the plan rides ``ix_channel_inbound_receipt_state`` with no Seq Scan."""
    plan = "\n".join(lines)
    assert "Seq Scan on channel_inbound_event_logs" not in plan, (
        f"{label}: unexpected sequential scan — the receipt_state index stopped "
        f"serving the claim hot path.\n{plan}"
    )
    assert "ix_channel_inbound_receipt_state" in plan, (
        f"{label}: expected ix_channel_inbound_receipt_state to drive the scan.\n{plan}"
    )


# --------------------------------------------------------------------------- #
# fixtures / helpers
# --------------------------------------------------------------------------- #
@pytest.fixture
def channel_clean(pg_engine):
    """Yield the PG-lane engine; clear channel receipts/heartbeats/flag on teardown.

    Mirrors ``test_channel_inbound._reset_state`` (orders created via create_order
    leak, as they do across the whole PG lane — metrics here are scoped by run
    token so leakage never pollutes an assertion).
    """
    yield pg_engine
    session = sessionmaker(bind=pg_engine)()
    try:
        session.execute(text("DELETE FROM channel_inbound_event_logs"))
        session.execute(text("DELETE FROM channel_inbound_worker_heartbeats"))
        session.execute(text(
            "UPDATE channel_create_flag SET state='DISABLED', version=1 WHERE id=1"
        ))
        session.commit()
    finally:
        session.close()


def _make_sales_owner(engine) -> int:
    """Create one active SALES user and return its id (owner for channel orders)."""
    session = sessionmaker(bind=engine)()
    try:
        user = User(
            username=f"scale_chan_sales_{uuid.uuid4().hex[:10]}",
            password="pw-not-committed", name="영업", role="STAFF",
            team="SALES", is_active=True,
        )
        session.add(user)
        session.commit()
        return int(user.id)
    finally:
        session.close()


def _enable_flag(engine) -> None:
    """Enable the global create flag directly (OPS gate is verified elsewhere)."""
    session = sessionmaker(bind=engine)()
    try:
        session.execute(text("UPDATE channel_create_flag SET state='ENABLED' WHERE id=1"))
        session.commit()
    finally:
        session.close()


# --------------------------------------------------------------------------- #
# pure-function evidence (run even without a DSN)
# --------------------------------------------------------------------------- #
def test_bucket_5min_peak_pure() -> None:
    base = datetime.datetime(2026, 7, 1, 9, 0, 0)
    stamps = (
        [base + datetime.timedelta(seconds=s) for s in (0, 1, 2)]           # bucket A: 3
        + [base + datetime.timedelta(seconds=BUCKET_SECONDS + s)            # bucket B: 5
           for s in range(5)]
    )
    assert bucket_5min_peak(stamps) == 5
    assert bucket_5min_peak([]) is None  # no ingress → STOP signal


def test_derived_rate_floor_and_scaling_pure() -> None:
    assert derived_rate_per_sec(30) == PROD_MIN_RATE_PER_SEC  # 2×0.1/s floored to 1
    # peak well above the floor scales to 2× the observed arrival rate.
    assert derived_rate_per_sec(300) == pytest.approx(2.0)
    assert derived_rate_per_sec(600) == pytest.approx(4.0)


def test_derived_rate_stops_on_no_ingress_pure() -> None:
    with pytest.raises(StopLoadTest):
        derived_rate_per_sec(None)


def test_planned_receipt_count_pure() -> None:
    assert planned_receipt_count(2.0, PROD_LOAD_DURATION_SECONDS) == 1800
    assert planned_receipt_count(0.0, 900) == 1  # never below one receipt


def test_percentile_pure() -> None:
    assert _percentile([], 95) == 0.0
    assert _percentile([1.0], 95) == 1.0
    assert _percentile([float(i) for i in range(1, 101)], 95) == 95.0


# --------------------------------------------------------------------------- #
# PG lane: peak computation + STOP
# --------------------------------------------------------------------------- #
def test_compute_5min_peak_stops_when_no_ingress(channel_clean) -> None:
    """No prior ingress → peak None → derived rate raises StopLoadTest (no fabrication)."""
    session = sessionmaker(bind=channel_clean)()
    try:
        assert compute_5min_peak(session, now=now_utc_naive()) is None
    finally:
        session.close()
    with pytest.raises(StopLoadTest):
        derived_rate_per_sec(None)


def test_compute_5min_peak_from_prior_ingress(channel_clean) -> None:
    """Peak reflects the busiest real 5-minute window of prior-7-day ingress."""
    now = now_utc_naive()
    anchor = now - datetime.timedelta(days=2)
    session = sessionmaker(bind=channel_clean)()
    try:
        for i in range(30):  # 30 receipts inside one 5-minute window
            session.add(ChannelInboundEventLog(
                dedupe_key=f"prior-{uuid.uuid4().hex}", payload_hash="h",
                status="created", receipt_state="CREATED",
                received_at=anchor + datetime.timedelta(seconds=i),
            ))
        session.commit()
        assert compute_5min_peak(session, now=now) == 30
        assert derived_rate_per_sec(30) == PROD_MIN_RATE_PER_SEC
    finally:
        session.close()


# --------------------------------------------------------------------------- #
# PG lane: N-worker load SLA + PII-0 artifact
# --------------------------------------------------------------------------- #
def test_channel_load_n_worker_sla(channel_clean, monkeypatch) -> None:
    """N-worker burst drain holds every SLA and conserves receipt→order exactly."""
    owner_id = _make_sales_owner(channel_clean)
    monkeypatch.setenv(creation.ENV_DEFAULT_OWNER, str(owner_id))
    _enable_flag(channel_clean)

    # Tie the load to the peak→rate path: seed a small prior peak, derive the rate,
    # and size the burst from it (max(1/s, 2×peak) — never reduced).
    now = now_utc_naive()
    session = sessionmaker(bind=channel_clean)()
    try:
        anchor = now - datetime.timedelta(days=1)
        for i in range(30):
            session.add(ChannelInboundEventLog(
                dedupe_key=f"peakseed-{uuid.uuid4().hex}", payload_hash="h",
                status="created", receipt_state="CREATED",
                received_at=anchor + datetime.timedelta(seconds=i),
            ))
        session.commit()
        rate = derived_rate_per_sec(compute_5min_peak(session, now=now))
    finally:
        session.close()
    n_receipts = planned_receipt_count(rate, _TEST_DURATION_SECONDS)

    run_token = f"load-{uuid.uuid4().hex}"
    run_channel_load(
        channel_clean, n_receipts=n_receipts, n_workers=_TEST_N_WORKERS,
        run_token=run_token,
    )
    artifact = build_load_artifact(channel_clean, run_token=run_token, now=now_utc_naive())

    assert artifact["receipts_total"] == n_receipts
    assert artifact["receipts_created"] == n_receipts       # all valid → created
    assert artifact["backlog_remaining"] == 0               # drained
    assert artifact["duplicate_orders"] == 0                # SKIP LOCKED conservation
    assert artifact["missing_orders"] == 0
    assert artifact["expired_lease_accepted"] == 0
    assert artifact["recovery_required"] == 0
    assert artifact["distinct_orders"] == n_receipts        # receipt 1 = order 1
    assert artifact["p95_receipt_to_done_seconds"] <= SLA_P95_RECEIPT_TO_DONE_S
    assert artifact["heartbeat_age_seconds"] is not None
    assert artifact["heartbeat_age_seconds"] <= SLA_HEARTBEAT_AGE_S
    assert artifact["oldest_pending_seconds"] is None       # backlog 0 → no pending


def test_load_artifact_has_no_pii(channel_clean, monkeypatch) -> None:
    """The scale artifact carries aggregate metrics only — zero PII."""
    owner_id = _make_sales_owner(channel_clean)
    monkeypatch.setenv(creation.ENV_DEFAULT_OWNER, str(owner_id))
    _enable_flag(channel_clean)

    run_token = f"pii-{uuid.uuid4().hex}"
    run_channel_load(
        channel_clean, n_receipts=6, n_workers=2, run_token=run_token,
    )
    artifact = build_load_artifact(channel_clean, run_token=run_token, now=now_utc_naive())

    assert artifact["receipts_created"] == 6
    blob = json.dumps(artifact, ensure_ascii=False, default=str)
    for secret in _PII_STRINGS:
        assert secret not in blob, f"PII {secret!r} leaked into the scale artifact"
    # every value is a number or None — no strings that could carry PII.
    assert all(v is None or isinstance(v, (int, float)) for v in artifact.values())


# --------------------------------------------------------------------------- #
# PG lane: EXPLAIN index hit (Seq Scan 0) — reuses the real worker predicate
# --------------------------------------------------------------------------- #
def test_claim_hot_path_index_hit_no_seqscan(pg_session) -> None:
    """The worker claim query rides ix_channel_inbound_receipt_state (no Seq Scan)."""
    _seed_explain_volume(pg_session)
    now = now_utc_naive()
    stmt = (
        select(ChannelInboundEventLog)
        .where(*worker._claimable_filter(now))
        .order_by(ChannelInboundEventLog.received_at.asc())
        .limit(worker.DEFAULT_BATCH_SIZE)
        .with_for_update(skip_locked=True)
    )
    _assert_index_driven_no_seqscan(_explain_lines(pg_session, stmt), "claim query")


def test_oldest_lag_query_index_hit_no_seqscan(pg_session) -> None:
    """The oldest-pending-lag query rides the same index (no Seq Scan)."""
    _seed_explain_volume(pg_session)
    now = now_utc_naive()
    stmt = select(func.min(ChannelInboundEventLog.received_at)).where(
        *worker._claimable_filter(now)
    )
    _assert_index_driven_no_seqscan(_explain_lines(pg_session, stmt), "oldest-lag query")


def test_receipt_state_index_exists(pg_session) -> None:
    """The claim hot path depends on ix_channel_inbound_receipt_state — guard it."""
    row = pg_session.execute(text(
        "SELECT indexdef FROM pg_indexes WHERE tablename = 'channel_inbound_event_logs' "
        "AND indexname = 'ix_channel_inbound_receipt_state'"
    )).fetchone()
    assert row is not None, "ix_channel_inbound_receipt_state is missing — claim degrades"
    assert "receipt_state" in row[0] and "lease_expires_at" in row[0]
