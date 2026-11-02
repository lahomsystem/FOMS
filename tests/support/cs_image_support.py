"""그림 읽기(설계서 17.11) 시험 재료 — 합성 도면(Pillow 로 그 자리에서 그림) · 손으로 짠 PDF · 가짜 채널톡 파일 받기 · 답 꼴.

그림 파일 · 손님 그림 · 금액 · 직원 이름은 저장소에 두지 않는다. 도면 글자는 ASCII(합성 방 이름 · 치수)뿐이다.
"""

from __future__ import annotations

import io
import zlib
from typing import Any, Optional

from PIL import Image, ImageDraw

from db import db_session
from foms.services.cs_agent import settings as st
from models import SystemSetting
from tests.support.cs_agent_fakes import FakeChannel, FakeResponse

FILE_HOST = "https://files.example/signed/"


def plan_image(width: int = 1600, height: int = 1200, *, marks: bool = True, mode: str = "RGB") -> Image.Image:
    """합성 평면도 — 방 네모 · 방 이름 · 치수 글자 · 창(겹선) · 문(호) · 손님 표시(빨간 동그라미 · 엑스) · 축척 막대."""
    image = Image.new(mode, (width, height), (255, 255, 255, 0) if mode == "RGBA" else (255, 255, 255))
    draw = ImageDraw.Draw(image)
    w, h = width, height
    draw.rectangle((w * 0.1, h * 0.1, w * 0.6, h * 0.7), outline=(0, 0, 0), width=8)
    draw.rectangle((w * 0.6, h * 0.1, w * 0.9, h * 0.5), outline=(0, 0, 0), width=8)
    draw.text((w * 0.3, h * 0.35), "BED 1", fill=(0, 0, 0))
    draw.text((w * 0.3, h * 0.05), "3600", fill=(0, 0, 0))
    draw.line((w * 0.25, h * 0.7, w * 0.45, h * 0.7), fill=(0, 0, 255), width=4)  # 창(겹선)
    draw.line((w * 0.25, h * 0.71, w * 0.45, h * 0.71), fill=(0, 0, 255), width=4)
    draw.arc((w * 0.55, h * 0.55, w * 0.65, h * 0.65), 180, 270, fill=(0, 0, 0), width=4)  # 문(호)
    draw.line((w * 0.1, h * 0.9, w * 0.3, h * 0.9), fill=(0, 0, 0), width=6)  # 축척 막대
    if marks:
        draw.ellipse((w * 0.12, h * 0.12, w * 0.22, h * 0.22), outline=(255, 0, 0), width=6)
        draw.line((w * 0.7, h * 0.2, w * 0.8, h * 0.3), fill=(255, 0, 0), width=6)
        draw.line((w * 0.8, h * 0.2, w * 0.7, h * 0.3), fill=(255, 0, 0), width=6)
    return image


def encoded(image: Image.Image, fmt: str = "JPEG", **kwargs: Any) -> bytes:
    """그림 → 바이트(메모리)."""
    out = io.BytesIO()
    image.save(out, format=fmt, **kwargs)
    return out.getvalue()


def pdf_bytes(pages: int = 1, *, image_jpeg: Optional[bytes] = None, image_filter: str = "/DCTDecode",
              encrypt: bool = False, image_size: tuple[int, int] = (64, 64), object_stream: bool = False) -> bytes:
    """손으로 짠 작은 PDF — 쪽 나무 · 쪽 · 내용 글(압축) · (있으면) 그림 객체. ``object_stream`` 이면 쪽 나무를 묶음 속에."""
    objects: list[bytes] = []
    kids = " ".join(f"{3 + i} 0 R" for i in range(pages))
    pages_dict = f"<< /Type /Pages /Kids [{kids}] /Count {pages} >>".encode()
    objects.append(b"<< /Type /Catalog /Pages 2 0 R >>")
    objects.append(b"<< /Type /Placeholder >>" if object_stream else pages_dict)
    content_id = 3 + pages
    image_id = content_id + 1
    for _ in range(pages):
        resources = f"/Resources << /XObject << /Im1 {image_id} 0 R >> >>" if image_jpeg is not None else ""
        objects.append(f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 200 200] /Contents {content_id} 0 R "
                       f"{resources} >>".encode())
    body = zlib.compress(b"0 0 m 100 100 l S\nBT /F1 12 Tf (3600) Tj ET")
    objects.append(b"<< /Filter /FlateDecode /Length %d >>\nstream\n" % len(body) + body + b"\nendstream")
    if image_jpeg is not None:
        w, h = image_size
        objects.append(f"<< /Type /XObject /Subtype /Image /Width {w} /Height {h} /ColorSpace /DeviceRGB "
                       f"/BitsPerComponent 8 /Filter {image_filter} /Length {len(image_jpeg)} >>\nstream\n".encode()
                       + image_jpeg + b"\nendstream")
    if object_stream:
        packed = zlib.compress(b"2 0 " + pages_dict)
        objects.append(b"<< /Type /ObjStm /N 1 /First 4 /Filter /FlateDecode /Length %d >>\nstream\n" % len(packed)
                       + packed + b"\nendstream")
    out = [b"%PDF-1.7\n"]
    for number, obj in enumerate(objects, start=1):
        out.append(b"%d 0 obj\n" % number + obj + b"\nendobj\n")
    trailer = b"<< /Root 1 0 R /Encrypt 99 0 R >>" if encrypt else b"<< /Root 1 0 R >>"
    out.append(b"trailer\n" + trailer + b"\n%%EOF\n")
    return b"".join(out)


def file_item(key: str, data: bytes, *, content_type: str = "image/jpeg", width: int = 1600,
              height: int = 1200) -> dict[str, Any]:
    """채널톡 글 ``files[]`` 칸 하나(합성 key)."""
    return {"id": f"f-{key}", "type": "image" if content_type.startswith("image/") else "file", "key": key,
            "bucket": "bin", "name": "synthetic.bin", "contentType": content_type, "size": len(data),
            "width": width, "height": height}


class FileStore:
    """파일 key → 바이트(가짜 채널톡 서명 주소 · 내려받기가 같이 본다). 부른 key · 주소를 남긴다."""

    def __init__(self) -> None:
        self.files: dict[str, bytes] = {}
        self.signed: list[str] = []
        self.downloads: list[str] = []

    def put(self, key: str, data: bytes) -> str:
        self.files[key] = data
        return key


class ImageChannel(FakeChannel):
    """가짜 채널톡 + 파일 서명 주소(``user-chats/{상담}/messages/file?key=``) — 응답 ``{"result": 주소}``."""

    def __init__(self, store: FileStore) -> None:
        super().__init__()
        self.store = store

    def __call__(self, url, *, params, headers, timeout):
        path = url.split("/open/", 1)[1]
        if path.endswith("/messages/file"):
            self.calls.append(path)
            key = params.get("key")
            if key not in self.store.files:
                return FakeResponse(404)
            self.store.signed.append(key)
            return FakeResponse(200, {"result": FILE_HOST + key})
        return super().__call__(url, params=params, headers=headers, timeout=timeout)


class _Download:
    def __init__(self, data: bytes, status: int = 200) -> None:
        self.data, self.status_code, self.closed = data, status, False

    def iter_content(self, chunk_size: int):
        for start in range(0, len(self.data), chunk_size):
            yield self.data[start:start + chunk_size]

    def close(self) -> None:
        self.closed = True


class FakeDownload:
    """서명 주소 내려받기 대역(``requests.get(url, stream=True, timeout=…)`` 꼴)."""

    def __init__(self, store: FileStore) -> None:
        self.store = store

    def __call__(self, url, *, stream, timeout):
        assert stream is True and url.startswith(FILE_HOST)
        key = url[len(FILE_HOST):]
        self.store.downloads.append(key)
        return _Download(self.store.files[key]) if key in self.store.files else _Download(b"", 404)


def wall(low: int, high: int = 0, *, basis: str = "center_line", ends: str = "both_walls", usable: bool = True,
         marked: bool = False, side: str = "top", source: str = "written", blocked=("none",)) -> dict[str, Any]:
    """모델 답의 벽 칸 하나."""
    return {"side": side, "usable": usable, "marked": marked, "blocked_by": list(blocked), "read_min_mm": low,
            "read_max_mm": high or low, "source": source, "basis": basis, "ends": ends}


def room(name: str = "안방", *walls: dict, target: str = "named", door: str = "unknown", handle: str = "unknown",
         height: int = 0, basis=("label_on_plan",), marks=()) -> dict[str, Any]:
    """모델 답의 공간 칸 하나."""
    return {"room": name, "room_basis": list(basis), "target": target, "mark_kinds": list(marks),
            "walls": list(walls), "door": door, "handle": handle, "molding": "unknown", "height_mm": height}


def answer(*spaces: dict, confidence: str = "medium", reasons=(), personal=("none",), kinds=("floor_plan",),
           drawing: bool = True, other: bool = False) -> dict[str, Any]:
    """그림 읽기 구조화 출력(합성)."""
    return {"images": [{"index": i, "kind": k} for i, k in enumerate(kinds)], "is_drawing": drawing,
            "spaces": list(spaces), "confidence": confidence, "reasons": list(reasons),
            "personal_seen": list(personal), "other_question": other}


def image_switch(mode: str = "note", **extra: Any) -> None:
    """관리 화면 설정 — 견적 계산 넣기 켬 + 그림 읽기 모드(나머지는 처음 값)."""
    value = {**st.DEFAULTS, "quote_calc_enabled": True, "image_read_mode": mode, **extra}
    row = db_session.get(SystemSetting, st.SETTINGS_KEY)
    if row is None:
        db_session.add(SystemSetting(setting_key=st.SETTINGS_KEY, version=1, setting_value=value))
    else:
        row.setting_value = value
    db_session.commit()
