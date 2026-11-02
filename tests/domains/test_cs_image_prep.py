"""그림 준비(설계서 17.11 (a)) — 받기 전 거르기 · Pillow 다시 보기 · 긴 변 2,000 JPEG · 방향 · 투명 칸 · 덧붙은 칸 빠짐 ·
얼굴 거르기 막는 쪽(얼굴 1 → 안 보냄 · 0 → 보냄 · 고장 → 안 보냄) · 진짜 YuNet(합성 도면 얼굴 0 · 모델 파일 없음 → 막힘) ·
PDF 쪽 상한 · 바이트 상한 · 잠긴 PDF · 못 푸는 그림 · 안 그림 얼굴.

그림은 시험 안에서 Pillow 로 그린다(저장소에 그림 파일 · 얼굴 사진 없음).
"""

from __future__ import annotations

import io
import zlib

import pytest
from PIL import Image

from foms.services.cs_agent import image_faces as faces
from foms.services.cs_agent import image_pdf
from foms.services.cs_agent import image_prep as prep
from foms.services.cs_agent.image_files import FileRef, parse_files
from tests.support.cs_image_support import encoded, pdf_bytes, plan_image

PAGE_CAP, PDF_MAX = 3, 10 * 1024 * 1024


def ref(content_type="image/jpeg", size=1000, width=1600, height=1200):
    return FileRef("m-1", 0, content_type, size, width, height, key="synthetic/key")


def run(data, content_type="image/jpeg"):
    return prep.prepare(ref(content_type, len(data)), data, page_cap=PAGE_CAP, pdf_max_bytes=PDF_MAX)


@pytest.fixture
def no_faces(monkeypatch):
    calls = []
    monkeypatch.setattr(prep, "count_faces", lambda image: calls.append(image.shape) or 0)
    return calls


# ── 받기 전 거르기 ───────────────────────────────────────────────────────
@pytest.mark.parametrize("content_type,size,pixels,code", [
    ("image/heic", 1000, (100, 100), prep.SKIP_FORMAT), ("image/gif", 1000, (100, 100), prep.SKIP_FORMAT),
    ("video/mp4", 1000, (100, 100), prep.SKIP_FORMAT), ("image/jpeg", 21 * 1024 * 1024, (100, 100), prep.SKIP_SIZE),
    ("image/png", 1000, (6000, 5000), prep.SKIP_SIZE), ("application/pdf", 11 * 1024 * 1024, (0, 0), prep.SKIP_SIZE),
    ("image/jpeg", 1000, (4000, 3000), None), ("image/webp", 1000, (0, 0), None), ("application/pdf", 1000, (0, 0), None),
])
def test_the_file_fields_are_checked_before_download(content_type, size, pixels, code):
    assert prep.precheck(ref(content_type, size, *pixels), pdf_max_bytes=PDF_MAX) == code


def test_file_fields_keep_the_key_out_of_repr_and_skip_keyless_items():
    item = {"files": [{"key": "pub-file/1/a.jpg", "contentType": "IMAGE/JPEG", "size": 9, "width": 3, "height": 2,
                       "name": "합성 이름.jpg"}, {"id": "no-key"}, "broken"]}
    (one,) = parse_files("m-9", item)
    assert (one.message_id, one.file_index, one.content_type, one.size, one.pixels) == ("m-9", 0, "image/jpeg", 9, 6)
    assert "pub-file" not in repr(one) and "합성 이름" not in repr(one)  # 파일 key · 이름은 repr · 로그에 없다


# ── Pillow 다시 보기 · 줄이기 ────────────────────────────────────────────
def test_a_big_plan_is_redrawn_as_a_2000px_jpeg_without_extra_fields(no_faces):
    exif = Image.Exif()
    exif[0x010F] = "synthetic-camera"
    data = encoded(plan_image(4000, 3000), "JPEG", exif=exif.tobytes())
    got = run(data)
    assert (got.kind, got.media_type, max(got.width, got.height)) == ("image", "image/jpeg", prep.LONG_EDGE)
    with Image.open(io.BytesIO(got.data)) as again:
        assert again.format == "JPEG" and max(again.size) == 2000 and not again.getexif()  # 덧붙은 칸이 빠졌다
    assert len(got.sha256) == 64 and no_faces == [(1500, 2000, 3)]  # 줄인 그림에서 얼굴을 센다


def test_exif_orientation_is_applied_before_resizing(no_faces):
    exif = Image.Exif()
    exif[0x0112] = 6  # 90도 돌려 보기
    got = run(encoded(plan_image(1200, 800), "JPEG", exif=exif.tobytes()))
    assert (got.width, got.height) == (800, 1200)


def test_transparent_png_pixels_become_white_not_black(no_faces):
    image = Image.new("RGBA", (300, 200), (0, 0, 0, 0))
    got = run(encoded(image, "PNG"), "image/png")
    with Image.open(io.BytesIO(got.data)) as again:
        assert again.convert("RGB").getpixel((150, 100))[0] > 240


def test_formats_and_pixel_bombs_are_refused_after_opening(no_faces):
    assert run(encoded(plan_image(100, 100), "GIF"), "image/jpeg") == prep.SKIP_FORMAT  # 글은 JPEG 라 해도 실제 꼴로
    assert run(b"not an image") == prep.SKIP_FORMAT
    big = Image.new("L", (5001, 5001))
    assert run(encoded(big, "PNG", compress_level=9), "image/png") == prep.SKIP_SIZE  # 열기 전에 머리로 거름
    assert run(b"x" * (prep.MAX_BYTES + 1)) == prep.SKIP_SIZE
    assert no_faces == []  # 거른 그림은 얼굴 거르기 · 모델로 가지 않는다


# ── 얼굴 거르기(막는 쪽) ─────────────────────────────────────────────────
def test_one_face_blocks_zero_passes_and_a_broken_filter_blocks(monkeypatch):
    data = encoded(plan_image(800, 600))
    monkeypatch.setattr(prep, "count_faces", lambda image: 1)
    assert run(data) == prep.SKIP_FACE
    monkeypatch.setattr(prep, "count_faces", lambda image: 0)
    assert isinstance(run(data), prep.Prepared)

    def broken(image):
        raise faces.FaceCheckError("detect_failed")

    monkeypatch.setattr(prep, "count_faces", broken)
    assert run(data) == prep.SKIP_FACE_CHECK  # 거르기가 고장이어도 보내지 않는다


def test_real_yunet_sees_no_face_in_a_synthetic_plan():
    pytest.importorskip("cv2")
    got = run(encoded(plan_image(1600, 1200)))
    assert isinstance(got, prep.Prepared)  # 합성 도면은 얼굴 0 — 진짜 모델 · opencv 길
    assert faces.MODEL_PATH.is_file() and faces.MODEL_PATH.stat().st_size > 200_000
    assert (faces.MODEL_PATH.parent / "YUNET_LICENSE.txt").read_text(encoding="utf-8").count("MIT License") == 1


def test_a_missing_model_file_blocks_the_image(monkeypatch, tmp_path):
    pytest.importorskip("cv2")
    monkeypatch.setattr(faces, "MODEL_PATH", tmp_path / "missing.onnx")
    assert run(encoded(plan_image(800, 600))) == prep.SKIP_FACE_CHECK
    with pytest.raises(faces.FaceCheckError):
        faces.count_faces(__import__("numpy").zeros((10, 10, 3), dtype="uint8"))


# ── PDF(D96) ─────────────────────────────────────────────────────────────
def test_a_short_pdf_is_sent_as_is_as_a_document(no_faces):
    data = pdf_bytes(2)
    got = run(data, "application/pdf")
    assert (got.kind, got.media_type, got.pages, got.data) == ("document", "application/pdf", 2, data)


def test_pdf_page_cap_byte_cap_and_locked_pdfs(no_faces):
    assert run(pdf_bytes(PAGE_CAP + 1), "application/pdf") == prep.SKIP_CAP  # 자르지 않는다 — 보내지 않는다
    assert isinstance(run(pdf_bytes(PAGE_CAP), "application/pdf"), prep.Prepared)
    assert prep.prepare(ref("application/pdf"), pdf_bytes(1), page_cap=3, pdf_max_bytes=100) == prep.SKIP_SIZE
    assert run(pdf_bytes(1, encrypt=True), "application/pdf") == prep.SKIP_PDF
    assert run(b"%PDF-1.7\nno pages here", "application/pdf") == prep.SKIP_PDF  # 쪽 수를 못 세면 막는다
    assert run(encoded(plan_image(100, 100)), "application/pdf") == prep.SKIP_PDF


def test_pdf_page_count_reads_the_page_tree_inside_an_object_stream():
    assert image_pdf.scan_pdf(pdf_bytes(5, object_stream=True)).pages == 5
    assert image_pdf.page_count(b"<< /Type /Pages /Count 7 /Kids [] >> << /Type /Page >>") == 7


def test_images_inside_a_pdf_go_through_the_face_filter(monkeypatch):
    jpeg = encoded(plan_image(64, 64))
    data = pdf_bytes(1, image_jpeg=jpeg)
    seen = []
    monkeypatch.setattr(prep, "count_faces", lambda pixels: seen.append(pixels.shape) or 1)
    assert run(data, "application/pdf") == prep.SKIP_FACE and seen == [(64, 64, 3)]
    monkeypatch.setattr(prep, "count_faces", lambda pixels: 0)
    assert isinstance(run(data, "application/pdf"), prep.Prepared)
    unknown_filter = pdf_bytes(1, image_jpeg=b"\x00" * 64, image_filter="/JPXDecode")
    assert run(unknown_filter, "application/pdf") == prep.SKIP_PDF  # 못 푸는 그림 — 확인 못 하면 보내지 않는다


def test_flate_rgb_images_inside_a_pdf_are_unpacked_for_the_face_filter(monkeypatch):
    raw = plan_image(40, 30).tobytes()  # RGB 8비트 픽셀 그대로
    data = pdf_bytes(1, image_jpeg=zlib.compress(raw), image_filter="/FlateDecode", image_size=(40, 30))
    seen = []
    monkeypatch.setattr(prep, "count_faces", lambda pixels: seen.append(pixels.shape) or 0)
    assert isinstance(run(data, "application/pdf"), prep.Prepared) and seen == [(30, 40, 3)]
    broken = pdf_bytes(1, image_jpeg=zlib.compress(raw[:-5]), image_filter="/FlateDecode", image_size=(40, 30))
    assert run(broken, "application/pdf") == prep.SKIP_PDF  # 크기가 안 맞는 픽셀 — 막는다
