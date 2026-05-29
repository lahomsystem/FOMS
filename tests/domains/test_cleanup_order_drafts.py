"""P0-00C: OrderDraft cleanup cron dry-run / execute tests."""

from __future__ import annotations

from datetime import datetime, timedelta

from werkzeug.security import generate_password_hash

from db import db_session
from models import OrderDraft, User
from tools.cron.cleanup_order_drafts import run


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

        scanned, deleted = run(execute=False)

        assert scanned == 1
        assert deleted == 0
        assert db_session.get(OrderDraft, expired_id) is not None
        assert db_session.get(OrderDraft, active_id) is not None

    def test_execute_deletes_only_expired(self, app):
        user = _make_user("cleanup-execute")
        expired_id = _make_draft(user, "new.expired-exec", expired=True).id
        active_id = _make_draft(user, "new.active-exec", expired=False).id

        scanned, deleted = run(execute=True)

        assert scanned == 1
        assert deleted == 1
        assert db_session.get(OrderDraft, expired_id) is None
        assert db_session.get(OrderDraft, active_id) is not None
