"""ERP drawing workbench read-model — seed cap + order id cache DTO."""
from __future__ import annotations

from typing import Any

from models import Order

DRAWING_WORKBENCH_SEED_CAP = 250


def fetch_drawing_seed_order_ids(orders_query: Any, *, cap: int = DRAWING_WORKBENCH_SEED_CAP) -> list[int]:
    """Newest ERP orders for workbench stage filter (cap replaces legacy 500)."""
    rows = (
        orders_query.order_by(Order.created_at.desc())
        .with_entities(Order.id)
        .limit(cap)
        .all()
    )
    return [int(row[0]) for row in rows]


def hydrate_drawing_orders_by_ids(orders_query: Any, order_ids: list[int]) -> list[Order]:
    """Preserve id order; re-apply workbench scope filters (cache-hit safe)."""
    if not order_ids:
        return []
    rows = orders_query.filter(Order.id.in_(order_ids)).all()
    by_id = {int(o.id): o for o in rows}
    return [by_id[i] for i in order_ids if i in by_id]
