"""Tests for measurement main_rows micro-cache read-model."""
from unittest.mock import MagicMock

from foms.services.measurement_read_model import (
    MEASUREMENT_MAIN_SEED_LIMIT,
    compute_measurement_main_rows_blob,
    fetch_measurement_main_seed_rows,
)


def test_fetch_measurement_main_seed_rows_caps_at_300():
    q = MagicMock()
    q.options.return_value = q
    q.order_by.return_value = q
    q.limit.return_value = q
    q.all.return_value = []

    fetch_measurement_main_seed_rows(q)

    q.limit.assert_called_with(MEASUREMENT_MAIN_SEED_LIMIT)


def test_compute_measurement_main_rows_blob_returns_order_ids(monkeypatch):
    q = MagicMock()
    # 표시 상한 적용 전 모집단(total_count) — 잘림 안내의 소스라 DTO 에 함께 실린다.
    q.order_by.return_value.count.return_value = 1
    fake_order = MagicMock()
    fake_order.id = 42
    monkeypatch.setattr(
        "foms.services.measurement_read_model.fetch_measurement_main_seed_rows",
        lambda _q: [fake_order],
    )
    monkeypatch.setattr(
        "foms.services.measurement_read_model.build_measurement_main_rows",
        lambda *a, **k: ([fake_order], [99]),
    )

    blob = compute_measurement_main_rows_blob(
        MagicMock(), q, q, None, False, "", False, False, "", "", None
    )

    assert blob == {
        "order_ids": [42],
        "row_fallback_added_ids": [99],
        "total_count": 1,
    }
