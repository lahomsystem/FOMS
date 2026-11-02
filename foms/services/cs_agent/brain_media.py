"""최악값 예약의 그림 · PDF 셈 — 요청 글자 수에서 base64 를 빼고, 그림은 픽셀 식 · PDF 는 쪽 식으로 따로 센다(17.11 (f)).

:func:`.brain_prompt.worst_case_cost` 는 요청 칸 JSON 의 글자 수로 입력을 어림한다. base64 그림을 그대로 세면 한 장이 수십만
'토큰'으로 잡혀 예약이 하루 상한을 바로 채운다. 그래서:

- 그림(``image`` 블록 · base64): 글자 수에서 빼고 ``⌈가로/28⌉ × ⌈세로/28⌉``(28×28 한 칸에 1토큰)으로 센다 — 한 장 상한
  :data:`IMAGE_TOKEN_CAP`(높은 해상도 모델 — 공식 vision 문서 2026-11-02 열람: 긴 변 2,576px · 4,784 토큰). 머리를 못 읽으면
  상한으로 센다.
- PDF(``document`` 블록 · base64): 쪽마다 글 토큰 :data:`PDF_TEXT_TOKENS_PER_PAGE`(공식 PDF 문서 '쪽마다 1,500 ~ 3,000' 의 위
  끝) + 쪽 그림 한 장 상한. 쪽 수를 못 세면 :data:`PDF_UNKNOWN_PAGES` 쪽으로 센다(넉넉한 쪽).
"""

from __future__ import annotations

import base64
import binascii
import copy
import io
import math
from typing import Any, Mapping

from foms.services.cs_agent.image_pdf import page_count

__all__ = [
    "IMAGE_TOKEN_CAP", "PATCH_PX", "PDF_TEXT_TOKENS_PER_PAGE", "PDF_UNKNOWN_PAGES", "image_tokens", "media_tokens",
]

PATCH_PX = 28
IMAGE_TOKEN_CAP = 4784
PDF_TEXT_TOKENS_PER_PAGE = 3000
PDF_UNKNOWN_PAGES = 100
_MEDIA = ("image", "document")


def image_tokens(width: int, height: int) -> int:
    """그림 한 장의 시각 토큰(상한까지). 크기를 모르면 상한."""
    if width <= 0 or height <= 0:
        return IMAGE_TOKEN_CAP
    return min(IMAGE_TOKEN_CAP, math.ceil(width / PATCH_PX) * math.ceil(height / PATCH_PX))


def _decoded(data: Any) -> bytes:
    """base64 글 → 바이트(틀리면 빈 바이트)."""
    try:
        return base64.b64decode(data, validate=True) if isinstance(data, str) else b""
    except (binascii.Error, ValueError):
        return b""


def _image_size(raw: bytes) -> tuple[int, int]:
    """그림 머리에서 가로 · 세로(픽셀을 풀지 않는다). 못 읽으면 (0, 0)."""
    from PIL import Image, UnidentifiedImageError  # noqa: PLC0415

    try:
        with Image.open(io.BytesIO(raw)) as image:
            return int(image.width), int(image.height)
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError):
        return 0, 0


def _block_tokens(block: Mapping[str, Any]) -> int:
    """미디어 블록 하나의 토큰 어림."""
    raw = _decoded(block.get("source", {}).get("data"))
    if block.get("type") == "image":
        return image_tokens(*_image_size(raw))
    pages = page_count(raw) or PDF_UNKNOWN_PAGES
    return pages * (PDF_TEXT_TOKENS_PER_PAGE + IMAGE_TOKEN_CAP)


def media_tokens(params: Mapping[str, Any]) -> tuple[dict[str, Any], int]:
    """요청 칸 → (base64 를 비운 사본, 그림 · PDF 토큰 어림 합). 미디어가 없으면 (원본 dict 사본, 0)."""
    out = dict(params)
    total = 0
    messages = params.get("messages")
    if not isinstance(messages, list):
        return out, 0
    stripped = []
    for message in messages:
        content = message.get("content") if isinstance(message, Mapping) else None
        if not isinstance(content, list):
            stripped.append(message)
            continue
        blocks = []
        for block in content:
            source = block.get("source") if isinstance(block, Mapping) else None
            if isinstance(source, Mapping) and block.get("type") in _MEDIA and source.get("type") == "base64":
                total += _block_tokens(block)
                block = {**block, "source": {**source, "data": ""}}
            blocks.append(block)
        stripped.append({**message, "content": blocks})
    out["messages"] = copy.copy(stripped)
    return out, total
