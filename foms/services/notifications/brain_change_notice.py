"""문장으로 고치기 반영 알림 — 알림 종류 · 제목 · 글 · 누르면 열 주소(설계서 2026-11-18-brain-sentence-change 4절 '알림').

[이대로 고치기]가 끝나면 넣은 사람에게 FOMS 안 알림 한 줄(``Notification`` — 종류 :data:`BRAIN_CHANGE_REQUEST_TYPE`,
``target_user_id`` = 넣은 사람, 주문 없음)을 만든다(:mod:`foms.services.brain.change_request_apply`). **폰 알림(푸시)은 보내지
않는다** — 본인이 방금 한 일이다(이 종류는 폰 보내기 줄에 세우지 않는다).

- 제목 :data:`TITLE`('문장으로 고치기'). 글 첫 줄은 ``[문장으로 고치기] /brain/requests/<번호>``(알림 목록 바로가기가 이 꼴에서
  주소를 읽는다 — :func:`request_link`), 둘째 줄은 '<N>곳을 고쳤어요'(승인 대기가 있으면 ' · <M>곳은 승인을 기다려요').
- 넣은 문장 · 고친 글 · 항목 이름은 싣지 않는다(번호 · 수만).
- 이 모듈은 다른 서비스를 import 하지 않는다(``brain_ask_push.py`` 와 같은 꼴).
"""
from __future__ import annotations

import re
from typing import Any, Optional

__all__ = ["BRAIN_CHANGE_REQUEST_TYPE", "REQUEST_LINK", "TITLE", "first_line", "notice_message", "notice_text",
           "request_link", "request_path"]

BRAIN_CHANGE_REQUEST_TYPE = "BRAIN_CHANGE_REQUEST"
TITLE = "문장으로 고치기"
REQUEST_LINK = "/brain/requests"
_HEAD = "[문장으로 고치기]"
_LINK = re.compile(r"^\[문장으로 고치기\] (/brain/requests/(\d{1,12}))$", re.M)


def request_path(request_id: int) -> str:
    """묶음 화면 주소(같은 출처)."""
    return f"{REQUEST_LINK}/{int(request_id)}"


def first_line(request_id: int) -> str:
    """알림 글 첫 줄 ``[문장으로 고치기] /brain/requests/<번호>``."""
    return f"{_HEAD} {request_path(request_id)}"


def notice_text(applied: int, pending: int) -> str:
    """'<N>곳을 고쳤어요'(+ ' · <M>곳은 승인을 기다려요')."""
    text = f"{int(applied)}곳을 고쳤어요"
    return f"{text} · {int(pending)}곳은 승인을 기다려요" if pending else text


def notice_message(request_id: int, applied: int, pending: int) -> str:
    """알림 글 — 주소 줄 + 수 줄."""
    return "\n".join((first_line(request_id), notice_text(applied, pending)))


def request_link(message: Any) -> Optional[str]:
    """알림 글의 묶음 화면 주소(알림 목록 바로가기) — 꼴이 아니면 ``None``."""
    found = _LINK.search(str(message or ""))
    return found.group(1) if found else None
