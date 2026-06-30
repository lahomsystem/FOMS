"""P0-00C: OrderDraft cleanup cron dry-run / execute tests."""

from __future__ import annotations

from datetime import datetime, timedelta

from werkzeug.security import generate_password_hash

from db import db_session
from models import Order, OrderDraft, User
from tools.cron.cleanup_order_drafts import run, run_erp_draft_orders


def _make_user(username: str) -> User:
    user = User(
        username=username,
        password=generate_password_hash("pass"),
        role="ADMIN",
        name="Cleanup User",
    )
    db_session.add(user)
    db_session.commit()
    return user


def _make_draft(user: User, draft_key: str, *, expired: bool) -> OrderDraft:
    expires_at = datetime.now() + (timedelta(days=-1) if expired else timedelta(days=7))
    draft = OrderDraft(
        user_id=user.id,
        draft_key=draft_key,
        step=1,
        payload={"schema_version": 1, "step": 1, "data": {}},
        expires_at=expires_at,
    )
    db_session.add(draft)
    db_session.commit()
    return draft


class TestCleanupOrderDrafts:
    def test_dry_run_counts_expired_without_delete(self, app):
        user = _make_user("cleanup-dry-run")
        expired_id = _make_draft(user, "new.expired", expired=True).id
        active_id = _make_draft(user, "new.active", expired=False).id

        scanned, deleted = run(execute=False, session=db_session)

        assert scanned == 1
        assert deleted == 0
        assert db_session.get(OrderDraft, expired_id) is not None
        assert db_session.get(OrderDraft, active_id) is not None

    def test_execute_deletes_only_expired(self, app):
        user = _make_user("cleanup-execute")
        expired_id = _make_draft(user, "new.expired-exec", expired=True).id
        active_id = _make_draft(user, "new.active-exec", expired=False).id

        scanned, deleted = run(execute=True, session=db_session)

        assert scanned == 1
        assert deleted == 1
        assert db_session.get(OrderDraft, expired_id) is None
        assert db_session.get(OrderDraft, active_id) is not None


def _make_draft_order(*, age_hours: float, status: str = "DRAFT") -> Order:
    ts = datetime.now() - timedelta(hours=age_hours)
    order = Order(
        received_date="2026-06-01",
        received_time="10:00",
        customer_name="ERP Order",
        phone="000-0000-0000",
        address="-",
        product="ERP Order",
        status=status,
        is_erp_order=True,
        structured_data={"meta": {"draft": status == "DRAFT"}},
        structured_updated_at=ts,
        created_at=ts,
    )
    db_session.add(order)
    db_session.commit()
    return order


class TestCleanupErpDraftOrders:
    def test_dry_run_counts_stale_without_change(self, app):
        stale_id = _make_draft_order(age_hours=72).id
        fresh_id = _make_draft_order(age_hours=1).id

        scanned, deleted = run_erp_draft_orders(execute=False, session=db_session, stale_hours=48)

        assert scanned == 1
        assert deleted == 0
        assert db_session.get(Order, stale_id).status == "DRAFT"
        assert db_session.get(Order, fresh_id).status == "DRAFT"

    def test_execute_soft_deletes_only_stale_drafts(self, app):
        stale_id = _make_draft_order(age_hours=72).id
        fresh_id = _make_draft_order(age_hours=1).id
        # 승격된(미-DRAFT) 오래된 주문은 절대 건드리지 않는다.
        promoted_id = _make_draft_order(age_hours=200, status="RECEIVED").id

        scanned, deleted = run_erp_draft_orders(execute=True, session=db_session, stale_hours=48)

        assert scanned == 1
        assert deleted == 1
        stale = db_session.get(Order, stale_id)
        assert stale.status == "DELETED"
        assert stale.deleted_at
        assert stale.original_status == "DRAFT"
        assert db_session.get(Order, fresh_id).status == "DRAFT"
        assert db_session.get(Order, promoted_id).status == "RECEIVED"
