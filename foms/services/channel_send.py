"""채널톡 상담에 손님이 보는 글 쓰기(Open API) — 봇 이름 공개 글(requestId) · 링크 버튼 글 · 둘이 같이 쓰는 POST 한 번.

- :func:`send_public_bot_message` — AI 상담팀원 [보내기](플랜 C10-3 · 설계서 17.2 · 원장 D68 — 상담원 이름으로 보내지 않는다)의
  보내기 감싸개(:mod:`foms.services.cs_agent.send`)가 부르는 유일한 쓰기 길이다. requestId 를 꼭 붙인다 — 채널톡은 같은
  requestId 를 거르지 않는다(C10-2 시험 10-30). 겹침은 부르는 쪽의 '보내는 중' 상태가 막고, requestId 는 결과를 모를 때 상담
  글을 다시 읽어 맞추는 표지다. 본문에 옵션 칸이 없다(공개 글 — 내부 메모는 :mod:`foms.services.channel_memo`).
  ``request_failed`` 는 받았는지 모름(시간 초과 · 연결 오류 · 5xx — 다시 보내지 말 것), ``provider_error`` 는 확실히 거절(4xx).
- :func:`send_user_chat_buttons` — 문서 링크 버튼 글(share_consult). 예전 :mod:`foms.services.channel_client` 에 있던 것을 그대로
  옮겼다(동작 · 오류 코드 ``http_<상태>`` 같음, ``channel_client.send_user_chat_buttons`` 이름으로도 남는다 — 검수 R15 단순화).

토큰 · 열쇠 · ``requests`` 는 :mod:`foms.services.channel_client` 것을 부를 때마다 읽는다(시험이 바꿔 끼울 수 있다). 글은 로그에
싣지 않는다.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Optional
from urllib.parse import quote

import requests

from foms.services import channel_client

logger = logging.getLogger(__name__)

__all__ = ["CHAT_ID", "send_public_bot_message", "send_user_chat_buttons"]

#: 채널톡 상담 id 꼴(영문 · 숫자 · ``_`` · ``-``, 64자까지) — 주소 경로를 바꿀 수 없는 꼴. 상담 에이전트 보내기도 이 꼴 하나를 쓴다.
CHAT_ID = re.compile(r"[A-Za-z0-9_-]{1,64}")
#: requestId 꼴 — 영문 · 숫자 · ``-`` · ``_`` 64자까지(로그 · 다시 읽어 맞추기에 쓰는 표지).
_REQUEST_ID = re.compile(r"[A-Za-z0-9_-]{1,64}")


def _post_message(brand: str, chat_segment: str, body: dict[str, Any], *, bot_name: str) -> Optional[Any]:
    """Open API 상담 글 쓰기 POST 한 번 — 그 브랜드 열쇠가 없으면 ``None``. 요청 예외는 그대로 올린다(부르는 쪽이 가른다)."""
    headers = channel_client._open_api_headers(brand)
    if headers is None:
        return None
    return channel_client.requests.post(f"{channel_client._OPEN_API_BASE}/open/user-chats/{chat_segment}/messages",
                                        params={"botName": bot_name}, json=body, headers=headers, timeout=10)


def _sent(data: Any) -> tuple[Optional[str], Any]:
    """받은 뒤의 응답에서 (글 id, 글 시각 원값) — 꼴이 틀려도 던지지 않는다(받은 것은 받은 것이다)."""
    message = data.get("message") if isinstance(data, dict) else None
    if not isinstance(message, dict):
        return None, None
    message_id = message.get("id")
    return (message_id if isinstance(message_id, str) and message_id else None), message.get("createdAt")


def send_public_bot_message(user_chat_id: str, plain_text: str, *, brand: str, bot_name: str,
                            request_id: str) -> dict[str, Any]:
    """
    Write one customer-visible bot message into a user chat (Open API) with a caller-chosen requestId.

    Args:
        user_chat_id: 채널톡 userChat id(:data:`CHAT_ID` 꼴).
        plain_text: 손님에게 보낼 글.
        brand: ``LAHOM``/``HAUD`` — 어느 채널 키를 쓸지.
        bot_name: 보낸 이로 보일 봇 이름.
        request_id: 다시 읽어 맞출 표지(같은 값으로 다시 부르지 말 것 — 채널톡은 겹침을 거르지 않는다).

    Returns:
        ``{'success': bool, 'message_id': str | None, 'created_at': Any, 'error': str | None}``.

    Raises:
        ValueError: 상담 id · requestId 꼴이 틀렸다(네트워크 전).
    """
    if not isinstance(user_chat_id, str) or not CHAT_ID.fullmatch(user_chat_id):
        raise ValueError("상담 id 꼴이 아니다")
    if not isinstance(request_id, str) or not _REQUEST_ID.fullmatch(request_id):
        raise ValueError("requestId 꼴이 아니다")
    try:
        resp = _post_message(brand, quote(user_chat_id, safe=""), {"plainText": plain_text, "requestId": request_id},
                             bot_name=bot_name)
    except requests.RequestException as exc:
        logger.error("[채널톡] 공개 글 요청 실패 — 받았는지 모름 (chat=%s request=%s): %s", user_chat_id, request_id,
                     type(exc).__name__)
        return {"success": False, "message_id": None, "created_at": None, "error": "request_failed"}
    if resp is None:
        return {"success": False, "message_id": None, "created_at": None, "error": "not_configured"}
    if resp.status_code >= 400:
        logger.error("[채널톡] 공개 글 실패 (chat=%s request=%s) status=%s", user_chat_id, request_id, resp.status_code)
        error = "request_failed" if resp.status_code >= 500 else "provider_error"  # 5xx 는 받았는지 모른다
        return {"success": False, "message_id": None, "created_at": None, "error": error}
    try:
        data = resp.json()
    except ValueError:
        data = None
    message_id, created_at = _sent(data)
    return {"success": True, "message_id": message_id, "created_at": created_at, "error": None}


def send_user_chat_buttons(
    brand: str,
    user_chat_id: str,
    plain_text: str,
    buttons: list[tuple[str, str]],
    *,
    bot_name: str = "FOMS",
) -> dict[str, Any]:
    """
    Write a customer-visible message with link buttons into a user chat (Open API).

    앱 함수는 버튼을 422 로 거절했지만 Open API 공식 형식으로 보내면 카카오 상담톡에도 버튼으로
    간다(2026-10-21 실폰 확인). 키가 없으면 ``not_configured`` — 호출자가 글 속 링크로 보낸다.

    Args:
        brand: ``LAHOM``/``HAUD`` — 어느 채널 키를 쓸지.
        user_chat_id: 채널톡 userChat id.
        plain_text: 버튼 위에 보일 글.
        buttons: ``[(버튼 이름, 열 주소), ...]`` — 한 글에 2개까지.
        bot_name: 보낸 이로 보일 봇 이름.

    Returns:
        ``{'success': bool, 'message_id': str | None, 'error': str | None}``.
    """
    if channel_client._open_api_headers(brand) is None:
        return {"success": False, "message_id": None, "error": "not_configured"}
    if not user_chat_id:
        return {"success": False, "message_id": None, "error": "no_user_chat"}
    body = {
        "plainText": plain_text,
        "buttons": [{"title": title, "colorVariant": "cobalt",
                     "action": {"type": "web", "attributes": {"url": url}}}
                    for title, url in buttons[:2]],
    }
    try:
        resp = _post_message(brand, user_chat_id, body, bot_name=bot_name)
    except Exception as exc:
        logger.error("[채널톡] 버튼 메시지 요청 실패 (chat=%s): %s", user_chat_id, exc)
        return {"success": False, "message_id": None, "error": "request_failed"}
    if resp is None:
        return {"success": False, "message_id": None, "error": "not_configured"}
    if resp.status_code >= 400:
        logger.error("[채널톡] 버튼 메시지 실패 (chat=%s) status=%s", user_chat_id, resp.status_code)
        return {"success": False, "message_id": None, "error": f"http_{resp.status_code}"}
    try:
        return {"success": True, "message_id": (resp.json().get("message") or {}).get("id"), "error": None}
    except ValueError:
        return {"success": True, "message_id": None, "error": None}
