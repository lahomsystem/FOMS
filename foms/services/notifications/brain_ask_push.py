"""물어보기 [○○팀에 묻기] 알림의 폰 알림 — 알림 종류 · 잠금화면 글 · 누르면 열 주소(사용자 결정 D240, 2026-11-15).

[팀에 묻기](:mod:`foms.services.brain.chat_team_ask`)가 그 팀 직원마다 ``Notification``(종류 :data:`BRAIN_ASK_TEAM_TYPE`,
``target_user_id`` = 그 사람, 주문 없음)을 한 줄 만든다. 알림 글 첫 줄은 ``[물어보기] /brain/ask?question=<번호>`` 이고, 폰
발송기(:mod:`.push_sender`)가 이 꼴에서 여는 주소와 꼬리표를 꺼낸다(꼴이 아니면 물어보기 첫 화면).

- 잠금화면: 제목 :data:`BRAIN_ASK_PUSH_TITLE` + 본문 '<○○팀>에 물어본 질문이 왔어요' 뿐 — 질문 글(가린 글이라도) · 묻는 사람 ·
  답 글을 싣지 않는다. 팀 이름은 알림 제목이 코드가 만든 꼴일 때만 읽는다(아니면 일반 글).
- 누르면 ``/brain/ask?question=<번호>``(같은 출처 경로 — 새 화면 · 옛 화면 모두 그 질문 한 건을 보인다).
- 이 모듈은 다른 서비스를 import 하지 않는다(``erp_action_push.py`` 와 같은 꼴) — 발송기와 알림 만들기가 같이 쓴다.
"""
from __future__ import annotations

import re
from typing import Any, Optional

__all__ = [
    "ASK_LINK", "BRAIN_ASK_GENERIC_BODY", "BRAIN_ASK_PUSH_TITLE", "BRAIN_ASK_TEAM_TYPE", "brain_ask_deep_link",
    "brain_ask_push_text", "brain_ask_tag", "is_brain_ask_notification_type", "team_ask_first_line", "team_ask_link",
    "team_ask_title",
]

BRAIN_ASK_TEAM_TYPE = "BRAIN_ASK_TEAM"
BRAIN_ASK_PUSH_TITLE = "회사 지식 물어보기"
BRAIN_ASK_GENERIC_BODY = "우리 팀에 물어본 질문이 왔어요"
ASK_LINK = "/brain/ask"
_HEAD = "[물어보기]"
_LINK = re.compile(r"^\[물어보기\] (/brain/ask\?question=(\d{1,12}))$", re.M)
_TITLE_TAIL = "에 물어본 질문이 왔어요"
#: 알림 제목 꼴 — '<○○팀>에 물어본 질문이 왔어요'(팀 이름은 코드의 팀 표기 — 짧은 한 낱말).
_TITLE = re.compile(r"^(?P<team>[^\s\n]{1,12})에 물어본 질문이 왔어요$")


def is_brain_ask_notification_type(ntype: Any) -> bool:
    """물어보기 [팀에 묻기] 알림인가."""
    return str(ntype or "").strip().upper() == BRAIN_ASK_TEAM_TYPE


def team_ask_first_line(question_id: int) -> str:
    """알림 글 첫 줄 ``[물어보기] /brain/ask?question=<번호>``."""
    return f"{_HEAD} {ASK_LINK}?question={int(question_id)}"


def team_ask_title(team_label: str) -> str:
    """알림 제목 '<○○팀>에 물어본 질문이 왔어요'."""
    return f"{team_label}{_TITLE_TAIL}"


def team_ask_link(message: Any) -> Optional[str]:
    """알림 글의 물어보기 질문 주소(폰 알림 · 알림 목록 바로가기) — 꼴이 아니면 ``None``."""
    found = _LINK.search(str(message or ""))
    return found.group(1) if found else None


def brain_ask_deep_link(message: Any) -> str:
    """누르면 열 같은 출처 경로 — 그 질문, 꼴이 아니면 물어보기 첫 화면."""
    return team_ask_link(message) or ASK_LINK


def brain_ask_push_text(title: Any) -> tuple[str, str]:
    """잠금화면 (제목, 본문) — 본문 '<○○팀>에 물어본 질문이 왔어요'(알림 제목이 그 꼴이 아니면 일반 글)."""
    found = _TITLE.match(str(title or "").strip())
    return BRAIN_ASK_PUSH_TITLE, (team_ask_title(found.group("team")) if found else BRAIN_ASK_GENERIC_BODY)


def brain_ask_tag(message: Any) -> Optional[str]:
    """잠금화면 꼬리표 — 같은 질문의 알림은 하나로 접는다(꼴이 아니면 ``None``)."""
    found = _LINK.search(str(message or ""))
    return f"foms-brain-ask-{found.group(2)}" if found else None
