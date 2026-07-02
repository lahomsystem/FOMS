"""Drawing workbench read-model seed cap tests."""
from unittest.mock import MagicMock

from foms.services.drawing_workbench_read_model import (
    DRAWING_WORKBENCH_SEED_CAP,
    fetch_drawing_seed_order_ids,
)


def test_fetch_drawing_seed_order_ids_respects_cap():
    q = MagicMock()
    q.order_by.return_value = q
    q.with_entities.return_value = q
    q.limit.return_value = q
    q.all.return_value = [(1,), (2,)]

    ids = fetch_drawing_seed_order_ids(q)

    q.limit.assert_called_with(DRAWING_WORKBENCH_SEED_CAP)
    assert ids == [1, 2]
