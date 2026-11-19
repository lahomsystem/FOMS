"""목록 화면 도면 작은 그림(긴 변 320px) — 설계서 ``docs/specs/2026-11-19-list-drawing-small-image_SPEC.md``.

목록의 손톱만 한 칸(40~112px)에 원본 그림을 통째로 받던 것을, 원본 옆에 한 번 만들어 둔 작은 그림으로 바꾼다.

* 이름: 원본 옆 ``sthumb320_<원본 이름>.jpg``. 도면 key 는 올릴 때마다 새 이름이라 작은 그림 이름도 판마다 새것 —
  옛 작은 그림이 새 도면 자리에 나올 수 없고, 그래서 응답을 ``immutable`` 로 오래 캐시해도 된다.
* 만들기는 **워커만** 한다(운영 web 은 gevent 2개 — 그림을 줄이는 동안 그 프로세스의 다른 요청이 멈춘다).
  web 은 있나 보기 · 읽기 · 예약만 한다(예약 = :mod:`foms.services.files.list_thumb_schedule`). web 안 ThreadPool 폴백은 없다.
* 그리기는 생산 파트 작은 그림(``foms/web/production/part_thumb.py``)과 같은 :func:`render_white_jpeg_thumb` —
  흰 바탕(투명 칸이 검정이 되지 않게) · EXIF 회전 · LANCZOS · JPEG 품질 85.

이 모듈은 Flask 앱(``foms.platform``)을 열지 않는다 — RQ 워커(``foms.services.jobs.tasks``)가 그대로 부른다.
"""

from __future__ import annotations

import hashlib
import io
import logging
import posixpath

from foms.services.storage import get_storage

logger = logging.getLogger(__name__)

#: 작은 그림 긴 변(px) · JPEG 품질 · 저장 이름 접두. 가장 큰 목록 칸(112px)의 3배 화면까지 맞는다.
LIST_THUMB_LONG_EDGE = 320
LIST_THUMB_QUALITY = 85
LIST_THUMB_PREFIX = "sthumb320_"
#: key 가 판마다 새 이름이라 내용이 안 바뀐다 — 30일 · 다시 묻지 않음(생산 파트 작은 그림 길과 같은 값).
LIST_THUMB_CACHE_CONTROL = "private, max-age=2592000, immutable"
#: 풀었을 때 화소 상한 — 공유 합본(``foms/api/share.py`` ``_SHEET_MAX_PIXELS``)과 같은 16MP.
#: 넘으면 만들지 않는다(원본이 계속 나간다). 두 값이 갈리면 시험이 빨강이 된다.
LIST_THUMB_MAX_PIXELS = 16_000_000
#: 작은 그림을 만들 수 있는 원본 확장자(화면 쪽 그림 판정과 같은 묶음). 그 밖(PDF · HEIC 등)은 길이 404.
LIST_THUMB_IMAGE_SUFFIXES = (".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp")
#: 파생 파일 이름 접두 — 작은 그림의 작은 그림은 만들지 않는다.
_DERIVED_PREFIXES = ("thumb_", "pthumb720_", LIST_THUMB_PREFIX)

#: :func:`create_list_thumb` 결과(로그 · 시험용).
RESULT_STORED = "stored"
RESULT_EXISTS = "exists"
RESULT_NOT_IMAGE = "not_image"
RESULT_MISSING = "missing_source"
RESULT_TOO_LARGE = "too_large"
RESULT_UNREADABLE = "unreadable"
RESULT_STORE_FAILED = "store_failed"


#: 작은 그림 길 주소 앞부분 — ``foms.api.files.routes.build_file_thumb_url`` 과 서비스 쪽 :func:`list_thumb_url` 의 정본.
LIST_THUMB_ROUTE_PREFIX = "/api/files/thumb/"


def list_thumb_url(key: str | None) -> str | None:
    """작은 칸용 작은 그림 길 주소(원본 key 에서 계산만 — 조회 없음). 만들 수 없는 key 면 None.

    서비스 레이어는 api 를 import 하지 않으므로(레이어 래칫) 주소 모양을 여기 둔다. 저장 URL 은 믿지 않는다 —
    늘 key 에서 다시 만든다.
    """
    text = (key or "").strip()
    return f"{LIST_THUMB_ROUTE_PREFIX}{text}" if is_list_thumb_source(text) else None


def is_list_thumb_source(key: str | None) -> bool:
    """작은 그림을 만들 수 있는 원본 key 인지(그림 확장자 · 파생 파일 아님)."""
    text = (key or "").strip()
    if not text:
        return False
    name = posixpath.basename(text).lower()
    if name.startswith(_DERIVED_PREFIXES):
        return False
    return name.endswith(LIST_THUMB_IMAGE_SUFFIXES)


def list_thumb_key(key: str) -> str:
    """원본 key → 작은 그림 저장 key(원본 옆 ``sthumb320_<원본 이름>.jpg``).

    원본 이름을 통째로 넣는다(확장자까지) — 같은 폴더의 ``a.png`` 와 ``a.jpg`` 가 한 작은 그림을 나눠 쓰지 않게.
    원본과 같은 폴더라 문지기(``orders/<id>/...`` 정규 key 길)도 원본과 같다.
    """
    folder, name = posixpath.split(key)
    thumb = f"{LIST_THUMB_PREFIX}{name}.jpg"
    return posixpath.join(folder, thumb) if folder else thumb


def list_thumb_job_id(key: str) -> str:
    """같은 key 는 같은 RQ job id(글자 · 숫자 · 밑줄만 — RQ job id 규칙)."""
    return "list_thumb_" + hashlib.sha1(key.encode("utf-8")).hexdigest()


def render_white_jpeg_thumb(raw: bytes, long_edge: int, *, quality: int = LIST_THUMB_QUALITY,
                            max_pixels: int | None = None) -> bytes:
    """원본 그림 바이트 → 흰 바탕 · EXIF 회전 · 긴 변 ``long_edge`` px · JPEG 바이트.

    생산 파트 작은 그림(720px)과 목록 작은 그림(320px)이 같이 쓴다.

    Args:
        raw: 원본 그림 바이트(PNG 투명 칸 · 팔레트 · EXIF 회전 포함).
        long_edge: 줄인 그림의 긴 변(px). 원본이 더 작으면 키우지 않는다.
        quality: JPEG 품질.
        max_pixels: 주면 머리글의 가로 x 세로가 이 값을 넘을 때 풀기 전에 ``ValueError``.

    Returns:
        JPEG 바이트.

    Raises:
        OSError: 그림으로 읽을 수 없을 때(PIL ``UnidentifiedImageError`` 포함).
        ValueError: ``max_pixels`` 를 넘을 때.
    """
    from PIL import Image, ImageOps

    with Image.open(io.BytesIO(raw)) as source:
        if max_pixels is not None and source.size[0] * source.size[1] > max_pixels:
            raise ValueError(f"too many pixels: {source.size[0]}x{source.size[1]}")
        if source.format == "JPEG":
            source.draft("RGB", (long_edge * 2, long_edge * 2))  # 큰 사진은 줄여 읽는다
        image = ImageOps.exif_transpose(source).convert("RGBA")
    image.thumbnail((long_edge, long_edge), Image.Resampling.LANCZOS)
    canvas = Image.new("RGB", image.size, (255, 255, 255))
    canvas.paste(image, mask=image.getchannel("A"))  # 투명 칸 = 흰색(검정이 되지 않게)
    out = io.BytesIO()
    canvas.save(out, "JPEG", quality=quality, optimize=True)
    return out.getvalue()


def create_list_thumb(storage_key: str, storage=None) -> str:
    """워커 본체: 원본을 읽어 작은 그림을 만들어 원본 옆에 한 번 저장한다(이미 있으면 건너뜀).

    Args:
        storage_key: 원본 key.
        storage: 시험용 저장소(없으면 :func:`foms.services.storage.get_storage`).

    Returns:
        ``RESULT_*`` 중 하나. 예외는 올리지 않는다(그림 문제는 건너뜀 — 원본이 계속 나간다).
    """
    key = (storage_key or "").strip()
    if not is_list_thumb_source(key):
        return RESULT_NOT_IMAGE
    if storage is None:
        storage = get_storage()
    thumb_key = list_thumb_key(key)
    if storage.object_exists(thumb_key):
        return RESULT_EXISTS
    raw = storage.read_file_bytes(key)
    if not raw:
        return RESULT_MISSING
    from PIL import Image

    try:
        data = render_white_jpeg_thumb(raw, LIST_THUMB_LONG_EDGE, max_pixels=LIST_THUMB_MAX_PIXELS)
    except ValueError:
        logger.info("[list-thumb] too large — skip key=%s", key)
        return RESULT_TOO_LARGE
    except (OSError, Image.DecompressionBombError):
        logger.info("[list-thumb] unreadable image — skip key=%s", key)
        return RESULT_UNREADABLE
    if not storage.put_private_bytes(thumb_key, data, "image/jpeg"):
        return RESULT_STORE_FAILED  # 로컬 저장소는 비공개 저장을 받지 않는다 · R2 오류는 다음 예약에서 다시
    return RESULT_STORED
