import pytest

import foms.services.channel_client as channel_client
import foms.services.channel_security as channel_security


class _FakeResponse:
    def __init__(self, data, *, status_code=200):
        self._data = data
        self.status_code = status_code

    def raise_for_status(self):
        return None

    def json(self):
        return self._data


def test_format_order_message_uses_canonical_short_link_import(monkeypatch):
    monkeypatch.setattr(channel_client, "FOMS_BASE_URL", "https://example.com")
    monkeypatch.setattr(channel_security, "generate_wam_short_link_token", lambda order_id: "short-123")

    message = channel_client.format_order_message(
        customer_name="테스터",
        status="MEASURE",
        address="서울",
        order_id=2762,
    )

    assert "https://example.com/w/short-123" in message


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
