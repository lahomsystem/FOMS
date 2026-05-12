import datetime

from db import db_session
from models import Order


def _order(customer_name: str, **overrides) -> Order:
    base = {
        "received_date": "2026-05-12",
        "customer_name": customer_name,
        "phone": "010-0000-0000",
        "address": "서울",
        "product": "붙박이장",
        "status": "RECEIVED",
        "is_erp_order": True,
        "erp_stage_code": "COMPLETED",
    }
    base.update(overrides)
    return Order(**base)


def test_completed_order_uses_stage_updated_at_for_dashboard_active_window(app):
    now = datetime.datetime.now()
    order = _order(
        "stage recent",
        erp_stage_updated_at=now - datetime.timedelta(days=5),
        structured_updated_at=now - datetime.timedelta(days=120),
        created_at=now - datetime.timedelta(days=120),
    )
    db_session.add(order)
    db_session.commit()

    results = db_session.query(Order).filter(Order.dashboard_active_filter(days=60)).all()

    assert order in results


def test_completed_order_excluded_when_stage_updated_at_is_old_even_if_structured_recent(app):
    now = datetime.datetime.now()
    order = _order(
        "stage old",
        erp_stage_updated_at=now - datetime.timedelta(days=120),
        structured_updated_at=now - datetime.timedelta(days=5),
        created_at=now - datetime.timedelta(days=5),
    )
    db_session.add(order)
    db_session.commit()

    results = db_session.query(Order).filter(Order.dashboard_active_filter(days=60)).all()

    assert order not in results


def test_completed_order_falls_back_to_structured_then_created_when_stage_timestamp_missing(app):
    now = datetime.datetime.now()
    structured_recent = _order(
        "structured recent",
        erp_stage_updated_at=None,
        structured_updated_at=now - datetime.timedelta(days=5),
        created_at=now - datetime.timedelta(days=120),
    )
    all_old = _order(
        "all old",
        erp_stage_updated_at=None,
        structured_updated_at=now - datetime.timedelta(days=120),
        created_at=now - datetime.timedelta(days=120),
    )
    created_recent = _order(
        "created recent",
        erp_stage_updated_at=None,
        structured_updated_at=None,
        created_at=now - datetime.timedelta(days=5),
    )
    db_session.add_all([structured_recent, all_old, created_recent])
    db_session.commit()

    results = db_session.query(Order).filter(Order.dashboard_active_filter(days=60)).all()

    assert structured_recent in results
    assert created_recent in results
    assert all_old not in results
