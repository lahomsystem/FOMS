"""ChannelTalk inbound and WAM security helpers."""

from __future__ import annotations

import hashlib
import hmac
import logging
import os
import time
import uuid
from datetime import timedelta
from functools import wraps
from typing import Any

from flask import jsonify, request
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from foms.services.datetime_kst import now_utc_naive
from foms.services.security.signing.signing_keys import (
    resolve_legacy_secret,
    resolve_secret_key_list,
    wam_not_before,
)

__all__ = [
    "verify_channel_signature",
    "require_channel_signature",
    "generate_wam_launch_token",
    "generate_wam_entry_token",
    "generate_wam_short_link_token",
    "generate_wam_session_token",
    "verify_wam_launch_token",
    "verify_wam_entry_token",
    "verify_wam_short_link_token",
    "verify_wam_session_token",
]

logger = logging.getLogger(__name__)

CHANNEL_SIGNING_KEY = os.environ.get("CHANNEL_SIGNING_KEY", "")
WAM_DEFAULT_SCOPES = ("page", "attachments")
WAM_DEFAULT_ALLOWED_SECTIONS = ("customer", "site", "schedule", "people", "items", "attachments")

# WAM 토큰 종류 → itsdangerous salt(= HKDF subkey label). 서명 key 는 상태기계에서 파생한다
# (SESSION-SIGNING-SECRET-01). legacy(미engaged/EMPTY/READY)는 legacy raw secret 로 byte-identical.
_WAM_LABELS = {
    "launch": "wam-launch-token",
    "entry": "wam-entry-token",
    "shortlink": "wam-short-link",
    "session": "wam-session-token",
}
# entry-token 의 iat 만료 여유(단일사용 nonce row TTL 계산용 최소값).
_ENTRY_NONCE_MIN_TTL = 30


def _wam_serializer(kind: str) -> URLSafeTimedSerializer:
    """WAM 토큰 종류별 state-aware 직렬화기(요청마다 상태기계에서 서명 key 파생, process cache 0).

    :param kind: ``launch``/``entry``/``shortlink``/``session``.
    :returns: 현재 서명 상태에 맞는 :class:`URLSafeTimedSerializer`.
    """
    label = _WAM_LABELS[kind]
    keys = resolve_secret_key_list("wam", label, legacy_secret=resolve_legacy_secret())
    return URLSafeTimedSerializer(keys, salt=label)


def claim_wam_entry_nonce(
    engine: Any, *, nonce_hash: str, subject_hash: str, ttl_seconds: int, now: Any = None,
) -> bool:
    """WAM entry nonce 를 PostgreSQL 단일사용(single-use)으로 원자 소비한다(P1-33).

    ``wam_entry_nonces`` 에 대한 한 statement 원자 claim: 최초 사용은 INSERT(consumed 표시)로
    성공하고, 재사용/replay 는 conflict 후 ``consumed_at IS NULL`` 조건 미충족으로 0 행 →
    거부한다. 동시 2 요청은 PK conflict 로 직렬화돼 정확히 1건만 성공한다(RETURNING). Redis/
    process-local fallback 을 두지 않으며, DB 미가용은 **fail-closed**(거부)다.

    :param engine: claim 을 커밋할 SQLAlchemy Engine(운영은 앱 엔진, 테스트는 pg_engine).
    :param nonce_hash: raw nonce 의 sha256 hex(raw 는 저장하지 않는다).
    :param subject_hash: 주체(manager/order) fingerprint hex.
    :param ttl_seconds: nonce row expires_at 여유 초.
    :param now: 기준 시각(테스트 주입용). 기본 :func:`now_utc_naive`.
    :returns: 이번 호출이 nonce 를 최초로 소비했으면 True, 재사용/만료/DB오류면 False.
    """
    now = now or now_utc_naive()
    exp = now + timedelta(seconds=max(int(ttl_seconds or _ENTRY_NONCE_MIN_TTL), 1))
    # 스키마리스 테스트 DB 대비 존재 시 no-op(운영은 STATE-00 마이그레이션이 이미 생성). 마이그레이션 아님.
    from models import WamEntryNonce

    try:
        WamEntryNonce.__table__.create(bind=engine, checkfirst=True)
        stmt = text(
            "INSERT INTO wam_entry_nonces "
            "(nonce_hash, subject_hash, expires_at, consumed_at, created_at) "
            "VALUES (:h, :subj, :exp, :now, :now) "
            "ON CONFLICT (nonce_hash) DO UPDATE SET consumed_at = :now "
            "WHERE wam_entry_nonces.consumed_at IS NULL "
            "AND wam_entry_nonces.expires_at > :now "
            "RETURNING nonce_hash"
        )
        with engine.begin() as conn:
            row = conn.execute(
                stmt, {"h": nonce_hash, "subj": subject_hash, "exp": exp, "now": now}
            ).fetchone()
    except SQLAlchemyError:
        logger.warning(
            "[ChannelSecurity] WAM entry nonce DB claim failed; rejecting (fail-closed).",
            exc_info=True,
        )
        return False
    return row is not None


def _consume_entry_nonce(nonce: str | None, ttl_seconds: int, subject_hash: str = "") -> bool:
    """entry nonce 를 앱 DB 엔진으로 단일사용 소비한다(:func:`claim_wam_entry_nonce` 래퍼)."""
    if not nonce:
        return False
    from db import engine

    return claim_wam_entry_nonce(
        engine,
        nonce_hash=hashlib.sha256(nonce.encode("utf-8")).hexdigest(),
        subject_hash=hashlib.sha256((subject_hash or "").encode("utf-8")).hexdigest(),
        ttl_seconds=ttl_seconds,
    )


def _normalize_wam_payload(payload: Any) -> dict[str, Any] | None:
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


def _build_wam_token_payload(manager_id: str, order_id: int | None = None, **extra_claims) -> dict[str, Any]:
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
    """Validate the inbound ChannelTalk webhook signature."""
    if not CHANNEL_SIGNING_KEY or not signature:
        return False

    expected_hash = hmac.new(
        CHANNEL_SIGNING_KEY.encode("utf-8"),
        msg=raw_body,
        digestmod=hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(expected_hash, signature)


def require_channel_signature(f):
    """Reject ChannelTalk requests that fail signature or replay checks."""

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


def generate_wam_launch_token(manager_id: str, order_id: int | None = None, **extra_claims) -> str:
    """Create a signed WAM launch token."""
    payload = _build_wam_token_payload(
        manager_id,
        order_id,
        token_type="wam_launch",
        source="launch_token",
        **extra_claims,
    )
    return _wam_serializer("launch").dumps(payload)


def generate_wam_entry_token(manager_id: str, order_id: int | None = None, **extra_claims) -> str:
    """Create a single-use WAM entry ticket."""
    payload = _build_wam_token_payload(
        manager_id,
        order_id,
        token_type="wam_entry",
        source="entry_ticket",
        nonce=extra_claims.pop("nonce", None) or uuid.uuid4().hex,
        **extra_claims,
    )
    return _wam_serializer("entry").dumps(payload)


def generate_wam_short_link_token(order_id: int, manager_id: str = "wam_viewer", **extra_claims) -> str:
    """Create the compact short-link token used in ChannelTalk messages."""
    # Keep the default shareable link payload as small as possible because it is
    # surfaced directly in ChannelTalk messages. Non-default manager bindings
    # still use a compact dict so binding checks continue to work.
    if manager_id == "wam_viewer" and not extra_claims:
        return _wam_serializer("shortlink").dumps(int(order_id))

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
    return _wam_serializer("shortlink").dumps(payload)


def generate_wam_session_token(manager_id: str, order_id: int | None = None, **extra_claims) -> str:
    """Create the short-lived WAM session cookie token."""
    payload = _build_wam_token_payload(
        manager_id,
        order_id,
        token_type="wam_session",
        source="session_cookie",
        nonce=extra_claims.pop("nonce", None) or uuid.uuid4().hex,
        **extra_claims,
    )
    return _wam_serializer("session").dumps(payload)


def _rejected_by_wam_cutoff(payload: Any) -> bool:
    """ACTIVE ``wam_not_before`` cutoff 이전에 발급된(iat) WAM 토큰인가(FORCE/compromise 무효화).

    legacy/EMPTY(cutoff None)나 iat 부재 payload 는 거부하지 않는다(회귀 0).
    """
    cutoff = wam_not_before()
    if cutoff is None or not isinstance(payload, dict):
        return False
    iat = payload.get("iat")
    if not isinstance(iat, (int, float)):
        return False
    # wam_not_before 는 naive UTC(now_utc_naive 규약) — UTC 로 해석해 epoch 로 변환한다
    # (naive.timestamp() 는 로컬TZ 로 오해석하므로 금지).
    from datetime import timezone

    cutoff_epoch = cutoff.replace(tzinfo=timezone.utc).timestamp()
    return iat < cutoff_epoch


def verify_wam_launch_token(token: str, max_age: int = 3600) -> dict[str, Any] | None:
    """Validate a WAM launch token and normalize its payload."""
    try:
        payload = _wam_serializer("launch").loads(token, max_age=max_age)
        if _rejected_by_wam_cutoff(payload):
            logger.warning("[ChannelSecurity] WAM launch token predates active signing cutoff")
            return None
        return _normalize_wam_payload(payload)
    except SignatureExpired:
        logger.warning("[ChannelSecurity] WAM token expired")
        return None
    except BadSignature:
        logger.warning("[ChannelSecurity] Invalid WAM token")
        return None


def verify_wam_entry_token(token: str, max_age: int = 30) -> dict[str, Any] | None:
    """Validate a WAM entry ticket and enforce single-use nonce semantics."""
    try:
        payload = _wam_serializer("entry").loads(token, max_age=max_age)
        if _rejected_by_wam_cutoff(payload):
            logger.warning("[ChannelSecurity] WAM entry token predates active signing cutoff")
            return None
        normalized = _normalize_wam_payload(payload)
        if not normalized:
            return None
        subject = f"{normalized.get('manager_id')}\0{normalized.get('order_id')}"
        if not _consume_entry_nonce(normalized.get("nonce"), max_age, subject_hash=subject):
            logger.warning("[ChannelSecurity] Reused WAM entry token")
            return None
        return normalized
    except SignatureExpired:
        logger.warning("[ChannelSecurity] WAM entry token expired")
        return None
    except BadSignature:
        logger.warning("[ChannelSecurity] Invalid WAM entry token")
        return None


def verify_wam_short_link_token(token: str, max_age: int = 30 * 24 * 3600) -> dict[str, Any] | None:
    """Validate a WAM short-link token and expand compact payload aliases."""
    try:
        payload = _wam_serializer("shortlink").loads(token, max_age=max_age)
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


def verify_wam_session_token(token: str, max_age: int = 300) -> dict[str, Any] | None:
    """Validate the WAM session cookie token."""
    try:
        payload = _wam_serializer("session").loads(token, max_age=max_age)
        if _rejected_by_wam_cutoff(payload):
            logger.warning("[ChannelSecurity] WAM session token predates active signing cutoff")
            return None
        return _normalize_wam_payload(payload)
    except SignatureExpired:
        logger.warning("[ChannelSecurity] WAM session token expired")
        return None
    except BadSignature:
        logger.warning("[ChannelSecurity] Invalid WAM session token")
        return None
