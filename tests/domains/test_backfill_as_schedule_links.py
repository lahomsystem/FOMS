"""``tools/ops/backfill_as_schedule_links.py`` 백필 멱등성 테스트.

로컬 dev DB(``AS_RECOMMENDATION_APPLIED`` 이벤트 0건)에는 실제 대상이 없어
``--dry-run``/``--execute`` 실측 대신, 최소 fixture(출고 주문 1 + AS 주문 1 +
``OrderEvent``)로 백필을 2회 실행해 두 번째 실행이 0건임을 검증한다.
"""
from datetime import date

from db import db_session
from models import Order, OrderEvent

from foms.services.orders.as_schedule_link import SOURCE_SHIPMENT, read_link
from tools.ops.backfill_as_schedule_links import EVENT_TYPE, run_backfill


def _make_ship_and_as_orders() -> tuple[Order, Order]:
    """출고 주문(스냅샷 보유) + AS 주문(링크 없음) 한 쌍을 만든다."""
    today = date.today().strftime("%Y-%m-%d")

    as_order = Order(
        received_date=today, customer_name="AS 백필 대상", phone="010-1111-2222",
        address="Seoul", product="장", status="AS", is_erp_order=True,
        structured_data={},
    )
    db_session.add(as_order)
    db_session.flush()

    ship = Order(
        received_date=today, customer_name="출고 백필 기준", phone="010-3333-4444",
        address="Seoul", product="장", status="IN_CONSTRUCTION", is_erp_order=True,
        structured_data={
            "shipment": {
                "recommendations": [{
                    "as_order_id": as_order.id,
                    "applied_visit_date": "2026-08-05",
                    "applied_by_user_id": None,
                    "applied_at": "2026-07-30T02:11:00",
                }],
            },
        },
    )
    db_session.add(ship)
    db_session.flush()

    db_session.add(OrderEvent(
        order_id=ship.id, event_type=EVENT_TYPE,
        payload={"as_order_id": as_order.id}, created_by_user_id=None,
    ))
    db_session.commit()
    return ship, as_order


def test_backfill_writes_link_then_is_idempotent(app) -> None:
    ship, as_order = _make_ship_and_as_orders()

    dry = run_backfill(db_session, execute=False)
    assert dry == {
        "mode": "dry-run", "candidates": 1, "entries_scanned": 1,
        "written": 1, "skipped": {},
    }
    # dry-run은 아무것도 쓰지 않는다.
    assert read_link(db_session.get(Order, as_order.id).structured_data) is None

    first = run_backfill(db_session, execute=True)
    assert first["written"] == 1
    assert first["skipped"] == {}

    db_session.expire_all()
    link = read_link(db_session.get(Order, as_order.id).structured_data)
    assert link is not None
    assert link["ref_order_id"] == ship.id
    assert link["ref_date"] == "2026-08-05"
    assert link["source"] == SOURCE_SHIPMENT

    second = run_backfill(db_session, execute=True)
    assert second["written"] == 0
    assert second["skipped"] == {"already_linked": 1}
