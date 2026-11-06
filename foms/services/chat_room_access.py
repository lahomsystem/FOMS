"""사내 채팅 접근 판정 한 곳 — Socket.IO 채팅 이벤트와 채팅 파일 받기가 같이 쓴다.

예전 구멍 두 개(설계서 FCOMM-01 §6.4, 사용자 결정 D19 — 모든 직원에게 적용)와 프리랜서 옆길(§6.3 겹 5)을 닫는다.

- 실시간 방: 개인 알림 방 ``user_<id>`` 는 **본인만**, 채팅방(숫자 id)은 **그 방 회원만** 들어간다. 예전에는 아무 방
  이름이나 들어갈 수 있어 남의 개인 방에서 그 사람의 실시간 알림 · 채팅 사본을 받았다.
- 채팅 파일 받기 · 미리보기: 저장소 key 가 ``chat/`` 로 시작하고, 그 key 를 처음 올린 첨부 줄의 방에 내가 회원일
  때만 서명한다. 예전에는 아무 key 에나 서명해 채팅과 무관한 주문 파일도 받았다. 같은 key 를 내 방 메시지에
  끼워 넣어도(``file_info.key`` 는 손님이 보내는 값) 처음 올린 방이 주인이라 열리지 않는다.
- 켜진 프리랜서는 채팅을 쓰지 않는다(이벤트 · 파일 모두 거부). 개인 알림 방만 남는다.

시험: tests/security/test_socket_room_membership.py · tests/security/test_chat_file_key_scope.py
"""
from __future__ import annotations

from typing import Any, Iterable, Optional

from foms.services.auth.freelancer_scope import is_freelancer_user
from foms.services.sales_commission.links import cached_snapshot
from models import ChatAttachment, ChatMessage, ChatRoomMember

#: 채팅 업로드가 쓰는 저장소 key 접두어(``storage.upload_chat_file`` · 직접 올리기 세션 모두 ``chat/...``).
CHAT_KEY_PREFIX = "chat/"
#: 개인 알림 방 이름 접두어(연결 때 서버가 넣는다 — ``user_<id>``).
USER_ROOM_PREFIX = "user_"

DENY_LOGIN = "인증이 필요합니다."
DENY_CHAT_CLOSED = "채팅을 쓸 수 없는 계정입니다."
DENY_NOT_MEMBER = "채팅방에 접근할 권한이 없습니다."
DENY_FILE_NOT_FOUND = "파일을 찾을 수 없습니다."


def user_room(user_id: Any) -> str:
    """개인 알림 방 이름."""
    return f"{USER_ROOM_PREFIX}{int(user_id)}"


def parse_chat_room_id(value: Any) -> Optional[int]:
    """손님이 보낸 방 값 → 채팅방 id(양의 정수). 숫자가 아니면(``user_3`` 같은 방 이름 포함) None."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if value > 0 else None
    text = str(value or "").strip()
    if not text.isdigit():
        return None
    number = int(text)
    return number if number > 0 else None


def chat_closed_for(user: Any) -> bool:
    """채팅을 못 쓰는 계정인가 — 지금은 켜진 프리랜서."""
    return is_freelancer_user(user)


def is_chat_member(db: Any, room_id: Any, user_id: Any) -> bool:
    """``user_id`` 가 채팅방 ``room_id`` 의 회원인가(``send_message`` 와 같은 판정)."""
    rid = parse_chat_room_id(room_id)
    if rid is None or user_id is None:
        return False
    return db.query(ChatRoomMember.id).filter(
        ChatRoomMember.room_id == rid,
        ChatRoomMember.user_id == int(user_id),
    ).first() is not None


def chat_room_denial(db: Any, user: Any, room_value: Any) -> tuple[Optional[int], Optional[str]]:
    """채팅 이벤트(방 들어가기 · 보내기 · 입력 중 · 읽음) 판정.

    Returns:
        ``(room_id, None)`` 허용, ``(None, 이유)`` 거부.
    """
    if user is None or getattr(user, "is_active", None) is False:
        return None, DENY_LOGIN
    if chat_closed_for(user):
        return None, DENY_CHAT_CLOSED
    room_id = parse_chat_room_id(room_value)
    if room_id is None or not is_chat_member(db, room_id, user.id):
        return None, DENY_NOT_MEMBER
    return room_id, None


def chat_member_fanout_ids(db: Any, room_id: int, exclude_user_id: Any, members: Iterable[Any]) -> list[int]:
    """새 메시지 사본을 개인 방으로 보낼 회원 — 보낸 사람 · 켜진 프리랜서는 뺀다.

    지정 뒤에도 직원이 프리랜서를 방에 다시 넣을 수 있으므로 보낼 때 한 번 더 거른다(검수 원장 A5).
    """
    freelancers = cached_snapshot(db).active_ids
    out: list[int] = []
    for member in members:
        uid = int(member.user_id)
        if exclude_user_id is not None and uid == int(exclude_user_id):
            continue
        if uid in freelancers or uid in out:
            continue
        out.append(uid)
    return out


def chat_key_room_id(db: Any, storage_key: str) -> Optional[int]:
    """채팅 파일 key → 그 key 를 **처음** 올린 첨부 줄의 방 id. 채팅 key 가 아니거나 첨부 줄이 없으면 None."""
    key = str(storage_key or "")
    if not key.startswith(CHAT_KEY_PREFIX):
        return None
    row = (
        db.query(ChatMessage.room_id)
        .join(ChatAttachment, ChatAttachment.message_id == ChatMessage.id)
        .filter(ChatAttachment.storage_key == key)
        .order_by(ChatAttachment.id.asc())
        .first()
    )
    return int(row[0]) if row is not None else None


def chat_file_denial(db: Any, user: Any, storage_key: str) -> Optional[tuple[int, str]]:
    """채팅 파일 받기 · 미리보기 판정.

    Returns:
        거부면 ``(HTTP 상태, 이유)``, 허용이면 None. 모르는 key · 회원이 아닌 방의 파일은 둘 다 404 다
        (파일이 있는지 알리지 않는다). 켜진 프리랜서는 403(채팅이 닫힌 계정).
    """
    if user is None or getattr(user, "is_active", None) is False:
        return 403, DENY_LOGIN
    if chat_closed_for(user):
        return 403, DENY_CHAT_CLOSED
    room_id = chat_key_room_id(db, storage_key)
    if room_id is None or not is_chat_member(db, room_id, user.id):
        return 404, DENY_FILE_NOT_FOUND
    return None


__all__ = [
    "CHAT_KEY_PREFIX",
    "USER_ROOM_PREFIX",
    "chat_closed_for",
    "chat_file_denial",
    "chat_key_room_id",
    "chat_member_fanout_ids",
    "chat_room_denial",
    "is_chat_member",
    "parse_chat_room_id",
    "user_room",
]
