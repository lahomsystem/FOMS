"""AI 상담 초안 알림(``CS_DRAFT_READY`` — 플랜 C10-5)과 [보내기] · [수정하기] 화면 주소의 꼴 — 만들기 · 읽기를 이 한 곳에 둔다.

- 만들기: :func:`send_path` · :func:`edit_path`(같은 출처 경로 — 초안 메모 링크 버튼 · 직원 알림이 같이 쓴다), :func:`alert_message`
  (알림 글 — 첫 줄 ``[보내기 화면] <경로>``, 손님 글 · 초안 없음).
- 읽기: :func:`cs_send_link`(폰 푸시 · 알림 목록 바로가기 — 같은 함수라 같은 곳을 연다) · :func:`cs_draft_chat`(푸시 꼬리표 — 같은
  상담 알림을 하나로 접는다). 꼴이 아니면 ``None`` 이다(바깥 주소 · ``//`` · 뒤에 다른 값이 붙은 주소는 꼴에 맞지 않는다).
"""

from __future__ import annotations

import re
from typing import Any, Optional

__all__ = ["NOTIFY_DRAFT_READY", "SEND_LINE_HEAD", "alert_message", "cs_draft_chat", "cs_send_link", "edit_path",
           "send_path"]

NOTIFY_DRAFT_READY = "CS_DRAFT_READY"
SEND_LINE_HEAD = "[보내기 화면]"
_SEND_PATH = re.compile(r"^\[보내기 화면\] (/cs-agent/turns/\d{1,12}/send\?c=([A-Za-z0-9_-]{1,64}))$", re.M)


def send_path(turn_id: int, chat_id: str) -> str:
    """[보내기] 화면 같은 출처 경로 — 상담 id(``c``)는 다른 환경의 같은 차례 번호를 거르는 표지다."""
    return f"/cs-agent/turns/{int(turn_id)}/send?c={chat_id}"


def edit_path(turn_id: int, chat_id: str) -> str:
    """[수정하기] 화면 같은 출처 경로."""
    return f"/cs-agent/turns/{int(turn_id)}/edit?c={chat_id}"


def alert_message(path: str, desk_url: str) -> str:
    """직원 알림 글 — 보내기 화면 · 데스크 주소 · 할 일만(손님 글 · 초안 없음)."""
    return "\n".join((f"{SEND_LINE_HEAD} {path}", f"[상담] {desk_url}",
                      "[할 일] 초안을 보고 [보내기] 또는 [수정하기]를 눌러 주세요"))


def cs_send_link(message: Any) -> Optional[str]:
    """알림 글의 [보내기] 화면 경로(같은 출처 ``/cs-agent/...``) — 꼴이 아니면 ``None``."""
    found = _SEND_PATH.search(str(message or ""))
    return found.group(1) if found else None


def cs_draft_chat(message: Any) -> Optional[str]:
    """알림 글의 상담 id — 푸시 꼬리표(같은 상담 알림을 잠금화면에서 하나로 접는다). 꼴이 아니면 ``None``."""
    found = _SEND_PATH.search(str(message or ""))
    return found.group(2) if found else None
