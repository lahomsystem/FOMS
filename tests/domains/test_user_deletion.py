from types import SimpleNamespace

import pytest

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
