from types import SimpleNamespace

import foms.services.order_storage_cleanup as order_storage_cleanup


class _FakeStorage:
    def __init__(self):
        self.deleted_keys = []

    def delete_file(self, key):
        self.deleted_keys.append(key)


class _FakeQuery:
    def __init__(self, attachments):
        self._attachments = attachments

    def filter(self, *_args, **_kwargs):
        return self

    def all(self):
        return self._attachments


class _FakeDB:
    def __init__(self, attachments):
        self._attachments = attachments

    def query(self, _model):
        return _FakeQuery(self._attachments)


def test_delete_storage_files_for_order_deletes_valid_attachment_blueprint_and_drawing_keys(monkeypatch):
    storage = _FakeStorage()
    monkeypatch.setattr(order_storage_cleanup, "get_storage", lambda: storage)

    db = _FakeDB(
        [
            SimpleNamespace(storage_key="orders/12/attachment.pdf", thumbnail_key="orders/12/thumb.png"),
            SimpleNamespace(storage_key="", thumbnail_key=None),
        ]
    )
    order = SimpleNamespace(
        id=12,
        blueprint_image_url="/api/files/view/orders/12/blueprint.png",
        structured_data={
            "drawing_current_files": [
                {"key": "orders/12/current-a.pdf"},
                {"key": "../escape.pdf"},
                {"key": "orders/99/other.pdf"},
                "invalid",
            ]
        },
    )

    order_storage_cleanup.delete_storage_files_for_order(db, order)

    assert storage.deleted_keys == [
        "orders/12/attachment.pdf",
        "orders/12/thumb.png",
        "orders/12/blueprint.png",
        "orders/12/current-a.pdf",
    ]


def test_delete_storage_files_for_order_returns_early_when_order_missing(monkeypatch):
    monkeypatch.setattr(
        order_storage_cleanup,
        "get_storage",
        lambda: (_ for _ in ()).throw(AssertionError("get_storage should not be called")),
    )

    order_storage_cleanup.delete_storage_files_for_order(db=None, order=None)
