"""CS 상담 에이전트(C1-2 · C1-3 · C3-1) 시험 재료 — 손으로 꾸민 합성 글 · 가짜 시계 · 전송 · Redis · Open API 읽기.

손님 글 · 전화 꼴 숫자는 쓰지 않는다. 네트워크 · Redis · 채널톡은 모두 가짜다.
시각은 2026-11 KST(11-02 월요일), 상태 계산 달력은 '주말만 쉼' 가짜 달력이다.
"""

from __future__ import annotations

import datetime
import json
from types import SimpleNamespace
from urllib.parse import unquote

import pytest
from anthropic.types.beta import BetaMessage
from sqlalchemy import func, select

from db import db_session
from foms.services.cs_agent import channel_read as cr
from foms.services.cs_agent import read_budget as rb
from foms.services.cs_agent import state_store as ss
from foms.services.cs_agent.state import KST, ChatState
from models import ChannelInboundEventLog, CsAgentChat, CsAgentMessage

LAHOM_CHANNEL = "201824"
HAUD_CHANNEL = "109717"
CODE_TEXT = "문서 받기\n[라홈] 도면 준비 완료\n■ 주문번호: 42\n■ 확인코드: ABC234"


def at(day: int, hour: int, minute: int = 0) -> datetime.datetime:
    return datetime.datetime(2026, 11, day, hour, minute, tzinfo=KST)


def naive(when: datetime.datetime) -> datetime.datetime:
    return when.astimezone(datetime.timezone.utc).replace(tzinfo=None)


def weekdays_only(day: datetime.date) -> bool:
    return day.weekday() < 5


def entity(msg_id: str, when: datetime.datetime, person: str = "user", text: str = "",
           chat: str = "uc-1", channel: str = LAHOM_CHANNEL, **extra) -> dict:
    """웹훅 ``entity`` 꼴 글."""
    return {"id": msg_id, "chatId": chat, "chatType": "userChat", "channelId": channel,
            "personType": person, "createdAt": int(when.timestamp() * 1000), "plainText": text, **extra}


def iso(when: datetime.datetime) -> str:
    """Open API 2026-06-01 판 시각 꼴(ISO 글자, UTC 'Z') — 10-28 스테이징 첫 호출에서 확인."""
    return when.astimezone(datetime.timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def api_message(msg_id: str, when: datetime.datetime, person: str = "user", text: str = "", **extra) -> dict:
    """Open API 글 꼴 — 상담 · 채널 칸이 없어도 읽기 도우미가 채운다. 시각은 ISO 글자(웹훅은 밀리초 숫자)."""
    return {"id": msg_id, "personType": person, "createdAt": iso(when), "plainText": text, **extra}


def inbound(log_id: int, body: dict) -> None:
    """수신 기록 한 줄(웹훅 본문 꼴)을 그 id 로 커밋한다 — id 순서와 커밋 순서를 시험이 정한다."""
    db_session.add(ChannelInboundEventLog(
        id=log_id, dedupe_key=f"msg_message_{log_id}", payload_hash="0" * 64,
        raw_payload={"event": "push", "type": "message", "entity": body}, chat_type="message",
        source_chat_id=body.get("chatId"), status="user_chat_handled"))
    db_session.commit()


def derived(msg_id: str, when: datetime.datetime, person: str = "user", text: str = "", **extra):
    message, reason = cr.derive_message(entity(msg_id, when, person, text, **extra))
    assert message is not None, reason
    return message


def state_of(chat: str = "uc-1", now: datetime.datetime = at(2, 11)) -> ChatState:
    return ss.compute_state_from_table(db_session, chat, now=now, is_business_day=weekdays_only)


def msg_row(message_id: str, chat: str = "uc-1"):
    table = CsAgentMessage.__table__
    return db_session.execute(
        select(table).where(table.c.chat_id == chat, table.c.message_id == message_id)).one()


def chat_row(chat: str = "uc-1"):
    table = CsAgentChat.__table__
    return db_session.execute(select(table).where(table.c.chat_id == chat)).one()


def message_count() -> int:
    return db_session.scalar(select(func.count()).select_from(CsAgentMessage.__table__))


def snap(state_value: str, when: datetime.datetime, chat: str = "uc-1") -> cr.ChatSnapshot:
    return cr.ChatSnapshot(chat, "LAHOM", LAHOM_CHANNEL, state_value, when)


class FakeClock:
    """``sleep`` 이 시각을 앞으로 민다 — 양동이 · 쉼 표시가 실제 기다림과 맞물린다."""

    def __init__(self, start: float = 1000.2) -> None:
        self.now = start
        self.sleeps: list[float] = []

    def __call__(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds


class FakeResponse:
    def __init__(self, status: int = 200, body=None, *, headers=None, raw: bytes | None = None) -> None:
        self.status_code = status
        self.headers = headers or {}
        self.content = raw if raw is not None else (b"" if body is None else json.dumps(body).encode())

    def json(self):
        return json.loads(self.content.decode("utf-8"))


class FakeTransport:
    """``requests.get`` 꼴 — 준비한 응답(또는 예외)을 차례로 내고 부른 내용을 남긴다."""

    def __init__(self, *responses) -> None:
        self.responses = list(responses)
        self.calls: list[dict] = []

    def __call__(self, url, *, params, headers, timeout):
        self.calls.append({"url": url, "params": dict(params), "headers": dict(headers)})
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


class FakeRedis:
    """양동이가 쓰는 명령만(PTTL · SET PX · INCR · PEXPIRE · MULTI 파이프라인), 가짜 시계로 수명을 센다."""

    def __init__(self, clock: FakeClock) -> None:
        self.clock = clock
        self.values: dict[str, object] = {}
        self.expires: dict[str, float] = {}

    def _expire_old(self, key: str) -> None:
        if key in self.expires and self.expires[key] <= self.clock():
            self.values.pop(key, None)
            self.expires.pop(key, None)

    def pttl(self, key: str) -> int:
        self._expire_old(key)
        if key not in self.values:
            return -2
        return -1 if key not in self.expires else int((self.expires[key] - self.clock()) * 1000)

    def set(self, key: str, value, px: int | None = None) -> bool:
        self.values[key] = value
        if px is not None:
            self.expires[key] = self.clock() + px / 1000
        return True

    def incr(self, key: str) -> int:
        self._expire_old(key)
        self.values[key] = int(self.values.get(key, 0)) + 1
        return int(self.values[key])

    def pexpire(self, key: str, ms: int) -> bool:
        if key not in self.values:
            return False
        self.expires[key] = self.clock() + ms / 1000
        return True

    def pipeline(self, transaction: bool = True) -> "_FakePipeline":
        return _FakePipeline(self)


class _FakePipeline:
    def __init__(self, redis: FakeRedis) -> None:
        self.redis = redis
        self.ops: list = []

    def incr(self, key: str) -> None:
        self.ops.append(lambda: self.redis.incr(key))

    def pexpire(self, key: str, ms: int) -> None:
        self.ops.append(lambda: self.redis.pexpire(key, ms))

    def execute(self) -> list:
        return [op() for op in self.ops]


@pytest.fixture
def keys(monkeypatch):
    """두 브랜드 Open API 키(가짜 값)."""
    for brand in ("LAHOM", "HAUD"):
        monkeypatch.setenv(f"CHANNEL_OPENAPI_KEY_{brand}", f"key-{brand.lower()}")
        monkeypatch.setenv(f"CHANNEL_OPENAPI_SECRET_{brand}", f"secret-{brand.lower()}")


class FakeReader:
    """Open API 읽기 대역(감시 루프용) — 준비한 상담 목록 · 글을 내고 부른 순서를 남긴다(네트워크 없음)."""

    def __init__(self, chats=(), messages=None, *, on_read=None, missing_keys=(), errors=None):
        self.chats, self.messages = list(chats), dict(messages or {})
        self.on_read, self.missing_keys = on_read, set(missing_keys)
        self.errors = {chat: list(excs) for chat, excs in (errors or {}).items()}  # 상담마다 차례로 던질 읽기 오류
        self.calls: list[tuple] = []

    def iter_user_chats(self, brand, *, changed_from, changed_to, state=None):
        """Open API 처럼 창(``changed_from`` 부터 바뀐 상담)만 낸다 — 창 시작이 상담을 넘어가면 그 상담은 안 나온다."""
        self.calls.append(("list", brand, changed_from))
        if brand in self.missing_keys:
            raise cr.OpenApiNotConfigured(f"{brand} 키 없음")
        return iter([chat for chat in self.chats if chat.brand == brand
                     and (chat.updated_at is None or chat.updated_at >= changed_from)])

    def read_messages(self, brand, chat_id, *, limit=50):
        self.calls.append(("read", brand, chat_id))
        if self.on_read:
            self.on_read(chat_id)
        if self.errors.get(chat_id):
            raise self.errors[chat_id].pop(0)
        return list(self.messages.get(chat_id, []))


class FakeChannel:
    """채널톡 Open API GET 대역(``requests.get`` 꼴 — 주소로 가른다): 상담 목록은 빈 쪽 · 상담 정보는 매체 · 상담 글은 원문 꼴.

    상담마다 매체와 글(:func:`api_message` 꼴)을 둔다. 시험이 ``messages[상담]`` 에 글을 더하면 다음 읽기부터 보인다 —
    '그사이 손님이 더 씀 · 직원이 답함'을 꾸민다. 부른 경로(``user-chats/…``)는 ``calls`` 에 차례로 남는다.
    """

    def __init__(self) -> None:
        self.media: dict[str, str | None] = {}
        self.messages: dict[str, list[dict]] = {}
        self.calls: list[str] = []

    def chat(self, chat_id: str, *messages: dict, medium: str | None = "native") -> None:
        self.media[chat_id], self.messages[chat_id] = medium, list(messages)

    def __call__(self, url, *, params, headers, timeout):
        path = url.split("/open/", 1)[1]
        self.calls.append(path)
        parts = path.split("/")
        if len(parts) == 1:  # 상담 목록 — 감시 보정은 상태 표만으로 돈다
            return FakeResponse(200, {"userChats": [], "hasNext": False})
        chat = unquote(parts[1])
        if chat not in self.messages:
            return FakeResponse(404)
        if len(parts) == 3:  # 상담 글(새 글부터)
            newest = sorted(self.messages[chat], key=lambda m: m["createdAt"], reverse=True)
            return FakeResponse(200, {"messages": newest})
        medium = self.media[chat]
        source = {"source": {"medium": {"mediumType": medium}}} if medium else {}
        return FakeResponse(200, {"userChat": {"id": chat, "state": "opened", **source}})


class FakeAnthropic:
    """``anthropic.Anthropic`` 흉내 — 진짜 두뇌 길(가림 · 돈 셈 · 응답 읽기)을 그대로 돌린다(네트워크 · 키 없음).

    받은 인자를 남기고, 정한 구조화 출력(dict)을 SDK 실제 응답 형(``BetaMessage``)으로 차례로 낸다(마지막 것은 계속).
    """

    def __init__(self, *answers: dict) -> None:
        self.answers, self.params = list(answers), []
        self.beta = SimpleNamespace(messages=SimpleNamespace(create=self.create))

    def with_options(self, **_options):
        return self

    def create(self, **params):
        self.params.append(params)
        answer = self.answers.pop(0) if len(self.answers) > 1 else self.answers[0]
        return BetaMessage.model_validate({
            "id": "msg_synthetic", "type": "message", "role": "assistant", "model": params["model"],
            "content": [{"type": "text", "text": json.dumps(answer, ensure_ascii=False)}], "stop_reason": "end_turn",
            "stop_sequence": None, "stop_details": None,
            "usage": {"input_tokens": 1000, "output_tokens": 200, "cache_read_input_tokens": 0,
                      "cache_creation_input_tokens": 0}})


def chat_snap(chat: str, when: datetime.datetime, state: str = "opened", brand: str = "LAHOM") -> cr.ChatSnapshot:
    """Open API 상담 목록 항목(상태 · 바뀐 시각)."""
    return cr.ChatSnapshot(chat, brand, LAHOM_CHANNEL if brand == "LAHOM" else HAUD_CHANNEL, state, when)


def make_reader(transport: FakeTransport, clock: FakeClock, budget=None, **kw) -> cr.OpenApiReader:
    """가짜 전송 · 가짜 시계 · (기본) 프로세스 안 양동이로 읽기 도우미를 만든다."""
    return cr.OpenApiReader(budget=budget or rb.LocalChannelBudget(clock=clock),
                            transport=transport, sleep=clock.sleep, **kw)
