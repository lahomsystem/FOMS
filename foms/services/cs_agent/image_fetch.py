"""손님 그림 받기 — 고를 파일(마지막 공개 직원 글 뒤 손님 글 · 새 것부터) · 채널톡 Open API 로 바이트 받기(17.11 (a)).

- **고르기(:func:`pending_files`)**: 라홈 공개 손님 글의 파일만(직원 · 봇 · 내부 메모 · 기록 글의 파일은 읽지 않는다 — 글 읽기가
  손님 공개 글에만 파일 정보를 붙인다). 마지막 공개 직원 글 뒤의 것을 새 것부터 차례당 상한까지.
- **받기(:func:`fetch_bytes`)**: Open API ``GET /open/user-chats/{상담}/messages/file?key=…`` 가 서명 주소(15분)를 준다(공개
  문서 v4 꼴 — 2026-06-01 판 경로 · 응답 꼴은 **스테이징 시험 상담에서 처음 잰다**, 설계서 17.11 (j)). 서명 주소에서 바이트를
  나눠 받으며 :data:`.image_prep.MAX_BYTES` 를 넘으면 그만 받는다. 채널톡 읽기 양동이(``read_budget``)를 같이 쓴다. 주소 ·
  key · 응답 본문은 로그 · 예외 글에 싣지 않는다(상태 코드만). 학습 때 쓴 데스크 주소 · 사람 로그인 토큰은 쓰지 않는다(9.2).
"""

from __future__ import annotations

from typing import Any, Callable, Optional, Sequence
from urllib.parse import quote

import requests

from foms.services.cs_agent.channel_read import ChannelReadError
from foms.services.cs_agent.image_files import FileRef
from foms.services.cs_agent.image_prep import MAX_BYTES
from foms.services.cs_agent.read_budget import BUCKET_MESSAGE

__all__ = ["FILE_PATH", "FetchError", "fetch_bytes", "pending_files"]

FILE_PATH = "/open/user-chats/{chat}/messages/file"
_URL_KEYS = ("result", "url")
_CHUNK = 256 * 1024


class FetchError(RuntimeError):
    """파일을 못 받았다(까닭 코드만 — 주소 · key 없음). ``too_big`` 이면 바이트 상한을 넘었다."""


def pending_files(lines: Sequence[Any], *, limit: int) -> list[FileRef]:
    """마지막 공개 직원 글 뒤 손님 글의 파일(새 글부터 · 글 안 차례대로) — 차례당 ``limit`` 개까지."""
    after = max((i for i, line in enumerate(lines) if line.meta.is_answer), default=-1)
    refs: list[FileRef] = []
    for line in reversed(list(lines[after + 1:])):
        if line.meta.is_customer_signal:
            refs.extend(getattr(line, "files", ()))
    return refs[:max(0, limit)]


def _signed_url(reader: Any, brand: str, chat_id: str, key: str) -> str:
    """서명 주소 한 번(같은 공유 양동이 · 429 · 기다림 상한). 응답 꼴이 다르면 :class:`FetchError`."""
    path = FILE_PATH.format(chat=quote(chat_id, safe=""))
    try:
        data = reader._get(brand, path, {"key": key}, BUCKET_MESSAGE)  # noqa: SLF001 — 같은 패키지 읽기 도우미
    except ChannelReadError as exc:
        raise FetchError(f"signed_url_{exc.status or 'error'}") from None
    url = next((data.get(name) for name in _URL_KEYS if isinstance(data.get(name), str)), "")
    if not url.startswith("https://"):
        raise FetchError("signed_url_shape")
    return url


def fetch_bytes(reader: Any, brand: str, chat_id: str, ref: FileRef, *, timeout: float,
                transport: Optional[Callable[..., Any]] = None, max_bytes: int = MAX_BYTES) -> bytes:
    """파일 하나의 바이트(메모리). ``max_bytes`` 를 넘으면 ``FetchError('too_big')`` — 나머지는 받지 않는다.

    Raises:
        FetchError: 서명 주소 · 내려받기 실패(까닭 코드만).
    """
    url = _signed_url(reader, brand, chat_id, ref.key)
    get = transport or requests.get
    try:
        response = get(url, stream=True, timeout=timeout)
    except requests.RequestException as exc:
        raise FetchError(f"download_{type(exc).__name__}") from None
    try:
        status = int(getattr(response, "status_code", 0) or 0)
        if not 200 <= status < 300:
            raise FetchError(f"download_http_{status}")
        chunks: list[bytes] = []
        size = 0
        for chunk in response.iter_content(chunk_size=_CHUNK):
            size += len(chunk)
            if size > max_bytes:
                raise FetchError("too_big")
            chunks.append(chunk)
        return b"".join(chunks)
    except requests.RequestException as exc:
        raise FetchError(f"download_{type(exc).__name__}") from None
    finally:
        close = getattr(response, "close", None)
        if callable(close):
            close()
