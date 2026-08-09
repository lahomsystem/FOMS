"""user_deletion 서비스 단위 계약 — AUDIT-LOG T11 개정판.

**계약 개정 사유(T11 / 스펙 §8 결정 ⑤)**: 감사 actor(``security_logs``·``order_events``·
``access_logs``·``order_attachments``)를 사용자 삭제 시 일괄 NULL 로 미는 설계를 폐기하고,
관리자 "삭제"를 비활성화 전환으로 바꿨다. 그래서 참조 분류(감사 보존 / 운영 NULL /
동반 삭제)와 비활성화 헬퍼 계약을 추가로 고정한다. hard delete 경로
(:func:`~foms.services.user_deletion.detach_user_references_for_delete`)는 가입 신청
거절 전용으로 남아 종전 의미(전 필드 NULL)를 유지한다.
"""

from types import SimpleNamespace

import pytest
from werkzeug.security import check_password_hash

from foms.services import user_deletion


class _FakeColumn:
    def __init__(self, model_name: str, column_name: str):
        self.model_name = model_name
        self.column_name = column_name

    def __hash__(self):
        return hash((self.model_name, self.column_name))

    def __eq__(self, other):
        return ("eq", self.model_name, self.column_name, other)

    def in_(self, values):
        return ("in", self.model_name, self.column_name, tuple(values))


class _FakeModel:
    def __init_subclass__(cls, *, table_name: str):
        cls.__tablename__ = table_name


class _FakeChatRoom(_FakeModel, table_name="chat_rooms"):
    id = _FakeColumn("chat_rooms", "id")
    created_by = _FakeColumn("chat_rooms", "created_by")


class _FakeChatMessage(_FakeModel, table_name="chat_messages"):
    room_id = _FakeColumn("chat_messages", "room_id")
    user_id = _FakeColumn("chat_messages", "user_id")


class _FakeChatRoomMember(_FakeModel, table_name="chat_room_members"):
    room_id = _FakeColumn("chat_room_members", "room_id")
    user_id = _FakeColumn("chat_room_members", "user_id")


class _FakeNotification(_FakeModel, table_name="notifications"):
    created_by_user_id = _FakeColumn("notifications", "created_by_user_id")
    read_by_user_id = _FakeColumn("notifications", "read_by_user_id")


class _FakeAttachment(_FakeModel, table_name="order_attachments"):
    user_id = _FakeColumn("order_attachments", "user_id")


class _FakeNotificationUserState(_FakeModel, table_name="notification_user_states"):
    id = _FakeColumn("notification_user_states", "id")
    user_id = _FakeColumn("notification_user_states", "user_id")


class _FakeNotificationEvent(_FakeModel, table_name="notification_events"):
    user_state_id = _FakeColumn("notification_events", "user_state_id")


class _FakeOrderAssignment(_FakeModel, table_name="order_assignments"):
    user_id = _FakeColumn("order_assignments", "user_id")


class _ScalarResult:
    def __init__(self, value):
        self._value = value

    def scalar(self):
        return self._value


class _FakeDDLDb:
    def __init__(self, *, dialect_name: str, constraint_def=None):
        self._bind = SimpleNamespace(dialect=SimpleNamespace(name=dialect_name))
        self.constraint_def = constraint_def
        self.executed_sql: list[str] = []
        self.commit_calls = 0

    def get_bind(self):
        return self._bind

    def execute(self, statement):
        self.executed_sql.append(str(statement))
        if len(self.executed_sql) == 1:
            return _ScalarResult(self.constraint_def)
        return _ScalarResult(None)

    def commit(self):
        self.commit_calls += 1


class _FakeQuery:
    def __init__(self, target, counts, room_ids, state_ids):
        self.target = target
        self.counts = counts
        self.room_ids = room_ids
        self.state_ids = state_ids
        self.criteria = []

    def filter(self, criterion):
        self.criteria.append(criterion)
        return self

    def all(self):
        if self.target is _FakeChatRoom.id:
            return [(room_id,) for room_id in self.room_ids]
        if self.target is _FakeNotificationUserState.id:
            return [(state_id,) for state_id in self.state_ids]
        raise AssertionError(f"Unexpected all() target: {self.target}")

    def _count_key(self):
        criterion = self.criteria[-1]
        return (criterion[1], criterion[2], criterion[0])

    def update(self, values, synchronize_session=False):
        return self.counts.get(self._count_key(), 0)

    def delete(self, synchronize_session=False):
        return self.counts.get(self._count_key(), 0)

    def count(self):
        return self.counts.get(self._count_key(), 0)


class _FakeReferenceDb:
    def __init__(self, counts, room_ids, state_ids=()):
        self.counts = counts
        self.room_ids = room_ids
        self.state_ids = state_ids

    def query(self, target):
        return _FakeQuery(target, self.counts, self.room_ids, self.state_ids)


def test_detach_user_references_for_delete_returns_summary_and_applies_expected_operations(monkeypatch):
    monkeypatch.setattr(user_deletion, "ChatRoom", _FakeChatRoom)
    monkeypatch.setattr(user_deletion, "ChatMessage", _FakeChatMessage)
    monkeypatch.setattr(user_deletion, "ChatRoomMember", _FakeChatRoomMember)
    monkeypatch.setattr(user_deletion, "NotificationUserState", _FakeNotificationUserState)
    monkeypatch.setattr(user_deletion, "NotificationEvent", _FakeNotificationEvent)
    monkeypatch.setattr(user_deletion, "_BLOCKING_USER_REFERENCE_FIELDS", ())
    monkeypatch.setattr(
        user_deletion,
        "_NULLABLE_USER_REFERENCE_FIELDS",
        (
            (_FakeNotification, "created_by_user_id"),
            (_FakeNotification, "read_by_user_id"),
            (_FakeAttachment, "user_id"),
        ),
    )
    monkeypatch.setattr(
        user_deletion,
        "_DELETE_USER_REFERENCE_FIELDS",
        (
            (_FakeChatMessage, "user_id"),
            (_FakeChatRoom, "created_by"),
            (_FakeChatRoomMember, "user_id"),
        ),
    )

    db = _FakeReferenceDb(
        counts={
            ("chat_messages", "room_id", "in"): 2,
            ("chat_room_members", "room_id", "in"): 3,
            ("notifications", "created_by_user_id", "eq"): 4,
            ("notifications", "read_by_user_id", "eq"): 5,
            ("order_attachments", "user_id", "eq"): 6,
            ("chat_messages", "user_id", "eq"): 7,
            ("chat_rooms", "created_by", "eq"): 8,
            ("chat_room_members", "user_id", "eq"): 9,
        },
        room_ids=[101, 202],
    )

    summary = user_deletion.detach_user_references_for_delete(db, user_id=55)

    assert summary == {
        "chat_messages.room_id": 2,
        "chat_room_members.room_id": 3,
        "notifications.created_by_user_id": 4,
        "notifications.read_by_user_id": 5,
        "order_attachments.user_id": 6,
        "chat_messages.user_id": 7,
        "chat_rooms.created_by": 8,
        "chat_room_members.user_id": 9,
    }


def test_detach_user_references_unlinks_notification_events_before_deleting_states(monkeypatch):
    """상태 행 삭제 전에 감사 로그의 user_state_id 링크를 먼저 끊어야 FK 위반이 없다."""
    monkeypatch.setattr(user_deletion, "ChatRoom", _FakeChatRoom)
    monkeypatch.setattr(user_deletion, "ChatMessage", _FakeChatMessage)
    monkeypatch.setattr(user_deletion, "ChatRoomMember", _FakeChatRoomMember)
    monkeypatch.setattr(user_deletion, "NotificationUserState", _FakeNotificationUserState)
    monkeypatch.setattr(user_deletion, "NotificationEvent", _FakeNotificationEvent)
    monkeypatch.setattr(user_deletion, "_BLOCKING_USER_REFERENCE_FIELDS", ())
    monkeypatch.setattr(user_deletion, "_NULLABLE_USER_REFERENCE_FIELDS", ())
    monkeypatch.setattr(user_deletion, "_DELETE_USER_REFERENCE_FIELDS", ())

    db = _FakeReferenceDb(
        counts={
            ("notification_events", "user_state_id", "in"): 3,
            ("notification_user_states", "id", "in"): 2,
        },
        room_ids=[],
        state_ids=[11, 12],
    )

    summary = user_deletion.detach_user_references_for_delete(db, user_id=55)

    assert summary == {
        "notification_events.user_state_id": 3,
        "notification_user_states.user_id": 2,
    }


def test_detach_user_references_refuses_when_blocking_audit_rows_remain(monkeypatch):
    """nullify 도 삭제도 불가능한 감사 참조가 남으면 사유와 함께 거부한다."""
    monkeypatch.setattr(
        user_deletion,
        "_BLOCKING_USER_REFERENCE_FIELDS",
        ((_FakeOrderAssignment, "user_id", "주문 배정"),),
    )

    db = _FakeReferenceDb(
        counts={("order_assignments", "user_id", "eq"): 1},
        room_ids=[],
    )

    with pytest.raises(user_deletion.UserDeletionBlockedError) as excinfo:
        user_deletion.detach_user_references_for_delete(db, user_id=55)

    assert "주문 배정" in str(excinfo.value)
    assert "비활성화" in str(excinfo.value)


def test_detach_user_references_does_not_refuse_when_no_blocking_rows(monkeypatch):
    """차단 대상 테이블에 행이 없으면 삭제는 그대로 진행된다."""
    monkeypatch.setattr(user_deletion, "ChatRoom", _FakeChatRoom)
    monkeypatch.setattr(user_deletion, "ChatMessage", _FakeChatMessage)
    monkeypatch.setattr(user_deletion, "ChatRoomMember", _FakeChatRoomMember)
    monkeypatch.setattr(user_deletion, "NotificationUserState", _FakeNotificationUserState)
    monkeypatch.setattr(user_deletion, "NotificationEvent", _FakeNotificationEvent)
    monkeypatch.setattr(
        user_deletion,
        "_BLOCKING_USER_REFERENCE_FIELDS",
        ((_FakeOrderAssignment, "user_id", "주문 배정"),),
    )
    monkeypatch.setattr(user_deletion, "_NULLABLE_USER_REFERENCE_FIELDS", ())
    monkeypatch.setattr(user_deletion, "_DELETE_USER_REFERENCE_FIELDS", ())

    db = _FakeReferenceDb(counts={}, room_ids=[])

    assert user_deletion.detach_user_references_for_delete(db, user_id=55) == {}


def test_blocking_reference_fields_cover_non_detachable_audit_columns():
    """차단 목록이 nullify/삭제 불가 컬럼(cutover marker·배정 정본)을 실제로 덮는지."""
    covered = {
        (model.__tablename__, column_name)
        for model, column_name, _ in user_deletion._BLOCKING_USER_REFERENCE_FIELDS
    }

    assert ("feature_cutover_markers", "approved_by_admin_user_id") in covered
    assert ("order_assignments", "user_id") in covered
    assert ("order_assignments", "assigned_by_user_id") in covered


def test_detach_user_references_for_deactivate_skips_blocking_check(monkeypatch):
    """비활성화는 차단 검사를 통과할 필요가 없다 — row 가 남아 FK 가 계속 유효하다."""
    monkeypatch.setattr(user_deletion, "ChatRoom", _FakeChatRoom)
    monkeypatch.setattr(user_deletion, "ChatMessage", _FakeChatMessage)
    monkeypatch.setattr(user_deletion, "ChatRoomMember", _FakeChatRoomMember)
    monkeypatch.setattr(
        user_deletion,
        "_BLOCKING_USER_REFERENCE_FIELDS",
        ((_FakeOrderAssignment, "user_id", "주문 배정"),),
    )
    monkeypatch.setattr(user_deletion, "_OPERATIONAL_USER_REFERENCE_FIELDS", ())
    monkeypatch.setattr(user_deletion, "_AUDIT_ACTOR_USER_REFERENCE_FIELDS", ())
    monkeypatch.setattr(user_deletion, "_DELETE_USER_REFERENCE_FIELDS", ())

    db = _FakeReferenceDb(counts={("order_assignments", "user_id", "eq"): 1}, room_ids=[])

    assert user_deletion.detach_user_references_for_deactivate(db, user_id=55) == {}


def test_detach_user_references_for_deactivate_skips_audit_actor_columns(monkeypatch):
    """비활성화 경로는 운영 참조만 끊는다 — 감사 actor 컬럼은 UPDATE 대상이 아니다."""
    monkeypatch.setattr(user_deletion, "ChatRoom", _FakeChatRoom)
    monkeypatch.setattr(user_deletion, "ChatMessage", _FakeChatMessage)
    monkeypatch.setattr(user_deletion, "ChatRoomMember", _FakeChatRoomMember)
    monkeypatch.setattr(
        user_deletion,
        "_OPERATIONAL_USER_REFERENCE_FIELDS",
        ((_FakeNotification, "created_by_user_id"),),
    )
    monkeypatch.setattr(
        user_deletion,
        "_AUDIT_ACTOR_USER_REFERENCE_FIELDS",
        ((_FakeAttachment, "user_id"),),
    )
    monkeypatch.setattr(
        user_deletion,
        "_DELETE_USER_REFERENCE_FIELDS",
        ((_FakeChatMessage, "user_id"),),
    )

    db = _FakeReferenceDb(
        counts={
            ("chat_messages", "room_id", "in"): 2,
            ("chat_room_members", "room_id", "in"): 3,
            ("notifications", "created_by_user_id", "eq"): 4,
            ("order_attachments", "user_id", "eq"): 6,
            ("chat_messages", "user_id", "eq"): 7,
        },
        room_ids=[101],
    )

    summary = user_deletion.detach_user_references_for_deactivate(db, user_id=55)

    assert summary == {
        "chat_messages.room_id": 2,
        "chat_room_members.room_id": 3,
        "notifications.created_by_user_id": 4,
        "chat_messages.user_id": 7,
    }
    assert "order_attachments.user_id" not in summary


def test_reference_classification_splits_audit_actor_from_operational():
    """재분류 고정: 감사 actor 4 / 나머지는 운영, hard delete 경로만 둘을 합쳐 끊는다.

    감사 4종은 스펙 §8 결정 ⑤가 지목한 원장(``security_logs``·``order_events``·
    ``access_logs``·``order_attachments``)이다. deploy 에서 뒤늦게 추가된 FK 컬럼은
    전부 운영 참조로 둔다 — 비활성화 시 종전 삭제 동작(NULL)을 유지한다.
    """
    from models import (
        AccessLog,
        AddressLearningRequest,
        AuthRateKeyState,
        ChannelCreateFlag,
        ChannelInboundKeyState,
        ChannelManagerLink,
        InstallationWorker,
        Notification,
        NotificationEvent,
        OpsApprovalRequest,
        OrderAssignment,
        OrderAttachment,
        OrderEstimate,
        OrderEvent,
        OrderInstallationAssignment,
        OrderTask,
        SecurityLog,
        SecuritySigningState,
        UploadDraft,
        WDCLinkRuntimeState,
    )

    audit = set(user_deletion._AUDIT_ACTOR_USER_REFERENCE_FIELDS)
    operational = set(user_deletion._OPERATIONAL_USER_REFERENCE_FIELDS)

    assert audit == {
        (SecurityLog, "user_id"),
        (OrderEvent, "created_by_user_id"),
        (AccessLog, "user_id"),
        (OrderAttachment, "user_id"),
    }
    assert operational == {
        (OrderTask, "owner_user_id"),
        (Notification, "created_by_user_id"),
        (Notification, "read_by_user_id"),
        (Notification, "target_user_id"),
        (OrderEstimate, "created_by_user_id"),
        (ChannelManagerLink, "user_id"),
        (ChannelManagerLink, "deactivated_by_user_id"),
        (NotificationEvent, "actor_user_id"),
        (NotificationEvent, "recipient_user_id"),
        (OpsApprovalRequest, "approved_by_user_id"),
        (OrderAssignment, "released_by_user_id"),
        (AddressLearningRequest, "requested_by_user_id"),
        (UploadDraft, "created_by_user_id"),
        (WDCLinkRuntimeState, "updated_by_admin_user_id"),
        (SecuritySigningState, "updated_by_admin_user_id"),
        (AuthRateKeyState, "updated_by_admin_user_id"),
        (ChannelInboundKeyState, "updated_by_admin_user_id"),
        (ChannelCreateFlag, "updated_by_admin_user_id"),
        (InstallationWorker, "user_id"),
        (OrderInstallationAssignment, "assigned_by_user_id"),
        (OrderInstallationAssignment, "released_by_user_id"),
    }
    assert audit.isdisjoint(operational)
    # hard delete(가입 거절)는 row 가 사라지므로 FK 충족을 위해 감사 컬럼까지 끊는다.
    assert set(user_deletion._NULLABLE_USER_REFERENCE_FIELDS) == audit | operational


def _fake_user(user_id: int = 7, username: str = "hong", name: str = "홍길동"):
    return SimpleNamespace(
        id=user_id,
        username=username,
        name=name,
        is_active=True,
        password="old-hash",
        password_policy_version=0,
    )


def test_deactivate_user_preserving_audit_anonymizes_and_blocks_login():
    """비활성화는 익명화·표기 변경·비밀번호 무효화를 한 번에 수행한다."""
    user = _fake_user()

    summary = user_deletion.deactivate_user_preserving_audit(user)

    assert user.is_active is False
    assert user.username == "deleted_7_hong"
    assert user.name == "탈퇴 사용자"
    assert user.password != "old-hash"
    # 아무도 모르는 난수로 덮였으므로 어떤 기존 비밀번호로도 통과할 수 없다.
    assert not check_password_hash(user.password, "old-hash")
    assert summary == {
        "user_id": 7,
        "username_before": "hong",
        "username_after": "deleted_7_hong",
        "name_before": "홍길동",
        "was_active": True,
    }


def test_deactivate_user_preserving_audit_is_idempotent():
    """이미 익명화된 계정에 다시 적용해도 접두어가 중첩되지 않는다."""
    user = _fake_user()
    user_deletion.deactivate_user_preserving_audit(user)
    first_hash = user.password

    summary = user_deletion.deactivate_user_preserving_audit(user)

    assert user.username == "deleted_7_hong"
    assert summary["username_before"] == "deleted_7_hong"
    assert summary["was_active"] is False
    assert user.password != first_hash


def test_anonymized_deactivated_username_respects_length_cap():
    """긴 원본 username 은 상한에 맞춰 꼬리가 잘린다(접두어는 항상 보존)."""
    result = user_deletion.anonymized_deactivated_username(12, "u" * 500)

    assert result.startswith("deleted_12_")
    assert len(result) == user_deletion._DEACTIVATED_USERNAME_MAX_LENGTH


def test_ensure_order_attachment_user_fk_set_null_returns_false_outside_postgres():
    db = _FakeDDLDb(dialect_name="sqlite")

    changed = user_deletion.ensure_order_attachment_user_fk_set_null(db)

    assert changed is False
    assert db.executed_sql == []
    assert db.commit_calls == 0


def test_ensure_order_attachment_user_fk_set_null_skips_when_constraint_already_normalized():
    db = _FakeDDLDb(
        dialect_name="postgresql",
        constraint_def="FOREIGN KEY (user_id) REFERENCES users(id) on delete set null",
    )

    changed = user_deletion.ensure_order_attachment_user_fk_set_null(db)

    assert changed is False
    assert len(db.executed_sql) == 1
    assert "pg_get_constraintdef" in db.executed_sql[0]
    assert db.commit_calls == 0


def test_ensure_order_attachment_user_fk_set_null_repairs_constraint_when_needed():
    db = _FakeDDLDb(dialect_name="postgresql", constraint_def=None)

    changed = user_deletion.ensure_order_attachment_user_fk_set_null(db)

    assert changed is True
    assert len(db.executed_sql) == 3
    assert "pg_get_constraintdef" in db.executed_sql[0]
    assert "DROP CONSTRAINT IF EXISTS order_attachments_user_id_fkey" in db.executed_sql[1]
    assert "FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL" in db.executed_sql[2]
    assert db.commit_calls == 1
