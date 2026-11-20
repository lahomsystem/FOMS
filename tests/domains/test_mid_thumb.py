"""중간 크기 그림(긴 변 640) — SPEC docs/specs/2026-11-20-mid-size-image_SPEC.md.

길 · 워커 · 예약 · 지우기:
* ``GET /api/files/thumb/<원본 key>?w=640`` — 허용 크기는 320(기본, ``w`` 없음) · 640 둘뿐, 그 밖은 400.
  문지기 · 캐시 머리글 · "없으면 워커 예약 + 이번만 원본 no-store 302" 는 320 과 같다.
* 저장 이름 ``sthumb640_<원본 이름>.jpg``, 작업 id · 자물쇠가 크기마다 따로(320 은 예전 값 그대로 — 회귀 고정).
* 큐에 이미 든 옛 작업(인자 1개)도 새 워커에서 돈다.

화면 시험은 ``test_mid_thumb_screens.py``, 협력사 완공 · AS 사진은 ``tests/security/test_partner_mid_thumb.py``.
"""

from __future__ import annotations

import hashlib
import io
import itertools
from types import SimpleNamespace

import pytest
from PIL import Image

import foms.api.files.routes as file_routes
import foms.services.files.list_thumb_schedule as schedule_mod
import foms.services.jobs.queue as queue_mod
import foms.services.storage_delete_handler as handler_mod
from db import db_session
from foms.api.files import build_file_thumb_url
from foms.services.files import list_thumb as lt
from foms.services.jobs import tasks
from models import Order, User

_counter = itertools.count(1)
_R2 = "https://account.r2.cloudflarestorage.com/"


def _thumb(key: str) -> str:
    return f"/api/files/thumb/{key}"


def _mid(key: str) -> str:
    return f"/api/files/thumb/{key}?w=640"


def _view(key: str) -> str:
    return f"/api/files/view/{key}"


class _FakeR2:
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
    user = User(username=f"midthumb-{n}", password="x", role=role, team="CS", name=f"사람{n}", is_active=True)
    db_session.add(user)
    db_session.commit()
    return user


def _order() -> Order:
    order = Order(received_date="2026-11-20", customer_name="가짜고객", phone="010-0000-0000",
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


# ----------------------------------------------------------------------- 주소 · 이름 · 작업 id
def test_320_url_job_id_and_lock_unchanged_regression(queue):
    """운영 기기가 30일 캐시한 320 주소 · 큐에 든 작업 id · 걸린 자물쇠는 예전 값과 한 글자도 다르지 않다."""
    key = "orders/7/drawing/a.png"
    digest = hashlib.sha1(key.encode("utf-8")).hexdigest()
    assert lt.list_thumb_url(key) == lt.list_thumb_url(key, 320) == f"/api/files/thumb/{key}"
    assert build_file_thumb_url(key) == build_file_thumb_url(key, 320) == f"/api/files/thumb/{key}"
    assert lt.list_thumb_key(key) == lt.list_thumb_key(key, 320) == "orders/7/drawing/sthumb320_a.png.jpg"
    assert lt.list_thumb_job_id(key) == lt.list_thumb_job_id(key, 320) == f"list_thumb_{digest}"

    assert schedule_mod.schedule_list_thumb(key) is True
    assert list(queue.connection.store) == [f"foms:list_thumb_{digest}:lock"]
    path, args, kwargs = queue.jobs[0]
    assert path == "foms.services.jobs.tasks.create_list_thumb_for_key"
    assert args == (key,)  # 인자 1개 그대로 — 배포 순간 아직 옛 코드인 워커도 받는다
    assert kwargs["job_id"] == f"list_thumb_{digest}"


def test_640_names_url_and_job_id(app):
    key = "orders/7/drawing/a.png"
    digest = hashlib.sha1(key.encode("utf-8")).hexdigest()
    with app.test_request_context():
        from flask import url_for

        assert url_for("files.thumb", storage_key=key, w=640) == _mid(key)
    assert lt.list_thumb_url(key, 640) == lt.mid_thumb_url(key) == build_file_thumb_url(key, 640) == _mid(key)
    assert lt.list_thumb_key(key, 640) == "orders/7/drawing/sthumb640_a.png.jpg"
    assert lt.list_thumb_job_id(key, 640) == f"list_thumb640_{digest}" != lt.list_thumb_job_id(key)
    assert lt.list_thumb_sibling_keys(key) == ["orders/7/drawing/sthumb320_a.png.jpg",
                                               "orders/7/drawing/sthumb640_a.png.jpg"]
    # 판정은 320 과 같은 정본 — 그림 아님 · 파생 파일(640 포함)은 None.
    assert lt.mid_thumb_url("orders/7/drawing/a.pdf") is None
    assert lt.mid_thumb_url("orders/7/drawing/sthumb640_a.png.jpg") is None
    assert lt.list_thumb_url("orders/7/drawing/sthumb640_a.png.jpg") is None
    assert lt.mid_thumb_url("orders/7/drawing/20261120_101010_ab12cd34_png") == _mid(
        "orders/7/drawing/20261120_101010_ab12cd34_png")  # 한글 이름 key
    for bad in (0, 480, 1280):
        with pytest.raises(ValueError):
            lt.list_thumb_url(key, bad)


def test_mid_thumb_filter_registered(app):
    assert app.jinja_env.filters["mid_thumb_url"] is lt.mid_thumb_url
    assert app.jinja_env.filters["list_thumb_url"] is lt.list_thumb_url  # 320 필터는 그대로


# ----------------------------------------------------------------------- 길: 허용 크기
@pytest.mark.parametrize("query", ["", "?w=320", "?w=640"])
def test_allowed_sizes_pass(app, r2, queue, query):
    order = _order()
    key = f"orders/{order.id}/drawing/ok.png"
    resp = _client(app, _user()).get(f"/api/files/thumb/{key}{query}", follow_redirects=False)
    assert resp.status_code == 302 and resp.headers["Location"].startswith(f"{_R2}{key}")


@pytest.mark.parametrize("query", ["?w=0", "?w=1280", "?w=abc", "?w=", "?w=0640", "?w=%20640", "?w=-640"])
def test_other_sizes_are_400(app, r2, queue, query):
    order = _order()
    key = f"orders/{order.id}/drawing/bad.png"
    r2.objects[lt.list_thumb_key(key)] = b"x"
    r2.objects[lt.list_thumb_key(key, 640)] = b"y"
    resp = _client(app, _user()).get(f"/api/files/thumb/{key}{query}", follow_redirects=False)
    assert resp.status_code == 400
    body = resp.get_json()
    assert body["success"] is False and body["message"]  # files 라우트 오류 모양
    assert queue.jobs == [] and r2.reads == []


def test_640_stored_served_with_immutable_cache(app, r2, queue, audit_calls):
    order = _order()
    key = f"orders/{order.id}/as/a.jpg"
    r2.objects[lt.list_thumb_key(key)] = b"\xff\xd8small320"
    r2.objects[lt.list_thumb_key(key, 640)] = b"\xff\xd8mid640"
    client = _client(app, _user())
    resp = client.get(_mid(key))
    assert resp.status_code == 200 and resp.data == b"\xff\xd8mid640"
    assert resp.headers["Content-Type"] == "image/jpeg"
    assert resp.headers["Cache-Control"] == lt.LIST_THUMB_CACHE_CONTROL
    assert "Pragma" not in resp.headers
    assert client.get(_thumb(key)).data == b"\xff\xd8small320"  # 320 은 320 저장본
    assert queue.jobs == [] and audit_calls == []


def test_640_missing_redirects_once_and_does_not_block_320(app, r2, queue, audit_calls):
    order = _order()
    key = f"orders/{order.id}/as/b.jpg"
    client = _client(app, _user())
    for _ in range(2):  # 두 번 불러도 640 예약은 한 번
        resp = client.get(_mid(key), follow_redirects=False)
        assert resp.status_code == 302 and resp.headers["Location"].startswith(f"{_R2}{key}")
        assert resp.headers["Cache-Control"] == "no-store, max-age=0"
        assert resp.headers["Pragma"] == "no-cache" and resp.headers["Expires"] == "0"
    assert len(queue.jobs) == 1
    path, args, kwargs = queue.jobs[0]
    assert path == "foms.services.jobs.tasks.create_list_thumb_for_key" and args == (key, 640)
    assert kwargs["job_id"] == lt.list_thumb_job_id(key, 640)

    # 같은 key 의 320 은 640 자물쇠에 막히지 않는다(반대도 같다).
    assert client.get(_thumb(key), follow_redirects=False).status_code == 302
    assert [job[1] for job in queue.jobs] == [(key, 640), (key,)]
    assert len(queue.connection.store) == 2
    assert audit_calls == []


def test_640_route_same_gate_as_original(app, r2, queue):
    oid = _order().id
    key = f"orders/{oid}/as/c.jpg"
    r2.objects[lt.list_thumb_key(key, 640)] = b"x"
    anon = _client(app, None).get(_mid(key), follow_redirects=False)
    assert anon.status_code != 200 and not anon.headers.get("Location", "").startswith(_R2)
    staff = _client(app, _user())
    assert staff.get(_mid("random/bucket/x.png")).status_code == 403  # 행 없는 비정규 key
    assert staff.get(_mid(f"orders/{oid}/as/plan.pdf")).status_code == 404
    assert staff.get(_mid(f"orders/{oid}/as/sthumb640_c.jpg.jpg")).status_code == 404  # 640 의 640 없음
    assert staff.get(_thumb(f"orders/{oid}/as/sthumb640_c.jpg.jpg")).status_code == 404
    assert queue.jobs == []


def test_local_storage_640_stored_then_original(app, tmp_path, monkeypatch):
    local = SimpleNamespace(storage_type="local", upload_folder=str(tmp_path))
    monkeypatch.setattr(file_routes, "get_storage", lambda: local)
    order = _order()
    key = f"orders/{order.id}/as/g.png"
    (tmp_path / f"orders/{order.id}/as").mkdir(parents=True)
    (tmp_path / key).write_bytes(b"original-bytes")
    (tmp_path / lt.list_thumb_key(key)).write_bytes(b"small-320")
    client = _client(app, _user())
    first = client.get(_mid(key))
    assert first.data == b"original-bytes" and first.headers["Cache-Control"] == "no-store, max-age=0"
    (tmp_path / lt.list_thumb_key(key, 640)).write_bytes(b"mid-640")
    second = client.get(_mid(key))
    assert second.data == b"mid-640" and "immutable" in second.headers["Cache-Control"]


# ----------------------------------------------------------------------- 워커
def test_worker_640_long_edge_white_and_rotation():
    key = "orders/3/as/t.png"
    store = _FakeR2({key: _png(size=(3000, 1500), color=(0, 0, 0, 0))})
    assert lt.create_list_thumb(key, storage=store, size=640) == lt.RESULT_STORED
    assert store.puts == [lt.list_thumb_key(key, 640)]  # 320 저장본은 안 건드린다
    with Image.open(io.BytesIO(store.objects[lt.list_thumb_key(key, 640)])) as out:
        assert out.format == "JPEG" and out.size == (640, 320)
        assert all(c >= 250 for c in out.convert("RGB").getpixel((10, 10)))  # 투명 칸 = 흰색

    photo = "orders/3/as/phone.jpg"
    img = Image.new("RGB", (4032, 3024), (200, 30, 30))
    exif = img.getexif()
    exif[0x0112] = 6  # 90도 돌려서 보라
    raw = io.BytesIO()
    img.save(raw, "JPEG", exif=exif.tobytes())
    store = _FakeR2({photo: raw.getvalue()})
    assert lt.create_list_thumb(photo, storage=store, size=640) == lt.RESULT_STORED
    with Image.open(io.BytesIO(store.objects[lt.list_thumb_key(photo, 640)])) as out:
        assert out.size == (480, 640)  # 세운 사진 · 긴 변 640 — 2배 화면 240px 칸에 맞는다


def test_worker_640_skips_existing_small_and_bad_size():
    have = "orders/3/as/have.png"
    store = _FakeR2({have: _png(), lt.list_thumb_key(have, 640): b"old"})
    assert lt.create_list_thumb(have, storage=store, size=640) == lt.RESULT_EXISTS
    assert store.reads == []
    small = "orders/3/as/small.png"
    store = _FakeR2({small: _png(size=(300, 200))})
    lt.create_list_thumb(small, storage=store, size=640)
    with Image.open(io.BytesIO(store.objects[lt.list_thumb_key(small, 640)])) as out:
        assert out.size == (300, 200)  # 키우지 않는다
    big = "orders/3/as/big.png"
    store = _FakeR2({big: _png(size=(4001, 4001), color=0, mode="L")})
    assert lt.create_list_thumb(big, storage=store, size=640) == lt.RESULT_TOO_LARGE  # 16MP 상한 그대로
    assert lt.create_list_thumb(have, storage=_FakeR2({have: _png()}), size=1280) == lt.RESULT_NOT_IMAGE


def test_worker_task_old_one_arg_job_and_new_640(monkeypatch):
    """배포 전에 큐에 든 옛 작업(인자 1개)은 320 을 만든다. 새 작업 ``(key, 640)`` 은 640."""
    key = "orders/4/as/q.png"
    store = _FakeR2({key: _png(size=(2000, 1000))})
    monkeypatch.setattr(lt, "get_storage", lambda: store)
    assert tasks.create_list_thumb_for_key(key) == lt.RESULT_STORED
    assert tasks.create_list_thumb_for_key(key, 640) == lt.RESULT_STORED
    assert store.puts == [lt.list_thumb_key(key), lt.list_thumb_key(key, 640)]
    with Image.open(io.BytesIO(store.objects[lt.list_thumb_key(key)])) as out:
        assert out.size == (320, 160)
    with Image.open(io.BytesIO(store.objects[lt.list_thumb_key(key, 640)])) as out:
        assert out.size == (640, 320)


# ----------------------------------------------------------------------- 지우기 형제 둘
def test_storage_delete_removes_both_siblings_and_retries_640_failure(monkeypatch):
    store = _FakeR2()
    monkeypatch.setattr(handler_mod, "get_storage", lambda: store)
    handler_mod.handle_storage_delete(SimpleNamespace(source_domain="UPLOAD_TICKET", id=1,
                                                      payload={"object_key": "orders/5/as/a.jpg"}))
    assert store.deleted == ["orders/5/as/a.jpg", "orders/5/as/sthumb320_a.jpg.jpg",
                             "orders/5/as/sthumb640_a.jpg.jpg"]  # 없어도 성공

    failing = _FakeR2()
    failing.delete_file = lambda key: "sthumb640_" not in key
    monkeypatch.setattr(handler_mod, "get_storage", lambda: failing)
    with pytest.raises(handler_mod.StorageDeleteError):
        handler_mod.handle_storage_delete(SimpleNamespace(source_domain="UPLOAD_TICKET", id=2,
                                                          payload={"object_key": "orders/5/as/b.jpg"}))
