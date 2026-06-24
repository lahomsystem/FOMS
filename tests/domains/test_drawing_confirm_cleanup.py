"""Tests for drawing confirm cleanup — keep only latest drawings on sales confirm."""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace

from werkzeug.security import generate_password_hash

import foms.services.drawing_confirm_cleanup as cleanup
from db import db_session
from models import Order, OrderAttachment, User


def test_resolve_final_drawing_files_retransfer_append_keeps_latest_only():
    """Revision retransfer in APPEND mode should not retain the superseded file."""
    structured_data = {
        "drawing_current_files": [
            {"key": "orders/1/old.pdf", "filename": "old.pdf"},
            {"key": "orders/1/new.pdf", "filename": "new.pdf"},
        ],
        "drawing_transfer_history": [
            {
                "action": "TRANSFER",
                "mode": "APPEND",
                "files": [{"key": "orders/1/old.pdf", "filename": "old.pdf"}],
                "previous_current_files": [],
            },
            {"action": "REQUEST_REVISION", "files": []},
            {
                "action": "TRANSFER",
                "mode": "APPEND",
                "files": [{"key": "orders/1/new.pdf", "filename": "new.pdf"}],
                "previous_current_files": [{"key": "orders/1/old.pdf", "filename": "old.pdf"}],
            },
        ],
    }

    final = cleanup.resolve_final_drawing_files(structured_data)

    assert [f["key"] for f in final] == ["orders/1/new.pdf"]


def test_resolve_final_drawing_files_multi_append_without_revision_keeps_all():
    """Adding another drawing sheet without revision should keep every current file."""
    structured_data = {
        "drawing_current_files": [
            {"key": "orders/2/a.pdf", "filename": "a.pdf"},
            {"key": "orders/2/b.pdf", "filename": "b.pdf"},
        ],
        "drawing_transfer_history": [
            {
                "action": "TRANSFER",
                "mode": "APPEND",
                "files": [{"key": "orders/2/a.pdf", "filename": "a.pdf"}],
                "previous_current_files": [],
            },
            {
                "action": "TRANSFER",
                "mode": "APPEND",
                "files": [{"key": "orders/2/b.pdf", "filename": "b.pdf"}],
                "previous_current_files": [{"key": "orders/2/a.pdf", "filename": "a.pdf"}],
            },
        ],
    }

    final = cleanup.resolve_final_drawing_files(structured_data)

    assert [f["key"] for f in final] == ["orders/2/a.pdf", "orders/2/b.pdf"]


def test_resolve_final_drawing_files_partial_replace():
    """Partial replace should keep untouched drawings and swap only targets."""
    structured_data = {
        "drawing_transfer_history": [
            {
                "action": "TRANSFER",
                "mode": "APPEND",
                "files": [
                    {"key": "orders/3/a.pdf", "filename": "a.pdf"},
                    {"key": "orders/3/b.pdf", "filename": "b.pdf"},
                ],
                "previous_current_files": [],
            },
            {"action": "REQUEST_REVISION", "files": []},
            {
                "action": "TRANSFER",
                "mode": "REPLACE",
                "replace_target_keys": ["orders/3/b.pdf"],
                "files": [{"key": "orders/3/b-v2.pdf", "filename": "b-v2.pdf"}],
                "previous_current_files": [
                    {"key": "orders/3/a.pdf", "filename": "a.pdf"},
                    {"key": "orders/3/b.pdf", "filename": "b.pdf"},
                ],
            },
        ],
    }

    final = cleanup.resolve_final_drawing_files(structured_data)

    assert [f["key"] for f in final] == ["orders/3/a.pdf", "orders/3/b-v2.pdf"]


class _FakeStorage:
    def __init__(self):
        self.deleted_keys: list[str] = []

    def delete_file(self, key):
        self.deleted_keys.append(key)
        return True


def test_finalize_drawing_files_on_confirm_prunes_and_deletes(monkeypatch):
    """Confirm cleanup should rewrite structured_data and delete obsolete attachments."""
    storage = _FakeStorage()
    monkeypatch.setattr(cleanup, "get_storage", lambda: storage)

    structured_data = {
        "drawing_current_files": [
            {"key": "orders/9/old.pdf", "filename": "old.pdf"},
            {"key": "orders/9/new.pdf", "filename": "new.pdf"},
        ],
        "drawing_transfer_history": [
            {
                "action": "TRANSFER",
                "mode": "APPEND",
                "files": [{"key": "orders/9/old.pdf", "filename": "old.pdf"}],
                "previous_current_files": [],
            },
            {"action": "REQUEST_REVISION", "files": []},
            {
                "action": "TRANSFER",
                "mode": "APPEND",
                "files": [{"key": "orders/9/new.pdf", "filename": "new.pdf"}],
                "previous_current_files": [{"key": "orders/9/old.pdf", "filename": "old.pdf"}],
            },
        ],
    }

    old_attachment = SimpleNamespace(
        storage_key="orders/9/old.pdf",
        thumbnail_key="orders/9/thumb_old.png",
    )
    new_attachment = SimpleNamespace(
        storage_key="orders/9/new.pdf",
        thumbnail_key=None,
    )

    class _FakeQuery:
        def __init__(self, rows):
            self._rows = rows
            self._storage_keys: set[str] | None = None

        def filter(self, *args, **kwargs):
            for arg in args:
                left = getattr(arg, 'left', None)
                right = getattr(arg, 'right', None)
                if getattr(left, 'key', None) == 'storage_key' and right is not None:
                    self._storage_keys = set(getattr(right, 'value', []) or [])
            return self

        def all(self):
            if self._storage_keys is None:
                return list(self._rows)
            return [row for row in self._rows if row.storage_key in self._storage_keys]

    class _FakeDB:
        def __init__(self):
            self.deleted = []

        def query(self, model):
            if model is OrderAttachment:
                return _FakeQuery([old_attachment, new_attachment])
            return _FakeQuery([])

        def delete(self, row):
            self.deleted.append(row)

    db = _FakeDB()
    final_files, deleted_count = cleanup.finalize_drawing_files_on_confirm(db, 9, structured_data)

    assert [f["key"] for f in final_files] == ["orders/9/new.pdf"]
    assert structured_data["drawing_current_files"] == final_files
    assert deleted_count >= 1
    assert "orders/9/old.pdf" in storage.deleted_keys
    assert "orders/9/thumb_old.png" in storage.deleted_keys
    assert old_attachment in db.deleted
    assert new_attachment not in db.deleted


def _login_sales_user(client):
    user = User(
        username="drawing_confirm_sales",
        password=generate_password_hash("pass"),
        role="ADMIN",
        team="SALES",
        name="영업담당",
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    with client.session_transaction() as sess:
        sess["user_id"] = user.id
        sess["username"] = user.username
        sess["role"] = user.role
    return user


def test_confirm_drawing_receipt_api_prunes_old_files(client, monkeypatch):
    """API confirm should persist only the latest drawing file."""
    storage = _FakeStorage()
    monkeypatch.setattr(cleanup, "get_storage", lambda: storage)

    _login_sales_user(client)

    structured_data = {
        "parties": {"customer": {"name": "고객"}, "manager": {"name": "영업담당"}},
        "workflow": {"stage": "DRAWING"},
        "drawing_status": "TRANSFERRED",
        "assignments": {"sales_assignee_user_ids": []},
        "drawing_current_files": [
            {"key": "orders/77/old.pdf", "filename": "old.pdf"},
            {"key": "orders/77/new.pdf", "filename": "new.pdf"},
        ],
        "drawing_transfer_history": [
            {
                "action": "TRANSFER",
                "mode": "APPEND",
                "files": [{"key": "orders/77/old.pdf", "filename": "old.pdf"}],
                "previous_current_files": [],
            },
            {"action": "REQUEST_REVISION", "files": []},
            {
                "action": "TRANSFER",
                "mode": "APPEND",
                "files": [{"key": "orders/77/new.pdf", "filename": "new.pdf"}],
                "previous_current_files": [{"key": "orders/77/old.pdf", "filename": "old.pdf"}],
            },
        ],
    }
    order = Order(
        received_date=date.today().strftime("%Y-%m-%d"),
        customer_name="고객",
        phone="010-0000-0000",
        address="Seoul",
        product="북박이",
        status="DRAWING",
        manager_name="영업담당",
        is_erp_order=True,
        structured_data=structured_data,
    )
    db_session.add(order)
    db_session.flush()

    old_att = OrderAttachment(
        order_id=order.id,
        filename="old.pdf",
        file_type="file",
        category="drawing",
        storage_key="orders/77/old.pdf",
    )
    new_att = OrderAttachment(
        order_id=order.id,
        filename="new.pdf",
        file_type="file",
        category="drawing",
        storage_key="orders/77/new.pdf",
    )
    db_session.add(old_att)
    db_session.add(new_att)
    db_session.commit()
    order_id = order.id

    res = client.post(f"/api/orders/{order_id}/confirm-drawing-receipt", json={})
    assert res.status_code == 200
    assert res.get_json()["success"] is True

    order = db_session.get(Order, order_id)
    saved_keys = [f["key"] for f in order.structured_data["drawing_current_files"]]
    assert saved_keys == ["orders/77/new.pdf"]

    remaining = (
        db_session.query(OrderAttachment)
        .filter(OrderAttachment.order_id == order.id, OrderAttachment.category == "drawing")
        .all()
    )
    assert len(remaining) == 1
    assert remaining[0].storage_key == "orders/77/new.pdf"
    assert "orders/77/old.pdf" in storage.deleted_keys
