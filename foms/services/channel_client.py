"""ChannelTalk Native Functions API client."""

from __future__ import annotations

import logging
import os
import re
import time
from threading import Lock
from typing import Any
from urllib.parse import quote

import requests

logger = logging.getLogger(__name__)

_NATIVE_FUNCTIONS_URL = "https://app-store-api.channel.io/general/v1/native/functions"
_TOKEN_TTL_SECONDS = 29 * 60  # 29-minute cache (30-minute expiry minus one-minute buffer)
_TOKEN_EXPIRY_BUFFER_SECONDS = 60  # issueToken 이 준 expiresIn 에서 뺄 안전 버퍼

CHANNEL_APP_SECRET = os.environ.get("CHANNEL_APP_SECRET", "")
CHANNEL_ID = os.environ.get("CHANNEL_ID", "")
CHANNEL_GROUP_MEASUREMENT = os.environ.get("CHANNEL_GROUP_MEASUREMENT", "")
CHANNEL_GROUP_CONSTRUCTION = os.environ.get("CHANNEL_GROUP_CONSTRUCTION", "")
CHANNEL_GROUP_GENERAL = os.environ.get("CHANNEL_GROUP_GENERAL", "")
FOMS_BASE_URL = os.environ.get("FOMS_BASE_URL", "https://lahom-production.up.railway.app")

__all__ = [
    "CHANNEL_APP_SECRET",
    "CHANNEL_ID",
    "CHANNEL_GROUP_MEASUREMENT",
    "CHANNEL_GROUP_CONSTRUCTION",
    "CHANNEL_GROUP_GENERAL",
    "FOMS_BASE_URL",
    "is_configured",
    "get_target_group_id",
    "get_attachment_category_for_status",
    "format_order_message",
    "build_channel_bot_name",
    "send_group_message",
    "send_user_chat_message",
    "send_user_chat_buttons",
    "label_user_chat",
    "send_private_memo",
    "PrivateOptionMissing",
    "OPEN_API_PRIVATE",
    "NATIVE_PRIVATE",
]

_BOT_NAME_PREFIX = "FOMS"
_BOT_NAME_MAX_LEN = 40

# Token cache: {channel_id: (access_token, expires_at_unix_ts)}
_token_lock = Lock()
_token_cache: dict[str, tuple[str, float]] = {}

_STATUS_KR = {
    "RECEIVED": "접수",
    "MEASURE": "실측",
    "DRAWING": "도면",
    "CONFIRM": "컨펌",
    "PRODUCTION": "생산",
    "CONSTRUCTION": "시공",
    "CS": "CS",
    "COMPLETED": "완료",
    "AS": "AS",
}

_STATUS_TO_ATTACHMENT_CATEGORY = {
    "MEASURE": "measurement",
    "DRAWING": "drawing",
    "CONFIRM": "drawing",
    "CONSTRUCTION": "construction",
}


def is_configured() -> bool:
    """Return whether the required ChannelTalk env vars are configured."""
    return bool(CHANNEL_APP_SECRET and CHANNEL_ID)


def get_target_group_id(status: str) -> str:
    """Return the ChannelTalk group id for an order status."""
    mapping = {
        "RECEIVED": CHANNEL_GROUP_GENERAL,
        "MEASURE": CHANNEL_GROUP_MEASUREMENT,
        "DRAWING": CHANNEL_GROUP_MEASUREMENT,
        "CONFIRM": CHANNEL_GROUP_MEASUREMENT,
        "PRODUCTION": CHANNEL_GROUP_GENERAL,
        "CONSTRUCTION": CHANNEL_GROUP_CONSTRUCTION,
        "CS": CHANNEL_GROUP_GENERAL,
        "COMPLETED": CHANNEL_GROUP_GENERAL,
        "AS": CHANNEL_GROUP_GENERAL,
    }
    return mapping.get(status, CHANNEL_GROUP_GENERAL) or ""


def get_attachment_category_for_status(status: str) -> str:
    """Return the attachment category for an order status."""
    return _STATUS_TO_ATTACHMENT_CATEGORY.get(status, "")


def _build_order_detail_url(order_id: int) -> str:
    base_url = FOMS_BASE_URL.rstrip("/")
    try:
        return f"{base_url}/erp/orders/{int(order_id)}/mobile"
    except (TypeError, ValueError):
        return f"{base_url}/erp/orders/{order_id}"


def format_order_message(
    customer_name: str,
    status: str,
    address: str,
    order_id: int,
    schedule: dict[str, Any] | None = None,
    event_type: str = "update",
) -> str:
    """Build the legacy order message text."""
    event_label = {
        "new": "신규 접수",
        "update": "상태 변경",
        "save": "정보 저장",
    }.get(event_type, "업데이트")

    status_kr = _STATUS_KR.get(status, status)
    schedule = schedule or {}

    parts = [
        f"[{event_label}] {customer_name or '고객명 없음'}",
        f"상태: {status_kr}",
    ]

    if address:
        parts.append(f"주소: {address}")

    measure_date = (schedule.get("measurement") or {}).get("date", "")
    if measure_date:
        parts.append(f"실측일: {measure_date}")

    construction_date = (schedule.get("construction") or {}).get("date", "")
    if construction_date:
        parts.append(f"시공일: {construction_date}")

    parts.append(_build_order_detail_url(order_id))

    return "\n".join(parts)


def build_channel_bot_name(pushed_by_name: str | None = None) -> str:
    """
    Build the ChannelTalk bot display name for manual ERP push.

    Args:
        pushed_by_name: FOMS login user display name (``User.name``).

    Returns:
        ``FOMS{name}`` when name is present, otherwise ``FOMS``.
    """
    name = re.sub(r"[\x00-\x1f\x7f]", "", (pushed_by_name or "").strip())
    if not name:
        return _BOT_NAME_PREFIX
    bot_name = f"{_BOT_NAME_PREFIX}{name}"
    return bot_name[:_BOT_NAME_MAX_LEN]


def _issue_token(channel_id: str = "") -> tuple[str, float]:
    """Issue a ChannelTalk access token and return it with its local expiry timestamp.

    ``channel_id`` 를 주면 그 채널 토큰을 받는다(라홈·하우드는 채널톡 채널이 따로다 —
    앱이 그 채널에도 설치돼 있어야 한다). 비우면 기본 ``CHANNEL_ID``.
    """
    payload = {
        "method": "issueToken",
        "params": {
            "secret": CHANNEL_APP_SECRET,
            "channelId": channel_id or CHANNEL_ID,
        },
    }
    resp = requests.put(
        _NATIVE_FUNCTIONS_URL,
        json=payload,
        headers={"Content-Type": "application/json"},
        timeout=10,
    )
    resp.raise_for_status()
    data = resp.json()
    err = data.get("error") or {}
    if err.get("message"):
        raise RuntimeError(f"채널톡 issueToken 오류: {err['message']}")
    result = data["result"]
    access_token = result["accessToken"]
    try:
        ttl = int(result["expiresIn"]) - _TOKEN_EXPIRY_BUFFER_SECONDS
    except (KeyError, TypeError, ValueError):
        ttl = _TOKEN_TTL_SECONDS
    return access_token, time.time() + max(ttl, 60)


def _get_access_token(channel_id: str = "") -> str:
    """Return a cached valid access token (per channel) or issue a new one."""
    if not is_configured():
        raise RuntimeError("CHANNEL_APP_SECRET, CHANNEL_ID 환경변수 미설정")

    cid = channel_id or CHANNEL_ID
    with _token_lock:
        cached = _token_cache.get(cid)
        if cached and time.time() < cached[1]:
            return cached[0]

        access_token, expires_at = _issue_token(cid)
        _token_cache[cid] = (access_token, expires_at)
        return access_token


def _invalidate_token(stale_token: str, channel_id: str = "") -> None:
    """
    Drop the cached access token when ChannelTalk rejected it.

    다른 스레드가 이미 새 토큰을 캐시했으면 그대로 둔다(방금 실패한 토큰만 버린다).

    Args:
        stale_token: 401 을 받은 토큰 값.
    """
    cid = channel_id or CHANNEL_ID
    with _token_lock:
        cached = _token_cache.get(cid)
        if cached and cached[0] == stale_token:
            _token_cache.pop(cid, None)


def _is_unauthenticated_error(err: dict[str, Any]) -> bool:
    """
    Return whether a native-functions error means the access token is no longer valid.

    ChannelTalk 은 토큰이 죽으면 ``{"type":"unauthenticatedError","status":401,...}`` 을
    ``error.data`` 로 주거나 ``error.message`` 문자열 안에 그대로 실어 보낸다.

    Args:
        err: 응답 JSON 의 ``error`` 객체.

    Returns:
        토큰 재발급이 필요한 인증 오류면 True.
    """
    data = err.get("data") or {}
    if str(data.get("type") or "").lower() == "unauthenticatederror":
        return True
    message = str(err.get("message") or "").lower()
    return "unauthenticatederror" in message


def _put_native_function(payload: dict[str, Any], access_token: str) -> dict[str, Any]:
    """
    Call the native-functions endpoint with an access token and return the parsed body.

    Args:
        payload: ``method``/``params`` 요청 본문.
        access_token: ``x-access-token`` 헤더 값.

    Returns:
        응답 JSON dict.
    """
    resp = requests.put(
        _NATIVE_FUNCTIONS_URL,
        json=payload,
        headers={
            "Content-Type": "application/json",
            "x-access-token": access_token,
        },
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json()


def _call_native_function(payload: dict[str, Any], channel_id: str = "") -> dict[str, Any]:
    """
    Call a native function with the cached token, retrying once on a dead token.

    캐시된 토큰이 만료 전에 무효화되는 경우가 있다(채널톡이 세션을 끊음). 죽은 토큰을
    버리고 재발급해 1회 재시도한다.

    Args:
        payload: ``method``/``params`` 요청 본문.
        channel_id: 토큰을 받을 채널(비우면 기본 ``CHANNEL_ID``).

    Returns:
        응답 JSON dict(``result`` 또는 ``error``).
    """
    access_token = _get_access_token(channel_id)
    data = _put_native_function(payload, access_token)
    err = data.get("error") or {}
    if err.get("message") and _is_unauthenticated_error(err):
        logger.warning("[채널톡] 액세스 토큰 무효 - 재발급 후 1회 재시도")
        _invalidate_token(access_token, channel_id)
        data = _put_native_function(payload, _get_access_token(channel_id))
    return data


def send_user_chat_message(
    user_chat_id: str,
    plain_text: str,
    *,
    bot_name: str = "FOMS",
    private: bool = False,
    channel_id: str = "",
) -> dict[str, Any]:
    """
    Write a message into a customer user chat (``writeUserChatMessage``).

    고객 상담(userChat)에 쓰는 유일한 경로다. 카카오 상담톡 상담이면 고객 카톡 대화방으로
    전달된다. ``private`` 면 매니저에게만 보이는 내부 메모로 쓴다(고객에게 안 감).
    실패는 예외 대신 ``success=False`` 로 돌려준다 — 호출자가 발급한 링크를 회수하는 등
    뒷정리를 해야 하므로 결과를 꼭 확인해야 한다.

    Args:
        user_chat_id: 채널톡 userChat id.
        plain_text: 보낼 글(링크는 글 안에 그대로 넣는다 — 카카오에서도 눌린다).
        bot_name: 보낸 이로 보일 봇 이름.
        private: 내부 메모로 쓸지.
        channel_id: 상담이 있는 채널(웹훅이 알려 준 값). 라홈·하우드는 채널이 따로라
            반드시 넘긴다. 비우면 기본 ``CHANNEL_ID``.

    Returns:
        ``{'success': bool, 'message_id': str | None, 'error': str | None}``.
    """
    if not user_chat_id:
        return {"success": False, "message_id": None, "error": "no_user_chat"}
    dto: dict[str, Any] = {"plainText": plain_text, "botName": bot_name}
    if private:
        dto["options"] = ["MESSAGE_OPTION_PRIVATE"]
    payload = {
        "method": "writeUserChatMessage",
        "params": {"channelId": channel_id or CHANNEL_ID, "userChatId": user_chat_id, "dto": dto},
    }
    try:
        data = _call_native_function(payload, channel_id)
    except Exception as exc:
        logger.error("[채널톡] writeUserChatMessage 실패 (chat=%s): %s", user_chat_id, exc)
        return {"success": False, "message_id": None, "error": "request_failed"}
    err = data.get("error") or {}
    if err.get("message"):
        logger.error("[채널톡] writeUserChatMessage 오류 (chat=%s): %s", user_chat_id, err["message"])
        return {"success": False, "message_id": None, "error": "provider_error"}
    message_id = ((data.get("result") or {}).get("message") or {}).get("id")
    return {"success": True, "message_id": message_id, "error": None}


#: 채널톡 Open API(앱 함수에는 고객·상담 이름을 바꾸는 기능이 없다). 키는 채널마다 따로다.
_OPEN_API_BASE = "https://api.channel.io"
_OPEN_API_VERSION = "2026-06-01"


def _open_api_headers(brand: str) -> dict[str, str] | None:
    """브랜드 채널의 Open API 인증 헤더. 키가 없으면 ``None``(이름표 기능 꺼짐)."""
    key = os.environ.get(f"CHANNEL_OPENAPI_KEY_{brand}", "").strip()
    secret = os.environ.get(f"CHANNEL_OPENAPI_SECRET_{brand}", "").strip()
    if not (key and secret):
        return None
    return {"x-access-key": key, "x-access-secret": secret,
            "Channel-Version": _OPEN_API_VERSION, "Content-Type": "application/json"}


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
    headers = _open_api_headers(brand)
    if headers is None:
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
        resp = requests.post(f"{_OPEN_API_BASE}/open/user-chats/{user_chat_id}/messages",
                             params={"botName": bot_name}, json=body, headers=headers, timeout=10)
    except Exception as exc:
        logger.error("[채널톡] 버튼 메시지 요청 실패 (chat=%s): %s", user_chat_id, exc)
        return {"success": False, "message_id": None, "error": "request_failed"}
    if resp.status_code >= 400:
        logger.error("[채널톡] 버튼 메시지 실패 (chat=%s) status=%s", user_chat_id, resp.status_code)
        return {"success": False, "message_id": None, "error": f"http_{resp.status_code}"}
    try:
        return {"success": True, "message_id": (resp.json().get("message") or {}).get("id"), "error": None}
    except ValueError:
        return {"success": True, "message_id": None, "error": None}


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
    :func:`send_user_chat_message` 와 같다. 글은 로그에 싣지 않는다.

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
                   "params": {"channelId": channel_id or CHANNEL_ID, "userChatId": user_chat_id, "dto": dto}}
        _require_private(payload["params"]["dto"]["options"], NATIVE_PRIVATE)
        try:
            data = _call_native_function(payload, channel_id)
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
    headers = _open_api_headers(brand)
    if headers is None:
        return {"success": False, "message_id": None, "error": "not_configured"}
    body = {"plainText": plain_text, "buttons": button_items, "options": [OPEN_API_PRIVATE]}
    _require_private(body["options"], OPEN_API_PRIVATE)
    try:
        resp = requests.post(f"{_OPEN_API_BASE}/open/user-chats/{quote(user_chat_id, safe='')}/messages",
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


def label_user_chat(
    brand: str,
    *,
    user_chat_id: str,
    user_id: str,
    customer_name: str,
    description: str,
) -> dict[str, Any]:
    """
    Name the customer and describe the user chat so the inbox shows who it is.

    카카오 상담톡 고객은 채널톡 받은편지함에 이름 없이 뜬다. 고객 프로필 이름을 주문의
    고객 이름으로, 상담 설명을 "주문 · 고객 · 담당"으로 적는다. 실패해도 링크 발송은 이미
    끝났으므로 예외 없이 결과만 돌려준다.

    Args:
        brand: ``LAHOM``/``HAUD`` — 어느 채널 키를 쓸지.
        user_chat_id: 채널톡 userChat id.
        user_id: 채널톡 user id(웹훅 ``entity.personId``).
        customer_name: 고객 이름.
        description: 상담 설명(1000자 이하).

    Returns:
        ``{'success': bool, 'error': str | None}``.
    """
    headers = _open_api_headers(brand)
    if headers is None:
        return {"success": False, "error": "not_configured"}
    calls = []
    if user_id and customer_name:
        calls.append((f"{_OPEN_API_BASE}/open/users/{user_id}", {"profile": {"name": customer_name}}))
    if user_chat_id and description:
        calls.append((f"{_OPEN_API_BASE}/open/user-chats/{user_chat_id}",
                      {"description": description[:1000]}))
    error = None
    for url, body in calls:
        try:
            resp = requests.patch(url, json=body, headers=headers, timeout=10)
            if resp.status_code >= 400:
                logger.warning("[채널톡] 이름표 실패 %s status=%s", url.rsplit("/", 2)[-2], resp.status_code)
                error = f"http_{resp.status_code}"
        except Exception as exc:
            logger.warning("[채널톡] 이름표 요청 실패: %s", exc)
            error = "request_failed"
    return {"success": error is None, "error": error}


def send_group_message(
    group_id: str,
    plain_text: str,
    blocks: list[dict[str, Any]] | None = None,
    files: list[dict[str, Any]] | None = None,
    bot_name: str = "FOMS",
    raise_on_error: bool = False,
) -> dict[str, Any]:
    """Send a message to a ChannelTalk group chat."""
    if not group_id:
        logger.warning("[채널톡] group_id 없음 - 전송 건너뜀")
        return {"success": False, "message_id": None}

    try:
        payload = {
            "method": "writeGroupMessage",
            "params": {
                "channelId": CHANNEL_ID,
                "groupId": group_id,
                "rootMessageId": "",
                "broadcast": False,
                "dto": {
                    "plainText": plain_text,
                    "blocks": blocks or [],
                    "botName": bot_name,
                    "files": files or [],
                },
            },
        }
        data = _call_native_function(payload)
        err = data.get("error") or {}
        if err.get("message"):
            logger.error("[채널톡] writeGroupMessage 오류: %s", err["message"])
            if raise_on_error:
                raise RuntimeError(err["message"])
            return {"success": False, "message_id": None}
        message_id = ((data.get("result") or {}).get("message") or {}).get("id")
        logger.info("[채널톡] 메시지 전송 완료 (group=%s, message_id=%s)", group_id, message_id)
        return {"success": True, "message_id": message_id}
    except Exception as exc:
        logger.error("[채널톡] 메시지 전송 실패 (group=%s): %s", group_id, exc)
        if raise_on_error:
            raise
        return {"success": False, "message_id": None}
