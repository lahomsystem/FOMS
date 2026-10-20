"""주문 완전 삭제 때 저장소 파일 정리 (SPEC 2026-10-20-purge-storage-files)."""

import pytest

import foms.services.order_storage_cleanup as cleanup
from db import db_session
from foms.services.storage import StorageAdapter
import datetime

from models import DrawingWizardPending, Order, OrderAttachment, UploadDraft, UploadTicket


def _order(**kw):
    order = Order(received_date="2026-10-20", customer_name="정리 대상", phone="010-0000-0000",
                  address="Seoul", product="Wardrobe", status="RECEIVED", **kw)
    db_session.add(order)
    db_session.commit()
    return order


def _attachment(order_id, key, thumb=None):
    db_session.add(OrderAttachment(order_id=order_id, filename="a.jpg", file_type="image",
                                   category="measurement", file_size=1, storage_key=key,
                                   thumbnail_key=thumb))


def test_targets_cover_every_file_table_and_skip_other_orders(app):
    target = _order(blueprint_image_url="/api/files/view/blueprints/bp.png",
                    structured_data={"drawing_current_files": [{"key": "legacy/drawing.pdf"}, "bad"]})
    other = _order(blueprint_image_url="/api/files/view/blueprints/other.png")
    _attachment(target.id, f"orders/{target.id}/attachments/a.jpg", "thumbnails/a_t.jpg")
    _attachment(other.id, f"orders/{other.id}/attachments/o.jpg", "thumbnails/o_t.jpg")
    later = datetime.datetime(2030, 1, 1)
    db_session.add_all([
        UploadTicket(order_id=target.id, object_key="tickets/t1.jpg", filename="t1.jpg",
                     file_type="image", expires_at=later),
        UploadTicket(order_id=other.id, object_key="tickets/o1.jpg", filename="o1.jpg",
                     file_type="image", expires_at=later),
        UploadDraft(order_id=target.id, kind="as_cycle", expires_at=later,
                    object_keys=["drafts/d1.jpg", 3, ""]),
        DrawingWizardPending(order_id=target.id, object_key="exports/w1.png", expires_at=later),
    ])
    db_session.commit()
    targets = cleanup.storage_targets_for_orders(db_session, [target.id])

    assert targets["prefixes"] == [f"orders/{target.id}/"]
    # 접두어 안 키는 따로 세지 않고, 밖 키(썸네일·옛 도면·도면 URL)만 남는다.
    assert targets["keys"] == ["blueprints/bp.png", "drafts/d1.jpg", "exports/w1.png",
                               "legacy/drawing.pdf", "thumbnails/a_t.jpg", "tickets/t1.jpg"]


def test_targets_empty_for_no_orders(app):
    assert cleanup.storage_targets_for_orders(db_session, []) == {"keys": [], "prefixes": []}


class _FakeStorage:
    def __init__(self, fail_key=None):
        self.calls = []
        self.fail_key = fail_key

    def delete_prefix(self, prefix):
        self.calls.append(("prefix", prefix))
        return 3

    def delete_file(self, key):
        self.calls.append(("key", key))
        if key == self.fail_key:
            raise RuntimeError("boom")
        return True


def test_delete_targets_continues_after_failure(monkeypatch):
    fake = _FakeStorage(fail_key="b")
    monkeypatch.setattr(cleanup, "get_storage", lambda: fake)

    deleted, failed = cleanup.delete_storage_targets({"keys": ["a", "b", "c"], "prefixes": ["orders/7/"]})

    assert fake.calls == [("prefix", "orders/7/"), ("key", "a"), ("key", "b"), ("key", "c")]
    assert (deleted, failed) == (5, 1)


@pytest.mark.parametrize("prefix", ["", "orders/", "orders/1", "orders/../", "orders/1/x/", "uploads/1/", None])
def test_delete_prefix_rejects_unsafe_prefix(prefix):
    storage = StorageAdapter.__new__(StorageAdapter)
    storage.storage_type = "local"
    storage.upload_folder = "does-not-matter"
    with pytest.raises(ValueError):
        storage.delete_prefix(prefix)


def test_delete_prefix_local_removes_only_that_order(tmp_path):
    storage = StorageAdapter.__new__(StorageAdapter)
    storage.storage_type = "local"
    storage.upload_folder = str(tmp_path)
    (tmp_path / "orders" / "7" / "attachments").mkdir(parents=True)
    (tmp_path / "orders" / "7" / "attachments" / "a.jpg").write_bytes(b"x")
    (tmp_path / "orders" / "7" / "b.jpg").write_bytes(b"x")
    (tmp_path / "orders" / "70").mkdir(parents=True)
    (tmp_path / "orders" / "70" / "keep.jpg").write_bytes(b"x")

    assert storage.delete_prefix("orders/7/") == 2
    assert not (tmp_path / "orders" / "7").exists()
    assert (tmp_path / "orders" / "70" / "keep.jpg").exists()


def _load_tool():
    import importlib.util
    from pathlib import Path

    path = Path(__file__).resolve().parents[2] / "tools" / "ops" / "apply_delete_retention.py"
    spec = importlib.util.spec_from_file_location("apply_delete_retention_tool", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _Session:
    def __init__(self, fail_commit=False):
        self.fail_commit = fail_commit

    def commit(self):
        if self.fail_commit:
            raise RuntimeError("commit failed")

    def rollback(self):
        pass

    def close(self):
        pass


@pytest.mark.parametrize("fail_commit", [False, True])
def test_tool_deletes_files_only_after_commit(monkeypatch, tmp_path, fail_commit):
    from foms.services.orders.delete_retention import DeleteRetentionResult

    tool = _load_tool()
    plan = tmp_path / "plan.json"
    plan.write_text('{"exact_order_ids": [7]}', encoding="utf-8")
    targets = {"keys": [], "prefixes": ["orders/7/"]}
    calls = []
    monkeypatch.setattr(tool.root_store, "resolve_control_root", lambda: tmp_path)
    monkeypatch.setattr(tool.root_store, "read_token", lambda *_a: {
        "operation_id": tool.OPS_APPROVAL_OPERATION_ID, "one_time_secret_b64url": "x"})
    monkeypatch.setattr(tool.root_store, "decode_secret_b64url", lambda _v: b"x")
    monkeypatch.setattr(tool, "sessionmaker", lambda **_k: (lambda: _Session(fail_commit)))
    monkeypatch.setattr(tool, "apply_delete_retention", lambda *_a, **_k: DeleteRetentionResult(
        target_count=1, deleted=1, applied=True, consumed=True, plan_sha256="p",
        count_sha256="c", result_sha256="r", storage_targets=targets))
    monkeypatch.setattr(tool, "count_retained_order_events", lambda *_a: 0)
    monkeypatch.setattr(tool, "delete_storage_targets", lambda t: calls.append(t) or (3, 0))

    argv = ["--plan-file", str(plan), "--approval-token-file", str(tmp_path / "t"), "--apply"]
    if fail_commit:
        with pytest.raises(RuntimeError):
            tool.main(argv)
        assert calls == []
    else:
        assert tool.main(argv) == 0
        assert calls == [targets]
