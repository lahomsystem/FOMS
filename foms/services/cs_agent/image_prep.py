"""그림 준비 — 받기 전 거르기(꼴 · 바이트 · 가로세로) · Pillow 로 다시 보기 · 줄이기 · 얼굴 거르기 · PDF 쪽 상한(17.11 (a)).

모두 메모리에서만 한다 — 임시 파일 · 로그 · 예외 글에 바이트를 싣지 않는다(D89). 결과는 보낼 바이트(:class:`Prepared`) 또는
건너뜀 코드 하나다.

- **그림**: JPEG · PNG · WebP 만(HEIC · GIF · 동영상은 ``skipped_format``). 원본 :data:`MAX_BYTES` 넘음 · 픽셀
  :data:`MAX_PIXELS` 넘음은 ``skipped_size``(압축 폭탄 — 열기 전에 머리만 본다). JPEG 는 줄여 읽고(``draft``), 방향(EXIF)을
  바로잡고, 투명한 칸은 흰 바탕에 얹어(검은 칸이 되지 않게) 긴 변 :data:`LONG_EDGE` JPEG 로 다시 그린다 — 위치 정보 등 덧붙은
  칸은 이때 빠진다. 줄인 그림에서 얼굴을 세어 하나라도 있으면 ``skipped_face``, 거르기 고장이면 ``skipped_face_check``.
- **PDF(D96)**: 그대로 보낸다. 바이트 상한(패널) · 쪽 상한(패널, 처음 3쪽)을 넘으면 ``skipped_size`` · ``skipped_cap``. 쪽을
  자르지 않는다(새 패키지 — :mod:`.image_pdf`). 안의 그림에서 얼굴을 세고, 훑기를 못 하면 ``skipped_pdf``(막는 쪽).
"""

from __future__ import annotations

import hashlib
import io
from dataclasses import dataclass, field
from typing import Optional, Union

from foms.services.cs_agent.image_faces import FaceCheckError, count_faces
from foms.services.cs_agent.image_files import FileRef
from foms.services.cs_agent.image_pdf import PdfImage, scan_pdf

__all__ = [
    "IMAGE_TYPES", "LONG_EDGE", "MAX_BYTES", "MAX_PIXELS", "PDF_TYPE", "SKIP_CAP", "SKIP_FACE", "SKIP_FACE_CHECK",
    "SKIP_FORMAT", "SKIP_PDF", "SKIP_SIZE", "Prepared", "precheck", "prepare",
]

IMAGE_TYPES: dict[str, str] = {"image/jpeg": "JPEG", "image/jpg": "JPEG", "image/png": "PNG", "image/webp": "WEBP"}
PDF_TYPE = "application/pdf"
MAX_BYTES = 20 * 1024 * 1024  # 원본 20MB 넘으면 받지 않는다
MAX_PIXELS = 25_000_000  # 열어 보아 픽셀 2천 5백만이 넘으면 버린다
LONG_EDGE = 2000  # 시험과 같은 크기(Sonnet 계열 상한 2,576px 안)
JPEG_QUALITY = 90
SKIP_FORMAT, SKIP_SIZE, SKIP_CAP = "skipped_format", "skipped_size", "skipped_cap"
SKIP_FACE, SKIP_FACE_CHECK, SKIP_PDF = "skipped_face", "skipped_face_check", "skipped_pdf"
_PIL_FORMATS = frozenset(IMAGE_TYPES.values())


@dataclass(frozen=True)
class Prepared:
    """보낼 준비가 된 파일 하나 — 블록 꼴(image · document) · 바이트 · 크기 · 받은 바이트의 sha256. 바이트는 repr 에 없다."""

    ref: FileRef
    kind: str  # 'image' | 'document'
    media_type: str
    data: bytes = field(repr=False)
    sha256: str = ""
    width: int = 0
    height: int = 0
    pages: int = 0


def precheck(ref: FileRef, *, pdf_max_bytes: int) -> Optional[str]:
    """받기 전 — 글의 파일 칸(꼴 · 바이트 · 가로세로)으로 먼저 거른다. 통과면 ``None``."""
    if ref.content_type == PDF_TYPE:
        return SKIP_SIZE if ref.size > min(pdf_max_bytes, MAX_BYTES) else None
    if ref.content_type not in IMAGE_TYPES:
        return SKIP_FORMAT
    if ref.size > MAX_BYTES or ref.pixels > MAX_PIXELS:
        return SKIP_SIZE
    return None


def _bgr(image) -> object:
    """Pillow RGB 그림 → opencv BGR 배열(연속 메모리)."""
    import numpy as np  # noqa: PLC0415 — opencv 와 함께만 쓴다

    return np.ascontiguousarray(np.asarray(image)[:, :, ::-1])


def _faces(image) -> Optional[str]:
    """얼굴이 있으면 ``skipped_face``, 거르기 고장이면 ``skipped_face_check``, 없으면 ``None``."""
    try:
        return SKIP_FACE if count_faces(_bgr(image)) else None
    except FaceCheckError:
        return SKIP_FACE_CHECK


def _redraw(data: bytes) -> Union[str, tuple[bytes, int, int, object]]:
    """원본 → (JPEG 바이트, 가로, 세로, RGB 그림). 꼴 · 크기가 틀리면 건너뜀 코드."""
    from PIL import Image, ImageOps, UnidentifiedImageError  # noqa: PLC0415

    try:
        with Image.open(io.BytesIO(data)) as source:
            if source.format not in _PIL_FORMATS:
                return SKIP_FORMAT
            if source.width * source.height > MAX_PIXELS:
                return SKIP_SIZE
            if source.format == "JPEG":
                source.draft("RGB", (LONG_EDGE, LONG_EDGE))  # 줄여 읽기(메모리)
            image = ImageOps.exif_transpose(source)
            if image.mode in ("RGBA", "LA", "PA") or (image.mode == "P" and "transparency" in image.info):
                rgba = image.convert("RGBA")
                image = Image.new("RGB", rgba.size, (255, 255, 255))
                image.paste(rgba, mask=rgba.getchannel("A"))
            image = image.convert("RGB")
            image.thumbnail((LONG_EDGE, LONG_EDGE), Image.Resampling.LANCZOS)
            out = io.BytesIO()
            image.save(out, format="JPEG", quality=JPEG_QUALITY)
            return out.getvalue(), image.width, image.height, image
    except (UnidentifiedImageError, Image.DecompressionBombError):
        return SKIP_FORMAT
    except (OSError, ValueError, SyntaxError):  # 잘린 · 깨진 파일 — 꼴로 본다(글은 싣지 않는다)
        return SKIP_FORMAT


def _pdf_image_faces(image: PdfImage) -> int:
    """PDF 안 그림 하나의 얼굴 수(풀 수 없는 꼴이면 :class:`FaceCheckError`)."""
    import cv2  # noqa: PLC0415
    import numpy as np  # noqa: PLC0415

    try:
        if image.jpeg:
            pixels = cv2.imdecode(np.frombuffer(image.jpeg, dtype=np.uint8), cv2.IMREAD_COLOR)
        else:
            raw = np.frombuffer(image.raw, dtype=np.uint8)
            if image.bits == 1:
                raw = np.unpackbits(raw.reshape(image.height, -1), axis=1)[:, :image.width * image.components] * 255
            grid = raw.reshape(image.height, image.width, image.components)
            pixels = (cv2.cvtColor(grid, cv2.COLOR_GRAY2BGR) if image.components == 1
                      else np.ascontiguousarray(grid[:, :, 2::-1]) if image.components == 3
                      else np.ascontiguousarray(255 - grid[:, :, 2::-1]))  # CMYK 어림 — 얼굴 찾기에는 밝기 꼴이면 된다
    except cv2.error:
        raise FaceCheckError("pdf_image_decode") from None
    if pixels is None:
        raise FaceCheckError("pdf_image_decode")
    return count_faces(pixels)


def _prepare_pdf(ref: FileRef, data: bytes, digest: str, *, page_cap: int, pdf_max_bytes: int) -> Union[str, Prepared]:
    """PDF — 바이트 · 쪽 상한, 훑기(막는 쪽), 안 그림 얼굴 거르기."""
    if len(data) > min(pdf_max_bytes, MAX_BYTES):
        return SKIP_SIZE
    scan = scan_pdf(data)
    if scan.problem is not None:
        return SKIP_PDF
    if scan.pages > page_cap:
        return SKIP_CAP
    try:
        if any(_pdf_image_faces(image) for image in scan.images):
            return SKIP_FACE
    except (FaceCheckError, ValueError, ImportError):
        return SKIP_FACE_CHECK
    return Prepared(ref=ref, kind="document", media_type=PDF_TYPE, data=data, sha256=digest, pages=scan.pages)


def prepare(ref: FileRef, data: bytes, *, page_cap: int, pdf_max_bytes: int) -> Union[str, Prepared]:
    """받은 바이트 → 보낼 준비(:class:`Prepared`) 또는 건너뜀 코드. 바이트는 이 함수 밖으로 그대로 넘기지 않는다."""
    if len(data) > MAX_BYTES:
        return SKIP_SIZE
    digest = hashlib.sha256(data).hexdigest()
    if ref.content_type == PDF_TYPE:
        return _prepare_pdf(ref, data, digest, page_cap=page_cap, pdf_max_bytes=pdf_max_bytes)
    drawn = _redraw(data)
    if isinstance(drawn, str):
        return drawn
    jpeg, width, height, image = drawn
    skipped = _faces(image)
    if skipped is not None:
        return skipped
    return Prepared(ref=ref, kind="image", media_type="image/jpeg", data=jpeg, sha256=digest, width=width,
                    height=height)
