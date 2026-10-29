"""채널톡 읽기 — 채널 id ↔ 브랜드 · 채널톡 글 → 파생 칸 · Open API 읽기(GET 만).

플랜 ``docs/plans/2026-10-27-cs-ai-agent-plan.md`` C1-2 · 설계서 4절 2 · 15.2. 채널톡 쓰기는 없다.

- **최소 보관**: 웹훅 ``entity`` 와 Open API 글은 꼴이 같다 — :func:`derive_message` 가 둘 다 파생 칸으로 바꾸고,
  글 원문은 맺음 · 확인코드 · 약속을 재는 데만 쓰고 버린다. 원문 · 손님 정보는 표에도 로그에도 남기지 않는다.
- **Open API(정본, R1-1)**: 바뀐 상담 목록 · 상담 최근 글을 GET 으로만 읽는다. 채널마다 공유 양동이
  (:mod:`foms.services.cs_agent.read_budget`)로 읽기 몫을 정해 '상담 먼저' 버튼 · 이름표(보내기 쪽) 몫을 남기고,
  429 면 ``Retry-After`` 만큼 그 채널 읽기를 모든 프로세스가 쉰다(R1-16 · R4-17).
- 상태 표(수신 기록 뒤돌아 읽기 · 저장 · 누락 경보)는 :mod:`foms.services.cs_agent.state_store`.

시각은 모두 시간대가 있는 UTC 로 다루고, 표에는 UTC naive 로 둔다(저장소 관례 ``now_utc_naive``).
"""

from __future__ import annotations

import datetime
import logging
import time
from dataclasses import dataclass
from typing import Any, Callable, Iterator, Mapping, Optional
from urllib.parse import quote

import requests

from foms.services.channel_client import _OPEN_API_BASE, _open_api_headers
from foms.services.cs_agent.read_budget import (
    BUCKET_LIST,
    BUCKET_MESSAGE,
    ChannelBudget,
    default_budget,
    note_remaining,
    retry_after_seconds,
)
from foms.services.cs_agent.state import ChatMessage, StaffPromise, detect_promise, is_closing_text
from foms.services.share_consult import parse_consult_message

logger = logging.getLogger(__name__)

__all__ = [
    "CHANNEL_BRANDS",
    "ChannelRateLimited",
    "ChannelReadError",
    "ChatPage",
    "ChatSnapshot",
    "DerivedMessage",
    "OpenApiNotConfigured",
    "OpenApiReader",
    "aware_utc",
    "brand_for_channel",
    "channel_for_brand",
    "derive_message",
    "naive_utc",
]

UTC = datetime.timezone.utc

# ── 브랜드 ↔ 채널 ─────────────────────────────────────────────────────────
#: 채널톡 채널 id → 브랜드. 채널은 브랜드마다 하나이고 스테이징도 같은 채널을 쓴다(설계서 2.4 · 4절 10).
#: 이전엔 코드에 없던 짝이다(원장 F5-4 — '상담 먼저'는 브랜드를 주문에서 읽고 답장만 받은 채널로 쓴다).
#: 값은 ``state.BRAND_HOURS`` · ``channel_client`` Open API 키 이름(``CHANNEL_OPENAPI_KEY_<브랜드>``)과 같다.
CHANNEL_BRANDS: dict[str, str] = {"201824": "LAHOM", "109717": "HAUD"}


def brand_for_channel(channel_id: Any) -> Optional[str]:
    """채널 id 의 브랜드. 모르는 채널이면 ``None`` — 그 글은 감시에 넣지 않는다."""
    return CHANNEL_BRANDS.get(str(channel_id or "").strip())


def channel_for_brand(brand: str) -> str:
    """브랜드의 채널 id.

    Raises:
        ValueError: 모르는 브랜드.
    """
    for channel_id, name in CHANNEL_BRANDS.items():
        if name == brand:
            return channel_id
    raise ValueError(f"모르는 브랜드: {brand!r}")


# ── 글 하나 → 파생 칸 ────────────────────────────────────────────────────
#: 채널톡 id · personType 칸 길이 상한(표 칸 String(64) · String(16)). 넘는 값은 이상한 원본이라 거른다.
_MAX_ID_LEN = 64
_MAX_PERSON_TYPE_LEN = 16
_PRIVATE_OPTIONS = frozenset({"private", "message_option_private"})
_FILE_KEYS = ("files", "attachments")
_CHAT_STATES = frozenset({"opened", "snoozed", "closed"})


@dataclass(frozen=True)
class DerivedMessage:
    """상담 글 하나의 파생 칸 — 글 원문이 없다. 상태 표 한 줄과 같은 칸이다."""

    chat_id: str
    message_id: str
    channel_id: str
    brand: str
    person_type: str  # 'user' | 'manager' | 'bot' (채널톡 값 그대로, 소문자)
    created_at: datetime.datetime  # 시간대 있는 UTC(entity.createdAt)
    is_private: bool = False
    is_log: bool = False
    has_file: bool = False
    is_closing: Optional[bool] = None  # 손님 글만
    is_code_message: bool = False  # 손님 글만
    promise_kind: Optional[str] = None  # 공개 직원 글만
    promise_due_at: Optional[datetime.datetime] = None
    promise_rule: Optional[str] = None

    @property
    def is_customer_signal(self) -> bool:
        """손님 글(확인코드 글 · 기록 제외) — '마지막 손님 글'과 실시간 시작 신호의 재료(R4-2)."""
        return (self.person_type == "user" and not self.is_private and not self.is_log
                and not self.is_code_message)

    @property
    def is_answer(self) -> bool:
        """공개 상담원 글 — '답'(원장 R1-6 · R4-8). 우리 봇 메모 · 직원 내부 메모 · 자동 안내는 아니다."""
        return self.person_type == "manager" and not self.is_private and not self.is_log

    def to_chat_message(self) -> ChatMessage:
        """상태 계산 입력. 원문이 없으니 미리 잰 맺음 · 확인코드 · 약속을 넘긴다."""
        promise = None
        if self.promise_kind and self.promise_due_at and self.promise_rule:
            promise = StaffPromise(self.message_id, self.created_at, self.promise_kind,
                                   self.promise_due_at, self.promise_rule)
        return ChatMessage(self.message_id, self.person_type, self.created_at, "",
                           private=self.is_private, is_log=self.is_log, has_file=self.has_file,
                           closing=self.is_closing, code_message=self.is_code_message, promise=promise)


def _created_at(value: Any) -> Optional[datetime.datetime]:
    """채널톡 시각 → 시간대 있는 UTC. 꼴이 틀리거나 0 이하면 ``None``.

    웹훅 ``entity`` 는 밀리초 숫자, Open API 2026-06-01 판은 ISO 글자(``2026-10-28T06:50:45.123Z``)다 — 둘 다 읽는다
    (10-28 스테이징 첫 호출에서 확인, 원장 Q1). 시간대 없는 ISO 는 UTC 로 본다(채널톡 API 시각은 UTC).
    """
    if isinstance(value, str) and not value.strip().isdigit():
        try:
            parsed = datetime.datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
        except ValueError:
            return None
        return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed.astimezone(UTC)
    if isinstance(value, str):
        value = int(value.strip())
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
        return None
    try:
        return datetime.datetime.fromtimestamp(value / 1000, tz=UTC)
    except (OverflowError, OSError, ValueError):
        return None


def _is_private(entity: Mapping[str, Any]) -> bool:
    """내부 메모인가 — ``private`` 칸 또는 ``options`` 의 private 표시(앱 함수 ``MESSAGE_OPTION_PRIVATE``)."""
    if entity.get("private") is True:
        return True
    options = entity.get("options")
    if not isinstance(options, (list, tuple)):
        return False
    return any(str(option).strip().lower() in _PRIVATE_OPTIONS for option in options)


def _text_fields(person_type: str, base: Mapping[str, Any], text: str) -> dict[str, Any]:
    """원문으로 재는 칸 — 손님 글은 맺음 · 확인코드, 공개 직원 글은 약속. 원문은 여기서만 쓴다."""
    if person_type == "user":
        return {"is_closing": is_closing_text(text),
                "is_code_message": parse_consult_message(text) is not None}
    if person_type != "manager" or base["is_private"] or base["is_log"]:
        return {}
    probe = ChatMessage(base["message_id"], "manager", base["created_at"], text)
    promise = detect_promise(probe, base["brand"])
    if promise is None:
        return {}
    return {"promise_kind": promise.kind, "promise_due_at": promise.due_at.astimezone(UTC),
            "promise_rule": promise.rule}


def _identity(entity: Any, expected_brand: Optional[str]) -> tuple[Optional[dict[str, Any]], str]:
    """글의 상담 · 메시지 id · 채널 · 브랜드 · 사람 · 시각. 거르면 ``(None, 이유)``."""
    if not isinstance(entity, Mapping):
        return None, "no_entity"
    if str(entity.get("chatType") or "") != "userChat":
        return None, "not_user_chat"
    chat_id = str(entity.get("chatId") or "").strip()
    message_id = str(entity.get("id") or "").strip()
    person_type = str(entity.get("personType") or "").strip().lower()
    if not (chat_id and message_id and person_type):
        return None, "no_ids"
    if (len(chat_id) > _MAX_ID_LEN or len(message_id) > _MAX_ID_LEN
            or len(person_type) > _MAX_PERSON_TYPE_LEN):
        return None, "bad_ids"
    channel_id = str(entity.get("channelId") or "").strip()
    brand = brand_for_channel(channel_id)
    if brand is None or (expected_brand is not None and brand != expected_brand):
        return None, "unknown_channel"
    created_at = _created_at(entity.get("createdAt"))
    if created_at is None:
        return None, "no_created_at"
    return {"chat_id": chat_id, "message_id": message_id, "channel_id": channel_id, "brand": brand,
            "person_type": person_type, "created_at": created_at}, ""


def derive_message(entity: Any, *, expected_brand: Optional[str] = None) -> tuple[Optional[DerivedMessage], str]:
    """채널톡 글(웹훅 ``entity`` · Open API 글 — 꼴이 같다)에서 파생 칸을 만든다.

    ``plainText`` 는 이 함수 안에서만 쓰고 버린다. ``chatType`` 이 ``userChat`` 이 아니면 거른다.

    Args:
        entity: 글 dict.
        expected_brand: Open API 로 읽은 글이면 읽은 브랜드 — 채널이 다르면 거른다.

    Returns:
        ``(파생 칸, '')`` 또는 ``(None, 거른 이유)``.
    """
    base, reason = _identity(entity, expected_brand)
    if base is None:
        return None, reason
    files = (entity.get(key) for key in _FILE_KEYS)
    base.update(is_private=_is_private(entity), is_log=bool(entity.get("log")),
                has_file=any(isinstance(value, (list, tuple)) and len(value) > 0 for value in files))
    base.update(_text_fields(base["person_type"], base, str(entity.get("plainText") or "")))
    return DerivedMessage(**base), ""


# ── 시각 ─────────────────────────────────────────────────────────────────
def naive_utc(value: datetime.datetime) -> datetime.datetime:
    """시간대 있는 시각 → 표에 둘 UTC naive."""
    return aware_utc(value).replace(tzinfo=None)


def aware_utc(value: datetime.datetime) -> datetime.datetime:
    """시간대 있는 시각만 받아 UTC 로. 없는 값은 UTC/KST 가 섞이면 조용히 틀리므로 거절한다."""
    if value.tzinfo is None:
        raise ValueError("시간대가 없는 시각은 받지 않는다")
    return value.astimezone(UTC)


# ── Open API 읽기(GET 만) ────────────────────────────────────────────────
#: 2026-06-01 판 주소 · 칸 이름(원장 F6-4). 10-28 스테이징 첫 호출에서 실제 응답으로 확인했다(원장 Q1):
#: 목록은 ``from``/``to``(밀리초, 바뀐 시각 기준, 30일까지 — 31일은 422) + 요청 ``cursor`` → 응답 ``nextCursor``
#: · ``hasNext``. 상태를 안 주면 열린 상담만 준다. 시각 칸은 모두 ISO 글자다.
_LIST_PATH = "/open/user-chats"
_LIST_ITEMS_KEY = "userChats"
_MESSAGES_KEY = "messages"
_CURSOR_KEY = "nextCursor"
#: 상태를 안 주고 목록을 읽을 때 차례로 읽는 상태 — 비우면 채널톡은 열린 상담만 준다(10-28 실측).
LIST_STATES: tuple[str, ...] = ("opened", "snoozed", "closed")
MAX_LIST_WINDOW = datetime.timedelta(days=30)
LIST_PAGE_LIMIT = 100
MESSAGE_PAGE_LIMIT = 50
#: 한 요청이 한도 · 오류로 기다릴 수 있는 합(초). 넘으면 그 요청을 멈추고 다음 바퀴로 미룬다.
MAX_WAIT_SECONDS = 10.0
MAX_ATTEMPTS = 4
_BACKOFF_SECONDS = (1.0, 2.0, 4.0)


class ChannelReadError(RuntimeError):
    """채널톡 Open API 읽기 실패 — 다시 시도해도 안 되는 응답 · 기다림 상한 넘김."""

    def __init__(self, message: str, *, status: Optional[int] = None) -> None:
        """``status`` 는 채널톡 HTTP 상태(없으면 ``None``)."""
        super().__init__(message)
        self.status = status


class OpenApiNotConfigured(ChannelReadError):
    """그 브랜드 채널의 Open API 키(``CHANNEL_OPENAPI_KEY_*`` · ``SECRET_*``)가 없다."""


class ChannelRateLimited(ChannelReadError):
    """한도에 걸려 기다림 상한을 넘었다 — ``retry_after`` 초 뒤에 다시."""

    def __init__(self, brand: str, retry_after: float) -> None:
        """``retry_after`` 는 다시 시도해도 되는 때까지 남은 초."""
        super().__init__(f"{brand} 채널 읽기 한도 — {retry_after:.1f}초 뒤", status=429)
        self.brand = brand
        self.retry_after = retry_after


@dataclass(frozen=True)
class ChatSnapshot:
    """Open API 상담 목록의 상담 하나 — 상태 · 바뀐 시각만."""

    chat_id: str
    brand: str
    channel_id: str
    state: Optional[str]  # 'opened' · 'snoozed' · 'closed', 모르는 값이면 None
    updated_at: Optional[datetime.datetime]  # 시간대 있는 UTC


@dataclass(frozen=True)
class ChatPage:
    """상담 목록 한 쪽."""

    chats: list[ChatSnapshot]
    next_cursor: Optional[str]


def _epoch_ms(value: datetime.datetime) -> int:
    """시간대 있는 시각 → 채널톡 시각(밀리초)."""
    return int(aware_utc(value).timestamp() * 1000)


def _backoff(attempt: int) -> float:
    """``attempt`` 번째(0부터) 다시 시도 전 지수 대기(초)."""
    return _BACKOFF_SECONDS[min(attempt, len(_BACKOFF_SECONDS) - 1)]


def _json_body(response: Any) -> dict[str, Any]:
    """응답 본문 dict. 빈 본문은 빈 dict, 객체가 아닌 JSON 은 꼴이 바뀐 것이라 오류."""
    if not getattr(response, "content", b""):
        return {}
    try:
        data = response.json()
    except ValueError as exc:
        raise ChannelReadError("응답이 JSON 이 아니다") from exc
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise ChannelReadError("응답 꼴이 객체가 아니다")
    return data


def _snapshot(item: Any, brand: str) -> Optional[ChatSnapshot]:
    """상담 목록 항목 → :class:`ChatSnapshot`. id 가 없거나 다른 채널이면 ``None``."""
    if not isinstance(item, Mapping):
        return None
    chat_id = str(item.get("id") or "").strip()
    if not chat_id or len(chat_id) > _MAX_ID_LEN:
        return None
    channel_id = str(item.get("channelId") or "").strip() or channel_for_brand(brand)
    if brand_for_channel(channel_id) != brand:
        return None
    state = str(item.get("state") or "").strip().lower()
    return ChatSnapshot(chat_id, brand, channel_id, state if state in _CHAT_STATES else None,
                        _created_at(item.get("updatedAt")))


class OpenApiReader:
    """채널톡 Open API 읽기(GET 만). 한도는 채널마다 공유 양동이, 429 는 ``Retry-After`` 를 따른다.

    Args:
        budget: 읽기 한도(기본 :func:`default_budget`).
        transport: ``requests.get`` 꼴 함수(시험은 가짜를 넣는다).
        sleep: 기다리는 함수(시험 주입).
        max_wait_seconds: 한 요청이 기다릴 수 있는 합.
        timeout: 요청 하나의 시간 상한(초).
    """

    def __init__(self, *, budget: Optional[ChannelBudget] = None,
                 transport: Optional[Callable[..., Any]] = None,
                 sleep: Callable[[float], None] = time.sleep,
                 max_wait_seconds: float = MAX_WAIT_SECONDS, timeout: float = 10.0) -> None:
        """인자는 클래스 설명과 같다. ``budget`` 을 안 주면 그때 공유 양동이를 고른다."""
        self._budget = budget if budget is not None else default_budget()
        self._transport = transport or requests.get
        self._sleep = sleep
        self._max_wait = max_wait_seconds
        self._timeout = timeout

    def list_user_chats(self, brand: str, *, changed_from: datetime.datetime,
                        changed_to: datetime.datetime, cursor: Optional[str] = None,
                        state: Optional[str] = None, limit: int = LIST_PAGE_LIMIT) -> ChatPage:
        """바뀐 상담 목록 한 쪽(``GET /open/user-chats``). 구간은 30일까지.

        Raises:
            ValueError: 모르는 브랜드, 또는 구간이 비었거나 30일을 넘음(:meth:`iter_user_chats` 가 나눠 부른다).
        """
        channel_for_brand(brand)
        start, end = aware_utc(changed_from), aware_utc(changed_to)
        if not start < end <= start + MAX_LIST_WINDOW:
            raise ValueError("상담 목록 구간은 0초보다 길고 30일 이하여야 한다")
        params: dict[str, Any] = {"limit": int(limit), "from": _epoch_ms(start), "to": _epoch_ms(end)}
        if cursor:
            params["cursor"] = cursor
        if state:
            params["state"] = state
        data = self._get(brand, _LIST_PATH, params, BUCKET_LIST)
        items = data.get(_LIST_ITEMS_KEY)
        snapshots = (_snapshot(item, brand) for item in (items if isinstance(items, list) else []))
        next_cursor = data.get(_CURSOR_KEY) if data.get("hasNext") is not False else None
        return ChatPage([snap for snap in snapshots if snap is not None],
                        str(next_cursor) if next_cursor else None)

    def iter_user_chats(self, brand: str, *, changed_from: datetime.datetime,
                        changed_to: datetime.datetime, state: Optional[str] = None,
                        max_pages: int = 50) -> Iterator[ChatSnapshot]:
        """바뀐 상담을 cursor 로 끝까지 읽는다. 30일보다 긴 구간은 30일씩 나눈다.

        ``state`` 를 안 주면 :data:`LIST_STATES` 를 차례로 다 읽는다 — 상태 칸을 비우면 채널톡은 열린 상담만 줘서
        닫힌 상담을 영영 못 본다(10-28 실측).
        """
        for one_state in (state,) if state else LIST_STATES:
            start, end = aware_utc(changed_from), aware_utc(changed_to)
            while start < end:
                stop = min(end, start + MAX_LIST_WINDOW)
                cursor: Optional[str] = None
                for _ in range(max_pages):
                    page = self.list_user_chats(brand, changed_from=start, changed_to=stop,
                                                cursor=cursor, state=one_state)
                    yield from page.chats
                    if not page.next_cursor or page.next_cursor == cursor:
                        break
                    cursor = page.next_cursor
                else:
                    logger.warning("[CS 상담] 상담 목록 쪽 수 상한(%d)에 닿음 brand=%s state=%s",
                                   max_pages, brand, one_state)
                start = stop

    def read_messages(self, brand: str, chat_id: str, *,
                      limit: int = MESSAGE_PAGE_LIMIT) -> list[DerivedMessage]:
        """상담 최근 글(``GET /open/user-chats/{id}/messages``, 새 글부터)을 파생 칸으로 — 원문은 버린다."""
        channel_id = channel_for_brand(brand)
        path = f"{_LIST_PATH}/{quote(chat_id, safe='')}/messages"
        data = self._get(brand, path, {"limit": int(limit), "sortOrder": "desc"}, BUCKET_MESSAGE)
        items = data.get(_MESSAGES_KEY)
        derived: list[DerivedMessage] = []
        for item in items if isinstance(items, list) else []:
            if not isinstance(item, Mapping):
                continue
            entity = {"chatType": "userChat", "chatId": chat_id, "channelId": channel_id, **item}
            message, _reason = derive_message(entity, expected_brand=brand)
            if message is not None and message.chat_id == chat_id:
                derived.append(message)
        return sorted(derived, key=lambda m: (m.created_at, m.message_id))

    def _get(self, brand: str, path: str, params: dict[str, Any], bucket: str) -> dict[str, Any]:
        """GET 한 번 — 양동이 칸을 받고, 429 · 5xx · 연결 오류는 기다림 상한 안에서 다시 한다."""
        headers = _open_api_headers(brand)
        if headers is None:
            raise OpenApiNotConfigured(f"{brand} 채널 Open API 키가 없다")
        url = f"{_OPEN_API_BASE}{path}"
        waited = 0.0
        for attempt in range(MAX_ATTEMPTS):
            waited = self._wait_budget(brand, bucket, waited)
            try:
                response = self._transport(url, params=params, headers=headers, timeout=self._timeout)
            except requests.RequestException as exc:
                waited = self._pause(brand, _backoff(attempt), waited, f"요청 실패({type(exc).__name__})")
                continue
            status = int(getattr(response, "status_code", 0) or 0)
            if status == 429:
                waited = self._rate_limited(brand, response, attempt, waited)
                continue
            if status >= 500:
                waited = self._pause(brand, _backoff(attempt), waited, f"http_{status}")
                continue
            if not 200 <= status < 300:
                raise ChannelReadError(f"http_{status}", status=status)
            note_remaining(brand, bucket, response)
            return _json_body(response)
        raise ChannelReadError("다시 시도 횟수를 다 썼다")

    def _wait_budget(self, brand: str, bucket: str, waited: float) -> float:
        """양동이 칸을 받을 때까지 기다린다. 기다림 합이 상한을 넘으면 :class:`ChannelRateLimited`."""
        while True:
            wait = float(self._budget.acquire(brand, bucket))
            if wait <= 0:
                return waited
            if waited + wait > self._max_wait:
                raise ChannelRateLimited(brand, wait)
            self._sleep(wait)
            waited += wait

    def _rate_limited(self, brand: str, response: Any, attempt: int, waited: float) -> float:
        """429 — ``Retry-After``(없으면 지수 대기)만큼 그 채널 읽기를 모두 쉬게 표시하고 기다린다."""
        delay = retry_after_seconds(response)
        delay = _backoff(attempt) if delay is None else delay
        self._budget.block(brand, delay)
        if waited + delay > self._max_wait:
            raise ChannelRateLimited(brand, delay)
        logger.warning("[CS 상담] 채널톡 429 — %.1f초 쉬고 다시 brand=%s", delay, brand)
        self._sleep(delay)
        return waited + delay

    def _pause(self, brand: str, delay: float, waited: float, reason: str) -> float:
        """일시 오류 뒤 쉰다. 기다림 합이 상한을 넘으면 :class:`ChannelReadError`."""
        if waited + delay > self._max_wait:
            raise ChannelReadError(f"{reason} — 기다림 상한을 넘었다")
        logger.warning("[CS 상담] 채널톡 읽기 %s — %.1f초 쉬고 다시 brand=%s", reason, delay, brand)
        self._sleep(delay)
        return waited + delay
