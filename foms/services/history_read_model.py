"""ERP history dashboard read-model — SQL pagination + page slice DTO for micro-cache."""
from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Query

from models import Order

HISTORY_DASHBOARD_PAGE_SIZE = 50


def paginate_history_order_ids(
    list_query: Query,
    *,
    page: int,
    per_page: int = HISTORY_DASHBOARD_PAGE_SIZE,
) -> tuple[int, int, int, list[int]]:
    """Return page metadata + order ids (no full-row hydrate beyond page)."""
    if page < 1:
        page = 1
    total_orders = int(list_query.order_by(None).count())
    total_pages = (total_orders + per_page - 1) // per_page if total_orders else 0
    if total_pages and page > total_pages:
        page = total_pages
    offset = (page - 1) * per_page
    id_rows = (
        list_query.order_by(Order.created_at.desc())
        .with_entities(Order.id)
        .offset(offset)
        .limit(per_page)
        .all()
    )
    order_ids = [int(row[0]) for row in id_rows]
    return page, total_pages, total_orders, order_ids


def compute_history_page_blob(list_query: Query, *, page: int, per_page: int) -> dict[str, Any]:
    """JSON DTO for history micro-cache slice."""
    page, total_pages, total_orders, order_ids = paginate_history_order_ids(
        list_query,
        page=page,
        per_page=per_page,
    )
    return {
        "page": page,
        "total_pages": total_pages,
        "total_orders": total_orders,
        "order_ids": order_ids,
    }


def fetch_history_orders_by_ids(list_query: Query, order_ids: list[int]) -> list[Order]:
    """Batch fetch page orders through the same filtered query (cache-hit safe)."""
    if not order_ids:
        return []
    rows = (
        list_query.order_by(None)
        .filter(Order.id.in_(order_ids))
        .all()
    )
    by_id = {int(o.id): o for o in rows}
    return [by_id[i] for i in order_ids if i in by_id]
