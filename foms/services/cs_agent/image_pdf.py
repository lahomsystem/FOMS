"""PDF 훑기 — 쪽 수 · 잠금 · 안에 든 그림(얼굴 거르기 재료)을 표준 라이브러리만으로 본다(설계서 17.11 (a) · D96).

PDF 는 그림으로 바꾸지 않고 Claude 문서 입력으로 그대로 보낸다(D96). 쪽을 자르거나 그림으로 바꾸려면 새 패키지가 필요해
(지금 requirements 에 PDF 패키지가 없다) **자르지 않는다** — 쪽 수가 상한을 넘으면 보내지 않는다(``skipped_cap``). 얼굴
거르기는 PDF 안의 그림(이미지 XObject)을 꺼내 본다: JPEG(``DCTDecode``)는 그대로, 압축만 된 8 · 1 비트 회색 · RGB ·
CMYK 그림(``FlateDecode`` · 예측기 없음)은 픽셀로 풀어 넘긴다. 그 밖의 꼴(JPX · CCITT · JBIG2 · 예측기 · 색 목록 ·
인라인 그림)이나 잠긴 PDF · 쪽 수를 못 센 PDF 는 **막는 쪽**(:attr:`PdfScan.problem`)이다 — 확인 못 한 것은 보내지 않는다.
바이트는 이 함수 안에서만 쓴다(표 · 로그에 두지 않는다).
"""

from __future__ import annotations

import re
import zlib
from dataclasses import dataclass, field
from typing import Optional

__all__ = ["PdfImage", "PdfScan", "page_count", "scan_pdf"]

#: 풀어 보는 바이트 합 상한(압축 폭탄 — 넘으면 막는다).
MAX_INFLATE = 64 * 1024 * 1024
#: 이보다 작은 그림은 얼굴이 담길 수 없다고 보고 건너뛴다(선 · 무늬 조각).
MIN_SIDE = 24
MAX_IMAGE_PIXELS = 25_000_000
_OBJ = re.compile(rb"(\d+)\s+(\d+)\s+obj\b")
_LENGTH = re.compile(rb"/Length\s+(\d+)(\s+\d+\s+R)?")
_INT = {name: re.compile(rb"/" + name + rb"\s+(\d+)") for name in (b"Width", b"Height", b"BitsPerComponent")}
_PAGES_COUNT = re.compile(rb"/Type\s*/Pages\b[^>]{0,400}?/Count\s+(\d+)|/Count\s+(\d+)[^>]{0,400}?/Type\s*/Pages\b")
_PAGE = re.compile(rb"/Type\s*/Page(?![a-zA-Z])")
_INLINE_IMAGE = re.compile(rb"(?:^|\s)BI\s+/[A-Za-z]")


@dataclass(frozen=True)
class PdfImage:
    """PDF 안 그림 하나 — JPEG 바이트(``jpeg``) 또는 풀어 낸 픽셀(``raw`` · 가로 · 세로 · 칸 수)."""

    width: int
    height: int
    jpeg: bytes = field(default=b"", repr=False)
    raw: bytes = field(default=b"", repr=False)
    components: int = 0
    bits: int = 8


@dataclass(frozen=True)
class PdfScan:
    """훑은 결과 — 쪽 수(0 = 못 셈) · 얼굴을 볼 그림들 · 막는 까닭(없으면 ``None``)."""

    pages: int
    images: tuple[PdfImage, ...] = ()
    problem: Optional[str] = None


class _Budget:
    """풀어 본 바이트 합(압축 폭탄 막기)."""

    def __init__(self) -> None:
        self.left = MAX_INFLATE

    def inflate(self, data: bytes) -> bytes:
        """한 덩어리를 푼다. 남은 몫을 넘거나 깨졌으면 ``ValueError``."""
        engine = zlib.decompressobj()
        out = engine.decompress(data, self.left + 1)
        if len(out) > self.left or engine.unconsumed_tail:
            raise ValueError("inflate_cap")
        self.left -= len(out)
        return out


def _stream(buf: bytes, head_end: int, length: Optional[int]) -> tuple[bytes, int]:
    """``stream`` 낱말 뒤의 몸통과 그 끝 자리(``/Length`` 가 맞지 않으면 ``endstream`` 으로 찾는다)."""
    start = head_end + len(b"stream")
    start += 2 if buf[start:start + 2] == b"\r\n" else 1 if buf[start:start + 1] in (b"\n", b"\r") else 0
    if length is not None and buf[start + length:start + length + 20].lstrip().startswith(b"endstream"):
        return buf[start:start + length], start + length
    end = buf.find(b"endstream", start)
    if end < 0:
        raise ValueError("no_endstream")
    return buf[start:end].rstrip(b"\r\n"), end


def _objects(buf: bytes) -> list[tuple[bytes, Optional[bytes]]]:
    """윗자리 객체마다 (사전 글, 몸통 — 없으면 ``None``). 몸통 길이가 간접 참조면 ``endstream`` 으로 찾는다."""
    out: list[tuple[bytes, Optional[bytes]]] = []
    pos = 0
    while True:
        found = _OBJ.search(buf, pos)
        if found is None:
            return out
        end_obj = buf.find(b"endobj", found.end())
        stream_at = buf.find(b"stream", found.end())
        if 0 <= stream_at and (end_obj < 0 or stream_at < end_obj):
            head = buf[found.end():stream_at]
            length = _LENGTH.search(head)
            direct = int(length.group(1)) if length and not length.group(2) else None
            body, pos = _stream(buf, stream_at, direct)
            out.append((head, body))
            continue
        out.append((buf[found.end():end_obj if end_obj >= 0 else len(buf)], None))
        pos = end_obj + 6 if end_obj >= 0 else len(buf)


def _filters(head: bytes) -> list[bytes]:
    """``/Filter`` 이름들(하나 · 배열 모두)."""
    found = re.search(rb"/Filter\s*(\[[^\]]*\]|/[A-Za-z0-9]+)", head)
    return re.findall(rb"/([A-Za-z0-9]+)", found.group(1)) if found else []


def _int(head: bytes, name: bytes) -> int:
    match = _INT[name].search(head)
    return int(match.group(1)) if match else 0


def _image(head: bytes, body: bytes, budget: _Budget) -> Optional[PdfImage]:
    """그림 객체 하나 → :class:`PdfImage`(작은 그림 · 마스크는 ``None``). 못 푸는 꼴이면 ``ValueError``."""
    width, height = _int(head, b"Width"), _int(head, b"Height")
    if re.search(rb"/ImageMask\s+true", head) or min(width, height) < MIN_SIDE:
        return None
    if width * height > MAX_IMAGE_PIXELS:
        raise ValueError("image_pixels")
    filters = _filters(head)
    if filters == [b"DCTDecode"]:
        return PdfImage(width, height, jpeg=body)
    if filters != [b"FlateDecode"] or b"/DecodeParms" in head or b"/Indexed" in head:
        raise ValueError("image_filter")
    bits = _int(head, b"BitsPerComponent") or 8
    raw = budget.inflate(body)
    for components in (1, 3, 4):
        if bits in (1, 8) and len(raw) == -(-width * components * bits // 8) * height:
            return PdfImage(width, height, raw=raw, components=components, bits=bits)
    raise ValueError("image_layout")


def _scan_streams(objects: list[tuple[bytes, Optional[bytes]]], budget: _Budget) -> tuple[list[PdfImage], bytes]:
    """그림을 꺼내고, 객체 묶음(ObjStm)을 풀어 쪽 수 재료 글을 모으고, 내용 글의 인라인 그림을 막는다."""
    images: list[PdfImage] = []
    texts: list[bytes] = []
    for head, body in objects:
        texts.append(head)
        if body is None:
            continue
        if re.search(rb"/Subtype\s*/Image\b", head):
            image = _image(head, body, budget)
            if image is not None:
                images.append(image)
        elif _filters(head) == [b"FlateDecode"]:
            inflated = budget.inflate(body)
            if re.search(rb"/Type\s*/ObjStm\b", head):
                texts.append(inflated)
            elif _INLINE_IMAGE.search(inflated):
                raise ValueError("inline_image")
    return images, b"\n".join(texts)


def page_count(text: bytes) -> int:
    """쪽 수 — 쪽 나무(``/Type /Pages``)의 가장 큰 ``/Count`` 와 쪽 객체(``/Type /Page``) 수 가운데 큰 값(못 세면 0)."""
    counts = [int(a or b) for a, b in _PAGES_COUNT.findall(text)]
    return max([*counts, len(_PAGE.findall(text))], default=0)


def scan_pdf(data: bytes) -> PdfScan:
    """PDF 바이트를 훑는다 — 막는 까닭: ``not_pdf`` · ``encrypted`` · ``pages_unknown`` · 못 푸는 그림 · 인라인 그림 · 폭탄."""
    if not data.startswith(b"%PDF-"):
        return PdfScan(0, problem="not_pdf")
    if re.search(rb"/Encrypt\b", data):
        return PdfScan(0, problem="encrypted")
    try:
        images, text = _scan_streams(_objects(data), _Budget())
    except (ValueError, zlib.error) as exc:
        reason = exc.args[0] if isinstance(exc, ValueError) and exc.args and isinstance(exc.args[0], str) else "broken"
        return PdfScan(0, problem=reason if reason.isidentifier() else "broken")
    pages = page_count(text)
    if pages <= 0:
        return PdfScan(0, problem="pages_unknown")
    return PdfScan(pages, tuple(images))
