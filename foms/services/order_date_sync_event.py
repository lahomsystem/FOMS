"""Legacy order date sync event stub in the runtime namespace."""

from __future__ import annotations

from sqlalchemy import event
from sqlalchemy.orm import Session

from foms.persistence.main.models import Order
from foms.services.order_date_sync import sync_order_dates

__all__ = ["sync_order_dates", "register_order_date_sync_listener"]


def register_order_date_sync_listener() -> None:
    """Keep the legacy after-flush stub available without changing behavior."""

    @event.listens_for(Session, "after_flush")
    def receive_after_flush(session, flush_context):  # pragma: no cover - inert legacy stub
        # We need to collect which orders were updated or inserted
        # and sync their dates. Since we shouldn't modify the session
        # in after_flush and trigger another flush, adding `OrderScheduleDate`
        # inside `after_flush` is generally not recommended unless cautious.
        _ = (session, flush_context, Order)
        pass
