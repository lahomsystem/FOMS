"""User deletion lifecycle helpers."""

from __future__ import annotations

from typing import Any

from sqlalchemy import text

from models import (
    AccessLog,
    AddressLearningRequest,
    AuthRateKeyState,
    ChannelCreateFlag,
    ChannelInboundKeyState,
    ChannelManagerLink,
    ChatMessage,
    ChatRoom,
    ChatRoomMember,
    FeatureCutoverMarker,
    InstallationWorker,
    Notification,
    NotificationEvent,
    NotificationPushSubscription,
    NotificationUserState,
    OpsApprovalRequest,
    OrderAssignment,
    OrderAttachment,
    OrderEstimate,
    OrderEvent,
    OrderInstallationAssignment,
    OrderMutationReceipt,
    OrderTask,
    SecurityLog,
    SecurityPrincipalVersion,
    SecuritySigningState,
    SystemSettingReceipt,
    UploadDraft,
    WDCLinkRuntimeState,
)

__all__ = [
    "detach_user_references_for_delete",
    "ensure_order_attachment_user_fk_set_null",
]


class UserDeletionBlockedError(RuntimeError):
    """Raised when audit rows that cannot be detached still reference the user.

    ``nullable=False`` 감사 참조는 NULL 로 끊을 수도, 감사를 지우지 않고는 삭제할 수도
    없다. 조용히 삼키는 대신 사유를 담아 삭제를 거부한다.
    """


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
    # --- deploy 신규 테이블: 행은 사람과 무관하게 살아남아야 하는 감사/설정 상태 ---
    (NotificationEvent, "actor_user_id"),
    (NotificationEvent, "recipient_user_id"),
    (OpsApprovalRequest, "approved_by_user_id"),
    (OrderAssignment, "released_by_user_id"),
    (AddressLearningRequest, "requested_by_user_id"),
    (UploadDraft, "created_by_user_id"),
    # singleton 설정 행 — 지우면 서비스 상태가 사라지므로 actor 만 끊는다.
    (WDCLinkRuntimeState, "updated_by_admin_user_id"),
    (SecuritySigningState, "updated_by_admin_user_id"),
    (AuthRateKeyState, "updated_by_admin_user_id"),
    (ChannelInboundKeyState, "updated_by_admin_user_id"),
    (ChannelCreateFlag, "updated_by_admin_user_id"),
    # 외부 설치 작업자 마스터는 내부 계정 소유물이 아니다(배정이 worker_id 로 참조).
    (InstallationWorker, "user_id"),
    (OrderInstallationAssignment, "assigned_by_user_id"),
    (OrderInstallationAssignment, "released_by_user_id"),
)

_DELETE_USER_REFERENCE_FIELDS: tuple[tuple[Any, str], ...] = (
    (ChatMessage, "user_id"),
    (ChatRoom, "created_by"),
    (ChatRoomMember, "user_id"),
    # --- deploy 신규 테이블: 사람이 사라지면 행 자체가 의미를 잃는다 ---
    (NotificationPushSubscription, "user_id"),  # 개인 기기 구독
    (SecurityPrincipalVersion, "user_id"),      # PK — NULL 불가, 사용자당 1행 카운터
    # receipt 는 expires_at(+24h) + retention purge 로 소멸하도록 설계된 일시 행이다
    # (tools/ops/purge_order_mutation_receipts.py). actor 가 사라지면 replay 도 불가능.
    (SystemSettingReceipt, "actor_user_id"),
    (OrderMutationReceipt, "actor_user_id"),
)

# nullify 도 행 삭제도 불가능한 참조 — (model, column, 거부 사유).
_BLOCKING_USER_REFERENCE_FIELDS: tuple[tuple[Any, str, str], ...] = (
    # PostgreSQL trigger 가 UPDATE/DELETE 자체를 거부한다(irreversible marker).
    (FeatureCutoverMarker, "approved_by_admin_user_id", "되돌릴 수 없는 시스템 설정 승인 이력"),
    # 권한 판정 정본 — 행을 지우면 주문 소유권/배정 이력이 조용히 사라진다.
    (OrderAssignment, "user_id", "주문 배정"),
    (OrderAssignment, "assigned_by_user_id", "주문 배정 실행 이력"),
)


def _assert_no_blocking_user_references(db: Any, user_id: int) -> None:
    """Refuse the deletion when non-detachable audit rows still name the user.

    Args:
        db: 활성 SQLAlchemy 세션.
        user_id: 삭제 대상 사용자 id.

    Returns:
        None. 남은 참조가 없으면 아무것도 하지 않는다.

    Raises:
        UserDeletionBlockedError: 위 참조가 하나라도 남아 있을 때.
    """
    reasons = [
        reason
        for model, column_name, reason in _BLOCKING_USER_REFERENCE_FIELDS  # perf-ok
        if db.query(model).filter(getattr(model, column_name) == user_id).count()
    ]
    if reasons:
        raise UserDeletionBlockedError(
            f"이 사용자는 {', '.join(reasons)}이(가) 남아 있어 삭제할 수 없습니다. "
            "계정 비활성화를 사용하세요."
        )


def _detach_notification_user_states(db: Any, user_id: int) -> dict[str, int]:
    """Delete the user's per-user notification state rows without losing the audit log.

    ``notification_events.user_state_id`` FK 에 ``ON DELETE`` 절이 없어 상태 행을 먼저
    지우면 append-only 감사 로그가 FK 위반을 낸다. 감사 행의 링크만 NULL 로 끊고 상태
    행을 삭제한다(감사 행 자체는 보존).

    Args:
        db: 활성 SQLAlchemy 세션.
        user_id: 삭제 대상 사용자 id.

    Returns:
        ``{"테이블.컬럼": 영향 행 수}`` 부분 요약. 상태 행이 없으면 빈 dict.
    """
    state_ids = [
        state_id
        for (state_id,) in db.query(NotificationUserState.id)
        .filter(NotificationUserState.user_id == user_id)
        .all()
    ]  # perf-ok: single-user notification state ids
    if not state_ids:
        return {}

    unlinked = (
        db.query(NotificationEvent)
        .filter(NotificationEvent.user_state_id.in_(state_ids))
        .update({NotificationEvent.user_state_id: None}, synchronize_session=False)
    )
    deleted = (
        db.query(NotificationUserState)
        .filter(NotificationUserState.id.in_(state_ids))
        .delete(synchronize_session=False)
    )
    return {
        "notification_events.user_state_id": unlinked or 0,
        "notification_user_states.user_id": deleted or 0,
    }


def _detach_owned_chat_rooms(db: Any, user_id: int) -> dict[str, int]:
    """Delete the messages and memberships of chat rooms the user owns.

    ``chat_rooms`` 자체는 뒤이은 ``_DELETE_USER_REFERENCE_FIELDS`` 루프가 지운다. 그
    전에 room 을 참조하는 child 행을 비워야 FK 위반이 나지 않는다.

    Args:
        db: 활성 SQLAlchemy 세션.
        user_id: 삭제 대상 사용자 id.

    Returns:
        ``{"테이블.컬럼": 영향 행 수}`` 부분 요약. 소유 room 이 없으면 빈 dict.
    """
    owned_room_ids = [room_id for (room_id,) in db.query(ChatRoom.id).filter(ChatRoom.created_by == user_id).all()]  # perf-ok: single-user owned room ids
    if not owned_room_ids:
        return {}

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
    return {
        "chat_messages.room_id": deleted_messages or 0,
        "chat_room_members.room_id": deleted_members or 0,
    }


def detach_user_references_for_delete(db: Any, user_id: int) -> dict[str, int]:
    """Detach or delete rows that still reference ``users.id`` before user deletion.

    Args:
        db: 활성 SQLAlchemy 세션.
        user_id: 삭제 대상 사용자 id.

    Returns:
        ``{"테이블.컬럼": 영향 행 수}`` 요약.

    Raises:
        UserDeletionBlockedError: 끊을 수 없는 감사 참조가 남아 있을 때(아무것도 쓰지 않음).
    """
    _assert_no_blocking_user_references(db, user_id)

    summary: dict[str, int] = {}
    summary.update(_detach_notification_user_states(db, user_id))
    summary.update(_detach_owned_chat_rooms(db, user_id))

    for model, column_name in _NULLABLE_USER_REFERENCE_FIELDS:  # perf-ok
        column = getattr(model, column_name)
        count = (
            db.query(model)
            .filter(column == user_id)
            .update({column: None}, synchronize_session=False)
        )
        summary[f"{model.__tablename__}.{column_name}"] = count or 0

    for model, column_name in _DELETE_USER_REFERENCE_FIELDS:  # perf-ok
        column = getattr(model, column_name)
        count = (
            db.query(model)
            .filter(column == user_id)
            .delete(synchronize_session=False)
        )
        summary[f"{model.__tablename__}.{column_name}"] = count or 0

    return summary


def ensure_order_attachment_user_fk_set_null(db: Any) -> bool:
    """Ensure the live Postgres FK uses ``ON DELETE SET NULL`` for attachment uploader ids."""
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
