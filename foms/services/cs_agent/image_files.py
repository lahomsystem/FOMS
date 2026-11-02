"""손님 그림 파일 정보 — 채널톡 글 ``files[]`` 의 칸을 메모리에만 담는 꼴(설계서 17.11 (a)).

글 읽기(:func:`.drafting_read.read_lines`)가 손님 공개 글의 파일 칸을 이 꼴로 붙인다. 파일 ``key`` 는 그 글의 파일을 받는
데만 쓰고 표 · 로그 · repr 에 두지 않는다(D89 — 파일 key · 주소 · 파일 이름은 남기지 않는다). 파일 이름은 읽지도 않는다.
의존이 없는 모듈이다 — 글 읽기 · 그림 받기 · 그림 읽기가 같이 쓴다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Optional

__all__ = ["MAX_FILES_PER_MESSAGE", "FileRef", "parse_files"]

#: 글 하나에서 보는 파일 수 상한(채널톡 글은 보통 10장 안쪽 — 넘는 것은 보지 않는다).
MAX_FILES_PER_MESSAGE = 20
_MAX_KEY = 1024
_FILE_KEYS = ("files", "attachments")


@dataclass(frozen=True)
class FileRef:
    """글 하나의 파일 하나 — 차례(``file_index``)와 받기 전에 거를 칸(꼴 · 바이트 · 가로세로). ``key`` 는 repr 에 없다."""

    message_id: str
    file_index: int
    content_type: str
    size: int
    width: int
    height: int
    key: str = field(repr=False, default="")

    @property
    def pixels(self) -> int:
        """글이 알려 준 픽셀 수(모르면 0)."""
        return self.width * self.height


def _int(value: Any) -> int:
    """음이 아닌 정수 칸(아니면 0)."""
    return value if isinstance(value, int) and not isinstance(value, bool) and value > 0 else 0


def _one(message_id: str, index: int, raw: Any) -> Optional[FileRef]:
    """파일 칸 하나 → :class:`FileRef`(key 가 없거나 꼴이 틀리면 ``None``)."""
    if not isinstance(raw, Mapping):
        return None
    key = raw.get("key")
    if not isinstance(key, str) or not key.strip() or len(key) > _MAX_KEY:
        return None
    content_type = raw.get("contentType")
    kind = content_type.strip().lower() if isinstance(content_type, str) else ""
    return FileRef(message_id=message_id, file_index=index, content_type=kind[:64], size=_int(raw.get("size")),
                   width=_int(raw.get("width")), height=_int(raw.get("height")), key=key.strip())


def parse_files(message_id: str, item: Mapping[str, Any]) -> tuple[FileRef, ...]:
    """채널톡 글 dict 의 파일 칸들(``files`` · ``attachments``) → 파일 정보 튜플(글 안 차례 = 0 부터)."""
    raw: list[Any] = []
    for name in _FILE_KEYS:
        value = item.get(name)
        if isinstance(value, (list, tuple)):
            raw.extend(value)
    refs = (_one(message_id, index, value) for index, value in enumerate(raw[:MAX_FILES_PER_MESSAGE]))
    return tuple(ref for ref in refs if ref is not None)
