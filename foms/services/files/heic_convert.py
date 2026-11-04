"""HEIC/HEIF(아이폰 원본 사진) → JPEG — 협력사 사진 올리기(사용자 2026-11-04 업로드 점검).

아이폰은 보통 브라우저로 보낼 때 jpg 로 바꾸지만, 원본(HEIC)이 그대로 오면 서버가 "올릴 수 없는 파일 형식"으로 막았다.
크롬 · 엣지는 HEIC 를 그리지 못하므로 받을 때 JPEG 로 다시 그려 저장한다(공지 사진과 같은 ``pillow_heif`` —
:mod:`foms.services.notices.images`). Pillow 전체에 HEIF 를 등록하지 않는다(다른 업로드의 받는 형식 규칙을 바꾸지 않게).
"""
from __future__ import annotations

import io
from typing import Any, Optional

import pillow_heif
from werkzeug.datastructures import FileStorage

HEIC_EXTS = frozenset({"heic", "heif"})
#: 풀었을 때 화소 상한 — 아이폰 48MP 원본도 들어오고, 일부러 부풀린 파일은 막는다.
MAX_PIXELS = 80_000_000
ERR_OPEN = "HEIC 사진을 열지 못했습니다. jpg 로 바꿔 올려 주세요."
ERR_PIXELS = "사진이 너무 큽니다. 크기를 줄여 올려 주세요."


def heic_to_jpeg(data: bytes) -> bytes:
    """HEIC 바이트 → JPEG 바이트(품질 90, 방향은 HEIC 정보대로). 못 열면 ``ValueError``(사용자 문구)."""
    if not data or not pillow_heif.is_supported(data):
        raise ValueError(ERR_OPEN)
    heif = pillow_heif.open_heif(data, convert_hdr_to_8bit=True)
    if heif.size[0] * heif.size[1] > MAX_PIXELS:
        raise ValueError(ERR_PIXELS)
    out = io.BytesIO()
    heif.to_pillow().convert("RGB").save(out, "JPEG", quality=90, optimize=True)
    return out.getvalue()


def jpeg_if_heic(file: Any) -> tuple[Any, Optional[str]]:
    """올린 파일이 HEIC/HEIF 면 JPEG ``FileStorage``(이름 ``.jpg``)로 바꿔 돌려준다. 아니면 그대로. 실패하면 (원본, 문구)."""
    name = str(getattr(file, "filename", "") or "")
    ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
    if ext not in HEIC_EXTS:
        return file, None
    try:
        data = heic_to_jpeg(file.read())
    except ValueError as exc:
        return file, str(exc)
    except Exception:  # noqa: BLE001 - 깨진 HEIC 는 사용자 문구로만 돌려준다
        return file, ERR_OPEN
    return FileStorage(stream=io.BytesIO(data), filename=name.rsplit(".", 1)[0] + ".jpg", content_type="image/jpeg"), None
