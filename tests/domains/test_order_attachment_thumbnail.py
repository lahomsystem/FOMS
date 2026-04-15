import foms.services.order_attachment_thumbnail as order_attachment_thumbnail
import foms.services.jobs.queue as job_queue


class _FakeExecutor:
    def __init__(self):
        self.calls = []

    def submit(self, *args):
        self.calls.append(args)


class _FakeStorage:
    def __init__(self, result):
        self.result = result
        self.keys = []

    def generate_thumbnail_from_storage_key(self, storage_key):
        self.keys.append(storage_key)
        return self.result


class _FakeQuery:
    def __init__(self, attachment):
        self.attachment = attachment

    def filter(self, *_args, **_kwargs):
        return self

    def first(self):
        return self.attachment


class _FakeDb:
    def __init__(self, attachment):
        self.attachment = attachment
        self.commit_calls = 0
        self.close_calls = 0

    def query(self, _model):
        return _FakeQuery(self.attachment)

    def commit(self):
        self.commit_calls += 1

    def close(self):
        self.close_calls += 1


class _FakeSessionFactory:
    def __init__(self, db):
        self.db = db
        self.remove_calls = 0

    def __call__(self):
        return self.db

    def remove(self):
        self.remove_calls += 1


class _FakeOrderAttachmentModel:
    id = object()


def test_schedule_order_attachment_thumbnail_generation_uses_rq_when_available(monkeypatch):
    executor = _FakeExecutor()

    monkeypatch.setattr(order_attachment_thumbnail, "_thumbnail_executor", executor)
    monkeypatch.setattr(job_queue, "enqueue_thumbnail_generation", lambda attachment_id, storage_key: True)

    order_attachment_thumbnail.schedule_order_attachment_thumbnail_generation(12, "orders/12/file.jpg")

    assert executor.calls == []


def test_schedule_order_attachment_thumbnail_generation_falls_back_to_executor(monkeypatch):
    executor = _FakeExecutor()

    monkeypatch.setattr(order_attachment_thumbnail, "_thumbnail_executor", executor)
    monkeypatch.setattr(job_queue, "enqueue_thumbnail_generation", lambda attachment_id, storage_key: False)

    order_attachment_thumbnail.schedule_order_attachment_thumbnail_generation("12", "orders/12/file.jpg")

    assert executor.calls == [
        (
            order_attachment_thumbnail._generate_order_attachment_thumbnail_background,
            12,
            "orders/12/file.jpg",
        )
    ]


def test_generate_order_attachment_thumbnail_background_sets_thumbnail_when_missing(monkeypatch):
    attachment = type("Attachment", (), {"thumbnail_key": None})()
    db = _FakeDb(attachment)
    session_factory = _FakeSessionFactory(db)
    storage = _FakeStorage({"success": True, "thumbnail_key": "thumb-key"})

    monkeypatch.setattr(order_attachment_thumbnail, "get_storage", lambda: storage)
    monkeypatch.setattr(order_attachment_thumbnail, "db_session", session_factory)
    monkeypatch.setattr(order_attachment_thumbnail, "OrderAttachment", _FakeOrderAttachmentModel)

    order_attachment_thumbnail._generate_order_attachment_thumbnail_background(
        12,
        "orders/12/file.jpg",
    )

    assert storage.keys == ["orders/12/file.jpg"]
    assert attachment.thumbnail_key == "thumb-key"
    assert db.commit_calls == 1
    assert db.close_calls == 1
    assert session_factory.remove_calls == 1
