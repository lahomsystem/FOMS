"""User deletion lifecycle helpers.

Centralizes all FK/nullification policy so admin user deletion does not rely on
an ad-hoc list inside the route handler.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import text

from models import (
    AccessLog,
    ChannelManagerLink,
    ChatMessage,
    ChatRoom,
    ChatRoomMember,
    Notification,
    OrderAttachment,
    OrderEstimate,
    OrderEvent,
    OrderTask,
    SecurityLog,
)


_NULLABLE_USER_REFERENCE_FIELDS: tuple[tuple[Any, str], ...] = (
    (SecurityLog, "user_id"),
    (OrderEvent, "created_by_user_id"),
    (OrderTask, "owner_user_id"),
    (Notification, "created_by_user_id"),
    (Notification, "read_by_user_id"),
    (Notification, "target_user_id"),
    (AccessLog, "user_id"),
    (OrderAttachment, "user_id"),
    (OrderEstimate, "created_by_user_id"),
    (ChannelManagerLink, "user_id"),
    (ChannelManagerLink, "deactivated_by_user_id"),
)

_DELETE_USER_REFERENCE_FIELDS: tuple[tuple[Any, str], ...] = (
    (ChatMessage, "user_id"),
    (ChatRoom, "created_by"),
    (ChatRoomMember, "user_id"),
)


def detach_user_references_for_delete(db, user_id: int) -> dict[str, int]:
    """Detach or delete rows that still reference ``users.id``.

    The route-level deletion flow calls this before ``db.delete(user)`` so the
    user record can be removed without depending on database-side cascades.
    """

    summary: dict[str, int] = {}
    owned_room_ids = [room_id for (room_id,) in db.query(ChatRoom.id).filter(ChatRoom.created_by == user_id).all()]

    if owned_room_ids:
        deleted_messages = (
            db.query(ChatMessage)
            .filter(ChatMessage.room_id.in_(owned_room_ids))
            .delete(synchronize_session=False)
        )
        deleted_members = (
            db.query(ChatRoomMember)
            .filter(ChatRoomMember.room_id.in_(owned_room_ids))
            .delete(synchronize_session=False)
        )
        summary["chat_messages.room_id"] = deleted_messages or 0
        summary["chat_room_members.room_id"] = deleted_members or 0

    for model, column_name in _NULLABLE_USER_REFERENCE_FIELDS:
        column = getattr(model, column_name)
        count = (
            db.query(model)
            .filter(column == user_id)
            .update({column: None}, synchronize_session=False)
        )
        summary[f"{model.__tablename__}.{column_name}"] = count or 0

    for model, column_name in _DELETE_USER_REFERENCE_FIELDS:
        column = getattr(model, column_name)
        count = (
            db.query(model)
            .filter(column == user_id)
            .delete(synchronize_session=False)
        )
        summary[f"{model.__tablename__}.{column_name}"] = count or 0

    return summary


def ensure_order_attachment_user_fk_set_null(db) -> bool:
    """Repair legacy PostgreSQL FK to use ``ON DELETE SET NULL``.

    Older manual migrations created ``order_attachments.user_id`` as a plain
    FK. When that drift exists, deleting a user fails even if the ORM expects
    ``SET NULL``. This routine normalizes the live constraint definition.
    """

    bind = db.get_bind()
    if bind is None or bind.dialect.name != "postgresql":
        return False

    constraint_def = db.execute(
        text(
            """
            SELECT pg_get_constraintdef(c.oid)
            FROM pg_constraint c
            JOIN pg_class t ON t.oid = c.conrelid
            JOIN pg_namespace n ON n.oid = t.relnamespace
            WHERE c.conname = 'order_attachments_user_id_fkey'
              AND t.relname = 'order_attachments'
            ORDER BY CASE WHEN n.nspname = 'public' THEN 0 ELSE 1 END, n.nspname
            LIMIT 1
            """
        )
    ).scalar()

    if constraint_def and "ON DELETE SET NULL" in constraint_def.upper():
        return False

    db.execute(
        text(
            """
            ALTER TABLE order_attachments
            DROP CONSTRAINT IF EXISTS order_attachments_user_id_fkey
            """
        )
    )
    db.execute(
        text(
            """
            ALTER TABLE order_attachments
            ADD CONSTRAINT order_attachments_user_id_fkey
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL
            """
        )
    )
    db.commit()
    return True
