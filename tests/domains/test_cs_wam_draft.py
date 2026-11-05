"""AI 초안 채널톡 안 작은 창(WAM) S1 — 함수 받는 곳 ``/v1`` · 함수 목록 · 시험 함수 · 메모 WAM 단추 · 빈 틀 화면(설계서 17.2.2).

채널톡은 등록한 함수 주소 뒤에 ``/v1`` 을 붙여 부르고, 함수 목록을 ``extension.core.function.getFunctions`` 로 묻는다(공식 SDK).
누른 사람은 서명된 ``context.caller`` 로만 안다 — 서명이 없거나 상담원이 아니면 받지 않는다.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json

import pytest

from foms.services import channel_memo
from foms.services.cs_agent import wam_functions

_KEY_HEX = "cd" * 32
_CHANNEL_ID = "chan-wam-501"


def _enable(monkeypatch) -> None:
    monkeypatch.setenv("CHANNEL_FUNCTION_ENABLED", "true")
    monkeypatch.setenv("CHANNEL_FUNCTION_SIGNING_KEY", _KEY_HEX)
    monkeypatch.setenv("CHANNEL_FUNCTION_CHANNEL_ID", _CHANNEL_ID)


def _put(client, payload: dict, *, path: str = "/api/channel/functions/v1", signed: bool = True):
    data = json.dumps(payload).encode("utf-8")
    signature = base64.b64encode(hmac.new(bytes.fromhex(_KEY_HEX), data, hashlib.sha256).digest()).decode("ascii")
    return client.open(path, method="PUT", data=data,
                       headers={"x-signature": signature if signed else "", "Content-Type": "application/json"})


def _call(method: str, params: dict | None = None, *, caller: dict | None = None) -> dict:
    context = {"channel": {"id": _CHANNEL_ID}, "caller": caller if caller is not None else {"type": "manager", "id": "m-1"}}
    return {"method": method, "params": params or {}, "context": context, "systemVersion": "v1"}


def test_v1_path_lists_functions_and_ping_answers_the_signed_manager(app, client, monkeypatch):
    _enable(monkeypatch)
    listed = _put(client, _call("extension.core.function.getFunctions"))
    assert listed.status_code == 200 and listed.get_json()["result"]["success"] is True
    names = [f["name"] for f in listed.get_json()["result"]["functions"]]
    assert "cs.draft.ping" in names and "foms" in names
    ping = _put(client, _call("cs.draft.ping", {"turn": 7}))
    assert ping.status_code == 200 and ping.get_json() == {"result": {"ok": True, "turn": 7}}
    same = _put(client, _call("cs.draft.ping", {"turn": 7}), path="/api/channel/functions")  # 예전 주소도 같은 처리
    assert same.get_json() == ping.get_json()


def test_unsigned_or_non_manager_calls_are_refused(app, client, monkeypatch):
    _enable(monkeypatch)
    assert _put(client, _call("cs.draft.ping", {"turn": 7}), signed=False).status_code == 401
    bot = _put(client, _call("cs.draft.ping", {"turn": 7}, caller={"type": "bot", "id": "b-1"}))
    assert bot.status_code == 200 and bot.get_json()["error"]["type"] == "unauthorized"
    other = _put(client, {**_call("cs.draft.ping"), "context": {"channel": {"id": "other"},
                                                                  "caller": {"type": "manager", "id": "m-1"}}})
    assert other.status_code == 401  # 다른 채널(서명이 맞아도)


def test_ping_only_returns_a_positive_turn_number():
    assert wam_functions.handle("cs.draft.ping", {"turn": "12"}, "m-1") == {"result": {"ok": True, "turn": 12}}
    for bad in ({"turn": True}, {"turn": -3}, {"turn": "x"}, {}, None):
        assert wam_functions.handle("cs.draft.ping", bad, "m-1")["result"]["turn"] is None
    assert wam_functions.handle("cs.draft.nope", {}, "m-1")["error"]["code"] == -32601


def test_memo_buttons_carry_a_wam_action_with_only_short_arguments():
    target = {"wam": "cs-draft", "app_id": "app-1", "args": {"turn": 9, "mode": "send"}}
    [button] = channel_memo._memo_buttons([("보내기", target)])
    assert button["action"] == {"type": "wam", "attributes": {"appId": "app-1", "name": "cs-draft",
                                                              "wamArgs": {"turn": 9, "mode": "send"}}}
    for bad in ({**target, "wam": "other"}, {**target, "app_id": ""}, {**target, "args": {"text": "가" * 65}},
                {**target, "args": {"turn": True}}, {**target, "args": {"a": {"nested": 1}}}):
        with pytest.raises(ValueError):
            channel_memo._memo_buttons([("보내기", bad)])
    [link] = channel_memo._memo_buttons([("보내기", "https://example.com/x")])  # 링크 단추는 그대로(대조군)
    assert link["action"]["type"] == "web"


def test_wam_page_is_an_empty_frame_allowed_only_inside_channel_desks(app, client, monkeypatch):
    monkeypatch.setenv("CS_WAM_APP_ID", "app-public-1")
    response = client.get("/channel/wam/cs-draft")
    html = response.get_data(as_text=True)
    assert response.status_code == 200 and response.headers["Cache-Control"] == "no-store"
    policy = response.headers["Content-Security-Policy"]
    assert "https://*.channel.works" in policy and "https://desk.channel.io" in policy
    assert 'data-app-id="app-public-1"' in html and "wam-draft.js" in html
    assert "<script>" not in html and "style=" not in html  # 인라인 스크립트 · 스타일 없음
    other = client.get("/orders")  # 다른 화면은 여전히 같은 출처만(대조군)
    assert "channel.works" not in (other.headers.get("Content-Security-Policy") or "")
