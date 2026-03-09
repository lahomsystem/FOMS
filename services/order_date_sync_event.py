from sqlalchemy import event
from sqlalchemy.orm import Session
from models import Order
from services.order_date_sync import sync_order_dates

def register_order_date_sync_listener():
    @event.listens_for(Session, 'after_flush')
    def receive_after_flush(session, flush_context):
        # We need to collect which orders were updated or inserted
        # and sync their dates. Since we shouldn't modify the session 
        # in after_flush and trigger another flush, adding `OrderScheduleDate` 
        # inside `after_flush` is generally not recommended unless cautious.
        pass
