"""
ChannelTalk inbound/WAM security helpers.
"""
import hashlib
import hmac
import logging
import os
import time
import uuid
from functools import wraps
from threading import Lock

from flask import jsonify, request
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

logger = logging.getLogger(__name__)

CHANNEL_SIGNING_KEY = os.environ.get("CHANNEL_SIGNING_KEY", "")
SECRET_KEY = os.environ.get("SECRET_KEY", "dev-foms-secret-key-123")
WAM_DEFAULT_SCOPES = ("page", "attachments")
WAM_DEFAULT_ALLOWED_SECTIONS = ("customer", "site", "schedule", "people", "items", "attachments")

wam_serializer = URLSafeTimedSerializer(SECRET_KEY, salt="wam-launch-token")
wam_entry_serializer = URLSafeTimedSerializer(SECRET_KEY, salt="wam-entry-token")
wam_shortlink_serializer = URLSafeTimedSerializer(SECRET_KEY, salt="wam-short-link")
wam_session_serializer = URLSafeTimedSerializer(SECRET_KEY, salt="wam-session-token")
_used_entry_nonces: dict[str, float] = {}
_used_entry_nonces_lock = Lock()


def _get_nonce_store():
    redis_url = os.environ.get("REDIS_URL")
    if not redis_url:
        return None

    try:
        from redis import Redis

        return Redis.from_url(redis_url)
    except Exception as exc:
        logger.warning("[ChannelSecurity] Failed to initialize nonce store: %s", exc, exc_info=True)
        return None


def _consume_entry_nonce(nonce: str | None, ttl_seconds: int) -> bool:
    if not nonce:
        return False

    ttl_seconds = max(int(ttl_seconds or 30), 1)
    store = _get_nonce_store()
    if store is not None:
        try:
            return bool(store.set(f"wam:entry-nonce:{nonce}", "1", ex=ttl_seconds, nx=True))
        except Exception as exc:
            logger.warning("[ChannelSecurity] Redis nonce consume failed: %s", exc, exc_info=True)

    now = time.time()
    with _used_entry_nonces_lock:
        expired = [key for key, expires_at in _used_entry_nonces.items() if expires_at <= now]
        for key in expired:
            _used_entry_nonces.pop(key, None)

        if nonce in _used_entry_nonces:
            return False

        _used_entry_nonces[nonce] = now + ttl_seconds
        return True


def _normalize_wam_payload(payload):
    if not isinstance(payload, dict):
        return None

    normalized = dict(payload)
    order_id = normalized.get("order_id")
    if order_id in (None, ""):
        return None

    try:
        normalized["order_id"] = int(order_id)
    except (TypeError, ValueError):
        return None

    scopes = normalized.get("scopes")
    if not scopes:
        scopes = list(WAM_DEFAULT_SCOPES)
    elif isinstance(scopes, str):
        scopes = [scopes]
    else:
        scopes = [str(scope) for scope in scopes if scope]

    normalized["scopes"] = scopes
    allowed_sections = normalized.get("allowed_sections")
    if not allowed_sections:
        allowed_sections = list(WAM_DEFAULT_ALLOWED_SECTIONS)
    elif isinstance(allowed_sections, str):
        allowed_sections = [allowed_sections]
    else:
        allowed_sections = [str(section) for section in allowed_sections if section]

    normalized["allowed_sections"] = allowed_sections
    attachment_scope = normalized.get("attachment_scope")
    if not attachment_scope:
        attachment_scope = "order" if "attachments" in scopes else "none"
    normalized["attachment_scope"] = str(attachment_scope)

    mapped_user_id = normalized.get("mapped_foms_user_id")
    if mapped_user_id in (None, ""):
        normalized["mapped_foms_user_id"] = None
    else:
        try:
            normalized["mapped_foms_user_id"] = int(mapped_user_id)
        except (TypeError, ValueError):
            normalized["mapped_foms_user_id"] = None

    normalized["nonce"] = str(normalized["nonce"]) if normalized.get("nonce") else None
    normalized.setdefault("token_type", "wam_launch")
    normalized.setdefault("source", "launch_token")
    return normalized


def _build_wam_token_payload(manager_id: str, order_id: int = None, **extra_claims) -> dict:
    payload = {
        "manager_id": manager_id,
        "order_id": order_id,
        "iat": time.time(),
        "scopes": list(WAM_DEFAULT_SCOPES),
        "allowed_sections": list(WAM_DEFAULT_ALLOWED_SECTIONS),
        "attachment_scope": "order",
    }
    for key, value in extra_claims.items():
        if value is not None:
            payload[key] = value
    normalized = _normalize_wam_payload(payload)
    if normalized is None:
        raise ValueError("Invalid WAM token payload")
    return normalized


def verify_channel_signature(raw_body: bytes, signature: str) -> bool:
    if not CHANNEL_SIGNING_KEY or not signature:
        return False

    expected_hash = hmac.new(
        CHANNEL_SIGNING_KEY.encode("utf-8"),
        msg=raw_body,
        digestmod=hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(expected_hash, signature)


def require_channel_signature(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if os.environ.get("CHANNEL_INBOUND_ENABLED", "true").lower() == "false":
            return (
                jsonify(
                    {
                        "error": "inbound_disabled",
                        "message": "Channel inbound is disabled via feature flag",
                    }
                ),
                503,
            )

        signature = request.headers.get("x-signature", "")
        if not signature:
            logger.warning("[ChannelSecurity] Missing x-signature header")
            return jsonify({"error": "unauthorized", "message": "Missing x-signature"}), 401

        raw_body = request.get_data()
        if not verify_channel_signature(raw_body, signature):
            logger.warning("[ChannelSecurity] Invalid x-signature")
            return jsonify({"error": "unauthorized", "message": "Invalid signature"}), 401

        payload = request.get_json(silent=True) or {}
        created_at_ms = payload.get("entity", {}).get("createdAt")
        if created_at_ms and isinstance(created_at_ms, (int, float)):
            now_ms = time.time() * 1000
            diff_ms = now_ms - created_at_ms
            window_secs = int(os.environ.get("CHANNEL_REPLAY_WINDOW_SECONDS", 300))
            if window_secs <= 0:
                window_secs = 300
            window_ms = window_secs * 1000
            if diff_ms > window_ms or diff_ms < -60000:
                logger.warning(
                    "[ChannelSecurity] Stale payload or Replay attack detected. Diff: %.1f ms",
                    diff_ms,
                )
                return (
                    jsonify(
                        {
                            "error": "forbidden",
                            "message": "Payload timestamp out of valid window",
                        }
                    ),
                    403,
                )

        return f(*args, **kwargs)

    return decorated_function


def generate_wam_launch_token(manager_id: str, order_id: int = None, **extra_claims) -> str:
    payload = _build_wam_token_payload(
        manager_id,
        order_id,
        token_type="wam_launch",
        source="launch_token",
        **extra_claims,
    )
    return wam_serializer.dumps(payload)


def generate_wam_entry_token(manager_id: str, order_id: int = None, **extra_claims) -> str:
    payload = _build_wam_token_payload(
        manager_id,
        order_id,
        token_type="wam_entry",
        source="entry_ticket",
        nonce=extra_claims.pop("nonce", None) or uuid.uuid4().hex,
        **extra_claims,
    )
    return wam_entry_serializer.dumps(payload)


def generate_wam_short_link_token(order_id: int, manager_id: str = "wam_viewer", **extra_claims) -> str:
    # Keep the default shareable link payload as small as possible because it is
    # surfaced directly in ChannelTalk messages. Non-default manager bindings
    # still use a compact dict so binding checks continue to work.
    if manager_id == "wam_viewer" and not extra_claims:
        return wam_shortlink_serializer.dumps(int(order_id))

    payload = {"o": int(order_id)}
    if manager_id != "wam_viewer":
        payload["m"] = manager_id

    claim_aliases = {
        "scopes": "s",
        "allowed_sections": "a",
        "attachment_scope": "t",
        "mapped_foms_user_id": "u",
    }
    for key, alias in claim_aliases.items():
        value = extra_claims.get(key)
        if value is not None:
            payload[alias] = value
    return wam_shortlink_serializer.dumps(payload)


def generate_wam_session_token(manager_id: str, order_id: int = None, **extra_claims) -> str:
    payload = _build_wam_token_payload(
        manager_id,
        order_id,
        token_type="wam_session",
        source="session_cookie",
        nonce=extra_claims.pop("nonce", None) or uuid.uuid4().hex,
        **extra_claims,
    )
    return wam_session_serializer.dumps(payload)


def verify_wam_launch_token(token: str, max_age: int = 3600) -> dict:
    try:
        payload = wam_serializer.loads(token, max_age=max_age)
        return _normalize_wam_payload(payload)
    except SignatureExpired:
        logger.warning("[ChannelSecurity] WAM token expired")
        return None
    except BadSignature:
        logger.warning("[ChannelSecurity] Invalid WAM token")
        return None


def verify_wam_entry_token(token: str, max_age: int = 30) -> dict:
    try:
        payload = wam_entry_serializer.loads(token, max_age=max_age)
        normalized = _normalize_wam_payload(payload)
        if not normalized:
            return None
        if not _consume_entry_nonce(normalized.get("nonce"), max_age):
            logger.warning("[ChannelSecurity] Reused WAM entry token")
            return None
        return normalized
    except SignatureExpired:
        logger.warning("[ChannelSecurity] WAM entry token expired")
        return None
    except BadSignature:
        logger.warning("[ChannelSecurity] Invalid WAM entry token")
        return None


def verify_wam_short_link_token(token: str, max_age: int = 30 * 24 * 3600) -> dict:
    try:
        payload = wam_shortlink_serializer.loads(token, max_age=max_age)
        if isinstance(payload, int):
            payload = {
                "manager_id": "wam_viewer",
                "order_id": payload,
                "token_type": "wam_shortlink",
                "source": "short_link",
            }
        if isinstance(payload, str) and payload.isdigit():
            payload = {
                "manager_id": "wam_viewer",
                "order_id": int(payload),
                "token_type": "wam_shortlink",
                "source": "short_link",
            }
        if isinstance(payload, dict) and "o" in payload:
            payload = {
                "manager_id": payload.get("m", "wam_viewer"),
                "order_id": payload.get("o"),
                "token_type": "wam_shortlink",
                "source": "short_link",
                "scopes": payload.get("s"),
                "allowed_sections": payload.get("a"),
                "attachment_scope": payload.get("t"),
                "mapped_foms_user_id": payload.get("u"),
            }

        normalized = _normalize_wam_payload(payload)
        if normalized:
            return normalized

        logger.warning("[ChannelSecurity] Invalid WAM short link payload type")
        return None
    except SignatureExpired:
        logger.warning("[ChannelSecurity] WAM short link expired")
        return None
    except BadSignature:
        logger.warning("[ChannelSecurity] Invalid WAM short link token")
        return None


def verify_wam_session_token(token: str, max_age: int = 300) -> dict:
    try:
        payload = wam_session_serializer.loads(token, max_age=max_age)
        return _normalize_wam_payload(payload)
    except SignatureExpired:
        logger.warning("[ChannelSecurity] WAM session token expired")
        return None
    except BadSignature:
        logger.warning("[ChannelSecurity] Invalid WAM session token")
        return None
