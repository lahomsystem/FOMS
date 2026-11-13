"""초안 재료 읽기 — 상담 글을 원문과 함께 읽기 · 매체 · 선점한 손님 글이 아직 마지막인가 · 두뇌 재료 · 메모 글.

:mod:`.drafting`(초안 차례 한 바퀴)이 쓴다 — 500줄 상한으로 나눴다(checks · checks_read 와 같은 꼴). 플랜 C3-1 · 설계서
4절 3 · 4 · 7 · 8. 채널톡은 GET 만, DB 는 없다.

- **원문은 메모리에만**: 감시용 :meth:`.channel_read.OpenApiReader.read_messages` 는 원문을 버린다. 초안 재료는 원문이 있어야
  해서 같은 GET(공유 양동이 · 429 · 기다림 상한 그대로)을 직접 부르고, 파생 칸은 감시와 같은 규칙(:func:`.channel_read
  .derive_message`)으로 낸다. 원문은 표 · 로그 · repr 에 두지 않는다.
- **재료(R1-12)**: 공개 손님 · 직원 글만 — 내부 메모 · 우리 AI 메모 · 기록 · 봇(자동 안내) · 확인코드 글은 뺀다. 첨부는
  모델이 못 보니 왔다는 표시만 붙인다(R1-13). 비공개 메모 글은 보내기 전 검사의 '비공개 메모 섞임' 재료로만 쓴다.
- **스토어 상품 문의 줄**: 손님이 네이버 스토어 상품 화면에서 [문의하기]를 누르면 톡톡 봇이 '<상품 링크>에 대한
  문의입니다.' 한 줄을 먼저 보낸다. 봇 글이지만 손님이 무엇을 묻는지 알려 주므로 상품 이름만 ``[스토어 상품 문의]``
  줄로 싣는다(:func:`store_product`) — 초안 · 견적 뽑기 · 물건 찾기가 같은 상품을 본다(사장님 11-13 '어떤 제품을
  문의했는지 통합적으로'). 대화가 길어 잘려도 마지막 상품 문의 줄은 남긴다(:func:`conversation`).
- **매체**: 상담 정보의 ``source.medium.mediumType``. 모르면 ``None`` — 검사가 톡톡 규칙(막는 쪽)을 더한다.
"""

from __future__ import annotations

import datetime
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Mapping, Optional, Sequence
from urllib.parse import quote

from foms.services.cs_agent.brain_prompt import ROLE_STORE, SPEAKERS
from foms.services.cs_agent.channel_read import (
    MESSAGE_PAGE_LIMIT,
    ChannelRateLimited,
    ChannelReadError,
    DerivedMessage,
    channel_for_brand,
    derive_message,
)
from foms.services.cs_agent.checks_rules import is_naver_talk
from foms.services.cs_agent.image_files import FileRef, parse_files
from foms.services.cs_agent.masking import mask
from foms.services.cs_agent.read_budget import BUCKET_MESSAGE

logger = logging.getLogger(__name__)

__all__ = [
    "CONVERSATION_LIMIT", "FILE_NOTE", "HANDOFF_MEMO_HEAD", "MEDIUM_EMAIL", "MEMO_CODE_HEADS", "MEMO_DRAFT_HEAD",
    "MEMO_HEAD", "MEMO_IMAGE_HEAD", "MEMO_NOTE_HEAD", "MEMO_QUOTE_HEAD",
    "SKIP_HUMAN_REPLIED", "SKIP_NOT_VISIBLE", "SKIP_NO_TEXT", "SKIP_PHOTO_ONLY", "SKIP_STALE", "ChatLine", "conversation",
    "customer_texts",
    "freshness",
    "memo_draft", "memo_snippets", "memo_text", "no_text_reason", "parse_lines", "public_turn", "read_lines",
    "read_medium", "store_product",
]

CONVERSATION_LIMIT = 30  # 두뇌에 넣는 최근 공개 글 수(설계서 5절 '최근 30개 안팎')
FILE_NOTE = "(사진 · 파일 첨부)"  # 모델은 첨부를 못 본다 — 왔다는 것만 알린다(R1-13)
#: 내부 메모 꼴 — PC 시범과 같다(직원이 같은 것을 본다). 첫 줄은 우리 AI 메모를 알아보는 표지이기도 하다.
MEMO_HEAD = "[AI 초안 · 손님에게 보내지 않음 · 직원이 고쳐서 보내 주세요]"
MEMO_DRAFT_HEAD = "■ 손님께 보낼 답(초안)"
MEMO_NOTE_HEAD = "■ 직원 참고(손님에게 보내지 마세요)"
#: 넘김 메모(초안 없음 — :mod:`.handoff_memo`)의 첫 줄. 'AI 냐' 한 줄 메모(``[AI 초안 없음]``)와 앞이 겹치지 않는다.
HANDOFF_MEMO_HEAD = "[AI 초안 없음 · 직원이 직접 답해 주세요]"
#: 직원 참고 칸에 코드가 붙이는 견적 계산 줄의 머리(C10-6) — 계산기 값 · 제품 이름이라 비공개 메모 섞임 재료에서 뺀다.
MEMO_QUOTE_HEAD = "[견적 계산"
#: 직원 참고 칸에 코드가 붙이는 그림 읽기 줄의 머리(설계서 17.11 (d)) — 숫자 · 정한 말뿐이라 같은 까닭으로 뺀다.
MEMO_IMAGE_HEAD = "[그림 읽기"
MEMO_CODE_HEADS = (MEMO_QUOTE_HEAD, MEMO_IMAGE_HEAD)
MEDIUM_EMAIL = "email"
#: 그대로 믿는 매체 이름(웹 · 이메일). ``app`` 은 카카오 · 톡톡 · 인스타가 mediumId 로만 갈려 모름으로 둔다.
_PLAIN_MEDIA = frozenset({"native", MEDIUM_EMAIL})
_MEDIUM = re.compile(r"[A-Za-z0-9_.-]{1,40}")
#: 상담원 id 꼴 — 빈칸 없는 ASCII 64자까지(꼴이 아니면 두지 않는다).
_PERSON_ID = re.compile(r"[\x21-\x7e]{1,64}")
#: 톡톡 상품 문의 봇 글의 글 덩어리(``blocks`` 의 text 값) — 스마트스토어 상품 링크 + '에 대한 문의입니다.'(11-13 라홈 지난
#: 상담 728줄이 모두 이 꼴). 상품 이름만 꺼낸다(링크 · 상품 번호는 싣지 않는다).
_STORE_BLOCK = re.compile(r'<link type="url" value="https://(?:m\.)?smartstore\.naver\.com/[^"<>]*">'
                          r"([^<>\n]{1,120})</link>\s?에 대한 문의입니다\.?")
#: 글 덩어리가 없을 때(Open API 꼴이 다르면) — 봇의 plainText 한 줄 전체가 이 꼴일 때만.
_STORE_PLAIN = re.compile(r"([^\n]{1,120}?)\s?에 대한 문의입니다\.?")
#: 건너뜀 코드 — 그사이 손님이 더 씀(선점한 글이 마지막이 아님) · 공개 직원 글이 옴 · 손님 글에 글자 없음(사진만 · 빈 글).
SKIP_STALE, SKIP_HUMAN_REPLIED = "stale", "human_replied"
#: 선점한 손님 글이 Open API 읽기에 아직 안 보임(수신 기록이 먼저 옴) — 지난 초안이 아니라 다시 집을 실패다(검수 R13-6).
SKIP_NOT_VISIBLE = "not_visible"
SKIP_PHOTO_ONLY, SKIP_NO_TEXT = "photo_only", "no_text"


@dataclass(frozen=True)
class ChatLine:
    """상담 글 하나 — 파생 칸(:class:`.channel_read.DerivedMessage`) + 원문. 원문은 이 바퀴 메모리에만 있다(repr 에도 없다).

    ``person_id`` 는 공개 직원 글을 쓴 상담원 id(채널톡 ``personId`` — 사례 기억의 '직접 답한 상담원', ADMIN 만 본다)다.
    ``request_id`` 는 글을 쓴 쪽이 붙인 채널톡 ``requestId``(꼴이 맞을 때만) — [보내기] 결과를 모를 때 맞추는 표지다(C10-3).
    ``files`` 는 손님 공개 글의 파일 정보(그림 읽기 — 설계서 17.11 (a))다. 파일 key 는 이 바퀴 메모리에만 있다.
    ``store_product`` 는 톡톡 상품 문의 봇 글이면 그 상품 이름(:func:`store_product`), 아니면 빈 글이다.
    """

    meta: DerivedMessage
    text: str = field(repr=False)
    person_id: Optional[str] = field(default=None, repr=False)
    request_id: Optional[str] = field(default=None, repr=False)
    files: tuple[FileRef, ...] = field(default=(), repr=False)
    store_product: str = field(default="", repr=False)

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
    channel_for_brand(brand)  # 모르는 브랜드는 읽기 전에 거절(ValueError)
    data = _get(reader, brand, f"{_chat_path(chat_id)}/messages", {"limit": MESSAGE_PAGE_LIMIT, "sortOrder": "desc"})
    return sorted(parse_lines(brand, chat_id, data.get("messages")), key=lambda line: line.key)


def parse_lines(brand: str, chat_id: str, items: Any) -> list[ChatLine]:
    """Open API 글 목록 한 쪽(``messages``) → 글들(받은 차례 그대로 — 꼴이 틀린 글 · 다른 상담 글은 뺀다).

    :func:`read_lines` 와 전체 대화 읽기(:mod:`.full_conversation`)가 같이 쓴다.

    Raises:
        ValueError: 모르는 브랜드.
    """
    channel = channel_for_brand(brand)
    lines: list[ChatLine] = []
    for item in items if isinstance(items, list) else []:
        if not isinstance(item, Mapping):
            continue
        meta, _reason = derive_message({"chatType": "userChat", "chatId": chat_id, "channelId": channel, **item},
                                       expected_brand=brand)
        if meta is not None and meta.chat_id == chat_id:
            text, person, request = item.get("plainText"), item.get("personId"), item.get("requestId")
            person_id = str(person).strip() if meta.is_answer and person is not None else ""
            files = parse_files(meta.message_id, item) if meta.is_customer_signal and meta.has_file else ()
            store = store_product(item) if meta.person_type == "bot" and not (meta.is_private or meta.is_log) else ""
            lines.append(ChatLine(meta, text if isinstance(text, str) else "",
                                  person_id if _PERSON_ID.fullmatch(person_id) else None,
                                  request if isinstance(request, str) and _PERSON_ID.fullmatch(request) else None,
                                  files, store))
    return lines


def store_product(item: Mapping[str, Any]) -> str:
    """톡톡 상품 문의 봇 글(채널톡 글 dict) → 상품 이름. 그 꼴이 아니면 빈 글.

    글 덩어리(``blocks``)가 있으면 스마트스토어 링크가 든 꼴만 믿는다. 덩어리가 없을 때만 ``plainText`` 한 줄 전체가
    '…에 대한 문의입니다.' 꼴인지 본다. 손님은 봇 글을 쓸 수 없다 — 부르는 쪽이 봇 공개 글에만 부른다.
    """
    blocks = item.get("blocks")
    if isinstance(blocks, list) and blocks:
        values = [b.get("value") for b in blocks if isinstance(b, Mapping) and b.get("type") == "text"]
        hit = next((m for m in (_STORE_BLOCK.fullmatch(v.strip()) for v in values if isinstance(v, str)) if m), None)
    else:
        plain = item.get("plainText")
        hit = _STORE_PLAIN.fullmatch(plain.strip()) if isinstance(plain, str) else None
    return " ".join(hit.group(1).split()) if hit else ""


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
    """선점한 손님 글이 아직 마지막 손님 글이고 그 뒤 공개 직원 글이 없으면 ``None``, 아니면 건너뜀 코드.

    선점한 글이 읽은 글에 아직 없으면 :data:`SKIP_NOT_VISIBLE`(채널톡 읽기가 늦음 — 다시 집는다), 그 글 뒤에 더 새 손님 글이
    보일 때만 :data:`SKIP_STALE` 이다.
    """
    customers = [line for line in lines if line.meta.is_customer_signal]
    if claimed_id not in {line.meta.message_id for line in customers}:
        return SKIP_NOT_VISIBLE
    if customers[-1].meta.message_id != claimed_id:
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


def public_turn(line: ChatLine) -> Optional[tuple[str, str]]:
    """글 하나 → (말한 사람, 글) — 공개 손님 · 직원 글 + 톡톡 상품 문의 줄(``store`` · 상품 이름만)뿐(내부 메모 · 기록 · 그 밖
    봇 · 확인코드 글 · 빈 글은 ``None``). 첨부는 왔다는 표시(:data:`FILE_NOTE`)만 붙인다. 두뇌 재료(:func:`conversation`)와
    전체 대화(:mod:`.full_conversation`)가 같은 규칙이다."""
    meta = line.meta
    if meta.is_private or meta.is_log or meta.is_code_message:
        return None
    if line.store_product:
        return ROLE_STORE, line.store_product
    if meta.person_type not in SPEAKERS:
        return None
    text = "\n".join(part for part in (line.text.strip(), FILE_NOTE if meta.has_file else "") if part)
    return (meta.person_type, text) if text else None


def conversation(lines: Sequence[ChatLine]) -> list[tuple[str, str]]:
    """두뇌 재료 — 공개 손님 · 직원 글 + 상품 문의 줄(내부 메모 · 기록 · 그 밖 봇 · 확인코드 글을 뺀다), 최근
    :data:`CONVERSATION_LIMIT` 개. 마지막 상품 문의 줄이 앞에서 잘리면 맨 앞에 남긴다 — 무엇을 묻는지는 끝까지 둔다."""
    turns = [turn for turn in (public_turn(line) for line in lines) if turn is not None]
    recent = turns[-CONVERSATION_LIMIT:]
    store = [turn for turn in turns if turn[0] == ROLE_STORE]
    if store and store[-1] not in recent:
        recent = [store[-1], *turns[-(CONVERSATION_LIMIT - 1):]]
    return recent


def customer_texts(lines: Sequence[ChatLine]) -> list[str]:
    """손님 글(공개 · 글 있는 것) + 손님이 문의한 스토어 상품 이름 — 숫자 검사 '같은 값'이 손님이 말한 치수 · 개수를 허용
    목록에 더할 때(:mod:`.checks_same`)와 물건 찾기 재료(:mod:`.drafting_pass`)로 쓴다."""
    return [line.store_product or line.text for line in lines
            if (line.store_product or (line.meta.is_customer_signal and not line.meta.is_private and line.text.strip()))]


def memo_snippets(lines: Sequence[ChatLine]) -> list[str]:
    """비공개 메모 글(직원 내부 메모 · 우리 AI 메모의 직원 참고 칸) — 초안에 섞이면 검사가 막는다(R1-12).

    우리 AI 메모(넘김 메모 포함)는 직원 참고 칸만 넣는다 — 같은 물음에 같은 답이 다시 나오는 것까지 막지 않게. 그 칸의 견적 계산 · 그림 읽기
    줄(:data:`MEMO_CODE_HEADS` — 코드가 쓴 계산기 값 · 읽은 범위)도 뺀다 — 다음 초안이 같은 제품 이름 · 값을 쓰는 것을 막지 않게.
    """
    out: list[str] = []
    for line in lines:
        if not line.meta.is_private or line.meta.is_log or not line.text.strip():
            continue
        text = line.text
        if text.lstrip().startswith((MEMO_HEAD, HANDOFF_MEMO_HEAD)):
            text = text.split(MEMO_NOTE_HEAD, 1)[1] if MEMO_NOTE_HEAD in text else ""
            text = "\n".join(part for part in text.split("\n") if not part.lstrip().startswith(MEMO_CODE_HEADS))
        out.append(text)
    return out


def memo_text(draft: str, staff_note: str) -> str:
    """내부 메모 글 — 첫 줄 표지 · 손님께 보낼 답 · 직원 참고(한 번 가려서 싣고, 비었으면 '없음').

    넘김 까닭은 이 메모에 싣지 않는다 — 넘긴 차례는 따로 넘김 메모(:mod:`.handoff_memo`, 처음 끔)다.
    """
    note = mask(staff_note).strip() if staff_note.strip() else ""
    return "\n".join((MEMO_HEAD, MEMO_DRAFT_HEAD, draft.strip(), MEMO_NOTE_HEAD, note or "없음"))


def memo_draft(text: str) -> Optional[str]:
    """우리 AI 메모(:func:`memo_text` 꼴)의 '손님께 보낼 답' 칸 — [보내기]가 보낼 글의 정본이다(DB 에는 가린 사본만 있다).

    첫 줄 표지 · 답 머리 · 직원 참고 머리가 모두 있어야 한다(초안에는 '직원 참고' 낱말이 검사로 막혀 끝이 헷갈리지 않는다).
    꼴이 아니거나 답이 비었으면 ``None``.
    """
    body = (text or "").replace("\r\n", "\n")
    if not body.lstrip().startswith(MEMO_HEAD):
        return None
    head = f"\n{MEMO_DRAFT_HEAD}\n"
    start = body.find(head)
    end = body.find(f"\n{MEMO_NOTE_HEAD}", start + len(head)) if start >= 0 else -1
    if end < 0:
        return None
    return body[start + len(head):end].strip() or None
