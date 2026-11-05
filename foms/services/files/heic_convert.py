"""아이폰 사진(HEIC/HEIF) → JPEG 변환 — 주문 첨부 · 협력사 사진 공용 (SPEC docs/specs/2026-11-04-heic-to-jpeg_SPEC.md).

Windows 크롬은 HEIC 를 띄우지 못해 사무실 PC 에서 사진이 깨져 보인다. 브라우저에서 바꾸면 사파리에서만 되므로
서버에서 바꾼다.

Pillow 전체에 ``register_heif_opener`` 를 걸지 않는다 — 다른 업로드의 받는 형식 규칙을 바꾸지 않게
``pillow_heif`` 로 직접 연다(공지 사진 ``foms/services/notices/images.py`` 와 같은 이유).
"""

from __future__ import annotations

import io
import os

import pillow_heif
from PIL import Image, ImageOps

__all__ = [
    "HEIC_EXTENSIONS",
    "HEIC_FAILED_MESSAGE",
    "HeicConvertError",
    "convert_upload_if_heic",
    "heic_to_jpeg",
    "is_heic_filename",
    "jpeg_filename_for",
    "upload_converting_heic",
]

#: 바꿀 대상 확장자(소문자, 점 없음).
HEIC_EXTENSIONS = frozenset({"heic", "heif"})
#: 바꾼 JPEG 의 긴 변 상한(사용자 결정 2026-11-04). 더 작은 사진은 크기를 그대로 둔다.
LONG_EDGE = 2560
JPEG_QUALITY = 85
#: 받는 원본 상한 — 주문 사진 업로드 상한(``get_erp_media_max_size``)과 같다.
MAX_BYTES = 20 * 1024 * 1024
MAX_PIXELS = 60_000_000


class HeicConvertError(ValueError):
    """HEIC 를 JPEG 로 바꾸지 못했다(깨진 파일 · 너무 큰 사진 · HEIC 가 아님)."""


def is_heic_filename(filename: object) -> bool:
    """파일 이름 확장자가 HEIC/HEIF 인지."""
    if not isinstance(filename, str) or "." not in filename:
        return False
    return filename.rsplit(".", 1)[1].strip().lower() in HEIC_EXTENSIONS


def jpeg_filename_for(filename: str) -> str:
    """``IMG_0001.HEIC`` → ``IMG_0001.jpg``. 확장자가 없으면 ``.jpg`` 를 붙인다."""
    base = os.path.splitext(filename or "")[0] or "photo"
    return f"{base}.jpg"


def heic_to_jpeg(data: bytes) -> bytes:
    """HEIC/HEIF 바이트 → JPEG 바이트.

    회전(EXIF) 을 반영해 바로 세우고, 긴 변을 :data:`LONG_EDGE` 까지 줄이고, 메타데이터(EXIF · GPS 위치)는 지운다.

    Raises:
        HeicConvertError: 비었거나 · 너무 크거나 · HEIC 가 아니거나 · 풀지 못한 경우.
    """
    if not data:
        raise HeicConvertError("empty")
    if len(data) > MAX_BYTES:
        raise HeicConvertError("too_large")
    try:
        if not pillow_heif.is_supported(data):
            raise HeicConvertError("not_heic")
        heif = pillow_heif.open_heif(data, convert_hdr_to_8bit=True)
        width, height = heif.size
        if width * height > MAX_PIXELS:
            raise HeicConvertError("too_many_pixels")
        image = heif.to_pillow()
        image = ImageOps.exif_transpose(image)
        if image.mode not in ("RGB", "L"):
            image = image.convert("RGB")
        image.thumbnail((LONG_EDGE, LONG_EDGE), Image.Resampling.LANCZOS)
        # 새 그림에 픽셀만 옮겨 EXIF · GPS · XMP 를 남기지 않는다.
        clean = Image.new(image.mode, image.size)
        clean.paste(image)
        out = io.BytesIO()
        clean.save(out, format="JPEG", quality=JPEG_QUALITY, optimize=True)
        return out.getvalue()
    except HeicConvertError:
        raise
    except (OSError, ValueError, SyntaxError, RuntimeError, Image.DecompressionBombError) as exc:
        raise HeicConvertError("decode_failed") from exc


def convert_upload_if_heic(file_obj, filename: str):
    """서버가 바이트를 직접 받는 업로드용 — HEIC 면 JPEG 로 바꿔 ``(stream, filename, size)`` 를 돌려준다.

    HEIC 가 아니면 ``(file_obj, filename, None)`` 를 그대로 돌려준다(크기는 부르는 쪽이 이미 안다).

    Raises:
        HeicConvertError: HEIC 인데 바꾸지 못한 경우(부르는 쪽이 400 으로 알린다).
    """
    if not is_heic_filename(filename):
        return file_obj, filename, None
    file_obj.seek(0)
    jpeg = heic_to_jpeg(file_obj.read())
    return io.BytesIO(jpeg), jpeg_filename_for(filename), len(jpeg)


def upload_converting_heic(storage, file_obj, filename: str, folder: str, size: int):
    """올리기 전에 HEIC 면 JPEG 로 바꾸고 ``storage.upload_file`` 한다. 반환 ``(result, filename, size)``.

    서버가 바이트를 직접 받는 업로드(주문 폼 업로드 · 협력사 파일 · 협력사 사진)가 같이 쓴다.

    Raises:
        HeicConvertError: HEIC 인데 바꾸지 못한 경우(올리지 않는다).
    """
    stream, name, converted_size = convert_upload_if_heic(file_obj, filename)
    result = storage.upload_file(stream, name, folder)
    return result, name, (converted_size if converted_size is not None else size)


#: 바꾸지 못했을 때 사용자에게 보일 문구.
HEIC_FAILED_MESSAGE = "아이폰 사진을 읽지 못했습니다. JPG 로 다시 올려 주세요."
