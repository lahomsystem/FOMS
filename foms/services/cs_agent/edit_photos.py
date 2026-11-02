"""[수정하기] 자세한 이유에 붙인 사진 — 서버가 다시 보는 것(꼴 · 크기 · 다시 그리기) · 저장소 key(설계서 17.6.1 (b)).

모두 메모리에서만 한다 — 임시 파일 · 로그 · 예외 글에 바이트를 싣지 않는다. 화면(브라우저)이 먼저 줄여 올리지만 서버는 믿지 않는다:

- **꼴**: 확장자 · Content-Type 이 아니라 **Pillow 로 열어** 판정한다 — JPEG · PNG · WebP 만. 이름만 바꾼 PDF · 글 파일은 열리지
  않아 ``photo_format``, HEIC(서버에 읽는 패키지 없음) · GIF 도 ``photo_format``.
- **크기**: 받은 바이트 :data:`MAX_BYTES`(5MB) 넘음 · 픽셀 :data:`MAX_PIXELS`(4천만 — 압축 폭탄) 넘음은 ``photo_size``(머리만 보고
  풀기 전에 막는다).
- **다시 그리기**: 방향(EXIF)을 바로잡은 뒤 새 그림으로 다시 저장한다 — EXIF · 위치 정보 · 숨은 덧붙임(뒤에 붙인 바이트 · 글 칸)이
  모두 빠진다. 투명 칸이 있으면 PNG, 아니면 JPEG. 긴 변은 :data:`LONG_EDGE` 아래로.
- **지문**: 받은 바이트의 sha256 — 같은 차례에 같은 사진 두 번 막기(:mod:`.edit_detail`).
- **key**: ``cs-agent/edit-photos/<차례 id>/<uuid>.<jpg|png>`` — 이름 · 상담 id · 파일 이름을 넣지 않는다(:func:`photo_key`).
"""

from __future__ import annotations

import hashlib
import io
import re
import uuid
from dataclasses import dataclass, field

__all__ = [
    "ERR_EMPTY", "ERR_FORMAT", "ERR_SIZE", "KEY_PATTERN", "KEY_PREFIX", "LONG_EDGE", "MAX_BYTES", "MAX_PHOTOS",
    "MAX_PIXELS", "PhotoError", "Redrawn", "photo_key", "redraw",
]

MAX_PHOTOS = 5  # 한 차례에 살아 있는 사진 상한
MAX_BYTES = 5 * 1024 * 1024  # 한 장 상한(화면이 줄인 뒤 — 서버가 다시 본다)
MAX_PIXELS = 40_000_000  # 열기 전에 머리로 보는 픽셀 상한(압축 폭탄 막기)
LONG_EDGE = 2048  # 화면이 줄이는 크기와 같다 — 더 크면 서버도 줄인다
JPEG_QUALITY = 88
KEY_PREFIX = "cs-agent/edit-photos"
#: 저장소 key 꼴 — 차례 id(숫자) · uuid(32 글자 16진) · 확장자뿐.
KEY_PATTERN = re.compile(r"cs-agent/edit-photos/[0-9]+/[0-9a-f]{32}\.(?:jpg|png)")
ERR_EMPTY, ERR_SIZE, ERR_FORMAT = "photo_empty", "photo_size", "photo_format"
_FORMATS = frozenset({"JPEG", "PNG", "WEBP"})
_ALPHA_MODES = frozenset({"RGBA", "LA", "PA"})


class PhotoError(ValueError):
    """받을 수 없는 사진 — :attr:`code` 만 싣는다(바이트 · 파일 이름 없음)."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class Redrawn:
    """다시 그린 사진 — 저장할 바이트 · 꼴 · 크기 · 받은 바이트의 sha256. 바이트는 repr 에 없다."""

    data: bytes = field(repr=False)
    content_type: str
    ext: str
    width: int
    height: int
    sha256: str


def photo_key(turn_id: int) -> str:
    """새 사진 저장소 key — 차례 id 와 새 uuid 만(확장자는 :func:`redraw` 결과로 붙인다)."""
    return f"{KEY_PREFIX}/{int(turn_id)}/{uuid.uuid4().hex}"


def _has_alpha(image) -> bool:
    """투명 칸이 있는 꼴인가(PNG · WebP 의 알파 · 팔레트 투명)."""
    return image.mode in _ALPHA_MODES or (image.mode == "P" and "transparency" in image.info)


def _encode(image) -> tuple[bytes, str, str]:
    """새 그림 → (바이트, Content-Type, 확장자). 덧붙은 칸(``info`` — EXIF · 글 칸)은 비우고 저장한다."""
    from PIL import Image  # noqa: PLC0415

    alpha = _has_alpha(image)
    clean = image.convert("RGBA" if alpha else "RGB")
    clean.thumbnail((LONG_EDGE, LONG_EDGE), Image.Resampling.LANCZOS)
    clean.info = {}
    out = io.BytesIO()
    if alpha:
        clean.save(out, format="PNG", optimize=True)
        return out.getvalue(), "image/png", "png"
    clean.save(out, format="JPEG", quality=JPEG_QUALITY)
    return out.getvalue(), "image/jpeg", "jpg"


def redraw(data: bytes) -> Redrawn:
    """받은 바이트 → 다시 그린 사진. 받을 수 없으면 :class:`PhotoError`(``photo_empty`` · ``photo_size`` · ``photo_format``)."""
    from PIL import Image, ImageOps, UnidentifiedImageError  # noqa: PLC0415

    if not data:
        raise PhotoError(ERR_EMPTY)
    if len(data) > MAX_BYTES:
        raise PhotoError(ERR_SIZE)
    digest = hashlib.sha256(data).hexdigest()
    try:
        with Image.open(io.BytesIO(data)) as source:
            if source.format not in _FORMATS:
                raise PhotoError(ERR_FORMAT)
            if source.width * source.height > MAX_PIXELS:
                raise PhotoError(ERR_SIZE)
            image = ImageOps.exif_transpose(source)
            body, content_type, ext = _encode(image)
    except PhotoError:
        raise
    except (UnidentifiedImageError, Image.DecompressionBombError):
        raise PhotoError(ERR_FORMAT) from None
    except (OSError, ValueError, SyntaxError):  # 잘린 · 깨진 파일 — 꼴로 본다(글은 싣지 않는다)
        raise PhotoError(ERR_FORMAT) from None
    if len(body) > MAX_BYTES:
        raise PhotoError(ERR_SIZE)
    with Image.open(io.BytesIO(body)) as check:
        width, height = check.size
    return Redrawn(data=body, content_type=content_type, ext=ext, width=width, height=height, sha256=digest)
