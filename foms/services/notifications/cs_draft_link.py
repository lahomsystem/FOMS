"""AI 상담 초안 알림(``CS_DRAFT_READY`` — 플랜 C10-5)의 바로가기 — 알림 글에서 [보내기] 화면 같은 출처 경로만 꺼낸다.

폰 푸시(:mod:`.push_sender`)와 알림 목록(``foms/api/notifications``)이 같은 함수를 쓴다(같은 곳으로 연다). 알림 글은
:mod:`foms.services.cs_agent.staff_alert` 가 만든다 — 첫 줄 ``[보내기 화면] /cs-agent/turns/<id>/send?c=<상담 id>``. 꼴이 아니면
``None`` 이다(바깥 주소 · ``//`` 로 시작하는 주소는 꼴에 맞지 않는다).
"""

from __future__ import annotations

import re
from typing import Any, Optional

__all__ = ["NOTIFY_DRAFT_READY", "cs_send_link"]

NOTIFY_DRAFT_READY = "CS_DRAFT_READY"
_SEND_PATH = re.compile(r"^\[보내기 화면\] (/cs-agent/turns/\d{1,12}/send\?c=[A-Za-z0-9_-]{1,64})$", re.M)


def cs_send_link(message: Any) -> Optional[str]:
    """알림 글의 [보내기] 화면 경로(같은 출처 ``/cs-agent/...``) — 꼴이 아니면 ``None``."""
    found = _SEND_PATH.search(str(message or ""))
    return found.group(1) if found else None
