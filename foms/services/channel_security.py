"""ChannelTalk inbound and WAM security helpers."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import os
import time
import uuid
from datetime import timedelta
from functools import wraps
from typing import Any, Callable

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from flask import jsonify, request
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from foms.services.datetime_kst import now_utc_naive
from foms.services.security.backfill.crypto import lp
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
        # disabled → 404 provider-first: flag 가 명시적으로 false 면 서명 검증/provider 를
        # 호출하지 않고 blueprint 가 없는 것처럼 404 로 닫는다(존재 여부 미노출).
        if os.environ.get("CHANNEL_INBOUND_ENABLED", "true").strip().lower() == "false":
            return jsonify({"error": "not_found"}), 404

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


# ==========================================================================
# CHANNEL-WEBHOOK-AUTH-01 — Webhook token/config + acceptance transaction
# ==========================================================================
#
# Webhook 전용(Function `verify_function_signature` 와 완전 분리). provider token 은
# 위 ``require_channel_signature`` (raw UTF-8 key + hex HMAC digest, exact source/hash)
# 가 검증하고, 여기서는 config fail-start · JCS stable hash · versioned AES-256-GCM
# envelope · acceptance transaction(transactional outbox)을 정본화한다.
#
# 이 헬퍼들은 Webhook 전용이라 모듈 ``__all__``(WAM/legacy 서명 계약)에는 넣지 않는다
# (namespace surface 계약 고정). channel_webhooks.py 가 이름으로 직접 import 한다.

WEBHOOK_SOURCE = "channeltalk"
WEBHOOK_DEDUP_DAYS = 30
_WEBHOOK_ENVELOPE_KEY_ENV = "CHANNEL_WEBHOOK_ENVELOPE_KEY"
_WEBHOOK_ENVELOPE_VERSION = 1
_WEBHOOK_ENVELOPE_ALG = "AES-256-GCM"
_WEBHOOK_ENVELOPE_AAD_PREFIX = b"FOMS_CHANNEL_WEBHOOK_ENVELOPE_V1\0"
_WEBHOOK_ENVELOPE_MIN_KEY_BYTES = 32  # AES-256
_WEBHOOK_ENVELOPE_NONCE_BYTES = 12  # GCM standard nonce


def _b64url(raw: bytes) -> str:
    """padding 없는 base64url 인코딩."""
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _b64url_decode(text_value: str) -> bytes:
    """padding 없는 base64url 을 raw bytes 로 decode."""
    pad = "=" * (-len(text_value) % 4)
    return base64.urlsafe_b64decode(text_value + pad)


def webhook_canonical_bytes(payload: Any) -> bytes:
    """payload 의 JCS-style canonical JSON bytes(dedup·hash 안정화용).

    key 정렬 + 구분자 최소화 + UTF-8 로 결정적 직렬화한다. 서로 다른 key 순서/whitespace
    가 같은 논리 payload 를 다른 hash 로 만들지 않게 한다.

    :param payload: JSON 직렬화 가능한 webhook payload(dict 기대).
    :returns: canonical JSON 의 UTF-8 bytes.

    ponytail: 완전한 RFC 8785(숫자 재정규화)는 아니다. provider payload 는 스키마가
    안정적이라 sort_keys + compact separators 로 충분하다. 숫자 표현이 흔들리면
    canonicaljson 라이브러리로 승급.
    """
    return json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def webhook_content_hash(payload: Any) -> str:
    """canonical payload 의 sha256 hex(30d dedup key + envelope AAD 바인딩)."""
    return hashlib.sha256(webhook_canonical_bytes(payload)).hexdigest()


def _webhook_envelope_key() -> bytes:
    """Webhook envelope 대칭 key 를 hex-decode 한다(≥32 byte 강제, raw UTF-8 금지).

    :returns: decode 된 32+ byte key.
    :raises RuntimeError: key 미설정·hex 아님·32 byte 미만(fail-closed, 조용한 우회 금지).
    """
    raw = os.environ.get(_WEBHOOK_ENVELOPE_KEY_ENV, "").strip()
    if not raw:
        raise RuntimeError(
            f"{_WEBHOOK_ENVELOPE_KEY_ENV} is required to encrypt webhook payload envelopes"
        )
    try:
        key = bytes.fromhex(raw)
    except ValueError as exc:
        raise RuntimeError(f"{_WEBHOOK_ENVELOPE_KEY_ENV} must be hex-encoded") from exc
    if len(key) < _WEBHOOK_ENVELOPE_MIN_KEY_BYTES:
        raise RuntimeError(
            f"{_WEBHOOK_ENVELOPE_KEY_ENV} must decode to >= {_WEBHOOK_ENVELOPE_MIN_KEY_BYTES} bytes"
        )
    return key


def _webhook_envelope_aad(source: str, content_hash: str) -> bytes:
    """envelope AAD = prefix + LP(source, content_hash) — payload 를 논리 위치에 바인딩."""
    return _WEBHOOK_ENVELOPE_AAD_PREFIX + lp(source, content_hash)


def encrypt_webhook_payload(raw_body: bytes, *, content_hash: str, source: str) -> dict:
    """raw payload 를 AES-256-GCM 으로 암호화해 versioned envelope dict 반환(평문 미저장).

    :param raw_body: webhook 요청 원본 body bytes.
    :param content_hash: JCS canonical hash(AAD 바인딩).
    :param source: provider 식별자(AAD 바인딩).
    :returns: version/alg/nonce/aad_sha256/ciphertext 를 담은 envelope dict.
    :raises RuntimeError: envelope key 미설정/형식 오류(fail-closed).
    """
    key = _webhook_envelope_key()
    aad = _webhook_envelope_aad(source, content_hash)
    nonce = os.urandom(_WEBHOOK_ENVELOPE_NONCE_BYTES)
    ciphertext = AESGCM(key).encrypt(nonce, raw_body, aad)
    return {
        "version": _WEBHOOK_ENVELOPE_VERSION,
        "alg": _WEBHOOK_ENVELOPE_ALG,
        "nonce_b64url": _b64url(nonce),
        "aad_sha256": hashlib.sha256(aad).hexdigest(),
        "ciphertext_b64url": _b64url(ciphertext),
    }


def decrypt_webhook_payload(envelope: dict, *, content_hash: str, source: str) -> bytes:
    """versioned envelope 를 복호화한다(AAD 불일치/GCM 인증 실패는 fail-closed).

    :raises RuntimeError: version/alg mismatch, AAD 불일치, GCM 인증 실패.
    """
    if not isinstance(envelope, dict):
        raise RuntimeError("webhook envelope must be a JSON object")
    if (envelope.get("version") != _WEBHOOK_ENVELOPE_VERSION
            or envelope.get("alg") != _WEBHOOK_ENVELOPE_ALG):
        raise RuntimeError("unsupported webhook envelope version/alg")
    key = _webhook_envelope_key()
    aad = _webhook_envelope_aad(source, content_hash)
    if hashlib.sha256(aad).hexdigest() != envelope.get("aad_sha256"):
        raise RuntimeError("webhook envelope AAD mismatch")
    nonce = _b64url_decode(envelope["nonce_b64url"])
    ciphertext = _b64url_decode(envelope["ciphertext_b64url"])
    try:
        return AESGCM(key).decrypt(nonce, ciphertext, aad)
    except InvalidTag as exc:
        raise RuntimeError("webhook envelope authentication failed") from exc


def validate_webhook_config() -> None:
    """enforce 상태(``CHANNEL_INBOUND_ENABLED`` 명시적 true)의 필수 key 를 기동 시 검증한다.

    unset(dev/test 기본)·명시적 false 면 no-op — fail-start 는 운영 enforcement 를 명시적
    으로 켠 배포에서만 발동한다. enforce 상태에서 provider token key(``CHANNEL_SIGNING_KEY``)
    나 envelope key 가 없으면 ``RuntimeError`` 로 앱 기동을 막는다(조용한 우회 금지).
    """
    if os.environ.get("CHANNEL_INBOUND_ENABLED", "").strip().lower() != "true":
        return
    if not os.environ.get("CHANNEL_SIGNING_KEY", "").strip():
        raise RuntimeError(
            "CHANNEL_SIGNING_KEY is required when CHANNEL_INBOUND_ENABLED=true"
        )
    _webhook_envelope_key()


def accept_webhook(
    payload: Any,
    raw_body: bytes,
    *,
    dispatch: Callable[[dict], tuple[int, dict]],
    now: Any = None,
    session: Any = None,
) -> tuple[int, dict]:
    """Webhook acceptance transaction — 2xx 는 durable receipt/intent/job 커밋 뒤에만.

    흐름(transactional outbox): (1) JCS ``content_hash``, (2) 30d dedup window 조회 →
    중복이면 masked conflict 만 append 하고 새 receipt/downstream 없이 2xx duplicate,
    (3) raw payload → versioned AES-256-GCM envelope, (4) receipt+intent+job 를 **한
    트랜잭션**에 커밋(durable ID-job), (5) 커밋 성공 뒤에만 best-effort 로 downstream
    dispatch(RQ 파이프라인)를 트리거하고 2xx. DB/job insert 실패는 롤백 → non-2xx 이며
    부분 수용이 없다. 이 함수는 실 Order 를 건드리지 않는다(Order mutation 은 downstream).

    :param payload: 파싱된 webhook JSON(dict 기대).
    :param raw_body: 요청 원본 body bytes(envelope 암호화 대상).
    :param dispatch: 수용 후 downstream 트리거(``receive_webhook``); ``(status, body)`` 반환.
    :param now: 기준 시각(테스트 주입). 기본 :func:`now_utc_naive`.
    :param session: DB 세션(주입 없으면 앱 ``db_session``). PG/SQLite 양 lane 테스트용.
    :returns: ``(http_status, response_body)`` — body 는 masked(payload/PII/token 0).
    """
    now = now or now_utc_naive()
    if not isinstance(payload, dict) or not payload:
        return 400, {"status": "invalid"}

    if session is None:
        from db import db_session as session
    from models import (
        ChannelWebhookConflict,
        ChannelWebhookIntent,
        ChannelWebhookJob,
        ChannelWebhookReceipt,
    )

    source = WEBHOOK_SOURCE
    content_hash = webhook_content_hash(payload)
    window_start = now - timedelta(days=WEBHOOK_DEDUP_DAYS)

    # (2) 30d dedup window.
    try:
        existing = (
            session.query(ChannelWebhookReceipt)
            .filter(
                ChannelWebhookReceipt.content_hash == content_hash,
                ChannelWebhookReceipt.accepted_at >= window_start,
            )
            .order_by(ChannelWebhookReceipt.accepted_at.desc())
            .first()
        )
    except SQLAlchemyError:
        session.rollback()
        logger.warning("[ChannelWebhook] dedup lookup failed")  # redacted: no payload
        return 503, {"status": "unavailable"}

    if existing is not None:
        # soak(중복 재전송): masked conflict 만 기록, 새 receipt/downstream 없음.
        try:
            session.add(
                ChannelWebhookConflict(
                    receipt_id=existing.id, content_hash=content_hash,
                    source=source, observed_at=now,
                )
            )
            session.commit()
        except SQLAlchemyError:
            session.rollback()
            logger.warning("[ChannelWebhook] conflict record failed")
        return 200, {"status": "duplicate", "receipt_id": str(existing.id)}

    # (3) versioned envelope(평문 미저장). key 미가용은 fail-closed → non-2xx.
    try:
        envelope = encrypt_webhook_payload(raw_body, content_hash=content_hash, source=source)
    except RuntimeError:
        logger.error("[ChannelWebhook] envelope key unavailable")  # no payload
        return 503, {"status": "unavailable"}

    # (4) receipt + intent + job 를 한 트랜잭션에 — durable ID-job 커밋 뒤에만 2xx.
    receipt_id = str(uuid.uuid4())
    job = ChannelWebhookJob(
        id=str(uuid.uuid4()), receipt_id=receipt_id, status="pending",
        created_at=now, updated_at=now,
    )
    try:
        session.add(
            ChannelWebhookReceipt(
                id=receipt_id, source=source, content_hash=content_hash,
                accepted_at=now, dedup_expires_at=now + timedelta(days=WEBHOOK_DEDUP_DAYS),
                envelope=envelope,
            )
        )
        # 부모 receipt 를 먼저 flush 해 child(intent/job)의 FK 를 같은 tx 안에서 만족시킨다
        # (relationship 없이 add 순서만으로는 PG unit-of-work 가 자식을 먼저 넣어 FK 위반).
        session.flush()
        session.add(
            ChannelWebhookIntent(
                id=str(uuid.uuid4()), receipt_id=receipt_id,
                intent_type=str(payload.get("type") or "unknown"), created_at=now,
            )
        )
        session.add(job)
        session.commit()
    except SQLAlchemyError:
        session.rollback()
        logger.error("[ChannelWebhook] acceptance transaction failed")  # no payload
        return 503, {"status": "unavailable"}  # non-2xx · 부분 수용 0(atomic)

    # (5) 커밋 성공 → 2xx 확정. downstream dispatch 는 best-effort(실패해도 job durable).
    try:
        disp_status, disp_body = dispatch(payload)
        job.status = "enqueued" if 200 <= int(disp_status) < 300 else "pending"
        legacy_log_id = disp_body.get("log_id") if isinstance(disp_body, dict) else None
        if legacy_log_id is not None:
            job.legacy_log_id = int(legacy_log_id)
        job.updated_at = now_utc_naive()
        session.commit()
    except Exception:  # noqa: BLE001 - downstream 실패는 2xx 취소가 아니다(job 재구동 가능)
        session.rollback()
        logger.warning("[ChannelWebhook] downstream dispatch deferred")  # no payload

    return 200, {"status": "accepted", "receipt_id": receipt_id}


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
