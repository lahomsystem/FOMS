"""목록 작은 그림 길 · 워커 작업 · 예약 · 지우기 계약 — SPEC docs/specs/2026-11-19-list-drawing-small-image_SPEC.md.

* ``GET /api/files/thumb/<원본 key>``: 문지기는 원본 보기와 같은 ``_deny_file_access``. 저장본 있으면 바이트 +
  ``private, max-age=2592000, immutable``, 없으면 워커 예약(같은 key 한 번만) + 원본 ``no-store`` 302. 그림 아니면 404.
  감사 기록(FILE_VIEW)은 남기지 않는다. 로컬 저장소는 저장본 → 원본 순서로 파일을 준다.
* 워커 ``create_list_thumb``: 흰 바탕 · EXIF 회전 · 긴 변 ≤ 320 · 16MP 초과 건너뜀 · 이미 있으면 건너뜀.
* 저장소 삭제 작업이 원본을 지울 때 ``sthumb320_`` 형제도 지운다.

협력사 · 프리랜서 범위는 ``tests/security/test_partner_gate.py`` · ``test_freelancer_order_scope.py`` 의 파일 관문
매개변수에 ``thumb`` 를 넣어 같은 자리에서 본다.
"""

from __future__ import annotations

import io
import itertools
from types import SimpleNamespace

import pytest
from PIL import Image
from sqlalchemy import text

import foms.api.files.routes as file_routes
import foms.services.files.list_thumb_schedule as schedule_mod
import foms.services.jobs.queue as queue_mod
import foms.services.storage_delete_handler as handler_mod
from db import db_session
from foms.api.files import build_file_thumb_url
from foms.services.files import list_thumb as lt
from foms.services.jobs import tasks
from models import Order, OrderAttachment, User

_counter = itertools.count(1)
_R2 = "https://account.r2.cloudflarestorage.com/"


class _FakeR2:
    """R2 모드 저장소 흉내 — key → 바이트."""

    storage_type = "r2"

    def __init__(self, objects: dict[str, bytes] | None = None):
        self.objects = dict(objects or {})
        self.reads: list[str] = []
        self.puts: list[str] = []
        self.deleted: list[str] = []

    def object_exists(self, key):
        return key in self.objects

    def read_file_bytes(self, key):
        self.reads.append(key)
        return self.objects.get(key)

    def put_private_bytes(self, key, data, content_type):
        self.puts.append(key)
        self.objects[key] = data
        return True

    def get_download_url(self, key, expires_in=3600, response_content_disposition=None):
        return f"{_R2}{key}?X-Amz-Signature=fresh"

    def delete_file(self, key):
        self.deleted.append(key)
        self.objects.pop(key, None)
        return True


class _FakeRedis:
    def __init__(self):
        self.store: dict[str, str] = {}

    def set(self, key, value, nx=False, ex=None):
        if nx and key in self.store:
            return None
        self.store[key] = value
        return True

    def delete(self, key):
        self.store.pop(key, None)


class _FakeQueue:
    def __init__(self):
        self.connection = _FakeRedis()
        self.jobs: list[tuple] = []

    def enqueue(self, path, *args, **kwargs):
        self.jobs.append((path, args, kwargs))


@pytest.fixture(autouse=True)
def _reset_backoff(monkeypatch):
    monkeypatch.setattr(schedule_mod, "_enqueue_backoff_until", 0.0)


@pytest.fixture
def r2(monkeypatch):
    fake = _FakeR2()
    monkeypatch.setattr(file_routes, "get_storage", lambda: fake)
    return fake


@pytest.fixture
def queue(monkeypatch):
    fake = _FakeQueue()
    monkeypatch.setattr(queue_mod, "get_rq_queue", lambda: fake)
    return fake


@pytest.fixture
def audit_calls(monkeypatch):
    calls: list[tuple] = []
    monkeypatch.setattr(file_routes, "_record_file_access", lambda *a, **k: calls.append((a, k)))
    monkeypatch.setattr(file_routes.audit_writer, "record_file_access", lambda *a, **k: calls.append((a, k)))
    return calls


def _user(role: str = "STAFF") -> User:
    n = next(_counter)
    user = User(username=f"lthumb-{n}", password="x", role=role, team="CS", name=f"사람{n}", is_active=True)
    db_session.add(user)
    db_session.commit()
    return user


def _order() -> Order:
    order = Order(received_date="2026-11-19", customer_name="가짜고객", phone="010-0000-0000",
                  address="가짜시", product="가짜장", status="RECEIVED")
    db_session.add(order)
    db_session.commit()
    return order


def _client(app, user: User | None):
    client = app.test_client()
    if user is not None:
        with client.session_transaction() as sess:
            sess["user_id"] = user.id
    return client


def _png(size=(1000, 500), color=(10, 20, 30, 255), mode="RGBA") -> bytes:
    out = io.BytesIO()
    Image.new(mode, size, color).save(out, "PNG")
    return out.getvalue()


# ----------------------------------------------------------------------- 주소 · 이름 규칙
def test_url_builders_agree_with_route(app):
    key = "orders/7/drawing_wizard/exports/a.png"
    with app.test_request_context():
        from flask import url_for

        assert url_for("files.thumb", storage_key=key) == build_file_thumb_url(key) == lt.list_thumb_url(key)
    assert lt.list_thumb_key(key) == "orders/7/drawing_wizard/exports/sthumb320_a.png.jpg"
    assert lt.list_thumb_url("orders/7/drawing/a.pdf") is None
    # 한글 이름 파일의 key 는 점 없이 ``_png`` 로 끝난다(secure_filename 이 한글을 지운다) — 그림으로 본다.
    assert lt.list_thumb_url("orders/7/drawing/20261119_101010_ab12cd34_png") == "/api/files/thumb/orders/7/drawing/20261119_101010_ab12cd34_png"
    assert lt.list_thumb_key("orders/7/drawing/20261119_101010_ab12cd34_png") == "orders/7/drawing/sthumb320_20261119_101010_ab12cd34_png.jpg"
    assert lt.is_list_thumb_source("orders/7/drawing/jpeg") and lt.is_list_thumb_source("orders/7/drawing/x_JPG")
    assert not lt.is_list_thumb_source("orders/7/drawing/20261119_101010_ab12cd34_pdf")
    assert not lt.is_list_thumb_source("orders/7/drawing/20261119_101010_ab12cd34_file")
    assert not lt.is_list_thumb_source("orders/7/drawing/a.b_png")
    assert lt.list_thumb_url("orders/7/drawing/thumb_a.png") is None  # 파생 파일의 작은 그림은 없다
    assert lt.list_thumb_url("orders/7/drawing/sthumb320_a.png.jpg") is None


def test_pixel_cap_matches_share_sheet_precedent():
    from foms.api import share

    assert lt.LIST_THUMB_MAX_PIXELS == share._SHEET_MAX_PIXELS


# ----------------------------------------------------------------------- 길: 있음 · 없음 · 그림 아님
def test_stored_thumb_served_with_immutable_cache(app, r2, queue, audit_calls):
    order = _order()
    key = f"orders/{order.id}/drawing/a.png"
    r2.objects[lt.list_thumb_key(key)] = b"\xff\xd8small"
    resp = _client(app, _user()).get(f"/api/files/thumb/{key}")
    assert resp.status_code == 200
    assert resp.data == b"\xff\xd8small"
    assert resp.headers["Content-Type"] == "image/jpeg"
    cache = resp.headers["Cache-Control"]
    assert "private" in cache and "max-age=2592000" in cache and "immutable" in cache
    assert "Pragma" not in resp.headers and queue.jobs == []
    assert audit_calls == []  # 감사 기록 안 남김


def test_missing_thumb_redirects_original_and_enqueues_once(app, r2, queue, audit_calls):
    order = _order()
    key = f"orders/{order.id}/drawing/b.png"
    client = _client(app, _user())
    for _ in range(2):  # 두 번 불러도 예약은 한 번
        resp = client.get(f"/api/files/thumb/{key}", follow_redirects=False)
        assert resp.status_code == 302
        assert resp.headers["Location"].startswith(f"{_R2}{key}")
        assert resp.headers["Cache-Control"] == "no-store, max-age=0"
        assert resp.headers["Pragma"] == "no-cache" and resp.headers["Expires"] == "0"
    assert len(queue.jobs) == 1
    path, args, kwargs = queue.jobs[0]
    assert path == "foms.services.jobs.tasks.create_list_thumb_for_key" and args == (key,)
    assert kwargs["job_id"] == lt.list_thumb_job_id(key)
    assert audit_calls == []  # 302(원본)도 목록 미리보기라 감사 기록을 남기지 않는다


def test_missing_thumb_without_queue_still_redirects_and_never_renders_in_web(app, r2, monkeypatch):
    monkeypatch.setattr(queue_mod, "get_rq_queue", lambda: None)
    monkeypatch.setattr(lt, "render_white_jpeg_thumb",
                        lambda *a, **k: pytest.fail("web 이 그림을 줄였다"))
    order = _order()
    key = f"orders/{order.id}/drawing/c.jpg"
    resp = _client(app, _user()).get(f"/api/files/thumb/{key}", follow_redirects=False)
    assert resp.status_code == 302 and r2.puts == []
    source = (file_routes.__file__, schedule_mod.__file__)
    for path in source:
        with open(path, encoding="utf-8") as fh:
            assert "ThreadPoolExecutor" not in fh.read()


def test_enqueue_failure_releases_lock_and_backs_off(app, monkeypatch):
    class _Broken(_FakeQueue):
        def enqueue(self, *a, **k):
            raise ConnectionError("redis down")

    broken = _Broken()
    monkeypatch.setattr(queue_mod, "get_rq_queue", lambda: broken)
    key = "orders/1/drawing/d.png"
    assert schedule_mod.schedule_list_thumb(key) is False
    assert broken.connection.store == {}  # 못 넣었으면 자물쇠를 푼다
    assert schedule_mod._enqueue_backoff_until > 0  # 잠깐 다시 시도하지 않는다


@pytest.mark.parametrize("name", ["plan.pdf", "clip.mp4", "sthumb320_a.png.jpg"])
def test_non_image_key_is_404(app, r2, queue, name):
    order = _order()
    resp = _client(app, _user()).get(f"/api/files/thumb/orders/{order.id}/drawing/{name}")
    assert resp.status_code == 404 and resp.get_json()["success"] is False
    assert queue.jobs == []


# ----------------------------------------------------------------------- 문지기
def test_unauthenticated_not_served(app, r2, queue):
    order = _order()
    key = f"orders/{order.id}/drawing/e.png"
    r2.objects[lt.list_thumb_key(key)] = b"x"
    resp = _client(app, None).get(f"/api/files/thumb/{key}", follow_redirects=False)
    assert resp.status_code != 200 and not resp.headers.get("Location", "").startswith(_R2)
    assert queue.jobs == []


def test_deleted_attachment_is_404(app, r2, queue):
    order = _order()
    key = f"orders/{order.id}/attachments/gone.jpg"
    att = OrderAttachment(order_id=order.id, filename="gone.jpg", file_type="image", category="measurement",
                          file_size=1, storage_key=key)
    db_session.add(att)
    db_session.commit()
    db_session.execute(text("UPDATE order_attachments SET deleted_at = CURRENT_TIMESTAMP WHERE id = :i"),
                       {"i": att.id})
    db_session.commit()
    r2.objects[lt.list_thumb_key(key)] = b"x"  # 저장본이 남아 있어도 원본 판정으로 막힌다
    assert _client(app, _user()).get(f"/api/files/thumb/{key}").status_code == 404
    assert queue.jobs == []


def test_raw_key_without_row_is_403_and_traversal_400(app, r2, queue):
    client = _client(app, _user())
    assert client.get("/api/files/thumb/random/bucket/x.png").status_code == 403
    assert client.get("/api/files/thumb/orders/1/../2/x.png").status_code in (400, 404)
    assert queue.jobs == []


def test_inactive_user_is_denied(app, r2, queue):
    user = _user()
    order = _order()
    user.is_active = False
    db_session.commit()
    resp = _client(app, user).get(f"/api/files/thumb/orders/{order.id}/drawing/f.png", follow_redirects=False)
    assert resp.status_code != 200 and not resp.headers.get("Location", "").startswith(_R2)


# ----------------------------------------------------------------------- 로컬 저장소
def test_local_storage_serves_stored_then_original(app, tmp_path, monkeypatch):
    local = SimpleNamespace(storage_type="local", upload_folder=str(tmp_path))
    monkeypatch.setattr(file_routes, "get_storage", lambda: local)
    order = _order()
    key = f"orders/{order.id}/drawing/g.png"
    (tmp_path / f"orders/{order.id}/drawing").mkdir(parents=True)
    (tmp_path / key).write_bytes(b"original-bytes")
    client = _client(app, _user())

    first = client.get(f"/api/files/thumb/{key}")
    assert first.status_code == 200 and first.data == b"original-bytes"
    assert first.headers["Cache-Control"] == "no-store, max-age=0"  # 원본 대신은 기억시키지 않는다

    (tmp_path / lt.list_thumb_key(key)).write_bytes(b"small-bytes")
    second = client.get(f"/api/files/thumb/{key}")
    assert second.status_code == 200 and second.data == b"small-bytes"
    assert second.headers["Content-Type"] == "image/jpeg" and "immutable" in second.headers["Cache-Control"]
    assert client.get(f"/api/files/thumb/orders/{order.id}/drawing/none.png").status_code == 404


def test_local_storage_rejects_private_put():
    """로컬 저장소는 비공개 저장을 받지 않는다 — 워커가 만들어도 저장 실패로 끝나고 화면은 원본(개발용)."""
    from foms.services.storage import StorageAdapter

    adapter = StorageAdapter.__new__(StorageAdapter)
    adapter.storage_type = "local"
    assert adapter.put_private_bytes("orders/1/drawing/sthumb320_a.png.jpg", b"x", "image/jpeg") is False


# ----------------------------------------------------------------------- 워커 작업
def test_worker_transparent_png_becomes_white_and_shrinks():
    key = "orders/3/drawing_wizard/exports/t.png"
    store = _FakeR2({key: _png(size=(1600, 800), color=(0, 0, 0, 0))})
    assert lt.create_list_thumb(key, storage=store) == lt.RESULT_STORED
    with Image.open(io.BytesIO(store.objects[lt.list_thumb_key(key)])) as out:
        assert out.format == "JPEG" and max(out.size) <= 320 and out.size == (320, 160)
        assert all(c >= 250 for c in out.convert("RGB").getpixel((10, 10)))  # 투명 칸 = 흰색


def test_worker_applies_exif_rotation():
    key = "orders/3/attachments/phone.jpg"
    img = Image.new("RGB", (600, 300), (200, 30, 30))
    exif = img.getexif()
    exif[0x0112] = 6  # 90도 돌려서 보라
    raw = io.BytesIO()
    img.save(raw, "JPEG", exif=exif.tobytes())
    store = _FakeR2({key: raw.getvalue()})
    assert lt.create_list_thumb(key, storage=store) == lt.RESULT_STORED
    with Image.open(io.BytesIO(store.objects[lt.list_thumb_key(key)])) as out:
        width, height = out.size
    assert height > width and max(out.size) <= 320


def test_worker_skips_over_16mp_and_existing_and_non_image():
    big = "orders/3/drawing/big.png"
    store = _FakeR2({big: _png(size=(4001, 4001), color=0, mode="L")})
    assert lt.create_list_thumb(big, storage=store) == lt.RESULT_TOO_LARGE
    assert store.puts == []

    have = "orders/3/drawing/have.png"
    store = _FakeR2({have: _png(), lt.list_thumb_key(have): b"old"})
    assert lt.create_list_thumb(have, storage=store) == lt.RESULT_EXISTS
    assert store.reads == [] and store.puts == []  # 원본을 읽지도 않는다

    assert lt.create_list_thumb("orders/3/drawing/plan.pdf", storage=_FakeR2()) == lt.RESULT_NOT_IMAGE
    assert lt.create_list_thumb("orders/3/drawing/missing.png", storage=_FakeR2()) == lt.RESULT_MISSING
    broken = _FakeR2({"orders/3/drawing/broken.png": b"not an image"})
    assert lt.create_list_thumb("orders/3/drawing/broken.png", storage=broken) == lt.RESULT_UNREADABLE


def test_worker_task_delegates(monkeypatch):
    seen = []
    monkeypatch.setattr(tasks, "create_list_thumb", lambda key: seen.append(key) or lt.RESULT_STORED)
    assert tasks.create_list_thumb_for_key("orders/1/drawing/a.png") == lt.RESULT_STORED
    assert tasks.create_list_thumb_for_key("") is None
    assert seen == ["orders/1/drawing/a.png"]


def test_part_thumb_still_720_white():
    from foms.web.production.part_thumb import render_part_thumb

    with Image.open(io.BytesIO(render_part_thumb(_png(size=(2000, 1000), color=(0, 0, 0, 0))))) as out:
        assert out.size == (720, 360)
        assert all(c >= 250 for c in out.convert("RGB").getpixel((5, 5)))


# ----------------------------------------------------------------------- 지우기 형제
def test_storage_delete_removes_list_thumb_sibling(monkeypatch):
    store = _FakeR2()
    monkeypatch.setattr(handler_mod, "get_storage", lambda: store)
    row = SimpleNamespace(source_domain="UPLOAD_TICKET", id=1, payload={"object_key": "orders/5/drawing/a.png"})
    handler_mod.handle_storage_delete(row)
    assert store.deleted == ["orders/5/drawing/a.png", "orders/5/drawing/sthumb320_a.png.jpg"]  # 없어도 성공

    store.deleted.clear()
    handler_mod.handle_storage_delete(SimpleNamespace(source_domain="UPLOAD_TICKET", id=2,
                                                      payload={"object_key": "orders/5/drawing/a.pdf"}))
    assert store.deleted == ["orders/5/drawing/a.pdf"]  # 그림이 아니면 형제가 없다


def test_storage_delete_sibling_failure_is_retried(monkeypatch):
    store = _FakeR2()
    store.delete_file = lambda key: not key.endswith(".jpg") or "sthumb320_" not in key
    monkeypatch.setattr(handler_mod, "get_storage", lambda: store)
    with pytest.raises(handler_mod.StorageDeleteError):
        handler_mod.handle_storage_delete(
            SimpleNamespace(source_domain="UPLOAD_TICKET", id=3, payload={"object_key": "orders/5/drawing/b.png"}))
