"""공지 사진 — 받기(다시 그리기) · 저장소 key · 보여 줄 주소(설계서 2026-11-02-foms-notices §8).

- **받기**: 확장자가 아니라 Pillow 로 열어 판정한다 — JPEG(MPO 포함) · PNG · WebP · HEIC/HEIF(아이폰 원본, ``pillow-heif``
  가 Pillow 에 여는 길을 더한다 — 사용자 요청 2026-11-02). 받은 바이트
  :data:`MAX_BYTES`(15MB) · 픽셀 :data:`MAX_PIXELS`(압축 폭탄) 넘음도 거절.
- **다시 그리기**: 방향(EXIF)을 바로잡고 긴 변 :data:`LONG_EDGE` 로 줄인 본 + 긴 변 :data:`THUMB_EDGE` 썸네일. EXIF · 위치 정보는
  빠진다. 투명 칸이 있으면 PNG, 아니면 JPEG.
- **key**: ``notices/images/<YYYYMM>/<uuid 32자>.<jpg|png>`` · 썸네일 ``..._thumb.<같은 확장자>`` — 파일 이름을 key 에 넣지 않는다.
  공지 페이로드는 이 꼴의 key 만 받는다(:data:`KEY_RE` — 남의 파일 key 끼워 넣기 금지).
- **보기**: 받는 사람은 ``/api/notices/<공지 id>/images/<차례>``(받는 사람 판정 뒤), 관리자는 ``/api/admin/notices/images/file?key=``
  (아직 저장 안 한 사진 · 지운 공지). 클라우드면 짧은 서명 주소로 302, 로컬(개발)이면 바이트를 바로 준다.

모두 메모리에서만 한다. 저장소는 :func:`foms.services.storage.get_storage` — 시험은 ``store`` 인자로 바꾼다.
"""
from __future__ import annotations

import datetime
import io
import os
import re
import uuid
from typing import Any, Optional
from urllib.parse import quote

from PIL import Image, ImageOps, UnidentifiedImageError
import pillow_heif

from foms.services.datetime_kst import now_utc_naive
from foms.services.storage import get_storage

__all__ = [
    "IMAGE_EXTS", "KEY_PREFIX", "KEY_RE", "LONG_EDGE", "MAX_BYTES", "MAX_IMAGES", "MAX_PIXELS", "NAME_MAX",
    "NoticeImageError", "THUMB_EDGE", "THUMB_RE", "admin_file_url", "admin_items", "clean_name", "image_target", "redraw",
    "store_image", "thumb_key_for", "viewer_items",
]

MAX_IMAGES = 5
MAX_BYTES = 15 * 1024 * 1024
MAX_PIXELS = 60_000_000
LONG_EDGE = 2000
THUMB_EDGE = 480
JPEG_QUALITY = 85
NAME_MAX = 120
#: 파일 고르기 · 끌어놓기에서 받는 확장자(HEIC · HEIF 는 JPEG/PNG 로 다시 그려 저장한다).
IMAGE_EXTS = ("jpg", "jpeg", "png", "webp", "heic", "heif")
KEY_PREFIX = "notices/images"
KEY_RE = re.compile(r"notices/images/[0-9]{6}/[0-9a-f]{32}\.(?:jpg|png)")
THUMB_RE = re.compile(r"notices/images/[0-9]{6}/[0-9a-f]{32}_thumb\.(?:jpg|png)")
SIGNED_URL_SECONDS = 600

_FORMATS = frozenset({"JPEG", "MPO", "PNG", "WEBP"})
_ALPHA_MODES = frozenset({"RGBA", "LA", "PA"})
_CONTENT_TYPES = {"jpg": "image/jpeg", "png": "image/png"}

ERR_EMPTY = "사진 파일이 비어 있습니다."
ERR_SIZE = "사진은 한 장에 15MB 까지 올릴 수 있어요."
ERR_PIXELS = "사진이 너무 큽니다. 크기를 줄여 다시 올려 주세요."
ERR_FORMAT = "JPG · PNG · WEBP · HEIC 사진만 올릴 수 있어요."
ERR_STORE = "사진을 저장하지 못했습니다. 잠시 뒤 다시 해 주세요."


class NoticeImageError(ValueError):
    """받을 수 없는 사진 — ``str(err)`` 가 화면 문구(바이트 · 파일 이름 없음)."""


def _ext_of(filename: Any) -> str:
    name = str(filename or "")
    return name.rsplit(".", 1)[-1].strip().lower() if "." in name else ""


def clean_name(filename: Any) -> str:
    """보여 줄 파일 이름 — 경로 · 제어 문자를 빼고 :data:`NAME_MAX` 자까지."""
    base = os.path.basename(str(filename or "").replace("\\", "/")).strip()
    base = "".join(ch for ch in base if ch.isprintable())
    return base[:NAME_MAX] or "사진"


def _has_alpha(image: Any) -> bool:
    return image.mode in _ALPHA_MODES or (image.mode == "P" and "transparency" in image.info)


def _encode(image: Any, edge: int, alpha: bool) -> bytes:
    clean = image.convert("RGBA" if alpha else "RGB")
    clean.thumbnail((edge, edge), Image.Resampling.LANCZOS)
    clean.info = {}
    out = io.BytesIO()
    if alpha:
        clean.save(out, format="PNG", optimize=True)
    else:
        clean.save(out, format="JPEG", quality=JPEG_QUALITY, optimize=True)
    return out.getvalue()


_HEIF_MARK = "foms_heif"


def _open(data: bytes) -> Any:
    """Pillow 로 연다. Pillow 가 모르는 HEIC/HEIF(아이폰 원본)면 ``pillow_heif`` 로 풀어 Pillow 그림으로 바꾼다.

    ``register_heif_opener`` 로 Pillow 전체에 등록하지 않는다 — 다른 업로드(CS 상담 사진 등)의 받는 형식 규칙을 바꾸지 않게
    공지 사진만 이 길로 연다.
    """
    try:
        return Image.open(io.BytesIO(data))
    except UnidentifiedImageError:
        if not pillow_heif.is_supported(data):
            raise
        heif = pillow_heif.open_heif(data, convert_hdr_to_8bit=True)
        if heif.size[0] * heif.size[1] > MAX_PIXELS:
            raise NoticeImageError(ERR_PIXELS) from None
        image = heif.to_pillow()
        image.info[_HEIF_MARK] = True
        return image


def redraw(data: bytes, filename: Any = "") -> dict[str, Any]:
    """받은 바이트 → ``{main, thumb, ext, content_type, width, height}``. 받을 수 없으면 :class:`NoticeImageError`."""
    if not data:
        raise NoticeImageError(ERR_EMPTY)
    if len(data) > MAX_BYTES:
        raise NoticeImageError(ERR_SIZE)
    try:
        with _open(data) as source:
            if source.format not in _FORMATS and not source.info.get(_HEIF_MARK):
                raise NoticeImageError(ERR_FORMAT)
            if source.width * source.height > MAX_PIXELS:
                raise NoticeImageError(ERR_PIXELS)
            if source.format in ("JPEG", "MPO"):
                source.draft("RGB", (LONG_EDGE, LONG_EDGE))  # 큰 사진은 줄인 크기로 바로 푼다(메모리 절약)
            image = ImageOps.exif_transpose(source)
            alpha = _has_alpha(image)
            main = _encode(image, LONG_EDGE, alpha)
            thumb = _encode(image, THUMB_EDGE, alpha)
    except NoticeImageError:
        raise
    except (UnidentifiedImageError, Image.DecompressionBombError):
        raise NoticeImageError(ERR_FORMAT) from None
    except (OSError, ValueError, SyntaxError, RuntimeError):  # 잘린 · 깨진 파일(HEIC 풀기 실패 포함)
        raise NoticeImageError(ERR_FORMAT) from None
    with Image.open(io.BytesIO(main)) as check:
        width, height = check.size
    ext = "png" if alpha else "jpg"
    return {"main": main, "thumb": thumb, "ext": ext, "content_type": _CONTENT_TYPES[ext],
            "width": int(width), "height": int(height)}


def thumb_key_for(key: str) -> str:
    """본 key → 썸네일 key(``<uuid>.jpg`` → ``<uuid>_thumb.jpg``)."""
    stem, ext = key.rsplit(".", 1)
    return f"{stem}_thumb.{ext}"


def _put(store: Any, key: str, data: bytes, content_type: str) -> bool:
    """비공개로 올린다. 로컬 저장소(개발 전용 — 운영은 R2)는 업로드 폴더에 바로 쓴다."""
    if store.put_private_bytes(key, data, content_type):
        return True
    if getattr(store, "storage_type", "") != "local":
        return False
    path = os.path.join(store.upload_folder, *key.split("/"))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as handle:
        handle.write(data)
    return True


def store_image(data: bytes, filename: Any = "", *, store: Any = None,
                now: Optional[datetime.datetime] = None) -> dict[str, Any]:
    """사진 한 장을 다시 그려 저장소에 올리고 공지 항목 ``{key, thumb_key, name, width, height, size}`` 를 돌려준다.

    Raises:
        NoticeImageError: 받을 수 없는 사진 · 저장 실패(글은 화면 문구).
    """
    drawn = redraw(data, filename)
    store = store or get_storage()
    month = (now or now_utc_naive()).strftime("%Y%m")
    key = f"{KEY_PREFIX}/{month}/{uuid.uuid4().hex}.{drawn['ext']}"
    thumb_key = thumb_key_for(key)
    if not _put(store, key, drawn["main"], drawn["content_type"]):
        raise NoticeImageError(ERR_STORE)
    if not _put(store, thumb_key, drawn["thumb"], drawn["content_type"]):
        store.delete_file(key)
        raise NoticeImageError(ERR_STORE)
    return {"key": key, "thumb_key": thumb_key, "name": clean_name(filename), "width": drawn["width"],
            "height": drawn["height"], "size": len(drawn["main"])}


def admin_file_url(key: str) -> str:
    """관리자 보기 주소(아직 저장 안 한 사진 · 지운 공지 사진도 연다)."""
    return f"/api/admin/notices/images/file?key={quote(key, safe='')}"


def _version(entry: dict[str, Any]) -> str:
    """주소 뒤 꼬리(사진이 바뀌면 다른 주소 — 브라우저가 옛 그림을 쓰지 않게)."""
    return str(entry.get("key") or "").rsplit("/", 1)[-1][:8]


def viewer_items(notice_id: int, images: Any) -> list[dict[str, Any]]:
    """받는 사람 화면용 ``[{url, thumb_url, name, width, height}]`` — 주소는 공지 · 차례로만(저장소 key 를 싣지 않는다)."""
    out: list[dict[str, Any]] = []
    for idx, entry in enumerate(images or []):
        if not isinstance(entry, dict):
            continue
        base = f"/api/notices/{int(notice_id)}/images/{idx}?v={_version(entry)}"
        out.append({"url": base, "thumb_url": f"{base}&thumb=1", "name": str(entry.get("name") or ""),
                    "width": int(entry.get("width") or 0), "height": int(entry.get("height") or 0)})
    return out


def admin_items(images: Any) -> list[dict[str, Any]]:
    """관리자 쓰기 화면용 — 저장 항목 + ``preview_url`` · ``thumb_url``."""
    out: list[dict[str, Any]] = []
    for entry in images or []:
        if not isinstance(entry, dict) or not KEY_RE.fullmatch(str(entry.get("key") or "")):
            continue
        key = str(entry["key"])
        thumb_key = thumb_key_for(key)
        out.append({"key": key, "thumb_key": thumb_key, "name": str(entry.get("name") or ""),
                    "width": int(entry.get("width") or 0), "height": int(entry.get("height") or 0),
                    "size": int(entry.get("size") or 0),
                    "preview_url": admin_file_url(key), "thumb_url": admin_file_url(thumb_key)})
    return out


def image_target(key: str, *, store: Any = None) -> Optional[tuple]:
    """보여 줄 곳 — ``("redirect", 서명 주소)`` (클라우드) · ``("bytes", 바이트, Content-Type)`` (로컬) · 없으면 None.

    key 는 :data:`KEY_RE` · :data:`THUMB_RE` 꼴만 — 다른 저장소 파일은 열지 않는다.
    """
    if not (KEY_RE.fullmatch(key or "") or THUMB_RE.fullmatch(key or "")):
        return None
    store = store or get_storage()
    if getattr(store, "storage_type", "") in ("r2", "s3"):
        url = store.get_download_url(key, expires_in=SIGNED_URL_SECONDS)
        return ("redirect", url) if url else None
    data = store.read_file_bytes(key)
    if data is None:
        return None
    return ("bytes", data, _CONTENT_TYPES[key.rsplit(".", 1)[-1]])
