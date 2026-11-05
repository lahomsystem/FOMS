"""아이폰 사진(HEIC) → JPEG 변환 계약 (SPEC docs/specs/2026-11-04-heic-to-jpeg_SPEC.md)."""

from __future__ import annotations

import io
import itertools
from pathlib import Path

import pillow_heif
import pytest
from PIL import Image

import foms.services.order_attachment_thumbnail as thumb_mod
from db import db_session
from foms.services import order_attachment_heic as heic_job
from foms.services.files.heic_convert import (
    LONG_EDGE,
    HeicConvertError,
    convert_upload_if_heic,
    heic_to_jpeg,
    is_heic_filename,
    jpeg_filename_for,
)
from models import DomainSideEffectOutbox, Order, OrderAttachment, OrderEvent

ROOT = Path(__file__).resolve().parents[2]
_counter = itertools.count(1)


def _heic_bytes(size=(64, 32), color=(200, 10, 10), exif: bytes | None = None) -> bytes:
    image = Image.new("RGB", size, color)
    heif = pillow_heif.from_pillow(image)
    out = io.BytesIO()
    kwargs = {"quality": 80}
    if exif is not None:
        kwargs["exif"] = exif
    heif.save(out, **kwargs)
    return out.getvalue()


def _exif_with_gps_and_rotation() -> bytes:
    exif = Image.Exif()
    exif[0x0112] = 6  # Orientation: 90도 돌려서 봐야 함
    exif[0x8825] = {1: "N", 2: (37.0, 30.0, 0.0)}  # GPSInfo
    return exif.tobytes()


# --- 변환 함수 -------------------------------------------------------------


def test_heic_to_jpeg_returns_jpeg_without_metadata() -> None:
    jpeg = heic_to_jpeg(_heic_bytes(size=(80, 40), exif=_exif_with_gps_and_rotation()))
    with Image.open(io.BytesIO(jpeg)) as img:
        assert img.format == "JPEG"
        # 회전 표시(6)를 반영해 세운다 — 가로 80×40 이 세로 40×80 이 된다.
        assert img.size == (40, 80)
        exif = img.getexif()
        assert 0x8825 not in exif  # GPS 위치 없음
        assert 0x0112 not in exif


def test_heic_to_jpeg_limits_long_edge() -> None:
    jpeg = heic_to_jpeg(_heic_bytes(size=(LONG_EDGE + 640, 1000)))
    with Image.open(io.BytesIO(jpeg)) as img:
        assert max(img.size) == LONG_EDGE


def test_heic_to_jpeg_keeps_small_photo_size() -> None:
    jpeg = heic_to_jpeg(_heic_bytes(size=(120, 90)))
    with Image.open(io.BytesIO(jpeg)) as img:
        assert img.size == (120, 90)


@pytest.mark.parametrize("data", [b"", b"not an image at all", b"\x00" * 64])
def test_heic_to_jpeg_rejects_non_heic(data: bytes) -> None:
    with pytest.raises(HeicConvertError):
        heic_to_jpeg(data)


def test_heic_to_jpeg_rejects_jpeg_input() -> None:
    out = io.BytesIO()
    Image.new("RGB", (10, 10)).save(out, format="JPEG")
    with pytest.raises(HeicConvertError):
        heic_to_jpeg(out.getvalue())


def test_filename_helpers() -> None:
    assert is_heic_filename("IMG_0001.HEIC")
    assert is_heic_filename("a/b/c.heif")
    assert not is_heic_filename("photo.jpg")
    assert not is_heic_filename("heic")
    assert not is_heic_filename(None)
    assert jpeg_filename_for("IMG_0001.HEIC") == "IMG_0001.jpg"
    assert jpeg_filename_for("") == "photo.jpg"


def test_convert_upload_if_heic_passes_other_files_through() -> None:
    stream = io.BytesIO(b"jpeg-bytes")
    out, name, size = convert_upload_if_heic(stream, "a.jpg")
    assert out is stream and name == "a.jpg" and size is None


def test_convert_upload_if_heic_converts() -> None:
    out, name, size = convert_upload_if_heic(io.BytesIO(_heic_bytes()), "IMG_1.heic")
    assert name == "IMG_1.jpg"
    assert size == len(out.getvalue())
    with Image.open(out) as img:
        assert img.format == "JPEG"


def test_heic_module_does_not_register_global_opener() -> None:
    """Pillow 전체에 HEIF opener 를 걸면 다른 업로드의 받는 형식 규칙이 바뀐다."""
    text = (ROOT / "foms/services/files/heic_convert.py").read_text(encoding="utf-8")
    assert "register_heif_opener(" not in text


# --- 받는 형식 계약 ----------------------------------------------------------


def test_order_attachment_policy_accepts_heic() -> None:
    from foms.api.files.common import allowed_erp_attachment_file, get_erp_media_max_size
    from foms.services.files.upload_policy import DIRECT_UPLOAD_ALLOWED_CONTENT_TYPES
    from foms.services.storage import get_storage

    storage = get_storage()
    for name in ("IMG_1.HEIC", "IMG_2.heif"):
        assert allowed_erp_attachment_file(name, "measurement")
        assert get_erp_media_max_size(name) == 20 * 1024 * 1024
        assert storage.get_file_type(name) == "image"
        assert storage._get_content_type(name) in DIRECT_UPLOAD_ALLOWED_CONTENT_TYPES


def test_upload_paths_convert_heic_before_storing() -> None:
    """서버가 바이트를 직접 받는 세 경로는 올리기 전에 바꾼다."""
    order_routes = (ROOT / "foms/api/files/order_routes.py").read_text(encoding="utf-8")
    partner = (ROOT / "foms/api/partner/__init__.py").read_text(encoding="utf-8")
    assert "convert_upload_if_heic(file, file.filename)" in order_routes
    assert "storage.upload_file(upload_stream, filename, folder)" in order_routes
    assert partner.count("upload_converting_heic(storage,") == 2
    assert "storage.upload_file(file, file.filename" not in partner
    assert "storage.upload_file(f, f.filename" not in partner


def test_direct_upload_schedules_heic_conversion_and_returns_signed_type() -> None:
    direct = (ROOT / "foms/api/files/direct_upload.py").read_text(encoding="utf-8")
    assert "schedule_order_attachment_post_upload(attachment.id, storage_key)" in direct
    assert "is_heic_filename(storage_key)" in direct
    assert direct.count('"content_type": ct,') == 2
    runtime = (ROOT / "static/js/runtime/upload-progress.js").read_text(encoding="utf-8")
    assert "session.content_type || entry.file.type" in runtime


# --- 주문 첨부 백그라운드 변환 ----------------------------------------------


class FakeStorage:
    storage_type = "r2"

    def __init__(self, files: dict[str, bytes], *, fail_upload: bool = False):
        self.files = dict(files)
        self.fail_upload = fail_upload
        self.deleted: list[str] = []

    def read_file_bytes(self, key):
        return self.files.get(key)

    def upload_file(self, file_obj, filename, folder="uploads"):
        if self.fail_upload:
            return {"success": False}
        key = f"{folder}/conv_{filename}"
        file_obj.seek(0)
        self.files[key] = file_obj.read()
        return {"success": True, "key": key}

    def delete_file(self, key):
        self.deleted.append(key)
        self.files.pop(key, None)
        return True


@pytest.fixture
def scheduled_thumbs(monkeypatch):
    calls: list[tuple[int, str]] = []
    monkeypatch.setattr(thumb_mod, "schedule_order_attachment_thumbnail_generation",
                        lambda aid, key: calls.append((aid, key)))
    return calls


def _make_heic_attachment(app, *, filename="IMG_7.HEIC"):
    with app.app_context():
        order = Order(received_date="2026-11-04", customer_name="heic", phone="010-0000-0000",
                      address="서울시", product="붙박이장", status="RECEIVED")
        db_session.add(order)
        db_session.commit()
        n = next(_counter)
        key = f"orders/{order.id}/attachments/20261104_{n}_{filename}"
        att = OrderAttachment(order_id=order.id, filename=filename, file_type="image", category="measurement",
                              file_size=1234, storage_key=key, thumbnail_key=None)
        db_session.add(att)
        db_session.commit()
        return order.id, att.id, key


def test_background_conversion_swaps_key_and_schedules_old_delete(app, scheduled_thumbs) -> None:
    order_id, att_id, key = _make_heic_attachment(app)
    storage = FakeStorage({key: _heic_bytes()})
    with app.app_context():
        result = heic_job.convert_order_attachment_heic(att_id, key, db=db_session, storage=storage)
        assert result == heic_job.CONVERTED
        db_session.expire_all()
        att = db_session.get(OrderAttachment, att_id)
        assert att.filename == "IMG_7.jpg"
        assert att.storage_key == f"orders/{order_id}/attachments/conv_IMG_7.jpg"
        assert att.file_size == len(storage.files[att.storage_key])
        assert att.thumbnail_key is None
        with Image.open(io.BytesIO(storage.files[att.storage_key])) as img:
            assert img.format == "JPEG"

        event = (db_session.query(OrderEvent)
                 .filter(OrderEvent.order_id == order_id, OrderEvent.event_type == "ATTACHMENT_META_UPDATED")
                 .one())
        assert event.payload["converted_from"] == key
        assert event.payload["change"] == "heic_to_jpeg"

        rows = db_session.query(DomainSideEffectOutbox).filter(
            DomainSideEffectOutbox.effect_type == "STORAGE_DELETE",
            DomainSideEffectOutbox.order_event_id == event.id,
        ).all()
        assert [r.payload["object_key"] for r in rows] == [key]
    # 원본은 바로 지우지 않는다(지연 삭제 길로만).
    assert storage.deleted == []
    assert scheduled_thumbs == [(att_id, f"orders/{order_id}/attachments/conv_IMG_7.jpg")]


def test_background_conversion_skips_when_key_changed(app, scheduled_thumbs) -> None:
    _order_id, att_id, key = _make_heic_attachment(app)
    storage = FakeStorage({key: _heic_bytes()})
    with app.app_context():
        result = heic_job.convert_order_attachment_heic(att_id, key + ".old.heic", db=db_session, storage=storage)
    assert result in (heic_job.SKIPPED, heic_job.FAILED)
    assert scheduled_thumbs == []


def test_background_conversion_skips_deleted_attachment_and_cleans_new_file(app, scheduled_thumbs) -> None:
    import datetime

    _order_id, att_id, key = _make_heic_attachment(app)
    storage = FakeStorage({key: _heic_bytes()})
    with app.app_context():
        att = db_session.get(OrderAttachment, att_id)
        att.deleted_at = datetime.datetime(2026, 11, 4)
        db_session.commit()
        result = heic_job.convert_order_attachment_heic(att_id, key, db=db_session, storage=storage)
        assert result == heic_job.SKIPPED
        db_session.expire_all()
        from foms.services.attachment_visibility import include_deleted

        att = include_deleted(db_session.query(OrderAttachment).filter(OrderAttachment.id == att_id)).one()
        assert att.storage_key == key
    assert list(storage.files) == [key]  # 새 JPEG 를 만들지 않았다
    assert scheduled_thumbs == []


def test_background_conversion_keeps_heic_when_decode_fails(app, scheduled_thumbs) -> None:
    _order_id, att_id, key = _make_heic_attachment(app)
    storage = FakeStorage({key: b"broken"})
    with app.app_context():
        assert heic_job.convert_order_attachment_heic(att_id, key, db=db_session, storage=storage) == heic_job.FAILED
        db_session.expire_all()
        assert db_session.get(OrderAttachment, att_id).storage_key == key
    assert scheduled_thumbs == []


def test_background_conversion_keeps_heic_when_upload_fails(app, scheduled_thumbs) -> None:
    _order_id, att_id, key = _make_heic_attachment(app)
    storage = FakeStorage({key: _heic_bytes()}, fail_upload=True)
    with app.app_context():
        assert heic_job.convert_order_attachment_heic(att_id, key, db=db_session, storage=storage) == heic_job.FAILED
        db_session.expire_all()
        assert db_session.get(OrderAttachment, att_id).storage_key == key


def test_post_upload_routes_heic_to_conversion(monkeypatch) -> None:
    conv: list = []
    thumbs: list = []
    monkeypatch.setattr(heic_job, "schedule_order_attachment_heic_conversion", lambda a, k: conv.append((a, k)))
    monkeypatch.setattr(thumb_mod, "schedule_order_attachment_thumbnail_generation", lambda a, k: thumbs.append((a, k)))
    heic_job.schedule_order_attachment_post_upload(1, "orders/1/attachments/a.HEIC")
    heic_job.schedule_order_attachment_post_upload(2, "orders/1/attachments/b.jpg")
    assert conv == [(1, "orders/1/attachments/a.HEIC")]
    assert thumbs == [(2, "orders/1/attachments/b.jpg")]
