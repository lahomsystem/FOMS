"""ChannelTalk Native Function 전용 서명·설정 계약 (CHANNEL-FUNCTION-CONTRACT-01).

이 모듈은 ChannelTalk Function 호출을 검증하는 **전용** 서명 체계를 소유한다. Webhook
서명(raw UTF-8 key + hex digest, ``channel_security.require_channel_signature``)을 절대
재사용하지 않는다. Function 서명은 다음을 요구한다:

* 서명 key = ``CHANNEL_FUNCTION_SIGNING_KEY`` 를 **hex-decode**(≥32 byte). raw UTF-8 금지.
* 서명 대상 = 요청 **원본 body(raw bytes)**. 재직렬화 금지.
* digest = HMAC-SHA256 → **Base64**(hex digest 금지).
* 비교 = ``hmac.compare_digest`` (constant-time, 타이밍 공격 방지).

disable gate(``CHANNEL_FUNCTION_ENABLED`` false·미설정=기본)는 provider 를 호출하기
**전에** 404 로 닫는다(provider-first). enable 상태에서 signing key/channel 미설정은
**fail-start**(앱 기동 실패, 조용한 우회 금지)다. read-only Function 이므로 어떤 경로도
Order 를 변경하지 않는다(PII/mutation 0). 성공·거부·오류 모두 HTTP 200 provider 봉투
(``{result|error}``)로 답하고, transport 실패만 401/400/404/405 로 분기한다.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import logging
import os

from flask import Blueprint, jsonify, request

logger = logging.getLogger(__name__)

channel_functions_bp = Blueprint('channel_functions', __name__, url_prefix='/api/channel/functions')

_ENABLED_ENV = "CHANNEL_FUNCTION_ENABLED"
_SIGNING_KEY_ENV = "CHANNEL_FUNCTION_SIGNING_KEY"
_CHANNEL_ID_ENV = "CHANNEL_FUNCTION_CHANNEL_ID"
_SIGNATURE_HEADER = "x-signature"
_MIN_KEY_BYTES = 32
_OFFICIAL_METHOD = "PUT"

#: 존재 여부·PII 를 노출하지 않는 단일 generic 오류 문구(모든 provider-level 실패 공통).
_GENERIC_ERROR = "요청을 처리할 수 없습니다."

#: 실제 등록된 Function method → 정확한 param 스키마(accept-all/wildcard 금지, stale 금지).
#: provider fixture 와 method schema manifest 는 이 정본을 반영해야 하며, 미등록 method 는
#: deny 와 구분 불가한 generic 오류로 답한다(존재 여부 미노출).
REGISTERED_FUNCTION_METHODS: dict[str, dict[str, str]] = {
    "foms": {"text": "str"},
}


def function_enabled() -> bool:
    """``CHANNEL_FUNCTION_ENABLED`` 이 명시적으로 ``true`` 일 때만 Function 을 활성화한다.

    기본값은 비활성(provider-first disable gate): 미설정/``false`` 는 blueprint 가 없는
    것처럼 모든 method 를 404 로 닫고 provider 를 호출하지 않는다.

    :returns: Function 이 활성화되어 있으면 True.
    """
    return os.environ.get(_ENABLED_ENV, "false").strip().lower() == "true"


def _decode_signing_key() -> bytes:
    """Function 서명 key 를 hex-decode 한다(≥32 byte 강제, raw UTF-8 금지).

    :returns: decode 된 key bytes.
    :raises RuntimeError: key 미설정·hex 아님·32 byte 미만(loud fail, 조용한 우회 금지).
    """
    raw = os.environ.get(_SIGNING_KEY_ENV, "").strip()
    if not raw:
        raise RuntimeError(f"{_SIGNING_KEY_ENV} is required when {_ENABLED_ENV}=true")
    try:
        key = bytes.fromhex(raw)
    except ValueError as exc:
        raise RuntimeError(f"{_SIGNING_KEY_ENV} must be hex-encoded (raw UTF-8 금지)") from exc
    if len(key) < _MIN_KEY_BYTES:
        raise RuntimeError(
            f"{_SIGNING_KEY_ENV} must decode to >= {_MIN_KEY_BYTES} bytes (got {len(key)})"
        )
    return key


def _configured_channel_id() -> str:
    """Function 이 신뢰하는 ChannelTalk channel id(signed context 와 exact 비교 대상).

    :returns: 설정된 channel id.
    :raises RuntimeError: 미설정(fail-start).
    """
    channel_id = os.environ.get(_CHANNEL_ID_ENV, "").strip()
    if not channel_id:
        raise RuntimeError(f"{_CHANNEL_ID_ENV} is required when {_ENABLED_ENV}=true")
    return channel_id


def validate_function_config() -> None:
    """enable 상태의 필수 설정(signing key·channel)을 기동 시 검증한다(fail-start).

    disable 상태(기본)면 no-op — provider-first: 비활성 Function 은 설정을 요구하지 않는다.
    enable 상태에서 key(hex≥32B)·channel 중 하나라도 없으면 ``RuntimeError`` 로 앱 기동을
    막는다. 모듈 import 시 1회 호출되어 잘못 활성화된 배포를 기동 단계에서 차단한다.
    """
    if not function_enabled():
        return
    _decode_signing_key()
    _configured_channel_id()


def verify_function_signature(raw_body: bytes, signature: str) -> bool:
    """Function 요청 서명을 검증한다(Webhook 서명 체계와 완전히 분리).

    hex-decode key → raw body HMAC-SHA256 → Base64 → constant-time 비교. Webhook 이 쓰는
    raw UTF-8 key·hex digest 를 재사용하지 않는다.

    :param raw_body: 요청 원본 body bytes(재직렬화 금지).
    :param signature: ``x-signature`` 헤더의 Base64 서명값.
    :returns: 서명이 유효하면 True, 미서명/위조/형식오류면 False.
    """
    if not signature:
        return False
    key = _decode_signing_key()
    digest = hmac.new(key, msg=raw_body, digestmod=hashlib.sha256).digest()
    expected = base64.b64encode(digest).decode("ascii")
    return hmac.compare_digest(expected, signature)


def _generic_error_result() -> dict:
    """존재 여부·PII 를 노출하지 않는 generic provider 오류 봉투(``{error}``)."""
    return {"error": {"message": _GENERIC_ERROR}}


@channel_functions_bp.route('', methods=['GET', 'POST', 'PUT'])
def handle_function():
    """ChannelTalk Function 요청을 검증하고 read-only provider 로 위임한다.

    보안 게이트 순서: (1) disable gate → 404(provider 미호출), (2) method gate → 405,
    (3) 서명 검증 → 401, (4) JSON 파싱 → 400, (5) signed context channel exact → 401,
    (6) caller exact 추출. 성공/거부/오류 모두 HTTP 200 provider 봉투(``{result|error}``)로
    답하며 Order 를 변경하지 않는다(read-only, PII/mutation 0).
    """
    # provider(도메인 로직)는 quick_actions 정본에서만 온다.
    from foms.services.channel_quick_actions import process_foms_command

    if not function_enabled():
        return jsonify({"error": "not_found"}), 404
    if request.method != _OFFICIAL_METHOD:
        return jsonify({"error": "method_not_allowed"}), 405

    raw_body = request.get_data()
    if not verify_function_signature(raw_body, request.headers.get(_SIGNATURE_HEADER, "")):
        return jsonify({"error": "unauthorized"}), 401

    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({"error": "invalid_json"}), 400

    context = payload.get("context") or {}
    channel = context.get("channel") or {}
    if str(channel.get("id") or "") != _configured_channel_id():
        return jsonify({"error": "unauthorized"}), 401

    # caller exact: 서명된 context 의 manager caller 만 인증 주체로 채택한다.
    # params/미서명 필드에서 caller 를 추정하지 않는다(권한 상승 차단).
    caller = context.get("caller") or {}
    manager_id = caller.get("id") if caller.get("type") == "manager" else None

    method = payload.get("method")
    if method not in REGISTERED_FUNCTION_METHODS:
        return jsonify(_generic_error_result()), 200

    params = payload.get("params") if isinstance(payload.get("params"), dict) else {}
    try:
        result = process_foms_command(params.get("text", ""), manager_id)
    except Exception:  # trust-boundary sanitizer: raw exception/stack 를 provider 에 미노출
        logger.exception("[ChannelFunction] provider call failed")
        return jsonify(_generic_error_result()), 200
    return jsonify(result), 200


# 기동 시 enable 상태의 필수 설정을 검증한다(fail-start). disable(기본)면 no-op.
validate_function_config()
