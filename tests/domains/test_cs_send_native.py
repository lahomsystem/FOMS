"""[보내기] 공개 봇 글은 앱 함수(네이티브 ``writeUserChatMessage``)로 보낸다 — 스테이징 실화면 시험(11-01)이 잡은 결함의 막는 시험.

결함: Open API 쓰기 본문에는 requestId 칸이 없어(C10-2 조사 — blocks · plainText · buttons · files · options 뿐), 스테이징 시험
상담에 보낸 글을 다시 읽으니 requestId 가 비어 있었다. 그래서 결과 모름을 requestId 로 영영 못 맞추고(5분 뒤 '못 보냄' → 다시
누르면 두 번 나갈 수 있음), 돌아온 봇 글을 requestId 앞말로 '답'으로 읽는 규칙도 실제로 안 걸렸다. 앱 함수로 쓴 글은 Open API 글
목록에 requestId 가 그대로 돌아온다(C10-2 시험, 원장 §3 34행).

본다: 앱 함수 dto 에 plainText · botName · requestId 만(옵션 없음 = 공개) · 채널은 라홈 상수 · Open API 로는 공개 봇 글을 보내지
않음(동작 · 소스) · 결과 분류(시간 초과 · 5xx = 모름, 4xx · 오류 응답 = 거절, 꼴 이상 = 받음 + id 없음) · 맞추기가 앱 함수로 보낸
글의 requestId 로 맞춤. 버튼 단 글(share_consult)은 Open API 그대로다. 네트워크 없음, 손으로 꾸민 합성 글만.
"""

from __future__ import annotations

import ast
import inspect
import textwrap

import pytest
import requests
from sqlalchemy import select

from db import db_session
from foms.services import channel_client, channel_send
from foms.services.cs_agent import send, send_flow
from models import CsAgentMessage
from tests.domains.test_cs_drafting import channel  # noqa: F401 — fixture
from tests.domains.test_cs_send import fresh, posted, press, ready, token, user  # noqa: F401 — ready 는 fixture
from tests.support.cs_agent_fakes import HAUD_CHANNEL, LAHOM_CHANNEL, FakeClock, api_message, at, keys, make_reader  # noqa

OK = {"result": {"message": {"id": "sent-1", "createdAt": "2026-11-02T00:01:00Z"}}}


class FakeNative:
    """``_call_native_function`` 대역 — 받은 본문을 남기고, ``deliver`` 면 가짜 채널톡 상담에 그 requestId 로 글을 붙인다
    (채널톡이 받아 둔 것). 결과(응답 dict 또는 예외)를 차례로 낸다."""

    def __init__(self, *outcomes, deliver=None):
        self.outcomes, self.deliver, self.calls = list(outcomes) or [OK], deliver, []

    def __call__(self, payload, channel_id=""):
        self.calls.append((payload, channel_id))
        dto = payload["params"]["dto"]
        if self.deliver is not None:
            self.deliver.messages[payload["params"]["userChatId"]].append(api_message(
                "sent-1", at(2, 9, 1), "bot", dto["plainText"], requestId=dto["requestId"]))
        outcome = self.outcomes.pop(0) if len(self.outcomes) > 1 else self.outcomes[0]
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome


@pytest.fixture
def native(monkeypatch):
    fake = FakeNative()
    monkeypatch.setattr(channel_client, "CHANNEL_APP_SECRET", "secret")
    monkeypatch.setattr(channel_client, "CHANNEL_ID", HAUD_CHANNEL)  # env 기본 채널이 다른 브랜드여도 라홈 상수로 간다
    monkeypatch.setattr(channel_client, "_call_native_function", fake)
    monkeypatch.setattr(channel_client.requests, "post",
                        lambda *a, **k: pytest.fail("공개 봇 글을 Open API 로 보냈다(requestId 가 사라진다)"))
    return fake


def http_error(status):
    response = requests.Response()
    response.status_code = status
    return requests.HTTPError("합성", response=response)


def send_one(**kwargs):
    kwargs = {"channel_id": LAHOM_CHANNEL, "bot_name": "라홈", "request_id": "foms-cs-send-7", **kwargs}
    return channel_send.send_public_bot_message("uc-1", "합성 답", **kwargs)


def test_the_public_reply_goes_through_the_app_function_with_its_request_id(native):
    assert send_one() == {"success": True, "message_id": "sent-1", "created_at": "2026-11-02T00:01:00Z", "error": None}
    ((payload, channel_id),) = native.calls
    assert payload["method"] == "writeUserChatMessage" and channel_id == LAHOM_CHANNEL
    assert payload["params"]["channelId"] == LAHOM_CHANNEL and payload["params"]["userChatId"] == "uc-1"
    assert payload["params"]["dto"] == {"plainText": "합성 답", "botName": "라홈", "requestId": "foms-cs-send-7"}
    assert "options" not in payload["params"]["dto"]  # 옵션 없음 = 손님이 보는 공개 글


@pytest.mark.parametrize("outcome,error", [
    ({"error": {"message": "합성 거절"}}, "provider_error"),  # 앱 함수 오류 응답 — 확실히 거절
    (http_error(422), "provider_error"), (http_error(403), "provider_error"),
    (http_error(502), "request_failed"),  # 5xx — 받았는지 모름
    (requests.Timeout("read timed out"), "request_failed"), (requests.ConnectionError("끊김"), "request_failed"),
])
def test_failures_keep_the_unknown_outcome_apart(native, outcome, error):
    native.outcomes = [outcome]
    assert send_one() == {"success": False, "message_id": None, "created_at": None, "error": error}


@pytest.mark.parametrize("body", [[1], {"result": "x"}, {"result": {"message": None}}, {"result": {"message": {"id": 7}}},
                                  None])
def test_an_odd_reply_after_acceptance_is_sent_without_an_id(native, body):
    native.outcomes = [body]
    assert send_one() == {"success": True, "message_id": None, "created_at": None, "error": None}


def test_nothing_is_called_without_the_app_secret_or_with_bad_ids(native, monkeypatch):
    for kwargs in ({"request_id": "foms cs"}, {"request_id": ""}, {"channel_id": ""}):
        with pytest.raises(ValueError):
            send_one(**kwargs)
    with pytest.raises(ValueError):
        channel_send.send_public_bot_message("x/../y", "합성", channel_id=LAHOM_CHANNEL, bot_name="라홈", request_id="r")
    monkeypatch.setattr(channel_client, "CHANNEL_APP_SECRET", "")
    assert send_one()["error"] == "not_configured" and native.calls == []


def test_the_wrapper_sends_with_the_lahom_channel_constant_and_the_turn_request_id(native, monkeypatch):
    monkeypatch.setenv("FOMS_CS_MEMO_TEST_CHAT_IDS", "uc-1")
    for env in ("FOMS_ENV", "RAILWAY_PROJECT_NAME"):
        monkeypatch.delenv(env, raising=False)
    sent = send.send_reply("uc-1", "  합성 답  ", brand="LAHOM", turn_id=42)
    assert (sent.posted, sent.message_id, sent.created_at.isoformat()) == (True, "sent-1", "2026-11-02T00:01:00+00:00")
    ((payload, channel_id),) = native.calls
    assert channel_id == LAHOM_CHANNEL == send.SEND_CHANNEL_ID
    assert payload["params"]["dto"] == {"plainText": "합성 답", "botName": send.SEND_BOT_NAME,
                                        "requestId": "foms-cs-send-42"}


def test_the_source_writes_public_replies_only_through_the_app_function():
    tree = ast.parse(textwrap.dedent(inspect.getsource(channel_send.send_public_bot_message)))
    called = [getattr(n.func, "attr", getattr(n.func, "id", None)) for n in ast.walk(tree) if isinstance(n, ast.Call)]
    assert called.count("_call_native_function") == 1
    assert not {"_post_message", "post", "put", "patch", "request"} & set(called)  # Open API · 바로 HTTP 쓰기 없음
    keys = {k.value for n in ast.walk(tree) if isinstance(n, ast.Dict) for k in n.keys if isinstance(k, ast.Constant)}
    assert {"plainText", "botName", "requestId"} <= keys and "options" not in keys
    buttons = inspect.getsource(channel_send.send_user_chat_buttons)
    assert "_post_message(" in buttons and "_call_native_function" not in buttons  # 버튼 글은 Open API 그대로


def test_a_timeout_through_the_app_function_is_matched_by_its_request_id(app, ready, monkeypatch):
    fake = FakeNative(requests.Timeout("read timed out"), deliver=ready)  # 채널톡은 받아 뒀는데 응답이 끊겼다
    monkeypatch.setattr(channel_client, "CHANNEL_APP_SECRET", "secret")
    monkeypatch.setattr(channel_client, "CHANNEL_ID", HAUD_CHANNEL)
    monkeypatch.setattr(channel_client, "_call_native_function", fake)
    monkeypatch.setattr(channel_client.requests, "post", lambda *a, **k: pytest.fail("Open API 로 보냈다"))
    staff = user()
    turn_id = posted(ready)
    first = press(app, ready, turn_id, staff.id, send.send_reply)  # 진짜 감싸개 · 진짜 채널 보내기 함수
    assert first.code == "checking" and fresh(turn_id).send_state == "unknown" and len(fake.calls) == 1
    matched = send_flow.reconcile_one(db_session, turn_id=turn_id, user_id=staff.id, token=token(app, turn_id, staff.id),
                                      secret_key=app.secret_key, now=at(2, 9, 2),
                                      reader=make_reader(ready, FakeClock()))
    row = fresh(turn_id)
    assert matched.code == "sent" and (row.send_state, row.sent_message_id) == ("sent", "sent-1") and len(fake.calls) == 1
    person = db_session.scalar(select(CsAgentMessage.person_type).where(CsAgentMessage.message_id == "sent-1"))
    assert person == "manager"  # 돌아온 봇 글을 requestId 앞말로 '답'으로 읽는다
