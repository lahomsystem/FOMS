"""상담 전체 대화(설계서 17.11.2) 시험 재료 — 쪽을 넘기는 가짜 채널톡 · 합성 긴 상담.

손님 글 · 전화 꼴 숫자 · 금액은 두지 않는다(글은 모두 '합성 글 N' 꼴). 네트워크 없음.
"""

from __future__ import annotations

import datetime
from typing import Any, Optional
from urllib.parse import unquote

from foms.services.cs_agent import settings as st
from tests.support.cs_agent_fakes import FakeResponse, api_message, at
from tests.support.cs_image_support import FileStore, ImageChannel

START = at(1, 9)  # 11-01 09:00 KST — 긴 상담의 첫 글


class PagedChannel(ImageChannel):
    """쪽을 넘기는 가짜 채널톡 — 글 목록은 새 글부터 ``limit`` 개와 응답 ``nextCursor`` · ``hasNext``(``style='since'`` 면 옛 판
    ``next`` 만). ``fail`` 은 몇 번째 글 목록 부르기를 404 로 낼지(``0`` 이면 모두). 부른 글 목록 칸은 ``asks`` 에 남는다.
    그림 서명 주소 · 상담 정보는 :class:`ImageChannel` 그대로다."""

    def __init__(self, store: Optional[FileStore] = None, *, style: str = "cursor", fail: Optional[int] = None) -> None:
        super().__init__(store or FileStore())
        self.style, self.fail, self.asks = style, fail, []

    def __call__(self, url, *, params, headers, timeout):
        parts = url.split("/open/", 1)[1].split("/")
        if len(parts) != 3 or parts[2] != "messages":
            return super().__call__(url, params=params, headers=headers, timeout=timeout)
        self.asks.append(dict(params))
        if self.fail is not None and self.fail in (0, len(self.asks)):
            return FakeResponse(404)
        newest = sorted(self.messages.get(unquote(parts[1]), []), key=lambda m: m["createdAt"], reverse=True)
        start = int(params.get("cursor") or params.get("since") or 0)
        end = start + int(params["limit"])
        body: dict[str, Any] = {"messages": newest[start:end]}
        more = end < len(newest)
        if self.style == "cursor":
            body.update(nextCursor=str(end) if more else None, hasNext=more)
        elif more:
            body["next"] = str(end)
        return FakeResponse(200, body)


def long_chat(count: int, *, start: datetime.datetime = START, prefix: str = "m") -> list[dict]:
    """손님 · 직원이 번갈아 쓴 합성 글 ``count`` 개(1분 간격, 글 ``합성 글 NNN``)."""
    return [api_message(f"{prefix}-{i:03d}", start + datetime.timedelta(minutes=i), "user" if i % 2 == 0 else "manager",
                        f"합성 글 {i:03d}") for i in range(count)]


def cfg(**values: Any) -> dict[str, Any]:
    """패널 값(처음 값 + 바꾼 칸) — ``.get`` 만 쓰는 읽기에 넘긴다."""
    return {**st.DEFAULTS, **values}
