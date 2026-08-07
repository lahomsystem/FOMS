"""User deactivation / deletion lifecycle helpers.

AUDIT-LOG T11(스펙 §8 결정 ⑤): 관리자 "사용자 삭제"는 더 이상 ``users`` row 를 지우지
않고 **비활성화(탈퇴 처리)** 한다. 감사 원장(``security_logs``·``order_events``·
``access_logs``·``order_attachments``)의 actor 를 NULL 로 밀어버리면 "누가 했는가"가
사후에 소멸해 감사 자체가 무의미해지기 때문이다.

그래서 ``users.id`` 참조는 세 갈래로 분류된다:

* **감사 보존** (:data:`_AUDIT_ACTOR_USER_REFERENCE_FIELDS`) — 비활성화 경로에서
  건드리지 않는다. row 가 남으므로 FK 도 그대로 유효하다.
* **운영 참조** (:data:`_OPERATIONAL_USER_REFERENCE_FIELDS`) — 담당자·수신자처럼
  "지금 일하는 사람"을 가리키는 값이라 끊어야 한다(NULL).
* **동반 삭제** (:data:`_DELETE_USER_REFERENCE_FIELDS`) — Chat 3종은 종전대로 hard
  delete(대화 기록은 감사 원장이 아니다).

:func:`detach_user_references_for_delete` 는 **row 자체가 사라지는 유일한 경로**
(가입 신청 거절 ``reject_user`` — ACCOUNT-SELF-01 은 재신청을 허용하려고 PENDING row 를
지운다) 전용으로 남는다. 그 경로는 FK 를 만족시켜야 하므로 감사 actor 도 NULL 이 된다.
"""

from __future__ import annotations

import secrets
from typing import Any

from sqlalchemy import text

from foms.services.security.password_policy import set_strong_password
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
    "anonymized_deactivated_username",
    "deactivate_user_preserving_audit",
    "detach_user_references_for_deactivate",
    "detach_user_references_for_delete",
    "ensure_order_attachment_user_fk_set_null",
]


class UserDeletionBlockedError(RuntimeError):
    """Raised when audit rows that cannot be detached still reference the user.

    ``nullable=False`` 감사 참조는 NULL 로 끊을 수도, 감사를 지우지 않고는 삭제할 수도
    없다. 조용히 삼키는 대신 사유를 담아 삭제를 거부한다. T11 이후 이 거부는 **row 가
    사라지는 유일한 경로**(가입 거절 ``reject_user``)에만 걸린다 — 비활성화는 row 를
    남기므로 애초에 FK 가 깨지지 않는다.
    """


#: 감사 actor — 비활성화 시 **절대 NULL 로 만들지 않는다**(행위자 소멸 방지).
#: ``order_attachments.user_id`` 는 업로더 = "누가 이 파일을 올렸는가"라 감사 성격이다.
_AUDIT_ACTOR_USER_REFERENCE_FIELDS: tuple[tuple[Any, str], ...] = (
    (SecurityLog, "user_id"),
    (OrderEvent, "created_by_user_id"),
    (AccessLog, "user_id"),
    (OrderAttachment, "user_id"),
)

#: 운영 참조 — 현재 담당/수신 대상을 가리키므로 탈퇴 시 끊는다(NULL).
_OPERATIONAL_USER_REFERENCE_FIELDS: tuple[tuple[Any, str], ...] = (
    (OrderTask, "owner_user_id"),
    (Notification, "created_by_user_id"),
    (Notification, "read_by_user_id"),
    (Notification, "target_user_id"),
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

#: hard delete 경로 전용 — row 가 사라지면 감사 actor FK 도 만족시킬 수 없다.
_NULLABLE_USER_REFERENCE_FIELDS: tuple[tuple[Any, str], ...] = (
    _OPERATIONAL_USER_REFERENCE_FIELDS + _AUDIT_ACTOR_USER_REFERENCE_FIELDS
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

#: 익명화 username 접두어. ``deleted_<id>_<원본>`` 이라 원본 아이디는 즉시 재사용 가능하고,
#: id 가 들어가므로 값 자체도 유일하다(unique 제약 충돌 없음).
_DEACTIVATED_USERNAME_PREFIX = "deleted"
#: username 표기 상한(초과분은 원본 꼬리를 잘라 맞춘다).
_DEACTIVATED_USERNAME_MAX_LENGTH = 100
#: 목록·감사 화면에 노출되는 탈퇴 표기.
_DEACTIVATED_NAME = "탈퇴 사용자"
#: 로그인 불가 비밀번호로 덮어쓸 때 쓰는 난수 바이트 수(평문은 즉시 폐기).
_UNRECOVERABLE_SECRET_BYTES = 48


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


def _purge_owned_chat_rooms(db: Any, user_id: int, summary: dict[str, int]) -> None:
    """user 가 만든 채팅방의 메시지·멤버를 먼저 지운다(방 삭제 FK 선행 정리).

    :param db: SQLAlchemy 세션.
    :param user_id: 대상 사용자 id.
    :param summary: 처리 건수를 누적할 dict(제자리 갱신).
    """
    owned_room_ids = [room_id for (room_id,) in db.query(ChatRoom.id).filter(ChatRoom.created_by == user_id).all()]  # perf-ok: single-user owned room ids
    if not owned_room_ids:
        return

    summary["chat_messages.room_id"] = (
        db.query(ChatMessage)
        .filter(ChatMessage.room_id.in_(owned_room_ids))
        .delete(synchronize_session=False)
    ) or 0
    summary["chat_room_members.room_id"] = (
        db.query(ChatRoomMember)
        .filter(ChatRoomMember.room_id.in_(owned_room_ids))
        .delete(synchronize_session=False)
    ) or 0


def _nullify_references(
    db: Any,
    fields: tuple[tuple[Any, str], ...],
    user_id: int,
    summary: dict[str, int],
) -> None:
    """``fields`` 가 가리키는 컬럼에서 ``user_id`` 참조를 NULL 로 끊는다.

    :param db: SQLAlchemy 세션.
    :param fields: ``(모델, 컬럼명)`` 튜플 목록.
    :param user_id: 대상 사용자 id.
    :param summary: 처리 건수를 누적할 dict(제자리 갱신).
    """
    for model, column_name in fields:  # perf-ok
        column = getattr(model, column_name)
        count = (
            db.query(model)
            .filter(column == user_id)
            .update({column: None}, synchronize_session=False)
        )
        summary[f"{model.__tablename__}.{column_name}"] = count or 0


def _delete_references(
    db: Any,
    fields: tuple[tuple[Any, str], ...],
    user_id: int,
    summary: dict[str, int],
) -> None:
    """``fields`` 가 가리키는 행을 삭제한다(Chat 3종 동반 삭제).

    :param db: SQLAlchemy 세션.
    :param fields: ``(모델, 컬럼명)`` 튜플 목록.
    :param user_id: 대상 사용자 id.
    :param summary: 처리 건수를 누적할 dict(제자리 갱신).
    """
    for model, column_name in fields:  # perf-ok
        column = getattr(model, column_name)
        count = (
            db.query(model)
            .filter(column == user_id)
            .delete(synchronize_session=False)
        )
        summary[f"{model.__tablename__}.{column_name}"] = count or 0


def detach_user_references_for_delete(db: Any, user_id: int) -> dict[str, int]:
    """row 가 사라지는 hard delete 직전에 남은 ``users.id`` 참조를 전부 끊는다.

    **가입 신청 거절(``reject_user``) 전용 경로**다. row 가 사라지면 감사 actor FK 도
    만족시킬 수 없으므로 감사 컬럼까지 NULL 이 된다 — 관리자 "삭제"는 이제
    :func:`detach_user_references_for_deactivate` + :func:`deactivate_user_preserving_audit`
    를 쓴다(T11 결정 ⑤).

    :param db: SQLAlchemy 세션(커밋은 호출부 책임).
    :param user_id: 삭제 대상 사용자 id.
    :return: ``{"테이블.컬럼": 처리 건수}`` 요약 dict.
    :raises UserDeletionBlockedError: NULL 로도 삭제로도 끊을 수 없는 참조가 남았을 때
        (아무것도 쓰지 않는다 — ACCOUNT-SELF-01 가입 거절 가드).
    """
    _assert_no_blocking_user_references(db, user_id)

    summary: dict[str, int] = {}
    summary.update(_detach_notification_user_states(db, user_id))
    _purge_owned_chat_rooms(db, user_id, summary)
    _nullify_references(db, _NULLABLE_USER_REFERENCE_FIELDS, user_id, summary)
    _delete_references(db, _DELETE_USER_REFERENCE_FIELDS, user_id, summary)
    return summary


def detach_user_references_for_deactivate(db: Any, user_id: int) -> dict[str, int]:
    """비활성화(탈퇴 처리) 전에 **운영 참조만** 끊는다 — 감사 actor 는 보존한다.

    :func:`detach_user_references_for_delete` 와의 유일한 차이가 감사 컬럼 4종
    (:data:`_AUDIT_ACTOR_USER_REFERENCE_FIELDS`)을 건드리지 않는 것이다. Chat 3종은
    종전대로 동반 hard delete 한다.

    :data:`_BLOCKING_USER_REFERENCE_FIELDS` 검사도 하지 않는다 — 그 차단은 row 소멸로
    FK 가 깨지는 경우의 방어이고, 여기서는 ``users`` row 가 남아 FK 가 계속 유효하다
    (오히려 "삭제할 수 없으니 비활성화하라"는 그 거부 메시지의 대안 경로가 이쪽이다).
    ``notification_user_states`` 도 남긴다 — 사람 행이 살아 있어 FK 정합이 유지되고,
    append-only ``notification_events.user_state_id`` 링크를 끊을 이유가 없다.

    :param db: SQLAlchemy 세션(커밋은 호출부 책임).
    :param user_id: 비활성화 대상 사용자 id.
    :return: ``{"테이블.컬럼": 처리 건수}`` 요약 dict.
    """
    summary: dict[str, int] = {}
    _purge_owned_chat_rooms(db, user_id, summary)
    _nullify_references(db, _OPERATIONAL_USER_REFERENCE_FIELDS, user_id, summary)
    _delete_references(db, _DELETE_USER_REFERENCE_FIELDS, user_id, summary)
    return summary


def anonymized_deactivated_username(user_id: int, username: str | None) -> str:
    """탈퇴 표기 username(``deleted_<id>_<원본>``)을 만든다.

    원본 아이디를 곧바로 재사용할 수 있게 비우는 것이 목적이고, 원본을 뒤에 남겨
    감사 화면에서 "어떤 계정이었는지"를 읽을 수 있게 한다. 접두어에 id 가 들어가므로
    ``users.username`` unique 제약과 충돌하지 않는다.

    :param user_id: 대상 사용자 id.
    :param username: 원본 username(``None`` 허용).
    :return: :data:`_DEACTIVATED_USERNAME_MAX_LENGTH` 이하로 잘린 익명화 username.
    """
    prefix = f"{_DEACTIVATED_USERNAME_PREFIX}_{user_id}_"
    room = max(_DEACTIVATED_USERNAME_MAX_LENGTH - len(prefix), 0)
    return f"{prefix}{(username or '')[:room]}"


def deactivate_user_preserving_audit(user: Any) -> dict[str, Any]:
    """사용자를 비활성화·익명화하고 로그인을 구조적으로 막는다(감사 actor 보존).

    row 를 남기므로 ``security_logs``·``order_events``·``access_logs``·
    ``order_attachments`` 의 actor FK 가 그대로 유효하다 — "누가 했는가"가 사후에
    소멸하지 않는다. 로그인은 ``is_active=False``(:func:`login_required` 게이트)와
    아무도 모르는 난수 비밀번호로 이중 차단한다. 난수 평문은 반환하지도, 기록하지도
    않는다(설정 chokepoint 는 :func:`set_strong_password` 하나뿐).

    커밋하지 않는다 — 호출부가 같은 트랜잭션에서 커밋한다(감사 로그와 원자성 유지).
    이미 익명화된 계정에 다시 적용해도 접두어가 겹치지 않는다(멱등).

    :param user: 대상 :class:`~models.User` 인스턴스.
    :return: ``user_id``·``username_before``·``username_after``·``name_before``·
        ``was_active`` 를 담은 요약 dict(감사 detail 격납용).
    """
    username_before = user.username
    name_before = user.name
    was_active = bool(user.is_active)

    prefix = f"{_DEACTIVATED_USERNAME_PREFIX}_{user.id}_"
    if not (username_before or "").startswith(prefix):
        user.username = anonymized_deactivated_username(user.id, username_before)
    user.name = _DEACTIVATED_NAME
    user.is_active = False
    set_strong_password(user, f"a1{secrets.token_urlsafe(_UNRECOVERABLE_SECRET_BYTES)}")

    return {
        "user_id": user.id,
        "username_before": username_before,
        "username_after": user.username,
        "name_before": name_before,
        "was_active": was_active,
    }


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
