"""PG lane: the global ``do_orm_execute`` attachment filter keeps working under ``yield_per``.

``foms/services/attachment_visibility.py`` rewrites every ORM SELECT with
``with_loader_criteria(OrderAttachment, deleted_at IS NULL)``. ``yield_per`` streams through a
psycopg server-side cursor. SQLAlchemy 2.0.50 (#13301) changed how ``do_orm_execute`` state
(yield_per, loader options) carries into the second compile pass, so this pins the combined
behaviour on real PostgreSQL (plan: docs/plans/2026-09-29-sqlalchemy-2-0-54-upgrade-plan.md).
"""
from __future__ import annotations

import time

from sqlalchemy import text

from foms.services.attachment_visibility import include_deleted
from models import Order, OrderAttachment

_SEQ = [0]


def _sfx() -> str:
    _SEQ[0] += 1
    return f"{_SEQ[0]}_{int(time.time() * 1000) % 1000000}"


def _seed(session) -> tuple[int, list[int], int]:
    """One order, three attachments, the middle one tombstoned. Returns (order, live ids, dead id)."""
    order = Order(
        received_date="2026-09-29", customer_name=f"yield_per_{_sfx()}",
        phone="010-1234-5678", address="서울 테헤란로 123", product="붙박이장",
        status="RECEIVED", is_erp_order=True,
    )
    session.add(order)
    session.flush()
    ids = []
    for _ in range(3):
        n = _sfx()
        att = OrderAttachment(
            order_id=order.id, filename=f"p-{n}.jpg", file_type="image", category="measurement",
            file_size=1, storage_key=f"orders/{order.id}/attachments/p-{n}.jpg",
        )
        session.add(att)
        session.flush()
        ids.append(att.id)
    session.execute(text("UPDATE order_attachments SET deleted_at = now() WHERE id = :i"), {"i": ids[1]})
    session.expire_all()
    return order.id, [ids[0], ids[2]], ids[1]


def test_yield_per_over_attachments_hides_tombstones(pg_session) -> None:
    order_id, live, dead = _seed(pg_session)
    q = pg_session.query(OrderAttachment).filter(OrderAttachment.order_id == order_id).order_by(OrderAttachment.id)
    assert [a.id for a in q.yield_per(1)] == live
    assert [a.id for a in include_deleted(q).yield_per(1)] == sorted(live + [dead])  # negative control


def test_yield_per_join_applies_the_filter_to_the_joined_entity(pg_session) -> None:
    order_id, live, _dead = _seed(pg_session)
    rows = (
        pg_session.query(Order.id, OrderAttachment.id)
        .join(OrderAttachment, OrderAttachment.order_id == Order.id)
        .filter(Order.id == order_id)
        .order_by(OrderAttachment.id)
        .yield_per(1)
    )
    assert [r[1] for r in rows] == live


def test_repeated_yield_per_and_plain_queries_do_not_leak_state(pg_session) -> None:
    """Same statement through the compiled cache: streamed, plain, streamed again — same rows."""
    order_id, live, _dead = _seed(pg_session)

    def q():
        return pg_session.query(OrderAttachment).filter(OrderAttachment.order_id == order_id).order_by(OrderAttachment.id)

    first = [a.id for a in q().yield_per(1)]
    plain = [a.id for a in q().all()]
    again = [a.id for a in q().yield_per(2)]
    assert first == plain == again == live
