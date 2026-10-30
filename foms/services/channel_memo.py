"""채널톡 내부 메모(매니저에게만 보임) 쓰기 — 손님에게 보이는 글은 이 모듈로 쓸 수 없다.

AI 상담팀원(플랜 C10-2 · 원장 R10-14 · 검수 R12)의 메모 감싸개(:mod:`foms.services.cs_agent.memo`)가 부르는 유일한 쓰기
길이다. 토큰 · 앱 함수 부르기 · Open API 열쇠는 :mod:`foms.services.channel_client` 것을 그대로 쓴다(부를 때마다 그 모듈
속성을 읽어 시험이 바꿔 끼울 수 있다). 버튼 없는 메모는 앱 함수, 링크 버튼 메모는 Open API 다 — 앱 함수는 버튼 단 비공개
글도 422 로 거절한다(C10-2 시험 10-30).
"""

from __future__ import annotations

import logging
from typing import Any
from urllib.parse import quote

import requests

from foms.services import channel_client

logger = logging.getLogger(__name__)

__all__ = ["NATIVE_PRIVATE", "OPEN_API_PRIVATE", "PrivateOptionMissing", "send_private_memo"]

#: 내부 메모(매니저에게만 보임) 옵션 이름 — Open API 와 앱 함수(네이티브)가 이름이 다르다(원장 R10-14).
OPEN_API_PRIVATE = "private"
NATIVE_PRIVATE = "MESSAGE_OPTION_PRIVATE"
_MEMO_BUTTON_MAX = 2
_MEMO_BUTTON_TITLE_MAX = 30


class PrivateOptionMissing(ValueError):
    """내부 메모로 쓰려는데 그 길의 비공개 옵션이 빠졌다 — 채널톡을 부르기 전에 막는다(손님에게 보이는 글이 될 수 있다)."""


def _require_private(options: list[str], name: str) -> None:
    """``options`` 에 그 길의 비공개 옵션(``name``)이 없으면 :class:`PrivateOptionMissing` — 네트워크 전에 부른다."""
    if name not in options:
        raise PrivateOptionMissing(f"내부 메모에 비공개 옵션({name})이 없다 — 보내지 않는다")


def _memo_buttons(buttons: Any) -> list[dict[str, Any]]:
    """링크 버튼 ``[(이름, https 주소), ...]`` → Open API 버튼 칸. 꼴이 틀리면 ``ValueError``(네트워크 전)."""
    items = list(buttons or ())
    if len(items) > _MEMO_BUTTON_MAX:
        raise ValueError(f"메모 버튼은 {_MEMO_BUTTON_MAX}개까지다")
    out = []
    for item in items:
        if not isinstance(item, (tuple, list)) or len(item) != 2:
            raise ValueError("메모 버튼은 (이름, 주소) 짝이다")
        title, url = item
        if not isinstance(title, str) or not 1 <= len(title.strip()) <= _MEMO_BUTTON_TITLE_MAX:
            raise ValueError("메모 버튼 이름은 1~30자다")
        if not isinstance(url, str) or not url.startswith("https://"):
            raise ValueError("메모 버튼 주소는 https 주소만 받는다")
        out.append({"title": title.strip(), "colorVariant": "cobalt",
                    "action": {"type": "web", "attributes": {"url": url}}})
    return out


def _sent_message_id(data: Any) -> str | None:
    """채널톡이 받은 뒤의 응답에서 글 id — 꼴이 틀려도 던지지 않고 ``None``(받은 것은 받은 것이다)."""
    message = data.get("message") if isinstance(data, dict) else None
    message_id = message.get("id") if isinstance(message, dict) else None
    return message_id if isinstance(message_id, str) and message_id else None


def send_private_memo(
    user_chat_id: str,
    plain_text: str,
    *,
    brand: str,
    bot_name: str,
    channel_id: str,
    private: bool,
    buttons: Any = (),
) -> dict[str, Any]:
    """
    Write an internal (manager-only) memo into a user chat — never a customer-visible message.

    버튼이 없으면 앱 함수(``writeUserChatMessage`` + ``MESSAGE_OPTION_PRIVATE``), 링크 버튼이 있으면 Open API
    (``private`` 옵션 + 버튼)로 쓴다 — 앱 함수는 버튼을 단 비공개 글도 422 로 거절한다(C10-2 시험 10-30). 길마다 비공개
    옵션 이름이 달라, 보낼 본문의 옵션은 늘 **그 길의 비공개 옵션 하나**다(부르는 쪽이 옵션을 고르는 칸이 없다 — 검수
    R12-1). 보내기 바로 전에 실제 본문에 그 이름이 있는지 다시 보고, 없으면 :class:`PrivateOptionMissing`(네트워크 전).
    ``private`` 는 늘 ``True`` 여야 한다(부르는 쪽이 공개를 고를 수 없다는 것을 소스에 남기는 칸). 결과 꼴은
    :func:`foms.services.channel_client.send_user_chat_message` 와 같다. 글은 로그에 싣지 않는다.

    실패 코드: ``request_failed`` 는 채널톡이 받았는지 모름(시간 초과 · 연결 오류 · 5xx) — 부르는 쪽은 다시 보내지 않고
    다시 읽어 맞춘다. ``provider_error`` 는 확실히 거절(4xx · 앱 함수 오류 응답).

    Args:
        user_chat_id: 채널톡 userChat id.
        plain_text: 메모 글.
        brand: ``LAHOM``/``HAUD`` — 버튼 길(Open API)에서 어느 채널 키를 쓸지.
        bot_name: 보낸 이로 보일 봇 이름.
        channel_id: 상담이 있는 채널(앱 함수 길).
        private: 늘 ``True``.
        buttons: ``[(버튼 이름, https 주소), ...]`` — 2개까지(``None`` 은 버튼 없음).

    Returns:
        ``{'success': bool, 'message_id': str | None, 'error': str | None}``.

    Raises:
        PrivateOptionMissing: ``private`` 가 참이 아니다(또는 보낼 본문에 비공개 옵션이 없다).
        ValueError: 버튼 꼴이 틀렸다.
    """
    if private is not True:
        raise PrivateOptionMissing("내부 메모 함수는 공개 글을 쓰지 않는다")
    button_items = _memo_buttons(buttons)
    if not user_chat_id:
        return {"success": False, "message_id": None, "error": "no_user_chat"}
    if not button_items:
        dto: dict[str, Any] = {"plainText": plain_text, "botName": bot_name, "options": [NATIVE_PRIVATE]}
        payload = {"method": "writeUserChatMessage",
                   "params": {"channelId": channel_id or channel_client.CHANNEL_ID, "userChatId": user_chat_id, "dto": dto}}
        _require_private(payload["params"]["dto"]["options"], NATIVE_PRIVATE)
        try:
            data = channel_client._call_native_function(payload, channel_id)
        except requests.HTTPError as exc:
            status = getattr(exc.response, "status_code", None)
            known = isinstance(status, int) and status < 500
            logger.error("[채널톡] 내부 메모 앱 함수 HTTP 실패 (chat=%s) status=%s", user_chat_id, status)
            return {"success": False, "message_id": None, "error": "provider_error" if known else "request_failed"}
        except Exception as exc:
            logger.error("[채널톡] 내부 메모 앱 함수 요청 실패 (chat=%s): %s", user_chat_id, type(exc).__name__)
            return {"success": False, "message_id": None, "error": "request_failed"}
        error = data.get("error") if isinstance(data, dict) else None
        if isinstance(error, dict) and error.get("message"):
            logger.error("[채널톡] 내부 메모 앱 함수 오류 (chat=%s)", user_chat_id)
            return {"success": False, "message_id": None, "error": "provider_error"}
        result = data.get("result") if isinstance(data, dict) else None
        return {"success": True, "message_id": _sent_message_id(result), "error": None}
    headers = channel_client._open_api_headers(brand)
    if headers is None:
        return {"success": False, "message_id": None, "error": "not_configured"}
    body = {"plainText": plain_text, "buttons": button_items, "options": [OPEN_API_PRIVATE]}
    _require_private(body["options"], OPEN_API_PRIVATE)
    try:
        resp = requests.post(f"{channel_client._OPEN_API_BASE}/open/user-chats/{quote(user_chat_id, safe='')}/messages",
                             params={"botName": bot_name}, json=body, headers=headers, timeout=10)
    except Exception as exc:
        logger.error("[채널톡] 내부 메모(버튼) 요청 실패 (chat=%s): %s", user_chat_id, type(exc).__name__)
        return {"success": False, "message_id": None, "error": "request_failed"}
    if resp.status_code >= 400:
        logger.error("[채널톡] 내부 메모(버튼) 실패 (chat=%s) status=%s", user_chat_id, resp.status_code)
        # 5xx 는 채널톡이 받았는지 모른다 — 시간 초과와 같은 '모름'으로 돌려 다시 보내지 않게 한다.
        error = "request_failed" if resp.status_code >= 500 else "provider_error"
        return {"success": False, "message_id": None, "error": error}
    try:
        data = resp.json()
    except ValueError:
        data = None
    return {"success": True, "message_id": _sent_message_id(data), "error": None}
