"""[보내기] · [수정하기] 짧은 화면의 재료 — GET 은 보여 주기만 한다(보내지 않고 · 표를 쓰지 않고 · DB 를 쓰지 않는다).

플랜 C10-3 · 설계서 17.2.1(링크 길 — 열기(GET)는 한 번용 표를 쓰지 않는다: 메신저 링크 미리 읽기 대비). 화면이 보일 글은 그 상담의
메모를 Open API 로 다시 읽은 '손님께 보낼 답'이다(DB 에는 가린 사본만 있다). 이 화면을 연 직원 · 그 차례 · 그 메모로 서명한 표를
싣는다 — POST 는 그 표와 CSRF 로만 움직인다.

링크 주소의 상담 id(``c``)가 차례와 다르면 열지 않는다 — 다른 환경(스테이징 · 운영)의 같은 차례 번호로 잘못 들어온 링크가
엉뚱한 상담을 보이지 않게.
"""

from __future__ import annotations

import datetime
import logging
from typing import Any, Optional

from foms.persistence.main.models import CsAgentTurn
from foms.services.cs_agent.case_memory import EDIT_REASONS
from foms.services.cs_agent.channel_read import ChannelReadError, OpenApiReader
from foms.services.cs_agent.drafting_read import freshness, memo_draft, read_lines
from foms.services.cs_agent.edit_detail import MAX_DETAIL, switches
from foms.services.cs_agent.edit_photos import MAX_BYTES as PHOTO_MAX_BYTES, MAX_PHOTOS
from foms.services.cs_agent.memo import memo_allowed
from foms.services.cs_agent.report import desk_link
from foms.services.cs_agent.send import SEND_BRAND
from foms.services.cs_agent.send_auth import issue_send_token
from foms.services.cs_agent.send_flow import MAX_NOTE, MAX_REWRITES, MAX_TEXT, MESSAGES, switch_on, turn_status
from foms.services.cs_agent.send_record import SEND_SENDING, SEND_UNKNOWN_STATE

logger = logging.getLogger(__name__)

__all__ = ["EDIT_REASON_LABELS", "STATUS_LABELS", "screen_view"]

#: 고친 까닭(설계서 17.2 — 틀린 사실 · 약속 · 말투 · 빠짐 · 기타). 코드는 :data:`.case_memory.EDIT_REASONS` 순서.
EDIT_REASON_LABELS: dict[str, str] = dict(zip(EDIT_REASONS, ("틀린 사실", "약속", "말투", "빠짐", "기타")))
STATUS_LABELS = {"sent": "손님께 보냈어요", "discarded": "버린 초안이에요", "superseded": "지난 초안이에요(손님이 더 썼어요)",
                 "staff_replied": "직원이 먼저 답했어요", "checking": "보냈는지 확인하고 있어요"}


def _status_text(row: Any) -> Optional[str]:
    """지금 할 수 없는 까닭 글(할 수 있으면 ``None``)."""
    if row.send_state in (SEND_SENDING, SEND_UNKNOWN_STATE):
        return STATUS_LABELS["checking"]
    if row.send_state == "sent" or row.outcome == "as_is" or row.outcome == "edited":
        return STATUS_LABELS["sent"]
    if row.outcome == "discarded":
        return STATUS_LABELS["discarded"]
    if row.outcome is not None:
        return MESSAGES["already"]
    if row.state != "posted" or not row.memo_message_id:
        return STATUS_LABELS.get(row.state, MESSAGES["not_open"])
    return None


def _detail_view(session: Any) -> Optional[dict[str, Any]]:
    """'왜 고쳤나요(자세히) · 사진' 칸 재료(설계서 17.6.1 (a)) — 칸이 꺼졌으면 ``None``(화면에 칸이 없다). DB 는 읽기만 한다."""
    on = switches(session)
    session.rollback()
    if not on.detail:
        return None
    return {"photos": on.photos, "max_detail": MAX_DETAIL, "max_photos": MAX_PHOTOS, "max_photo_bytes": PHOTO_MAX_BYTES}


def screen_view(session: Any, turn_id: int, user: Any, *, chat_hint: Any, secret_key: Any, now: datetime.datetime,
                reader: Any = None) -> Optional[dict[str, Any]]:
    """화면 재료 — 차례가 없거나 링크의 상담 id 가 다르면 ``None``(404). DB 는 읽기만 한다(읽기 트랜잭션은 닫는다).

    Returns:
        ``{"turn_id", "desk_url", "status": {...}, "blocked": 까닭 글 | None, "draft": 보낼 글 | None, "fresh_note",
        "token", "edit_reasons", "rewrite_left", "max_text", "max_note", "detail"}`` — 상담 글은 보낼 초안(직원이 보낼 글)만
        싣는다. ``detail`` 은 '왜 고쳤나요(자세히) · 사진' 칸 재료(꺼졌으면 ``None``).
    """
    row = session.get(CsAgentTurn, int(turn_id), populate_existing=True)
    session.rollback()
    if row is None or not isinstance(chat_hint, str) or chat_hint != row.chat_id:
        return None
    status = turn_status(row)
    blocked = _status_text(row)
    if blocked is None and (row.brand != SEND_BRAND or not memo_allowed(row.chat_id)):
        blocked = MESSAGES["not_allowed"]
    if blocked is None and not switch_on(session):
        blocked = MESSAGES["switch_off"]
    session.rollback()
    view: dict[str, Any] = {
        "turn_id": row.id, "desk_url": desk_link(row.brand, row.chat_id), "status": status, "blocked": blocked,
        "draft": None, "fresh_note": None, "token": None, "checking": status["send_state"] in (SEND_SENDING,
                                                                                               SEND_UNKNOWN_STATE),
        "edit_reasons": list(EDIT_REASON_LABELS.items()), "rewrite_left": max(0, MAX_REWRITES - status["rewrite_count"]),
        "max_text": MAX_TEXT, "max_note": MAX_NOTE, "detail": None,
    }
    if view["checking"] or blocked is None:
        view["token"] = issue_send_token(secret_key, turn_id=row.id, user_id=int(user.id), memo_id=row.memo_message_id)
    if blocked is not None:
        return view
    view["detail"] = _detail_view(session)
    try:
        lines = read_lines(reader if reader is not None else OpenApiReader(), row.brand, row.chat_id)
    except ChannelReadError as exc:
        logger.warning("[CS 보내기 화면] 상담 글 읽기 실패 turn=%s status=%s", row.id, exc.status)
        view["blocked"], view["token"] = MESSAGES["read_failed"], None
        return view
    memo = next((line for line in lines if line.meta.message_id == row.memo_message_id and line.meta.is_private), None)
    view["draft"] = memo_draft(memo.text) if memo is not None else None
    stale = freshness(lines, row.last_user_message_id)
    if stale:
        view["fresh_note"] = MESSAGES["new_message"]
    return view
