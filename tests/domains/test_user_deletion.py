from types import SimpleNamespace

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
    def __init__(self, target, counts, room_ids):
        self.target = target
        self.counts = counts
        self.room_ids = room_ids
        self.criteria = []

    def filter(self, criterion):
        self.criteria.append(criterion)
        return self

    def all(self):
        if self.target is _FakeChatRoom.id:
            return [(room_id,) for room_id in self.room_ids]
        raise AssertionError(f"Unexpected all() target: {self.target}")

    def update(self, values, synchronize_session=False):
        criterion = self.criteria[-1]
        key = (criterion[1], criterion[2], criterion[0])
        return self.counts.get(key, 0)

    def delete(self, synchronize_session=False):
        criterion = self.criteria[-1]
        key = (criterion[1], criterion[2], criterion[0])
        return self.counts.get(key, 0)


class _FakeReferenceDb:
    def __init__(self, counts, room_ids):
        self.counts = counts
        self.room_ids = room_ids

    def query(self, target):
        return _FakeQuery(target, self.counts, self.room_ids)


def test_detach_user_references_for_delete_returns_summary_and_applies_expected_operations(monkeypatch):
    monkeypatch.setattr(user_deletion, "ChatRoom", _FakeChatRoom)
    monkeypatch.setattr(user_deletion, "ChatMessage", _FakeChatMessage)
    monkeypatch.setattr(user_deletion, "ChatRoomMember", _FakeChatRoomMember)
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
