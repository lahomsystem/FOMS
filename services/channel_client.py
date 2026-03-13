"""
채널톡 Native Functions API 클라이언트.
FOMS → 채널톡 그룹 메시지 전송을 담당합니다.

Base URL: https://app-store-api.channel.io
Endpoint: PUT /general/v1/native/functions
인증: x-access-token 헤더 (issueToken으로 발급, 30분 TTL, 29분 캐시)
"""

import os
import time
import logging
from threading import Lock

import requests

logger = logging.getLogger(__name__)

_NATIVE_FUNCTIONS_URL = "https://app-store-api.channel.io/general/v1/native/functions"
_TOKEN_TTL_SECONDS = 29 * 60  # 29분 캐시 (실제 만료 30분 - 1분 버퍼)

# 환경변수
CHANNEL_APP_SECRET = os.environ.get("CHANNEL_APP_SECRET", "")
CHANNEL_ID = os.environ.get("CHANNEL_ID", "")
CHANNEL_GROUP_MEASUREMENT = os.environ.get("CHANNEL_GROUP_MEASUREMENT", "")
CHANNEL_GROUP_CONSTRUCTION = os.environ.get("CHANNEL_GROUP_CONSTRUCTION", "")
CHANNEL_GROUP_GENERAL = os.environ.get("CHANNEL_GROUP_GENERAL", "")
FOMS_BASE_URL = os.environ.get("FOMS_BASE_URL", "https://lahom-production.up.railway.app")

# 토큰 캐시: {channel_id: (access_token, expires_at_unix_ts)}
_token_lock = Lock()
_token_cache: dict = {}

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

# 단계별 첨부파일 카테고리
_STATUS_TO_ATTACHMENT_CATEGORY = {
    "MEASURE": "measurement",
    "DRAWING": "drawing",
    "CONFIRM": "drawing",
    "CONSTRUCTION": "construction",
}


def is_configured() -> bool:
    """채널톡 환경변수(APP_SECRET, CHANNEL_ID)가 모두 설정되어 있는지 확인."""
    return bool(CHANNEL_APP_SECRET and CHANNEL_ID)


def get_target_group_id(status: str) -> str:
    """
    주문 상태에 따른 채널톡 Group ID 반환.

    Args:
        status: Order.status 값

    Returns:
        채널톡 Group ID 문자열 (미설정 시 빈 문자열)
    """
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
    """
    주문 상태에 맞는 첨부파일 카테고리 반환.

    Args:
        status: Order.status 값

    Returns:
        카테고리 문자열 또는 빈 문자열 (해당 없을 때)
    """
    return _STATUS_TO_ATTACHMENT_CATEGORY.get(status, "")


def format_order_message(
    customer_name: str,
    status: str,
    address: str,
    order_id: int,
    schedule: dict = None,
    event_type: str = "update",
) -> str:
    """
    FOMS 주문 데이터를 채널톡 plainText 메시지로 변환.

    Args:
        customer_name: 고객명
        status: 주문 상태 코드
        address: 주소
        order_id: 주문 ID
        schedule: structured_data['schedule'] 딕셔너리
        event_type: "new" (신규) / "update" (상태변경) / "save" (저장)

    Returns:
        채널톡 plainText 메시지 문자열
    """
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

    parts.append(f"{FOMS_BASE_URL}/orders/{order_id}/erp")

    return "\n".join(parts)


def _issue_token() -> tuple:
    """
    채널톡 issueToken Native Function 호출.

    Returns:
        (access_token, expires_at_unix_ts) 튜플

    Raises:
        RuntimeError: API 오류 시
    """
    payload = {
        "method": "issueToken",
        "params": {
            "secret": CHANNEL_APP_SECRET,
            "channelId": CHANNEL_ID,
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
    access_token = data["result"]["accessToken"]
    return access_token, time.time() + _TOKEN_TTL_SECONDS


def _get_access_token() -> str:
    """
    유효한 채널 액세스 토큰 반환. 캐시 우선, 만료 시 재발급.

    Returns:
        유효한 access_token 문자열

    Raises:
        RuntimeError: 환경변수 미설정 또는 API 오류 시
    """
    if not is_configured():
        raise RuntimeError("CHANNEL_APP_SECRET, CHANNEL_ID 환경변수 미설정")

    with _token_lock:
        cached = _token_cache.get(CHANNEL_ID)
        if cached and time.time() < cached[1]:
            return cached[0]

        access_token, expires_at = _issue_token()
        _token_cache[CHANNEL_ID] = (access_token, expires_at)
        return access_token


def send_group_message(
    group_id: str,
    plain_text: str,
    files: list = None,
    bot_name: str = "FOMS",
    raise_on_error: bool = False,
) -> dict:
    """
    채널톡 그룹 채팅방에 메시지 전송.

    Args:
        group_id: 대상 그룹 채팅방 ID
        plain_text: 텍스트 메시지 내용
        files: 첨부파일 목록. 각 항목: {"fileName": str, "url": str, "mime": str}
        bot_name: 봇 발신자 표시명
        raise_on_error: True이면 전송 실패(API 오류 포함) 시 예외를 re-raise

    Returns:
        {"success": bool, "message_id": str | None}
        message_id: 전송 성공 시 result.message.id, 실패 시 None
    """
    if not group_id:
        logger.warning("[채널톡] group_id 없음 - 전송 건너뜀")
        return {"success": False, "message_id": None}

    try:
        access_token = _get_access_token()
        payload = {
            "method": "writeGroupMessage",
            "params": {
                "channelId": CHANNEL_ID,
                "groupId": group_id,
                "rootMessageId": "",
                "broadcast": False,
                "dto": {
                    "plainText": plain_text,
                    "botName": bot_name,
                    "files": files or [],
                },
            },
        }
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
        data = resp.json()
        err = data.get("error") or {}
        if err.get("message"):
            logger.error("[채널톡] writeGroupMessage 오류: %s", err["message"])
            if raise_on_error:
                raise RuntimeError(err["message"])
            return {"success": False, "message_id": None}
        message_id = ((data.get("result") or {}).get("message") or {}).get("id")
        logger.info("[채널톡] 메시지 전송 완료 (group=%s, message_id=%s)", group_id, message_id)
        return {"success": True, "message_id": message_id}
    except Exception as e:
        logger.error("[채널톡] 메시지 전송 실패 (group=%s): %s", group_id, e)
        if raise_on_error:
            raise
        return {"success": False, "message_id": None}
