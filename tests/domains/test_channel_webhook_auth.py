"""CHANNEL-WEBHOOK-AUTH-01: Webhook token/config·서명·acceptance transaction 계약 (red→green).

`foms/api/channel/channel_webhooks.py` + `foms/services/channel_security.py` 의 Webhook
**전용** 수용 계약을 봉인한다(Function `verify_function_signature` 재사용 금지, freshness 는
보조 anti-replay 이지 유일 auth 아님):

* disabled(`CHANNEL_INBOUND_ENABLED=false`) → provider 호출 전 **404**(provider-first).
* provider token(`x-signature`, raw UTF-8 key + hex HMAC) 정상 → 2xx, 미서명/위조 → **401**.
* acceptance transaction: JCS `content_hash` + 30d dedup window + versioned AES-256-GCM
  envelope + durable receipt/intent/job 가 **한 트랜잭션**에 커밋된 뒤에만 2xx. DB/job insert
  실패 → 롤백 → non-2xx(부분 수용 0). 중복 재전송 → masked conflict 만(새 receipt 0).
* 실 Order 변경 **0**(webhook 은 intent/job 큐잉만).
* log/envelope redaction: plaintext payload/PII/token **0**.
* enforce(`CHANNEL_INBOUND_ENABLED=true`)인데 key/token 미설정 → **fail-start**.

기본 lane 은 self-contained **SQLite in-memory**. `FOMS_TEST_DATABASE_URL`(local admin DSN)이
있으면 acceptance transaction 이 throwaway `foms_test_*` **PostgreSQL** DB 로도 실행된다
(+PG green). 비밀번호는 env 로만 주입 — 커밋 파일엔 없다.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import subprocess
import sys
import uuid
from datetime import timedelta
from pathlib import Path
from typing import Iterator

import pytest
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

import app  # noqa: F401  (register every model on Base.metadata)
from db import Base
from models import (
    ChannelWebhookConflict,
    ChannelWebhookIntent,
    ChannelWebhookJob,
    ChannelWebhookReceipt,
    Order,
)
import foms.services.channel_security as cs
from tests.postgres.conftest import (
    _admin_dsn_from_env,
    _raw_connect,
    assert_local_admin_url,
    assert_test_db_name,
)

_REPO_ROOT = Path(__file__).resolve().parents[2]

# 테스트 전용 상수(실 값과 무관).
_TOKEN_KEY = "webhook-token-secret-not-committed"
_ENVELOPE_KEY_HEX = "11" * 32  # 32 byte AES-256 key(64 hex)

# PII/token sentinel — redaction 검증용(로그/envelope 에 새면 실패).
_CUSTOMER = "PII_CUSTOMER_SENTINEL"
_PHONE = "010-7777-7777"
_TOKEN_SENTINEL = "TOKEN_SENTINEL_ABC123"


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------
def _sign(body: bytes, key: str = _TOKEN_KEY) -> str:
    """Webhook token 서명: raw UTF-8 key HMAC-SHA256 → hex digest(Function Base64 와 분리)."""
    return hmac.new(key.encode("utf-8"), body, hashlib.sha256).hexdigest()


def _payload(event_type: str = "userChat", **extra) -> dict:
    body = {"type": event_type, "entity": {"id": "chat-" + uuid.uuid4().hex[:8]}}
    body.update(extra)
    return body


def _post(client, payload: dict, *, sign: bool = True, key: str = _TOKEN_KEY,
          sig: str | None = None):
    raw = json.dumps(payload).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if sign or sig is not None:
        headers["x-signature"] = sig if sig is not None else _sign(raw, key)
    return client.open("/api/channel/webhooks", method="POST", data=raw, headers=headers)


@pytest.fixture
def token_env(monkeypatch):
    """provider token key + envelope key 를 설정(module const 도 갱신)."""
    monkeypatch.setenv("CHANNEL_SIGNING_KEY", _TOKEN_KEY)
    monkeypatch.setattr(cs, "CHANNEL_SIGNING_KEY", _TOKEN_KEY)
    monkeypatch.setenv("CHANNEL_WEBHOOK_ENVELOPE_KEY", _ENVELOPE_KEY_HEX)
    monkeypatch.delenv("CHANNEL_INBOUND_ENABLED", raising=False)  # 기본 enabled(unset)
    yield


@pytest.fixture
def envelope_key(monkeypatch):
    """envelope 대칭 key 만 설정(session-level tx 테스트용)."""
    monkeypatch.setenv("CHANNEL_WEBHOOK_ENVELOPE_KEY", _ENVELOPE_KEY_HEX)
    yield


def _make_pg_engine() -> tuple[Engine, "callable"]:
    """throwaway ``foms_test_*`` PG DB 를 만들고 (engine, drop) 반환(local-only·env DSN)."""
    admin_url = assert_local_admin_url(_admin_dsn_from_env())
    admin_dbname = admin_url.database or "postgres"
    db_name = assert_test_db_name(f"foms_test_whauth_{uuid.uuid4().hex[:12]}")

    conn = _raw_connect(admin_url, admin_dbname)
    conn.autocommit = True
    try:
        with conn.cursor() as cur:
            cur.execute(f'CREATE DATABASE "{db_name}"')
    finally:
        conn.close()

    engine = create_engine(
        admin_url.set(drivername="postgresql+psycopg2", database=db_name),
        connect_args={"client_encoding": "utf8"},
    )

    def _drop() -> None:
        engine.dispose()
        assert_test_db_name(db_name)  # defense in depth before DROP
        c = _raw_connect(admin_url, admin_dbname)
        c.autocommit = True
        try:
            with c.cursor() as cur:
                cur.execute(
                    "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                    "WHERE datname = %s AND pid <> pg_backend_pid()",
                    (db_name,),
                )
                cur.execute(f'DROP DATABASE IF EXISTS "{db_name}"')
        finally:
            c.close()

    return engine, _drop


@pytest.fixture
def session() -> Iterator[Session]:
    """acceptance tx 세션. FOMS_TEST_DATABASE_URL 있으면 PG, 없으면 SQLite in-memory."""
    if _admin_dsn_from_env():
        engine, drop = _make_pg_engine()
    else:
        engine = create_engine(
            "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
        )
        drop = engine.dispose

    Base.metadata.create_all(bind=engine)
    sess = sessionmaker(bind=engine)()
    try:
        yield sess
    finally:
        sess.close()
        drop()


def _ok_dispatch(log_id: int = 1):
    """수용 후 downstream dispatch stub — (200, {log_id}) 반환(실 RQ/Order 미실행)."""
    calls = []

    def _dispatch(payload):
        calls.append(payload)
        return 200, {"status": "received", "log_id": log_id}

    _dispatch.calls = calls
    return _dispatch


# ==========================================================================
# 1) endpoint token/config gate (SQLite app lane)
# ==========================================================================
def test_disabled_returns_404_and_never_calls_provider(app, client, monkeypatch):
    monkeypatch.setenv("CHANNEL_INBOUND_ENABLED", "false")
    calls = []
    monkeypatch.setattr(
        "foms.services.channel_inbound.receive_webhook",
        lambda *a, **k: calls.append((a, k)) or (200, {}),
    )
    resp = _post(client, _payload())
    assert resp.status_code == 404, resp.get_data(as_text=True)
    assert calls == [], "disabled 인데 provider(receive_webhook) 호출됨(provider-first 위반)"


def test_missing_token_is_401(app, client, token_env):
    resp = _post(client, _payload(), sign=False)
    assert resp.status_code == 401


def test_forged_token_is_401(app, client, token_env):
    resp = _post(client, _payload(), sig="not-a-valid-signature")
    assert resp.status_code == 401


def test_wrong_key_token_is_401(app, client, token_env):
    resp = _post(client, _payload(), key="different-secret")
    assert resp.status_code == 401


def test_valid_token_accepts_2xx_creates_receipt_no_order(app, client, token_env, monkeypatch):
    monkeypatch.setattr(
        "foms.services.channel_inbound.enqueue_channeltalk_inbound", lambda *a, **k: True
    )
    from db import db_session

    with app.app_context():
        before_orders = db_session.query(Order).count()

    resp = _post(client, _payload())
    assert resp.status_code == 200, resp.get_data(as_text=True)
    body = resp.get_json()
    assert body["status"] == "accepted"

    with app.app_context():
        assert db_session.query(ChannelWebhookReceipt).count() >= 1
        assert db_session.query(ChannelWebhookJob).count() >= 1
        assert db_session.query(Order).count() == before_orders  # 실 Order 변경 0


# ==========================================================================
# 2) acceptance transaction (dual lane: SQLite / PG)
# ==========================================================================
def test_accept_creates_receipt_intent_job_and_no_order(session, envelope_key):
    payload = _payload()
    raw = json.dumps(payload).encode("utf-8")
    status, body = accept(session, payload, raw, dispatch=_ok_dispatch())

    assert status == 200 and body["status"] == "accepted"
    receipt = session.query(ChannelWebhookReceipt).one()
    assert receipt.accepted_at is not None
    assert receipt.dedup_expires_at > receipt.accepted_at
    assert session.query(ChannelWebhookIntent).filter_by(receipt_id=receipt.id).count() == 1
    job = session.query(ChannelWebhookJob).filter_by(receipt_id=receipt.id).one()
    assert job.status == "enqueued"  # ID-job 커밋 뒤 dispatch 성공 반영
    assert job.legacy_log_id == 1
    assert session.query(Order).count() == 0  # webhook 은 Order 미변경


def test_envelope_is_encrypted_no_plaintext_and_round_trips(session, envelope_key):
    payload = _payload(customer=_CUSTOMER, phone=_PHONE)
    raw = json.dumps(payload).encode("utf-8")
    accept(session, payload, raw, dispatch=_ok_dispatch())

    receipt = session.query(ChannelWebhookReceipt).one()
    env = receipt.envelope
    assert env["version"] == 1 and env["alg"] == "AES-256-GCM"
    # envelope 직렬화에 평문 payload/PII 가 없어야 한다(암호문만).
    blob = json.dumps(env)
    assert _CUSTOMER not in blob and _PHONE not in blob
    assert "customer" not in blob
    # AAD 바인딩(content_hash/source) 하에 raw 로 복호화 왕복.
    content_hash = cs.webhook_content_hash(payload)
    plain = cs.decrypt_webhook_payload(env, content_hash=content_hash, source=cs.WEBHOOK_SOURCE)
    assert plain == raw


def test_resend_within_window_dedups_masked_only(session, envelope_key):
    payload = _payload()
    raw = json.dumps(payload).encode("utf-8")
    s1, _ = accept(session, payload, raw, dispatch=_ok_dispatch())
    s2, b2 = accept(session, payload, raw, dispatch=_ok_dispatch())

    assert s1 == 200
    assert s2 == 200 and b2["status"] == "duplicate"
    # 두 번째는 새 receipt 를 만들지 않고 masked conflict 만 기록.
    assert session.query(ChannelWebhookReceipt).count() == 1
    conflict = session.query(ChannelWebhookConflict).one()
    assert conflict.content_hash == cs.webhook_content_hash(payload)
    assert session.query(Order).count() == 0


def test_resend_after_30d_window_is_fresh_acceptance(session, envelope_key):
    payload = _payload()
    raw = json.dumps(payload).encode("utf-8")
    old = cs.now_utc_naive() - timedelta(days=31)
    accept(session, payload, raw, dispatch=_ok_dispatch(), now=old)
    # 31일 뒤 재전송 → window 밖이라 새 acceptance.
    accept(session, payload, raw, dispatch=_ok_dispatch())
    assert session.query(ChannelWebhookReceipt).count() == 2
    assert session.query(ChannelWebhookConflict).count() == 0


def test_db_job_failure_is_non_2xx_and_atomic(session, envelope_key, monkeypatch):
    payload = _payload()
    raw = json.dumps(payload).encode("utf-8")

    def _boom():
        raise SQLAlchemyError("injected acceptance commit failure")

    monkeypatch.setattr(session, "commit", _boom)
    status, body = accept(session, payload, raw, dispatch=_ok_dispatch())

    assert status == 503 and body["status"] == "unavailable"  # non-2xx
    monkeypatch.undo()  # commit 복구 후 상태 검증
    # 부분 수용 0: receipt/intent/job 어느 것도 남지 않는다(atomic).
    assert session.query(ChannelWebhookReceipt).count() == 0
    assert session.query(ChannelWebhookIntent).count() == 0
    assert session.query(ChannelWebhookJob).count() == 0


def test_invalid_payload_is_400(session, envelope_key):
    for bad in (None, [], {}, "x"):
        status, _ = accept(session, bad, b"", dispatch=_ok_dispatch())
        assert status == 400


def test_redaction_no_pii_or_token_in_logs_on_failure(session, envelope_key, monkeypatch, caplog):
    payload = _payload(customer=_CUSTOMER, phone=_PHONE, token=_TOKEN_SENTINEL)
    raw = json.dumps(payload).encode("utf-8")

    def _boom():
        raise SQLAlchemyError("injected")

    monkeypatch.setattr(session, "commit", _boom)
    with caplog.at_level("WARNING"):
        accept(session, payload, raw, dispatch=_ok_dispatch())

    text = "\n".join(r.getMessage() for r in caplog.records)
    assert _CUSTOMER not in text and _PHONE not in text and _TOKEN_SENTINEL not in text
    assert raw.decode("utf-8") not in text  # raw payload 미로깅


# ==========================================================================
# 3) crypto/hash unit (JCS stable · AAD · envelope key format)
# ==========================================================================
def test_jcs_hash_is_key_order_stable():
    a = cs.webhook_content_hash({"a": 1, "b": {"x": 1, "y": 2}})
    b = cs.webhook_content_hash({"b": {"y": 2, "x": 1}, "a": 1})
    assert a == b


def test_envelope_aad_mismatch_fails_closed(envelope_key):
    raw = b'{"k":"v"}'
    env = cs.encrypt_webhook_payload(raw, content_hash="h1", source=cs.WEBHOOK_SOURCE)
    with pytest.raises(RuntimeError):
        cs.decrypt_webhook_payload(env, content_hash="OTHER", source=cs.WEBHOOK_SOURCE)


def test_envelope_key_must_be_hex_and_32_bytes(monkeypatch):
    monkeypatch.setenv("CHANNEL_WEBHOOK_ENVELOPE_KEY", "")
    with pytest.raises(RuntimeError):
        cs.encrypt_webhook_payload(b"x", content_hash="h", source="s")
    monkeypatch.setenv("CHANNEL_WEBHOOK_ENVELOPE_KEY", "zzzz")  # non-hex
    with pytest.raises(RuntimeError):
        cs.encrypt_webhook_payload(b"x", content_hash="h", source="s")
    monkeypatch.setenv("CHANNEL_WEBHOOK_ENVELOPE_KEY", "11" * 16)  # 16 byte < 32
    with pytest.raises(RuntimeError):
        cs.encrypt_webhook_payload(b"x", content_hash="h", source="s")


# ==========================================================================
# 4) config fail-start
# ==========================================================================
def test_validate_config_noop_when_unset_or_false(monkeypatch):
    monkeypatch.delenv("CHANNEL_INBOUND_ENABLED", raising=False)
    monkeypatch.delenv("CHANNEL_SIGNING_KEY", raising=False)
    monkeypatch.delenv("CHANNEL_WEBHOOK_ENVELOPE_KEY", raising=False)
    cs.validate_webhook_config()  # unset → no raise
    monkeypatch.setenv("CHANNEL_INBOUND_ENABLED", "false")
    cs.validate_webhook_config()  # false → no raise


def test_validate_config_raises_when_enabled_without_token_key(monkeypatch):
    monkeypatch.setenv("CHANNEL_INBOUND_ENABLED", "true")
    monkeypatch.delenv("CHANNEL_SIGNING_KEY", raising=False)
    monkeypatch.setenv("CHANNEL_WEBHOOK_ENVELOPE_KEY", _ENVELOPE_KEY_HEX)
    with pytest.raises(RuntimeError):
        cs.validate_webhook_config()


def test_validate_config_raises_when_enabled_without_envelope_key(monkeypatch):
    monkeypatch.setenv("CHANNEL_INBOUND_ENABLED", "true")
    monkeypatch.setenv("CHANNEL_SIGNING_KEY", _TOKEN_KEY)
    monkeypatch.delenv("CHANNEL_WEBHOOK_ENVELOPE_KEY", raising=False)
    with pytest.raises(RuntimeError):
        cs.validate_webhook_config()


def _import_app_returncode(env_overrides: dict) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env.update(env_overrides)
    env["DATABASE_URL"] = "sqlite:///:memory:"
    env.setdefault("SECRET_KEY", "test-secret-key")
    return subprocess.run(
        [sys.executable, "-c", "import app"],
        env=env, cwd=str(_REPO_ROOT), capture_output=True, text=True, timeout=120,
    )


def test_app_fails_to_start_when_enabled_without_keys():
    proc = _import_app_returncode(
        {"CHANNEL_INBOUND_ENABLED": "true", "CHANNEL_SIGNING_KEY": "",
         "CHANNEL_WEBHOOK_ENVELOPE_KEY": ""}
    )
    assert proc.returncode != 0, proc.stdout + proc.stderr


def test_app_starts_when_enabled_with_keys():
    proc = _import_app_returncode(
        {"CHANNEL_INBOUND_ENABLED": "true", "CHANNEL_SIGNING_KEY": _TOKEN_KEY,
         "CHANNEL_WEBHOOK_ENVELOPE_KEY": _ENVELOPE_KEY_HEX}
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr


# accept_webhook 이 Webhook 전용(Function 서명 재사용 금지)임을 고정.
def test_webhook_owns_dedicated_acceptance_not_function_signature():
    assert hasattr(cs, "accept_webhook")
    assert not hasattr(cs, "verify_function_signature")


def accept(session, payload, raw, **kw):
    """accept_webhook 얇은 래퍼(session 주입)."""
    return cs.accept_webhook(payload, raw, session=session, **kw)
