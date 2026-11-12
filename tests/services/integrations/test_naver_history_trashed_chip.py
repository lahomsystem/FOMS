"""이력 칩 `주문 만듦` 은 휴지통 주문을 세지 않는다 (2026-11-12 운영 #6098 정광호).

행 배지는 휴지통 주문을 `주문 접음` 이라 말하는데 칩은 ``sync_status == 'LINKED'`` 만
세서, 같은 화면에서 행은 접음·칩은 `주문 만듦 2주문` 이 됐다. 칩 숫자와 칩을 눌렀을 때의
목록은 **같은 술어**여야 한다(칩 단위 계약) — 둘 다 여기서 잰다.
"""

from __future__ import annotations

from db import db_session
from foms.web.admin.naver_ingest import _link_rows, _status_group_counts
from models import Order
from tests.services.integrations.test_naver_history_status_axes import _link, _order

FIND = "N-HTC"


def _rows_linked() -> set[str]:
    rows, _total = _link_rows(db_session, status="LINKED", page=1, find=FIND)
    return {str(row.get("external_order_no") or "") for row in rows}


def test_linked_chip_skips_trashed_orders_and_keeps_living_ones(app):
    living = _order(product="살아 있는 주문")
    trashed = _order(product="휴지통 주문")
    trashed.deleted_at = "2026-11-12 08:26:00"
    legacy = _order(product="옛 삭제 주문")
    legacy.status = "DELETED"
    db_session.commit()
    _link(order_no="N-HTC-LIVE", product="칩 살아있음", order_id=int(living.id))
    _link(order_no="N-HTC-TRASH", product="칩 휴지통", order_id=int(trashed.id))
    _link(order_no="N-HTC-LEGACY", product="칩 옛삭제", order_id=int(legacy.id))
    _link(order_no="N-HTC-COLL", product="칩 받아옴")

    counts = _status_group_counts(db_session, find=FIND)

    assert counts["LINKED"] == 1, counts
    assert counts["COLLECTED"] == 1, counts
    assert _rows_linked() == {"N-HTC-LIVE"}


def test_restored_order_counts_again(app):
    """대조군 — 휴지통에서 되살린 주문은 다시 `주문 만듦` 에 든다."""
    order = _order(product="되살린 주문")
    order.deleted_at = "2026-11-12 08:26:00"
    db_session.commit()
    _link(order_no="N-HTC-BACK", product="칩 되살림", order_id=int(order.id))
    assert "N-HTC-BACK" not in _rows_linked()

    db_session.get(Order, int(order.id)).deleted_at = None
    db_session.commit()

    assert "N-HTC-BACK" in _rows_linked()
    assert _status_group_counts(db_session, find="N-HTC-BACK")["LINKED"] == 1
