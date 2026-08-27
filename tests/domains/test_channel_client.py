import pytest

import foms.services.channel_client as channel_client


class _FakeResponse:
    def __init__(self, data, *, status_code=200):
        self._data = data
        self.status_code = status_code

    def raise_for_status(self):
        return None

    def json(self):
        return self._data


def test_format_order_message_uses_mobile_erp_detail_link(monkeypatch):
    monkeypatch.setattr(channel_client, "FOMS_BASE_URL", "https://example.com")

    message = channel_client.format_order_message(
        customer_name="테스터",
        status="MEASURE",
        address="서울",
        order_id=2762,
    )

    assert "https://example.com/erp/orders/2762/mobile" in message


def test_format_order_message_keeps_legacy_fallback_for_bad_order_id(monkeypatch):
    monkeypatch.setattr(channel_client, "FOMS_BASE_URL", "https://example.com")

    message = channel_client.format_order_message(
        customer_name="테스터",
        status="MEASURE",
        address="서울",
        order_id="bad-id",
    )

    assert "https://example.com/erp/orders/bad-id" in message


def test_build_channel_bot_name_uses_login_display_name() -> None:
    assert channel_client.build_channel_bot_name("강민경") == "FOMS강민경"


def test_build_channel_bot_name_falls_back_to_foms_when_name_missing() -> None:
    assert channel_client.build_channel_bot_name(None) == "FOMS"
    assert channel_client.build_channel_bot_name("   ") == "FOMS"


def test_build_channel_bot_name_strips_control_characters() -> None:
    assert channel_client.build_channel_bot_name("강\x00민경") == "FOMS강민경"


def test_get_access_token_reuses_cached_token(monkeypatch):
    issued = []

    monkeypatch.setattr(channel_client, "CHANNEL_APP_SECRET", "secret")
    monkeypatch.setattr(channel_client, "CHANNEL_ID", "channel-1")
    monkeypatch.setattr(channel_client, "_token_cache", {})
    monkeypatch.setattr(channel_client.time, "time", lambda: 100.0)

    def _fake_issue_token():
        issued.append("called")
        return "cached-token", 200.0

    monkeypatch.setattr(channel_client, "_issue_token", _fake_issue_token)

    first = channel_client._get_access_token()
    second = channel_client._get_access_token()

    assert first == "cached-token"
    assert second == "cached-token"
    assert issued == ["called"]


def test_send_group_message_skips_without_group_id():
    result = channel_client.send_group_message(group_id="", plain_text="hello")

    assert result == {"success": False, "message_id": None}


def test_send_group_message_returns_message_id_on_success(monkeypatch):
    captured = {}

    monkeypatch.setattr(channel_client, "CHANNEL_ID", "channel-1")
    monkeypatch.setattr(channel_client, "_get_access_token", lambda: "access-token")

    def _fake_put(url, *, json, headers, timeout):
        captured["url"] = url
        captured["json"] = json
        captured["headers"] = headers
        captured["timeout"] = timeout
        return _FakeResponse({"result": {"message": {"id": "message-1"}}})

    monkeypatch.setattr(channel_client.requests, "put", _fake_put)

    result = channel_client.send_group_message(
        group_id="group-1",
        plain_text="payload",
        blocks=[{"type": "text"}],
        files=[{"fileName": "a.jpg"}],
    )

    assert result == {"success": True, "message_id": "message-1"}
    assert captured["url"] == channel_client._NATIVE_FUNCTIONS_URL
    assert captured["json"]["params"]["channelId"] == "channel-1"
    assert captured["json"]["params"]["groupId"] == "group-1"
    assert captured["headers"]["x-access-token"] == "access-token"
    assert captured["timeout"] == 10


def test_send_group_message_raises_runtime_error_when_api_returns_error_and_flag_enabled(monkeypatch):
    monkeypatch.setattr(channel_client, "CHANNEL_ID", "channel-1")
    monkeypatch.setattr(channel_client, "_get_access_token", lambda: "access-token")
    monkeypatch.setattr(
        channel_client.requests,
        "put",
        lambda *args, **kwargs: _FakeResponse({"error": {"message": "api-failed"}}),
    )

    with pytest.raises(RuntimeError, match="api-failed"):
        channel_client.send_group_message(
            group_id="group-1",
            plain_text="payload",
            raise_on_error=True,
        )


def test_send_group_message_returns_failure_when_api_returns_error_without_raise(monkeypatch):
    monkeypatch.setattr(channel_client, "CHANNEL_ID", "channel-1")
    monkeypatch.setattr(channel_client, "_get_access_token", lambda: "access-token")
    monkeypatch.setattr(
        channel_client.requests,
        "put",
        lambda *args, **kwargs: _FakeResponse({"error": {"message": "api-failed"}}),
    )

    result = channel_client.send_group_message(group_id="group-1", plain_text="payload")

    assert result == {"success": False, "message_id": None}


def test_issue_token_uses_expires_in_from_response(monkeypatch):
    monkeypatch.setattr(channel_client, "CHANNEL_APP_SECRET", "secret")
    monkeypatch.setattr(channel_client, "CHANNEL_ID", "channel-1")
    monkeypatch.setattr(channel_client.time, "time", lambda: 1000.0)
    monkeypatch.setattr(
        channel_client.requests,
        "put",
        lambda *args, **kwargs: _FakeResponse(
            {"result": {"accessToken": "token-1", "expiresIn": 1800}}
        ),
    )

    access_token, expires_at = channel_client._issue_token()

    assert access_token == "token-1"
    assert expires_at == 1000.0 + 1800 - channel_client._TOKEN_EXPIRY_BUFFER_SECONDS


def test_issue_token_falls_back_to_default_ttl_without_expires_in(monkeypatch):
    monkeypatch.setattr(channel_client, "CHANNEL_APP_SECRET", "secret")
    monkeypatch.setattr(channel_client, "CHANNEL_ID", "channel-1")
    monkeypatch.setattr(channel_client.time, "time", lambda: 1000.0)
    monkeypatch.setattr(
        channel_client.requests,
        "put",
        lambda *args, **kwargs: _FakeResponse({"result": {"accessToken": "token-1"}}),
    )

    _, expires_at = channel_client._issue_token()

    assert expires_at == 1000.0 + channel_client._TOKEN_TTL_SECONDS


_UNAUTHENTICATED_ERROR = {
    "error": {
        "code": 1,
        "message": (
            'request failed, body: {"type":"unauthenticatedError","status":401,'
            '"errors":[{"message":"Your credentials have changed and you have been '
            'logged out. Please log in again."}],"language":"en"}'
        ),
        "data": {"type": "unauthenticatedError"},
        "type": "common",
    }
}


def test_send_group_message_reissues_token_and_retries_on_unauthenticated(monkeypatch):
    """죽은 캐시 토큰으로 401 을 받으면 토큰을 버리고 재발급해 1회 재시도한다."""
    monkeypatch.setattr(channel_client, "CHANNEL_ID", "channel-1")
    monkeypatch.setattr(channel_client, "CHANNEL_APP_SECRET", "secret")
    monkeypatch.setattr(channel_client, "_token_cache", {"channel-1": ("stale-token", 1e12)})
    monkeypatch.setattr(
        channel_client, "_issue_token", lambda: ("fresh-token", 1e12)
    )

    used_tokens = []

    def _fake_put(url, *, json, headers, timeout):
        used_tokens.append(headers["x-access-token"])
        if headers["x-access-token"] == "stale-token":
            return _FakeResponse(_UNAUTHENTICATED_ERROR)
        return _FakeResponse({"result": {"message": {"id": "message-1"}}})

    monkeypatch.setattr(channel_client.requests, "put", _fake_put)

    result = channel_client.send_group_message(group_id="group-1", plain_text="payload")

    assert result == {"success": True, "message_id": "message-1"}
    assert used_tokens == ["stale-token", "fresh-token"]
    assert channel_client._token_cache["channel-1"][0] == "fresh-token"


def test_send_group_message_gives_up_when_retry_also_unauthenticated(monkeypatch):
    monkeypatch.setattr(channel_client, "CHANNEL_ID", "channel-1")
    monkeypatch.setattr(channel_client, "CHANNEL_APP_SECRET", "secret")
    monkeypatch.setattr(channel_client, "_token_cache", {})
    monkeypatch.setattr(channel_client, "_issue_token", lambda: ("fresh-token", 1e12))
    monkeypatch.setattr(
        channel_client.requests,
        "put",
        lambda *args, **kwargs: _FakeResponse(_UNAUTHENTICATED_ERROR),
    )

    with pytest.raises(RuntimeError, match="unauthenticatedError"):
        channel_client.send_group_message(
            group_id="group-1", plain_text="payload", raise_on_error=True
        )


def test_send_group_message_does_not_retry_non_auth_error(monkeypatch):
    calls = []

    monkeypatch.setattr(channel_client, "CHANNEL_ID", "channel-1")
    monkeypatch.setattr(channel_client, "_get_access_token", lambda: "access-token")

    def _fake_put(url, *, json, headers, timeout):
        calls.append(headers["x-access-token"])
        return _FakeResponse({"error": {"message": "api-failed"}})

    monkeypatch.setattr(channel_client.requests, "put", _fake_put)

    result = channel_client.send_group_message(group_id="group-1", plain_text="payload")

    assert result == {"success": False, "message_id": None}
    assert calls == ["access-token"]
