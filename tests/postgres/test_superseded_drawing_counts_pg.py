"""R3 — 생산·시공 대시보드 첨부 개수가 교체된 옛 도면을 빼고 센다 (PGTEST-00 lane).

두 곳의 raw SQL(``... WHERE order_id = ANY(:ids) AND deleted_at IS NULL``)은 PostgreSQL 전용이라
SQLite 레인에서 실행할 수 없다. 옛 도면 행은 목록 API(생산·시공 '도면' 탭)가 빼므로, 개수도
같은 수여야 📎N 이 눌러 연 목록과 맞는다. 옛 도면이 없는 페이지는 추가 쿼리가 없어야 한다.
"""
from __future__ import annotations

import time

import pytest
from sqlalchemy import event

from foms.services.construction_read_model import fetch_construction_attachment_counts
from foms.services.production_read_model import fetch_production_attachment_counts
from models import Order, OrderAttachment

_SEQ = [0]


def _sfx() -> str:
    _SEQ[0] += 1
    return f"{_SEQ[0]}_{int(time.time() * 1000) % 1000000}"


def _order_with_superseded(session) -> Order:
    """v1 → v2 로 교체되고 확정된 주문: 옛 도면 v1 + 현재 v2 + 실측 사진 1."""
    order = Order(received_date="2026-09-29", customer_name=f"옛도면_{_sfx()}",
                  phone="010-1234-5678", address="서울", product="붙박이장",
                  status="PRODUCTION", is_erp_order=True, structured_data={})
    session.add(order)
    session.flush()
    oid = order.id
    v1 = {"key": f"orders/{oid}/drawing_wizard/exports/v1.png", "filename": "v1.png"}
    v2 = {"key": f"orders/{oid}/drawing_wizard/exports/v2.png", "filename": "v2.png"}
    for key, category in ((v1["key"], "drawing"), (v2["key"], "drawing"),
                          (f"orders/{oid}/attachments/m.jpg", "measurement")):
        session.add(OrderAttachment(order_id=oid, filename=key.rsplit("/", 1)[-1],
                                    file_type="image", category=category, file_size=1,
                                    storage_key=key))
    order.structured_data = {
        "workflow": {"stage": "PRODUCTION"},
        "drawing_status": "CONFIRMED",
        "drawing_current_files": [v2],
        "drawing_transfer_history": [
            {"action": "TRANSFER", "files": [v1], "previous_current_files": []},
            {"action": "TRANSFER", "files": [v2], "previous_current_files": [v1]},
            {"action": "CONFIRM_RECEIPT", "files": [v2]},
        ],
    }
    session.flush()
    return order


def _plain_order(session) -> Order:
    order = Order(received_date="2026-09-29", customer_name=f"평범_{_sfx()}",
                  phone="010-1234-5678", address="서울", product="붙박이장",
                  status="PRODUCTION", is_erp_order=True,
                  structured_data={"workflow": {"stage": "PRODUCTION"}})
    session.add(order)
    session.flush()
    session.add(OrderAttachment(order_id=order.id, filename="a.jpg", file_type="image",
                                category="measurement", file_size=1,
                                storage_key=f"orders/{order.id}/attachments/a.jpg"))
    session.flush()
    return order


@pytest.mark.parametrize(
    "fetch_counts",
    [fetch_construction_attachment_counts, fetch_production_attachment_counts],
)
def test_dashboard_counts_skip_superseded_drawing_rows(pg_session, fetch_counts):
    """옛 도면 1개가 있는 주문은 2(v2·실측), 평범한 주문은 그대로 1."""
    old = _order_with_superseded(pg_session)
    plain = _plain_order(pg_session)

    assert fetch_counts(pg_session, [old, plain]) == {old.id: 2, plain.id: 1}


@pytest.mark.parametrize(
    "fetch_counts",
    [fetch_construction_attachment_counts, fetch_production_attachment_counts],
)
def test_dashboard_counts_add_no_query_without_superseded(pg_session, fetch_counts):
    """옛 도면 없는 페이지는 예전처럼 개수 쿼리 1회뿐(structured_data 재조회 없음)."""
    orders = [_plain_order(pg_session), _plain_order(pg_session)]
    statements: list[str] = []

    def _on(conn, cursor, statement, params, context, executemany):
        statements.append(statement)

    bind = pg_session.get_bind()
    event.listen(bind, "before_cursor_execute", _on)
    try:
        counts = fetch_counts(pg_session, orders)
    finally:
        event.remove(bind, "before_cursor_execute", _on)

    assert counts == {o.id: 1 for o in orders}
    assert len(statements) == 1, statements
