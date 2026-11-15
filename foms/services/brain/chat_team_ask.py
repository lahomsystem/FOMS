"""물어보기 '모름' 답의 [○○팀에 묻기](목업 BAsk · 사용자 결정 D233 · 점검 w2-19) — 그 질문(가린 글)을 답이 가리킨 팀의 켜진
우리 직원에게 **FOMS 안 알림**으로 보낸다(채널톡 아님).

- 묻는 사람 **자기 질문**만 · '모름' 답이고 물을 곳이 **팀**(:data:`.constants.TEAMS` — 사장님 · 관리자 · 주문 화면은 팀이 아니다)일
  때만. 같은 질문은 **한 번만**(이미 보냈으면 다시 만들지 않고 ``already``).
- 받는 사람: 그 팀(:func:`foms.services.notifications.recipients.team_condition` — 팀 표기 정규화)의 켜진 우리 직원
  (:func:`~foms.services.notifications.recipients.broad_recipient_ids` — 협력사 · 켜진 프리랜서 빼고) 가운데 물어보기 화면을 여는
  사람(:func:`.chat_access.page_viewer`), 묻는 사람 자신은 빼고, 번호 순 :data:`MAX_RECIPIENTS` 명까지.
- 사람마다 ``Notification`` 한 줄(``target_user_id``) + 받는 사람 상태(:func:`fan_out_new_notification`) — 지금 알림 장치 그대로.
  알림 글 첫 줄은 물어보기 화면의 그 질문 주소(:func:`question_path` — :func:`team_ask_link` 가 읽는다), 둘째 줄은 가린 질문
  앞부분. 원문 · 답 글 · 손님 정보는 싣지 않는다. 폰 보내기는 부르는 쪽이 커밋한 뒤(:func:`push_after_commit`).
- 받은 사람은 그 질문(가린 글)과 답을 물어보기 화면에서 읽을 수 있다(:func:`was_sent_to` — :mod:`.chat_log` 한 질문 읽기).
"""

from __future__ import annotations

import logging
import re
from typing import Any, Optional

from sqlalchemy import select

from foms.persistence.brain.models import BrainQuestion
from foms.services.brain.chat_access import page_viewer
from foms.services.brain.chat_settings import read_chat_settings
from foms.services.brain.constants import TEAMS
from foms.services.notifications.recipients import broad_recipient_ids, fan_out_new_notification, team_condition
from foms.services.orders.team_labels import team_label
from models import Notification, User
from foms.services.notifications.push_sender import enqueue_push_for_notification

logger = logging.getLogger(__name__)

__all__ = ["BRAIN_ASK_TEAM_TYPE", "MAX_RECIPIENTS", "TeamAskError", "ask_team", "push_after_commit", "question_path",
           "team_ask_link", "team_of", "was_sent_to"]

BRAIN_ASK_TEAM_TYPE = "BRAIN_ASK_TEAM"
MAX_RECIPIENTS = 20
QUESTION_CHARS = 80
_HEAD = "[물어보기]"
_LINK = re.compile(r"^\[물어보기\] (/brain/ask\?question=(\d{1,12}))$", re.M)


class TeamAskError(ValueError):
    """팀에 묻지 못한다 — ``code``: ``not_found``(없거나 내 질문 아님) · ``no_team``(모름 답이 아니거나 팀이 아님) · ``nobody``."""

    def __init__(self, code: str) -> None:
        """코드만."""
        super().__init__(code)
        self.code = code


def team_of(row: Any) -> Optional[str]:
    """[팀에 묻기]를 보일 팀 코드 — '모름' 답이고 물을 곳이 팀일 때만(그 밖 ``None``)."""
    team = getattr(row, "ask_team", None) if getattr(row, "unknown", False) else None
    return team if team in TEAMS else None


def team_name(team: str) -> str:
    """팀 화면 이름('도면팀')."""
    return "회계팀" if team == "ACCOUNTING" else team_label(team)


def question_path(question_id: int) -> str:
    """물어보기 화면의 그 질문 주소(같은 출처)."""
    return f"/brain/ask?question={int(question_id)}"


def _first_line(question_id: int) -> str:
    return f"{_HEAD} {question_path(question_id)}"


def team_ask_link(message: Any) -> Optional[str]:
    """알림 글의 물어보기 질문 주소(폰 알림 · 알림 목록 바로가기) — 꼴이 아니면 ``None``."""
    found = _LINK.search(str(message or ""))
    return found.group(1) if found else None


def _sent(session: Any, question_id: int, user_id: Optional[int] = None) -> bool:
    """이 질문의 팀 묻기 알림이 있나(``user_id`` 를 주면 그 사람 몫)."""
    query = select(Notification.id).where(Notification.notification_type == BRAIN_ASK_TEAM_TYPE,
                                          Notification.message.like(_first_line(question_id) + "\n%"))
    if user_id is not None:
        query = query.where(Notification.target_user_id == int(user_id))
    return session.execute(query.limit(1)).first() is not None


def was_sent_to(session: Any, question_id: int, user_id: int) -> bool:
    """이 사람이 그 질문의 팀 묻기 알림을 받았나(한 질문 읽기 권한)."""
    return _sent(session, question_id, user_id)


def already_sent(session: Any, question_id: int) -> bool:
    """그 질문을 이미 팀에 물었나(단추 '보냈어요')."""
    return _sent(session, question_id)


def _recipients(session: Any, team: str, asker_id: int) -> list[int]:
    """그 팀의 켜진 우리 직원 가운데 물어보기 화면을 여는 사람(묻는 사람 빼고 · 번호 순 · 상한)."""
    condition = team_condition(team)
    if condition is None:
        return []
    ids = sorted(uid for uid in broad_recipient_ids(session, condition) if uid != int(asker_id))
    if not ids:
        return []
    cfg = read_chat_settings(session)
    users = session.execute(select(User).where(User.id.in_(ids))).scalars().all()
    return sorted(int(u.id) for u in users if page_viewer(u, cfg) is not None)[:MAX_RECIPIENTS]


def ask_team(session: Any, *, user: Any, question_id: Any) -> dict[str, Any]:
    """내 '모름' 질문을 그 팀에 알린다(커밋은 부르는 쪽) — ``{"sent", "already", "team", "team_label", "ids"}``.

    Raises:
        TeamAskError: 없음 · 내 질문 아님(``not_found`` — 같은 답) · 팀 아님(``no_team``) · 받을 사람 0(``nobody``).
    """
    if isinstance(question_id, bool) or not isinstance(question_id, int):
        raise TeamAskError("not_found")
    row = session.get(BrainQuestion, question_id)
    if row is None or row.asker_id != int(user.id):
        raise TeamAskError("not_found")
    team = team_of(row)
    if team is None:
        raise TeamAskError("no_team")
    label = team_name(team)
    if already_sent(session, row.id):
        return {"sent": 0, "already": True, "team": team, "team_label": label, "ids": []}
    people = _recipients(session, team, row.asker_id)
    if not people:
        raise TeamAskError("nobody")
    text = " ".join((row.masked_question or "").split())
    short = text[:QUESTION_CHARS] + ("…" if len(text) > QUESTION_CHARS else "")
    message = "\n".join((_first_line(row.id), f"[질문] {short}", "[할 일] 아는 것을 물은 사람에게 알려 주세요"))
    ids = []
    for uid in people:
        note = Notification(notification_type=BRAIN_ASK_TEAM_TYPE, target_type="USER", target_user_id=uid, order_id=None,
                            is_urgent=False, title=f"{label}에 물어본 질문이 왔어요", message=message,
                            created_by_user_id=int(user.id), created_by_name=getattr(user, "name", None), is_read=False)
        session.add(note)
        session.flush()
        fan_out_new_notification(session, note, actor_user_id=int(user.id))
        ids.append(int(note.id))
    logger.info("[회사 지식 물어보기] 팀에 묻기 question=%s team=%s 받는 사람 %d명", row.id, team, len(ids))
    return {"sent": len(ids), "already": False, "team": team, "team_label": label, "ids": ids}


def push_after_commit(session: Any, ids: list[int]) -> None:
    """커밋한 뒤 폰 보내기 줄 세우기 — 지금 알림 장치가 하는 대로(종류가 폰 보내기 목록에 없으면 장치가 보내지 않는다)."""

    for nid in ids:
        try:
            enqueue_push_for_notification(int(nid), db=session)
        except Exception as exc:  # noqa: BLE001 — 폰 보내기 실패가 알림 줄(이미 커밋됨)을 되돌리지 않는다
            session.rollback()
            logger.warning("[회사 지식 물어보기] 팀에 묻기 폰 보내기 줄 세우기 실패 notification=%s error=%s", nid,
                           type(exc).__name__)
