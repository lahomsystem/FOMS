"""P0-00B: OrderDraft ORM + constraint tests."""

from __future__ import annotations

import copy
from datetime import datetime, timedelta

import pytest
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError
from werkzeug.security import generate_password_hash

from db import db_session, engine
from models import Order, OrderDraft, User


def _enable_sqlite_foreign_keys() -> None:
    """SQLite in-memory FK cascade requires PRAGMA per connection."""
    if engine.dialect.name != "sqlite":
        return
    with engine.connect() as conn:
        conn.execute(text("PRAGMA foreign_keys=ON"))
        conn.commit()


def _make_user(username: str = "draft-user") -> User:
    user = User(
        username=username,
        password=generate_password_hash("pass"),
        role="ADMIN",
        name="Draft User",
    )
    db_session.add(user)
    db_session.commit()
    return user


def _make_order() -> Order:
    order = Order(
        received_date="2026-05-29",
        customer_name="테스터",
        phone="010-0000-0000",
        address="서울",
        product="붙박이장",
    )
    db_session.add(order)
    db_session.commit()
    return order


def _expires_at(days: int = 7) -> datetime:
    return datetime.now() + timedelta(days=days)


class TestOrderDraftModel:
    def test_create_new_draft_without_order_id(self, app):
        user = _make_user("new-draft-user")
        draft = OrderDraft(
            user_id=user.id,
            order_id=None,
            draft_key="new.test-uuid",
            step=1,
            payload={"schema_version": 1, "step": 1, "data": {}},
            expires_at=_expires_at(),
        )
        db_session.add(draft)
        db_session.commit()

        saved = db_session.query(OrderDraft).filter_by(draft_key="new.test-uuid").one()
        assert saved.order_id is None
        assert saved.user_id == user.id
        assert saved.step == 1

    def test_create_edit_draft_with_order_id(self, app):
        user = _make_user("edit-draft-user")
        order = _make_order()
        draft = OrderDraft(
            user_id=user.id,
            order_id=order.id,
            draft_key=f"edit.{order.id}",
            step=2,
            payload={"schema_version": 1, "step": 2, "data": {"customer_name": "테스터"}},
            expires_at=_expires_at(),
        )
        db_session.add(draft)
        db_session.commit()

        saved = db_session.query(OrderDraft).filter_by(draft_key=f"edit.{order.id}").one()
        assert saved.order_id == order.id

    def test_payload_json_roundtrip_deepcopy(self, app):
        user = _make_user("payload-user")
        original_payload = {
            "schema_version": 1,
            "step": 3,
            "data": {
                "customer_name": "윤인선",
                "items": [{"product_name": "무몰딩", "spec_rows": [{"w": 100, "d": 200, "h": 2400}]}],
            },
        }
        payload_copy = copy.deepcopy(original_payload)
        draft = OrderDraft(
            user_id=user.id,
            draft_key="new.payload-roundtrip",
            step=3,
            payload=payload_copy,
            expires_at=_expires_at(),
        )
        db_session.add(draft)
        db_session.commit()
        draft_id = draft.id

        db_session.expire_all()
        loaded = db_session.get(OrderDraft, draft_id)
        assert loaded is not None
        assert loaded.payload == original_payload
        assert loaded.payload is not original_payload
        assert loaded.payload["data"]["items"][0]["spec_rows"][0]["w"] == 100

    def test_unique_user_id_draft_key_conflict(self, app):
        user = _make_user("unique-user")
        expires = _expires_at()
        db_session.add(
            OrderDraft(
                user_id=user.id,
                draft_key="new.shared-key",
                step=1,
                payload={"schema_version": 1, "step": 1, "data": {}},
                expires_at=expires,
            )
        )
        db_session.commit()

        db_session.add(
            OrderDraft(
                user_id=user.id,
                draft_key="new.shared-key",
                step=2,
                payload={"schema_version": 1, "step": 2, "data": {"phone": "010"}},
                expires_at=expires,
            )
        )
        with pytest.raises(IntegrityError):
            db_session.commit()
        db_session.rollback()

    def test_expires_at_index_exists(self, app):
        indexes = {idx["name"] for idx in inspect(engine).get_indexes("order_drafts")}
        assert "ix_order_drafts_expires_at" in indexes

    def test_user_delete_cascades_drafts(self, app):
        _enable_sqlite_foreign_keys()
        user = _make_user("cascade-user")
        draft = OrderDraft(
            user_id=user.id,
            draft_key="new.cascade",
            step=1,
            payload={"schema_version": 1, "step": 1, "data": {}},
            expires_at=_expires_at(),
        )
        db_session.add(draft)
        db_session.commit()
        draft_id = draft.id

        db_session.delete(user)
        db_session.commit()

        assert db_session.get(OrderDraft, draft_id) is None
