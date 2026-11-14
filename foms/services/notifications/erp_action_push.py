"""AI 할 일 제안 승인 대기 폰 알림 — 알림 종류 · 잠금화면 글 · 누르면 열 주소(설계서 2026-11-14-foms-graft 3.14 · D210).

새 제안 하나를 승인할 수 있는 사람마다 ``Notification``(종류 :data:`ERP_ACTION_PROPOSAL_TYPE`, ``target_user_id`` = 그 사람,
``order_id`` = 그 주문) 한 줄로 만든다(:mod:`foms.services.erp_actions.notify`). 알림 글(``message``)은 한 줄
``<할 일 이름> · 주문 #<번호> · 제안 #<번호>`` 이다 — 종 목록에 그대로 읽히는 글이고, 폰 발송기(:mod:`.push_sender`)가 이 꼴에서
잠금화면 본문과 여는 주소를 꺼낸다(꼴이 아니면 일반 글 · 승인 대기 첫 화면).

- 잠금화면: 제목 :data:`ERP_ACTION_PUSH_TITLE`('AI 제안 승인 대기') + 본문 '<할 일 이름> · 주문 #<번호>' 뿐 — 손님 이름 · 주소 ·
  날짜 · 제안 글을 싣지 않는다.
- 누르면 ``/brain?tab=inbox&proposal=<번호>``(같은 출처 경로 — 화면이 그 제안의 옆 창을 처음부터 연다).
- 이 모듈은 다른 서비스를 import 하지 않는다(``notice_push.py`` 와 같은 꼴) — 발송기와 알림 만들기가 같이 쓴다.
"""
from __future__ import annotations

import re
from typing import Any, Optional

__all__ = [
    "ERP_ACTION_GENERIC_BODY", "ERP_ACTION_PROPOSAL_TYPE", "ERP_ACTION_PUSH_TITLE", "INBOX_LINK", "erp_action_deep_link",
    "erp_action_message", "erp_action_push_text", "erp_action_tag", "is_erp_action_notification_type",
]

ERP_ACTION_PROPOSAL_TYPE = "ERP_ACTION_PROPOSAL"
ERP_ACTION_PUSH_TITLE = "AI 제안 승인 대기"
ERP_ACTION_GENERIC_BODY = "승인할 AI 제안이 있어요"
INBOX_LINK = "/brain?tab=inbox"
#: 할 일 이름 글자 상한(할 일 목록의 화면 이름 — 코드가 정한 말만 온다).
_LABEL_MAX = 40
_MESSAGE = re.compile(r"^(?P<label>[^\n#]{1,40}?) · 주문 #(?P<order>\d{1,12}) · 제안 #(?P<proposal>\d{1,12})$")


def is_erp_action_notification_type(ntype: Any) -> bool:
    """AI 할 일 제안 승인 대기 알림인가."""
    return str(ntype or "").strip().upper() == ERP_ACTION_PROPOSAL_TYPE


def erp_action_message(label: str, order_id: int, proposal_id: int) -> str:
    """알림 글 한 줄 ``<할 일 이름> · 주문 #<번호> · 제안 #<번호>``(이름은 한 줄로 접어 상한에서 자른다)."""
    text = " ".join(str(label or "").replace("#", " ").split())[:_LABEL_MAX] or "AI 제안"
    return f"{text} · 주문 #{int(order_id)} · 제안 #{int(proposal_id)}"


def _parts(message: Any) -> Optional[re.Match[str]]:
    return _MESSAGE.match(str(message or "").strip())


def erp_action_push_text(message: Any) -> tuple[str, str]:
    """잠금화면 (제목, 본문) — 본문 '<할 일 이름> · 주문 #<번호>'(꼴이 아니면 일반 글)."""
    found = _parts(message)
    body = f"{found.group('label')} · 주문 #{found.group('order')}" if found else ERP_ACTION_GENERIC_BODY
    return ERP_ACTION_PUSH_TITLE, body


def erp_action_deep_link(message: Any) -> str:
    """누르면 열 같은 출처 경로 — 그 제안(``/brain?tab=inbox&proposal=<번호>``), 꼴이 아니면 승인 대기 첫 화면."""
    found = _parts(message)
    return f"{INBOX_LINK}&proposal={found.group('proposal')}" if found else INBOX_LINK


def erp_action_tag(message: Any) -> Optional[str]:
    """잠금화면 꼬리표 — 같은 제안의 알림은 하나로 접는다(꼴이 아니면 ``None``)."""
    found = _parts(message)
    return f"foms-erp-action-{found.group('proposal')}" if found else None
