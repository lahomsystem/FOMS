"""Unit tests for history read-model pagination."""
from unittest.mock import MagicMock

from foms.services.history_read_model import (
    compute_history_page_blob,
    paginate_history_order_ids,
)


def test_paginate_history_order_ids_returns_metadata_and_ids():
    """Page slice returns ids only, not full ORM rows."""
    q = MagicMock()
    q.order_by.return_value = q
    q.count.return_value = 120
    q.with_entities.return_value = q
    q.offset.return_value = q
    q.limit.return_value = q
    q.all.return_value = [(10,), (9,), (8,)]

    page, total_pages, total_orders, order_ids = paginate_history_order_ids(
        q, page=2, per_page=50
    )

    assert page == 2
    assert total_orders == 120
    assert total_pages == 3
    assert order_ids == [10, 9, 8]


def test_compute_history_page_blob_json_shape():
    """Micro-cache DTO is JSON-serializable primitives."""
    q = MagicMock()
    q.order_by.return_value = q
    q.count.return_value = 2
    q.with_entities.return_value = q
    q.offset.return_value = q
    q.limit.return_value = q
    q.all.return_value = [(1,), (2,)]

    blob = compute_history_page_blob(q, page=1, per_page=50)

    assert blob == {
        "page": 1,
        "total_pages": 1,
        "total_orders": 2,
        "order_ids": [1, 2],
    }
