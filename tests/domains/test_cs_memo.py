"""AI 초안 메모 감싸개(플랜 C3-3) — 늘 비공개 · 라홈만 · 채널 상수만 · 운영 밖은 시험 상담만 · 다시 읽어 비공개 확인.

완료 기준(브리프): 공개 길은 한 번도 안 쓴다(보내기를 가짜로 바꿔 매번 ``private=True``, 진짜 보내기 함수 아래 앱 함수
본문까지 비공개 표시) · 하우드 거절 · 스테이징 허용 목록 밖 상담엔 0건 · 누가 다른 채널을 넘겨도 채널은 상수 · 글은
로그 · 예외 · 결과에 안 나온다(표지 글). 감싸개 밖 호출 금지는 패키지 소스를 훑어 막는다(원장 R1-14).
네트워크 없음 — 채널톡 쓰기 · Open API 읽기 모두 가짜. 손으로 꾸민 합성 글만(전화 꼴 숫자 없음).
"""

from __future__ import annotations

import ast
import logging
import pathlib

import pytest
import requests

from foms.services import channel_client
from foms.services.cs_agent import channel_read as cr
from foms.services.cs_agent import memo
from tests.support.cs_agent_fakes import HAUD_CHANNEL, LAHOM_CHANNEL, FakeReader, at, derived

#: 글 표지 — 로그 · 예외 · 결과 어디에도 나오면 안 된다.
MARK = "보라고래초안표지"
DRAFT = f"{MARK} 합성 초안입니다. 담당자가 곧 확인합니다."
TEST_CHAT, OTHER_TEST_CHAT, REAL_CHAT = "uc-test-1", "uc-test-2", "uc-real-9"
_ENV_KEYS = ("FOMS_ENV", "RAILWAY_PROJECT_NAME", "RAILWAY_ENVIRONMENT", memo.TEST_CHAT_IDS_ENV)
_PACKAGE = pathlib.Path(memo.__file__).resolve().parent
_RUNNER = _PACKAGE.parents[2] / "scripts" / "maintenance" / "run_cs_loop.py"
#: 채널톡에 글을 쓰는 이름 — 패키지 안에서는 memo.py 만 쓴다.
_WRITE_NAMES = ("send_user_chat_message", "writeUserChatMessage", "_call_native_function",
                "send_user_chat_buttons", "label_user_chat", "send_group_message", "send_private_memo")


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    """환경 판정 env 를 비운다(개발 PC 에 남은 값이 시험을 바꾸지 않게) — 비우면 'local' 이다."""
    for key in _ENV_KEYS:
        monkeypatch.delenv(key, raising=False)


class FakeSend:
    """``send_private_memo`` 대역 — 부른 인자를 남기고 정한 결과를 낸다."""

    def __init__(self) -> None:
        self.calls: list[dict] = []
        self.result = {"success": True, "message_id": "memo-1", "error": None}

    def __call__(self, user_chat_id, plain_text, **kwargs):
        self.calls.append({"chat": user_chat_id, "text": plain_text, **kwargs})
        return dict(self.result)


@pytest.fixture
def send(monkeypatch):
    fake = FakeSend()
    monkeypatch.setattr(channel_client, "send_private_memo", fake)
    return fake


def bot_memo(message_id="memo-1", chat=TEST_CHAT, *, private=True):
    """Open API 로 다시 읽은 우리 봇 메모(파생 칸 — 원문 없음)."""
    extra = {"options": ["private"]} if private else {}
    return derived(message_id, at(2, 9, 1), person="bot", chat=chat, **extra)


def reader_with(*messages, chat=TEST_CHAT, errors=None):
    return FakeReader(messages={chat: list(messages)}, errors=errors)


def post(chat=TEST_CHAT, *, reader=None, **kwargs):
    kwargs.setdefault("brand", "LAHOM")
    return memo.post_private_memo(chat, DRAFT, reader=reader or reader_with(bot_memo(chat=chat), chat=chat), **kwargs)


def assert_private_lahom(calls):
    assert calls, "보내기를 한 번도 안 불렀다"
    for call in calls:
        assert call["private"] is True
        assert call["channel_id"] == LAHOM_CHANNEL == memo.MEMO_CHANNEL_ID
        assert call["bot_name"] == memo.MEMO_BOT_NAME
        assert call["brand"] == "LAHOM"


# ── 늘 비공개 · 채널 상수 ────────────────────────────────────────────────


def test_production_posts_a_private_memo_and_verifies_it(send, monkeypatch):
    monkeypatch.setenv("FOMS_ENV", "production")
    monkeypatch.setenv("RAILWAY_PROJECT_NAME", "FOMS-PRODUCTION")  # 운영은 둘 다 맞아야(R7-6)
    reader = reader_with(bot_memo(chat=REAL_CHAT), chat=REAL_CHAT)
    result = memo.post_private_memo(REAL_CHAT, DRAFT, brand="LAHOM", reader=reader)
    assert result == memo.MemoResult(True, verified=True, message_id="memo-1")
    assert [(c["chat"], c["text"]) for c in send.calls] == [(REAL_CHAT, DRAFT)]
    assert_private_lahom(send.calls)
    assert reader.calls == [("read", "LAHOM", REAL_CHAT)]  # 다시 읽기는 라홈 키로 그 상담만


def test_the_public_path_is_never_used_on_any_route(send, monkeypatch):
    """성공 · 확인 실패 · 못 찾음 · 읽기 오류 · 보내기 실패 · id 없음 — 어느 길이든 보내기는 늘 비공개 · 라홈 채널."""
    monkeypatch.setenv(memo.TEST_CHAT_IDS_ENV, TEST_CHAT)
    post()
    post(reader=reader_with(bot_memo(private=False)))
    post(reader=reader_with(bot_memo("memo-other")))
    post(reader=FakeReader(errors={TEST_CHAT: [cr.ChannelReadError("http_500", status=500)]}))
    send.result = {"success": False, "message_id": None, "error": "provider_error"}
    post()
    send.result = {"success": True, "message_id": None, "error": None}
    post()
    monkeypatch.setenv("FOMS_ENV", "production")
    monkeypatch.setenv("RAILWAY_PROJECT_NAME", "FOMS-PRODUCTION")
    post(REAL_CHAT)
    assert len(send.calls) == 7
    assert_private_lahom(send.calls)


def test_the_real_sender_carries_the_private_option_and_the_lahom_channel(monkeypatch):
    """진짜 ``send_private_memo`` 아래 앱 함수 본문까지 — 비공개 표시 · 라홈 채널 · 봇 이름(네트워크는 가짜)."""
    monkeypatch.setenv(memo.TEST_CHAT_IDS_ENV, TEST_CHAT)
    monkeypatch.setattr(channel_client, "CHANNEL_ID", HAUD_CHANNEL)  # env 기본 채널이 다른 브랜드여도
    sent = []

    def fake_native(payload, channel_id=""):
        sent.append((payload, channel_id))
        return {"result": {"message": {"id": "memo-7"}}}

    monkeypatch.setattr(channel_client, "_call_native_function", fake_native)
    result = memo.post_private_memo(TEST_CHAT, DRAFT, brand="LAHOM", reader=reader_with(bot_memo("memo-7")))
    assert result == memo.MemoResult(True, verified=True, message_id="memo-7")
    (payload, channel_id), = sent
    assert payload["method"] == "writeUserChatMessage" and channel_id == LAHOM_CHANNEL
    assert payload["params"]["channelId"] == LAHOM_CHANNEL and payload["params"]["userChatId"] == TEST_CHAT
    assert payload["params"]["dto"]["options"] == ["MESSAGE_OPTION_PRIVATE"]
    assert payload["params"]["dto"]["botName"] == memo.MEMO_BOT_NAME


def test_the_channel_is_the_constant_even_if_another_is_passed(send, monkeypatch):
    monkeypatch.setenv(memo.TEST_CHAT_IDS_ENV, TEST_CHAT)
    for extra in ({"channel_id": HAUD_CHANNEL}, {"private": False}, {"bot_name": "다른 이름"}):
        with pytest.raises(TypeError):  # 넘길 칸이 없다 — 채널 · 공개 · 보낸 이를 부르는 쪽이 못 고른다
            memo.post_private_memo(TEST_CHAT, DRAFT, brand="LAHOM", **extra)
    assert send.calls == []
    monkeypatch.setattr(channel_client, "CHANNEL_ID", HAUD_CHANNEL)  # env 기본 채널로 빠지지 않는다
    monkeypatch.setitem(cr.CHANNEL_BRANDS, "999999", "LAHOM")  # 짝 표가 나중에 바뀌어도 불러올 때 정한 상수 그대로
    assert post().posted is True
    assert_private_lahom(send.calls)
    assert memo.MEMO_CHANNEL_ID == "201824" and cr.CHANNEL_BRANDS[memo.MEMO_CHANNEL_ID] == "LAHOM"


# ── 라홈만 · 운영 밖은 시험 상담만 ───────────────────────────────────────


def test_haud_and_unknown_brands_are_refused_without_any_call(send, monkeypatch):
    monkeypatch.setenv("FOMS_ENV", "production")
    reader = reader_with(bot_memo())
    for brand in ("HAUD", "lahom", "LAHOM ", "XYZ", ""):
        result = memo.post_private_memo(TEST_CHAT, DRAFT, brand=brand, reader=reader)
        assert result == memo.MemoResult(False, reason=memo.REASON_BRAND)
    assert send.calls == [] and reader.calls == []


def test_staging_writes_only_allow_listed_test_chats(send, monkeypatch):
    monkeypatch.setenv("FOMS_ENV", "staging")
    reader = reader_with(bot_memo(chat=REAL_CHAT), chat=REAL_CHAT)
    # env 목록이 없으면 아무 데도 안 쓴다.
    assert memo.post_private_memo(REAL_CHAT, DRAFT, brand="LAHOM", reader=reader).reason == memo.REASON_STAGING
    monkeypatch.setenv(memo.TEST_CHAT_IDS_ENV, f" {TEST_CHAT}, {OTHER_TEST_CHAT} ,, ")
    assert memo.env_test_chat_ids() == {TEST_CHAT, OTHER_TEST_CHAT}
    assert memo.post_private_memo(REAL_CHAT, DRAFT, brand="LAHOM", reader=reader).reason == memo.REASON_STAGING
    assert send.calls == [] and reader.calls == []  # 허용 목록 밖 상담엔 0건 — 읽기도 없다
    assert post(OTHER_TEST_CHAT).verified is True and [c["chat"] for c in send.calls] == [OTHER_TEST_CHAT]
    # 인자 목록이 env 보다 먼저다 — 빈 목록이면 env 에 있는 시험 상담도 안 쓴다.
    assert post(TEST_CHAT, allowed_chat_ids=[]).reason == memo.REASON_STAGING
    assert post(REAL_CHAT, allowed_chat_ids=[REAL_CHAT]).posted is True
    with pytest.raises(TypeError):
        post(TEST_CHAT, allowed_chat_ids=TEST_CHAT)  # 글 하나는 글자마다 나뉜다
    assert [c["chat"] for c in send.calls] == [OTHER_TEST_CHAT, REAL_CHAT]
    assert_private_lahom(send.calls)


def test_a_local_or_dev_project_is_never_production(send, monkeypatch):
    reader = reader_with(bot_memo(chat=REAL_CHAT), chat=REAL_CHAT)

    def refused(**kwargs):
        result = memo.post_private_memo(REAL_CHAT, DRAFT, brand="LAHOM", reader=reader, **kwargs)
        return result.reason == memo.REASON_STAGING

    assert refused()  # env 가 없으면 'local'
    assert refused(environment="production")  # 인자로 운영을 흉내 낼 수 없다
    monkeypatch.setenv("RAILWAY_PROJECT_NAME", "FOMS-DEV")
    monkeypatch.setenv("FOMS_ENV", "production")  # 스테이징에 잘못 남은 FOMS_ENV
    assert refused()
    monkeypatch.delenv("RAILWAY_PROJECT_NAME")
    assert refused()  # FOMS_ENV 만 운영이고 프로젝트 이름이 없으면 운영이 아니다(맞는 것만 — R7-6)
    monkeypatch.setenv("RAILWAY_PROJECT_NAME", "FOMS-PRODUCTION")
    assert refused(environment="staging")  # 인자는 더 막는 쪽으로만
    assert send.calls == []
    assert memo.post_private_memo(REAL_CHAT, DRAFT, brand="LAHOM", reader=reader).verified is True  # 음성 대조군: 운영
    assert len(send.calls) == 1


@pytest.mark.parametrize("env,production", [
    ({"RAILWAY_PROJECT_NAME": "FOMS-STAGING", "RAILWAY_ENVIRONMENT": "production"}, False),  # 검수 P7 — 이름이 바뀐 스테이징
    ({"RAILWAY_ENVIRONMENT": "production"}, False),  # P7b — 프로젝트 이름 변수가 없다(FOMS-DEV 환경 이름도 production)
    ({"FOMS_ENV": "production"}, False),
    ({"FOMS_ENV": "production", "RAILWAY_PROJECT_NAME": "FOMS-DEV"}, False),
    ({"FOMS_ENV": "staging", "RAILWAY_PROJECT_NAME": "FOMS-PRODUCTION"}, False),
    ({"RAILWAY_PROJECT_NAME": "foms-production"}, False),  # 끝 글자는 대소문자까지 정확히
    ({"RAILWAY_PROJECT_NAME": "FOMS-PRODUCTION-COPY"}, False),
    ({"RAILWAY_PROJECT_NAME": "FOMS-PRODUCTION"}, True),
    ({"FOMS_ENV": "production", "RAILWAY_PROJECT_NAME": "FOMS-PRODUCTION"}, True),
])
def test_production_is_only_the_exact_production_project(monkeypatch, env, production):
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    assert memo.is_production() is production  # 맞는 것만 운영 — 나머지는 시험 상담 허용 목록(원장 R7-6)
    assert memo.memo_allowed(REAL_CHAT) is production  # 허용 목록이 비면 운영만 쓴다


def test_bad_chat_ids_and_empty_text_are_refused_without_calls(send, monkeypatch):
    monkeypatch.setenv("FOMS_ENV", "production")
    for chat in ("", "합성 상담", "uc 1", "x" * 65, None):
        assert memo.post_private_memo(chat, DRAFT, brand="LAHOM").reason == memo.REASON_NO_CHAT
    for text in ("", "   \n", None):
        assert memo.post_private_memo(TEST_CHAT, text, brand="LAHOM").reason == memo.REASON_EMPTY
    assert send.calls == []


# ── 다시 읽어 비공개 확인 · 실패 이유 ────────────────────────────────────


def test_a_memo_that_is_not_private_or_not_found_is_unverified(send, monkeypatch, caplog):
    monkeypatch.setenv(memo.TEST_CHAT_IDS_ENV, TEST_CHAT)
    caplog.set_level(logging.WARNING, logger=memo.__name__)
    public = post(reader=reader_with(bot_memo(private=False)))
    assert public == memo.MemoResult(True, verified=False, message_id="memo-1", reason=memo.REASON_NOT_PRIVATE)
    assert any(r.levelno == logging.ERROR and TEST_CHAT in r.getMessage() for r in caplog.records)
    assert post(reader=reader_with(bot_memo("memo-other"))).reason == memo.REASON_NOT_FOUND
    for error in (cr.ChannelReadError("http_500", status=500), cr.OpenApiNotConfigured("LAHOM 키 없음")):
        result = post(reader=FakeReader(errors={TEST_CHAT: [error]}))
        assert (result.posted, result.verified, result.reason) == (True, False, memo.REASON_READ_FAILED)
    send.result = {"success": True, "message_id": None, "error": None}
    reader = reader_with(bot_memo())
    assert post(reader=reader) == memo.MemoResult(True, reason=memo.REASON_NO_MESSAGE_ID)
    assert reader.calls == []  # id 가 없으면 찾을 것이 없다


def test_send_failures_keep_the_unknown_outcome_apart(send, monkeypatch):
    monkeypatch.setenv(memo.TEST_CHAT_IDS_ENV, TEST_CHAT)
    send.result = {"success": False, "message_id": None, "error": "provider_error"}
    refused = post()
    assert refused == memo.MemoResult(False, reason="send_provider_error") and not refused.outcome_unknown
    send.result = {"success": False, "message_id": None, "error": "request_failed"}
    unknown = post()
    assert unknown.reason == memo.SEND_UNKNOWN and unknown.outcome_unknown  # 닿았는지 모름 — '올리는 중'으로 둔다
    send.result = {"success": False, "message_id": None, "error": f"{MARK} 이상한 오류"}
    assert post().reason == "send_unknown"  # 코드 꼴이 아닌 오류 값은 옮기지 않는다


# ── 글은 로그 · 예외 · 결과에 안 나온다 ──────────────────────────────────


def test_the_text_never_reaches_logs_results_or_exceptions(monkeypatch, caplog):
    caplog.set_level(logging.DEBUG)
    monkeypatch.setenv(memo.TEST_CHAT_IDS_ENV, TEST_CHAT)
    ok = {"result": {"message": {"id": "memo-1"}}}
    outcomes = iter([ok, {"error": {"message": "합성 거절"}}, requests.Timeout("read timed out"), ok])

    def fake_native(payload, channel_id=""):
        item = next(outcomes)
        if isinstance(item, Exception):
            raise item
        return item

    monkeypatch.setattr(channel_client, "_call_native_function", fake_native)
    results = [post(), post(reader=reader_with(bot_memo(private=False))), post(),
               post(reader=FakeReader(errors={TEST_CHAT: [cr.ChannelReadError("http_500", status=500)]})),
               memo.post_private_memo(DRAFT, TEST_CHAT, brand="LAHOM"),  # 자리를 바꿔 넘긴 글
               post(brand="HAUD"), post(REAL_CHAT, environment="staging", allowed_chat_ids=[])]
    errors = []
    for extra in ({"channel_id": HAUD_CHANNEL}, {"allowed_chat_ids": TEST_CHAT}):
        with pytest.raises(TypeError) as caught:
            memo.post_private_memo(TEST_CHAT, DRAFT, brand="LAHOM", **extra)
        errors.append(str(caught.value))
    assert [r.reason for r in results] == [
        None, "send_provider_error", memo.SEND_UNKNOWN, memo.REASON_READ_FAILED, memo.REASON_NO_CHAT,
        memo.REASON_BRAND, memo.REASON_STAGING]
    assert caplog.records and MARK not in caplog.text
    assert all(MARK not in repr(result) for result in results) and all(MARK not in text for text in errors)


# ── 감싸개 밖 호출 금지(소스) ────────────────────────────────────────────


def test_only_memo_writes_to_channel_talk_in_the_agent_package():
    sources = sorted(_PACKAGE.glob("*.py")) + [_RUNNER]
    assert len(sources) > 10 and _RUNNER.is_file()
    offenders = sorted(f"{path.name}:{name}" for path in sources if path.name != "memo.py"
                       for name in _WRITE_NAMES if name in path.read_text(encoding="utf-8"))
    assert not offenders, f"메모 감싸개 밖에서 채널톡에 쓴다: {offenders}"
    tree = ast.parse((_PACKAGE / "memo.py").read_text(encoding="utf-8"))
    calls = [node for node in ast.walk(tree) if isinstance(node, ast.Call)
             and getattr(node.func, "attr", getattr(node.func, "id", None)) in _WRITE_NAMES]
    assert len(calls) == 1, "memo.py 안 채널톡 쓰기는 한 곳이어야 한다"
    http_writes = sorted(f"{path.name}:{node.lineno}" for path in sources
                         for node in ast.walk(ast.parse(path.read_text(encoding="utf-8")))
                         if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                         and node.func.attr in ("post", "put", "patch", "delete", "request"))
    assert not http_writes, f"패키지 안에서 HTTP 쓰기를 직접 부른다(메모 감싸개도 channel_client 를 거친다): {http_writes}"
    keywords = {kw.arg: kw.value for kw in calls[0].keywords}
    assert isinstance(keywords["private"], ast.Constant) and keywords["private"].value is True
    assert getattr(keywords["channel_id"], "id", None) == "MEMO_CHANNEL_ID"
    assert getattr(keywords["bot_name"], "id", None) == "MEMO_BOT_NAME"


# ── 메모 + 링크 버튼 · 비공개 강제(C10-2 — 원장 R10-14) ──────────────────

BUTTONS = [("보내기", "https://foms.example/cs/send/1"), ("수정하기", "https://foms.example/cs/edit/1")]


class FakeHttp:
    """``requests.post`` 대역 — 받은 인자를 남기고 정한 응답을 낸다(네트워크 없음)."""

    def __init__(self, status=200, body=None):
        self.calls, self.status, self.body = [], status, body if body is not None else {"message": {"id": "memo-b1"}}

    def __call__(self, url, **kwargs):
        self.calls.append({"url": url, **kwargs})
        fake = self

        class _Resp:
            status_code = fake.status

            @staticmethod
            def json():
                return fake.body
        return _Resp()


@pytest.fixture
def open_api(monkeypatch):
    http = FakeHttp()
    monkeypatch.setattr(channel_client.requests, "post", http)
    monkeypatch.setattr(channel_client, "_open_api_headers", lambda brand: {"x-brand": brand})

    def no_native(*_a, **_k):
        raise AssertionError("버튼 메모는 앱 함수를 부르지 않는다")
    monkeypatch.setattr(channel_client, "_call_native_function", no_native)
    return http


def test_a_memo_with_link_buttons_goes_through_open_api_as_private(open_api, monkeypatch):
    monkeypatch.setenv(memo.TEST_CHAT_IDS_ENV, TEST_CHAT)
    result = memo.post_private_memo(TEST_CHAT, DRAFT, brand="LAHOM", buttons=BUTTONS,
                                    reader=reader_with(bot_memo("memo-b1")))
    assert result == memo.MemoResult(True, verified=True, message_id="memo-b1")
    (call,) = open_api.calls
    assert call["url"].endswith(f"/open/user-chats/{TEST_CHAT}/messages")
    assert call["params"] == {"botName": memo.MEMO_BOT_NAME} and call["headers"] == {"x-brand": "LAHOM"}
    assert call["json"]["options"] == [channel_client.OPEN_API_PRIVATE]
    assert [b["title"] for b in call["json"]["buttons"]] == ["보내기", "수정하기"]
    assert all(b["action"] == {"type": "web", "attributes": {"url": url}}
               for b, (_t, url) in zip(call["json"]["buttons"], BUTTONS))


def test_the_private_option_is_fixed_per_path_and_cannot_be_chosen(open_api, monkeypatch):
    """두 길의 비공개 옵션 이름이 다르다 — 보낼 본문의 옵션은 늘 그 길의 비공개 하나이고, 부르는 쪽이 고를 칸이 없다(R12-1)."""
    native_calls = []
    monkeypatch.setattr(channel_client, "_call_native_function",
                        lambda payload, channel_id="": native_calls.append(payload) or {"result": {"message": {"id": "n1"}}})
    kwargs = {"brand": "LAHOM", "bot_name": memo.MEMO_BOT_NAME, "channel_id": LAHOM_CHANNEL}
    for falsy in (False, 1, "True", None):
        with pytest.raises(channel_client.PrivateOptionMissing):
            channel_client.send_private_memo(TEST_CHAT, DRAFT, private=falsy, buttons=BUTTONS, **kwargs)
    with pytest.raises(TypeError):  # 옵션을 고르는 칸이 없다
        channel_client.send_private_memo(TEST_CHAT, DRAFT, private=True, options=["silentToUser"], **kwargs)
    assert open_api.calls == [] and native_calls == []
    assert channel_client.send_private_memo(TEST_CHAT, DRAFT, private=True, buttons=BUTTONS, **kwargs)["success"]
    assert channel_client.send_private_memo(TEST_CHAT, DRAFT, private=True, buttons=None, **kwargs)["success"]
    assert [call["json"]["options"] for call in open_api.calls] == [[channel_client.OPEN_API_PRIVATE]]
    assert [payload["params"]["dto"]["options"] for payload in native_calls] == [[channel_client.NATIVE_PRIVATE]]


def test_a_missing_private_option_inside_memo_is_never_swallowed(send, monkeypatch):
    """감싸개는 비공개 빠짐 예외를 '버튼 꼴 틀림'으로 바꾸지 않고 그대로 올린다(R12-7)."""
    monkeypatch.setenv(memo.TEST_CHAT_IDS_ENV, TEST_CHAT)

    def raising(*_a, **_k):
        raise channel_client.PrivateOptionMissing("합성")
    monkeypatch.setattr(channel_client, "send_private_memo", raising)
    with pytest.raises(channel_client.PrivateOptionMissing):
        post(buttons=BUTTONS)


def test_odd_responses_and_http_errors_are_classified_without_raising(open_api, monkeypatch):
    """받은 뒤 응답 꼴이 이상해도 던지지 않고 '받음 + id 없음', 앱 함수 4xx 는 거절 · 5xx 는 모름(R12-2)."""
    kwargs = {"brand": "LAHOM", "bot_name": memo.MEMO_BOT_NAME, "channel_id": LAHOM_CHANNEL, "private": True}
    for body in ([1], {"message": "글"}, {"message": {"id": 7}}, "x"):
        open_api.body = body
        assert channel_client.send_private_memo(TEST_CHAT, DRAFT, buttons=BUTTONS, **kwargs) == {
            "success": True, "message_id": None, "error": None}
    for data in ([1], {"result": "x"}, {"error": "글"}, {"result": {"message": None}}):
        monkeypatch.setattr(channel_client, "_call_native_function", lambda *a, _d=data, **k: _d)
        assert channel_client.send_private_memo(TEST_CHAT, DRAFT, **kwargs)["success"] is True
    for status, expected in ((403, "provider_error"), (422, "provider_error"), (502, "request_failed")):
        response = requests.Response()
        response.status_code = status

        def http_fail(*_a, _r=response, **_k):
            raise requests.HTTPError("합성", response=_r)
        monkeypatch.setattr(channel_client, "_call_native_function", http_fail)
        assert channel_client.send_private_memo(TEST_CHAT, DRAFT, **kwargs)["error"] == expected


def test_chat_ids_that_could_change_the_api_path_are_refused(open_api, monkeypatch):
    """``/`` · ``..`` 가 든 상담 id 는 메모를 쓰지 않는다 — Open API 주소 경로가 다른 곳으로 정리될 수 있다(R12-5)."""
    monkeypatch.setenv("FOMS_ENV", "production")
    monkeypatch.setenv("RAILWAY_PROJECT_NAME", "FOMS-PRODUCTION")
    for chat in ("x/../../groups/G1", "a/b", "..", "uc test", "uc%2Fx"):
        assert memo.post_private_memo(chat, DRAFT, brand="LAHOM", buttons=BUTTONS,
                                      reader=reader_with(bot_memo(), chat=chat)).reason == memo.REASON_NO_CHAT
    assert open_api.calls == []


def test_bad_buttons_are_refused_without_any_call(open_api, monkeypatch):
    monkeypatch.setenv(memo.TEST_CHAT_IDS_ENV, TEST_CHAT)
    bad = [BUTTONS + [("하나 더", "https://foms.example/x")], [("보내기", "http://foms.example/x")],
           [("", "https://foms.example/x")], [("가" * 31, "https://foms.example/x")]]
    for buttons in bad:
        assert memo.post_private_memo(TEST_CHAT, DRAFT, brand="LAHOM", buttons=buttons,
                                      reader=reader_with(bot_memo())) == memo.MemoResult(False,
                                                                                          reason=memo.REASON_BAD_BUTTONS)
    assert open_api.calls == []


def test_open_api_memo_failures_keep_unknown_apart_and_hide_the_text(open_api, monkeypatch, caplog):
    caplog.set_level(logging.DEBUG)
    monkeypatch.setenv(memo.TEST_CHAT_IDS_ENV, TEST_CHAT)
    open_api.status = 422
    refused = memo.post_private_memo(TEST_CHAT, DRAFT, brand="LAHOM", buttons=BUTTONS, reader=reader_with(bot_memo()))
    assert refused == memo.MemoResult(False, reason="send_provider_error") and not refused.outcome_unknown
    open_api.status = 503  # 받았는지 모름 — 다시 보내지 않게 '모름'
    unknown = memo.post_private_memo(TEST_CHAT, DRAFT, brand="LAHOM", buttons=BUTTONS, reader=reader_with(bot_memo()))
    assert unknown.reason == memo.SEND_UNKNOWN and unknown.outcome_unknown

    def boom(*_a, **_k):
        raise requests.Timeout("read timed out")
    monkeypatch.setattr(channel_client.requests, "post", boom)
    timed_out = memo.post_private_memo(TEST_CHAT, DRAFT, brand="LAHOM", buttons=BUTTONS,
                                       reader=reader_with(bot_memo()))
    assert timed_out.outcome_unknown
    assert MARK not in caplog.text and all(MARK not in repr(r) for r in (refused, unknown, timed_out))
