"""SCALE-AS-01 — AS dashboard hot-query index guard (PG lane, perf).

Investigation outcome: **no migration, no new index** (무변경 종료).

The AS dashboard (`foms/web/cs/as_dashboard.py` + `foms/services/as_dashboard_*`)
has two hot queries per load: the tab-count aggregate and the paginated list.
Both are driven by ``status IN ('AS', 'AS_RECEIVED', 'AS_COMPLETED')``, which the
existing ``ix_orders_as_axis_status`` btree already serves. The
``structured_data.shipment.sales_delivery`` JSONB extraction is only a residual
``Filter`` (list) / ``CASE`` projection (count) evaluated over the
already-status-bounded rows — it never drives the scan, so no trigram /
``@>`` / partial index changes TTFB. The per-page display enrichment
(`as_dashboard_display.apply_as_dashboard_row_display_fields`) already batches
its attachment lookups with ``order_id.in_(order_ids)`` (indexed) — no N+1.

Measurement (localhost dev, 60k orders / 10% AS, EXPLAIN ANALYZE):

    list  : Bitmap Index Scan on ix_orders_as_axis_status → top-N heapsort, 5.45 ms, no Seq Scan
    count : Bitmap Index Scan on ix_orders_as_axis_status → Aggregate,        4.95 ms, no Seq Scan

A candidate partial index ``(as_received_date DESC NULLS LAST, id DESC)
WHERE status IN (AS…)`` was created and measured: the planner **refused it** and
kept the status-bitmap plan — the residual JSONB / ``as_completed_date`` / draft
filters force heap access regardless, so an ordered index cannot stream the
LIMIT. Zero TTFB gain → per the guardrail "측정 전 index 금지·효과 없으면
무변경 종료", nothing is added.

This test locks the finding in as a regression guard. It seeds a production-like
``orders`` volume into the throwaway PG-lane database, ANALYZEs, and asserts each
hot query plan is index-driven on ``status`` with **no sequential scan** and with
the JSONB ``sales_delivery`` predicate appearing only as a residual filter (never
an ``Index Cond``). It goes red if ``ix_orders_as_axis_status`` is dropped or an
unindexed predicate is pushed onto the AS hot path.

PG lane only (opt-in via ``FOMS_TEST_DATABASE_URL``; skips otherwise). No
credentials in source — the DSN comes from the environment
(``tests/postgres/conftest.py``).
"""
from __future__ import annotations

import app  # noqa: F401  register every model on Base.metadata
from sqlalchemy import case, func, select
from sqlalchemy.dialects import postgresql
from sqlalchemy.sql import Select
from sqlalchemy import text

from models import Order
from foms.services.as_dashboard_helpers import (
    _erp_as_completed_condition,
    erp_as_scope_condition,
)
from foms.services.as_dashboard_read_model import build_as_tab_query_conditions

_AS_STATUSES = ["AS", "AS_RECEIVED", "AS_COMPLETED"]
_SEED_TOTAL = 12000  # production-like volume; ~7.5% land on AS statuses (selective)


def _base_where():
    """The AS dashboard base predicate shared by every query on the page."""
    return (
        Order.active_filter(),
        erp_as_scope_condition(),
    )


def _list_stmt() -> Select:
    """Default (tab=incomplete) paginated list query, as the route builds it."""
    conds = build_as_tab_query_conditions(dialect_name="postgresql")
    order_col = Order.as_received_date
    return (
        select(Order)
        .where(*_base_where())
        .where(conds["incomplete_non_sales_condition"])
        .order_by(order_col.desc().nullslast(), Order.id.desc())
        .offset(0)
        .limit(100)
    )


def _count_stmt() -> Select:
    """Tab-count aggregate (build_as_tab_count_context → _count_cases), as-is."""
    conds = build_as_tab_query_conditions(dialect_name="postgresql")
    defs = [
        ("sales_delivery", conds["sales_delivery_condition"]),
        ("incomplete", conds["incomplete_non_sales_condition"]),
        ("completed", _erp_as_completed_condition()),
    ]
    cols = [
        func.coalesce(func.sum(case((cond, 1), else_=0)), 0).label(name)
        for name, cond in defs
    ]
    return select(*cols).select_from(Order).where(*_base_where())


def _explain_lines(session, stmt: Select) -> list[str]:
    """Return the EXPLAIN plan for ``stmt`` as a list of text lines."""
    sql = str(
        stmt.compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    )
    rows = session.execute(text("EXPLAIN " + sql)).fetchall()
    return [r[0] for r in rows]


def _seed_orders(session) -> None:
    """Bulk-seed a production-like ``orders`` volume, then ANALYZE.

    ~7.5% of rows land on AS statuses (a selective slice, like production), the
    rest spread across the normal workflow stages. One in every 200 AS rows is a
    ``shipment.sales_delivery`` row so the residual JSONB filter has real work.
    """
    # mod()/jsonb_build_object() keep the SQL free of ``%`` and ``:`` so
    # SQLAlchemy's text() does not mistake them for paramstyle/bind markers.
    # _SEED_TOTAL is a module int constant, not user input.
    session.execute(text(
        f"""
        INSERT INTO orders
          (id, received_date, customer_name, phone, address, product,
           is_erp_order, structured_schema_version, deleted_at, status,
           as_axis_status, as_received_date, as_completed_date, structured_data)
        SELECT gs, '2025-01-01', 'c'||gs, '010'||gs, 'a'||gs, 'p'||gs,
               true, 3, NULL,
               CASE
                 WHEN mod(gs, 40) = 0 THEN 'AS'
                 WHEN mod(gs, 40) = 1 THEN 'AS_RECEIVED'
                 WHEN mod(gs, 40) = 2 THEN 'AS_COMPLETED'
                 ELSE (ARRAY['RECEIVED','MEASURE','DRAWING',
                             'PRODUCTION','CONSTRUCTION','COMPLETED'])[1 + mod(gs, 6)]
               END,
               CASE
                 WHEN mod(gs, 40) = 0 THEN 'IN_PROGRESS'
                 WHEN mod(gs, 40) = 1 THEN 'RECEIVED'
                 WHEN mod(gs, 40) = 2 THEN 'COMPLETED'
                 ELSE NULL
               END,
               '2025-06-01',
               CASE WHEN mod(gs, 40) = 2 AND mod(gs, 400) <> 2
                    THEN '2025-07-01' ELSE NULL END,
               CASE WHEN mod(gs, 200) = 0
                    THEN jsonb_build_object('shipment',
                             jsonb_build_object('sales_delivery', true))
                    ELSE jsonb_build_object('shipment', jsonb_build_object()) END
        FROM generate_series(1, {_SEED_TOTAL}) gs
        """
    ))
    session.execute(text("ANALYZE orders"))


def _assert_index_driven_no_seqscan(lines: list[str], label: str) -> None:
    """Assert a plan scans ``orders`` via ``ix_orders_as_axis_status`` with no Seq Scan.

    Also asserts the JSONB ``sales_delivery`` predicate is only a residual
    filter — it must never appear as an ``Index Cond`` (documents that no JSONB
    index is warranted).
    """
    plan = "\n".join(lines)
    assert "Seq Scan on orders" not in plan, (
        f"{label}: unexpected sequential scan on orders — the status index "
        f"stopped serving the AS hot path.\n{plan}"
    )
    assert "ix_orders_as_axis_status" in plan, (
        f"{label}: expected the status btree (ix_orders_as_axis_status) to drive the "
        f"scan.\n{plan}"
    )
    # 부분 인덱스(``WHERE as_axis_status IS NOT NULL``)는 조건이 인덱스 정의에 들어 있어
    # 계획에 ``Index Cond`` 줄이 없을 수 있다 — 인덱스가 스캔을 몰고 있으면 그게 계약이다.
    index_cond_lines = [ln for ln in lines if "Index Cond" in ln]
    assert not any("sales_delivery" in ln for ln in index_cond_lines), (
        f"{label}: JSONB sales_delivery leaked into an Index Cond — it must stay "
        f"a residual filter, never a scan driver.\n{plan}"
    )


def test_as_dashboard_hot_queries_are_index_driven(pg_session) -> None:
    """SCALE-AS-01 evidence lock: both AS hot queries ride ix_orders_as_axis_status.

    Proves the 무변경 종료 decision — the existing status index already keeps the
    list and tab-count queries off a sequential scan at production-like volume,
    so no SCALE-AS migration/index is needed.
    """
    _seed_orders(pg_session)

    _assert_index_driven_no_seqscan(
        _explain_lines(pg_session, _list_stmt()), "AS list query"
    )
    _assert_index_driven_no_seqscan(
        _explain_lines(pg_session, _count_stmt()), "AS tab-count query"
    )


def test_as_axis_index_exists(pg_session) -> None:
    """The AS hot path depends on ``ix_orders_as_axis_status`` — guard its existence."""
    row = pg_session.execute(text(
        "SELECT indexdef FROM pg_indexes "
        "WHERE tablename = 'orders' AND indexname = 'ix_orders_as_axis_status'"
    )).fetchone()
    assert row is not None, "ix_orders_as_axis_status is missing — AS dashboard hot path degrades to Seq Scan"
    assert "btree (as_axis_status)" in row[0]
