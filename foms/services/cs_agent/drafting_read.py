"""초안 재료 읽기 — 상담 글을 원문과 함께 읽기 · 매체 · 선점한 손님 글이 아직 마지막인가 · 두뇌 재료 · 메모 글.

:mod:`.drafting`(초안 차례 한 바퀴)이 쓴다 — 500줄 상한으로 나눴다(checks · checks_read 와 같은 꼴). 플랜 C3-1 · 설계서
4절 3 · 4 · 7 · 8. 채널톡은 GET 만, DB 는 없다.

- **원문은 메모리에만**: 감시용 :meth:`.channel_read.OpenApiReader.read_messages` 는 원문을 버린다. 초안 재료는 원문이 있어야
  해서 같은 GET(공유 양동이 · 429 · 기다림 상한 그대로)을 직접 부르고, 파생 칸은 감시와 같은 규칙(:func:`.channel_read
  .derive_message`)으로 낸다. 원문은 표 · 로그 · repr 에 두지 않는다.
- **재료(R1-12)**: 공개 손님 · 직원 글만 — 내부 메모 · 우리 AI 메모 · 기록 · 봇(자동 안내) · 확인코드 글은 뺀다. 첨부는
  모델이 못 보니 왔다는 표시만 붙인다(R1-13). 비공개 메모 글은 보내기 전 검사의 '비공개 메모 섞임' 재료로만 쓴다.
- **매체**: 상담 정보의 ``source.medium.mediumType``. 모르면 ``None`` — 검사가 톡톡 규칙(막는 쪽)을 더한다.
"""

from __future__ import annotations

import datetime
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Mapping, Optional, Sequence
from urllib.parse import quote

from foms.services.cs_agent.brain_prompt import SPEAKERS
from foms.services.cs_agent.channel_read import (
    MESSAGE_PAGE_LIMIT,
    ChannelRateLimited,
    ChannelReadError,
    DerivedMessage,
    channel_for_brand,
    derive_message,
)
from foms.services.cs_agent.checks_rules import is_naver_talk
from foms.services.cs_agent.masking import mask
from foms.services.cs_agent.read_budget import BUCKET_MESSAGE

logger = logging.getLogger(__name__)

__all__ = [
    "CONVERSATION_LIMIT", "FILE_NOTE", "MEDIUM_EMAIL", "MEMO_DRAFT_HEAD", "MEMO_HEAD", "MEMO_NOTE_HEAD",
    "SKIP_HUMAN_REPLIED", "SKIP_NO_TEXT", "SKIP_PHOTO_ONLY", "SKIP_STALE", "ChatLine", "conversation", "freshness",
    "memo_snippets", "memo_text", "no_text_reason", "read_lines", "read_medium",
]

CONVERSATION_LIMIT = 30  # 두뇌에 넣는 최근 공개 글 수(설계서 5절 '최근 30개 안팎')
FILE_NOTE = "(사진 · 파일 첨부)"  # 모델은 첨부를 못 본다 — 왔다는 것만 알린다(R1-13)
#: 내부 메모 꼴 — PC 시범과 같다(직원이 같은 것을 본다). 첫 줄은 우리 AI 메모를 알아보는 표지이기도 하다.
MEMO_HEAD = "[AI 초안 · 손님에게 보내지 않음 · 직원이 고쳐서 보내 주세요]"
MEMO_DRAFT_HEAD = "■ 손님께 보낼 답(초안)"
MEMO_NOTE_HEAD = "■ 직원 참고(손님에게 보내지 마세요)"
MEDIUM_EMAIL = "email"
#: 그대로 믿는 매체 이름(웹 · 이메일). ``app`` 은 카카오 · 톡톡 · 인스타가 mediumId 로만 갈려 모름으로 둔다.
_PLAIN_MEDIA = frozenset({"native", MEDIUM_EMAIL})
_MEDIUM = re.compile(r"[A-Za-z0-9_.-]{1,40}")
#: 건너뜀 코드 — 그사이 손님이 더 씀(선점한 글이 마지막이 아님) · 공개 직원 글이 옴 · 손님 글에 글자 없음(사진만 · 빈 글).
SKIP_STALE, SKIP_HUMAN_REPLIED = "stale", "human_replied"
SKIP_PHOTO_ONLY, SKIP_NO_TEXT = "photo_only", "no_text"


@dataclass(frozen=True)
class ChatLine:
    """상담 글 하나 — 파생 칸(:class:`.channel_read.DerivedMessage`) + 원문. 원문은 이 바퀴 메모리에만 있다(repr 에도 없다)."""

    meta: DerivedMessage
    text: str = field(repr=False)

    @property
    def key(self) -> tuple[datetime.datetime, str]:
        """시간 순서 열쇠(글 시각 · 메시지 id)."""
        return self.meta.created_at, self.meta.message_id


def _get(reader: Any, brand: str, path: str, params: dict[str, Any]) -> dict[str, Any]:
    """읽기 도우미의 GET 한 번 — 같은 공유 양동이 · 429 · 기다림 상한(감시 루프 도우미면 TERM 때 기다림이 멈춘다)."""
    return reader._get(brand, path, params, BUCKET_MESSAGE)  # noqa: SLF001 — 같은 패키지 읽기 도우미, 원문이 있어야 한다


def _chat_path(chat_id: str) -> str:
    """상담 하나의 Open API 주소(``/open/user-chats/{id}``)."""
    return f"/open/user-chats/{quote(chat_id, safe='')}"


def read_lines(reader: Any, brand: str, chat_id: str) -> list[ChatLine]:
    """상담 최근 글(새 글부터 :data:`~.channel_read.MESSAGE_PAGE_LIMIT` 개)을 원문과 함께 시간순으로.

    Raises:
        ChannelReadError: 읽기 실패(한도는 :class:`~.channel_read.ChannelRateLimited`).
    """
    channel = channel_for_brand(brand)
    data = _get(reader, brand, f"{_chat_path(chat_id)}/messages", {"limit": MESSAGE_PAGE_LIMIT, "sortOrder": "desc"})
    items = data.get("messages")
    lines: list[ChatLine] = []
    for item in items if isinstance(items, list) else []:
        if not isinstance(item, Mapping):
            continue
        meta, _reason = derive_message({"chatType": "userChat", "chatId": chat_id, "channelId": channel, **item},
                                       expected_brand=brand)
        if meta is not None and meta.chat_id == chat_id:
            text = item.get("plainText")
            lines.append(ChatLine(meta, text if isinstance(text, str) else ""))
    return sorted(lines, key=lambda line: line.key)


def read_medium(reader: Any, brand: str, chat_id: str) -> Optional[str]:
    """상담 매체 — 상담 정보의 ``source.medium.mediumType``(설계서 2.9 · 원장 F5-12). 모르면 ``None``(검사는 톡톡 규칙).

    웹(``native``) · ``email`` · 톡톡 꼴 이름만 돌려준다. Open API 의 칸 자리는 스테이징 실측 전이다(원장 Q1) — 칸이
    없으면 늘 ``None`` 이라 이메일을 못 거를 뿐 검사는 막는 쪽으로 닫힌다. 읽기가 실패해도 ``None``(한도 429 만 올린다).

    Raises:
        ChannelRateLimited: 읽기 한도.
    """
    try:
        data = _get(reader, brand, _chat_path(chat_id), {})
    except ChannelReadError as exc:
        if isinstance(exc, ChannelRateLimited):
            raise
        logger.warning("[CS 초안] 상담 매체를 못 읽어 모름으로 둔다 chat=%s status=%s", chat_id, exc.status)
        return None
    chat = data.get("userChat") if isinstance(data.get("userChat"), Mapping) else data
    source = chat.get("source") if isinstance(chat.get("source"), Mapping) else {}
    medium = source.get("medium") if isinstance(source.get("medium"), Mapping) else {}
    kind = medium.get("mediumType")
    if not isinstance(kind, str) or not _MEDIUM.fullmatch(kind.strip()):
        return None
    kind = kind.strip()
    if kind.lower() in _PLAIN_MEDIA:
        return kind.lower()
    return kind if is_naver_talk(kind) else None


def freshness(lines: Sequence[ChatLine], claimed_id: str) -> Optional[str]:
    """선점한 손님 글이 아직 마지막 손님 글이고 그 뒤 공개 직원 글이 없으면 ``None``, 아니면 건너뜀 코드."""
    customers = [line for line in lines if line.meta.is_customer_signal]
    if not customers or customers[-1].meta.message_id != claimed_id:
        return SKIP_STALE
    last = customers[-1].key
    return SKIP_HUMAN_REPLIED if any(line.meta.is_answer and line.key > last for line in lines) else None


def no_text_reason(lines: Sequence[ChatLine]) -> Optional[str]:
    """마지막 공개 직원 글 뒤 손님 글에 글자가 하나도 없으면 건너뜀 코드(사진만 · 빈 글 — 모델은 사진을 못 본다, R1-13)."""
    after = max((i for i, line in enumerate(lines) if line.meta.is_answer), default=-1)
    pending = [line for line in lines[after + 1:] if line.meta.is_customer_signal]
    if any(line.text.strip() for line in pending):
        return None
    return SKIP_PHOTO_ONLY if any(line.meta.has_file for line in pending) else SKIP_NO_TEXT


def conversation(lines: Sequence[ChatLine]) -> list[tuple[str, str]]:
    """두뇌 재료 — 공개 손님 · 직원 글만(내부 메모 · 기록 · 봇 · 확인코드 글을 뺀다), 최근 :data:`CONVERSATION_LIMIT` 개."""
    turns: list[tuple[str, str]] = []
    for line in lines:
        meta = line.meta
        if meta.is_private or meta.is_log or meta.person_type not in SPEAKERS or meta.is_code_message:
            continue
        text = "\n".join(part for part in (line.text.strip(), FILE_NOTE if meta.has_file else "") if part)
        if text:
            turns.append((meta.person_type, text))
    return turns[-CONVERSATION_LIMIT:]


def memo_snippets(lines: Sequence[ChatLine]) -> list[str]:
    """비공개 메모 글(직원 내부 메모 · 우리 AI 메모의 직원 참고 칸) — 초안에 섞이면 검사가 막는다(R1-12).

    우리 AI 메모는 직원 참고 칸만 넣는다 — 같은 물음에 같은 답이 다시 나오는 것까지 막지 않게.
    """
    out: list[str] = []
    for line in lines:
        if not line.meta.is_private or line.meta.is_log or not line.text.strip():
            continue
        text = line.text
        if text.lstrip().startswith(MEMO_HEAD):
            text = text.split(MEMO_NOTE_HEAD, 1)[1] if MEMO_NOTE_HEAD in text else ""
        out.append(text)
    return out


def memo_text(draft: str, staff_note: str) -> str:
    """내부 메모 글 — 첫 줄 표지 · 손님께 보낼 답 · 직원 참고(한 번 가려서 싣고, 비었으면 '없음').

    넘김 · 거절은 메모를 쓰지 않으니(:mod:`.drafting` 설명) 올리는 메모에는 넘김 까닭 줄이 없다.
    """
    note = mask(staff_note).strip() if staff_note.strip() else ""
    return "\n".join((MEMO_HEAD, MEMO_DRAFT_HEAD, draft.strip(), MEMO_NOTE_HEAD, note or "없음"))
