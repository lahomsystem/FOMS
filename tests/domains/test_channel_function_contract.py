"""CHANNEL-FUNCTION-CONTRACT-01: ChannelTalk Function 서명·계약 테스트 (red→green).

`foms/api/channel/channel_functions.py` 의 Function **전용** 서명/설정 계약을 봉인한다.
Webhook 서명 체계(raw UTF-8 key + hex digest, `require_channel_signature`)를 재사용하지
않고, Function 은 다음 전용 체계를 소유한다:

* key = `CHANNEL_FUNCTION_SIGNING_KEY` 를 **hex-decode**(≥32 byte, raw UTF-8 금지).
* 대상 = 요청 **원본 body(raw bytes)**. digest = HMAC-SHA256 → **Base64**(hex 금지).
* 비교 = `hmac.compare_digest` (constant-time).

계약:

* disable(기본/false) → provider 호출 전 **404**(모든 method), provider 미호출.
* enable → 공식 method **PUT** 만 provider contract, POST/GET → **405**.
* 미서명/위조 서명 → **401**, invalid JSON → **400**.
* signed context 의 channel **exact**(불일치 → 401), caller **exact**(manager caller 만 채택).
* success/deny/error 모두 provider **200** `{result|error}`, deny/nonexistent generic 동일,
  PII/mutation **0**.
* enable 상태에서 key/channel 미설정 → **fail-start**(앱 기동 실패).
* fixture/method schema manifest 가 실등록 method 를 반영(stale 0, accept-all 금지).
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import itertools
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from db import db_session
from models import ChannelManagerLink, Order, User

import foms.api.channel.channel_functions as cf

_REPO_ROOT = Path(__file__).resolve().parents[2]
_FIXTURE_DIR = _REPO_ROOT / "tests" / "fixtures" / "channeltalk"

# 32-byte(64 hex) 서명 key. 실제 값과 무관한 테스트 전용.
_KEY_HEX = "ab" * 32
_CHANNEL_ID = "chan-func-901"

# PII 감시 sentinel — deny/no-data 결과에 새면 실패.
_CUSTOMER = "PII_CUSTOMER_SENTINEL"
_PHONE = "010-7777-7777"
_ADDRESS = "SENTINEL_ADDRESS_RD_9"
_MANAGER = "SENTINEL_MANAGER_NAME"
_PRODUCT = "SENTINEL_PRODUCT_X"
_PII_VALUES = (_CUSTOMER, _PHONE, _ADDRESS, _MANAGER, _PRODUCT)

_counter = itertools.count(1)


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------
def _sign(body: bytes, key_hex: str = _KEY_HEX) -> str:
    """hex-decode key → raw body HMAC-SHA256 → Base64 (정본 서명 계산)."""
    key = bytes.fromhex(key_hex)
    return base64.b64encode(hmac.new(key, body, hashlib.sha256).digest()).decode("ascii")


def _enable(monkeypatch, *, key_hex: str = _KEY_HEX, channel_id: str = _CHANNEL_ID) -> None:
    monkeypatch.setenv("CHANNEL_FUNCTION_ENABLED", "true")
    monkeypatch.setenv("CHANNEL_FUNCTION_SIGNING_KEY", key_hex)
    monkeypatch.setenv("CHANNEL_FUNCTION_CHANNEL_ID", channel_id)


def _body(text: str = "주문 1", *, channel_id: str = _CHANNEL_ID,
          caller_type: str = "manager", manager_id: str | None = "mgr-x",
          method: str = "foms") -> dict:
    context: dict = {"channel": {"id": channel_id}}
    if caller_type is not None:
        context["caller"] = {"type": caller_type, "id": manager_id}
    return {"method": method, "params": {"text": text}, "context": context}


def _put(client, payload: dict | None = None, *, raw: bytes | None = None,
         sig: str | None = None, key_hex: str = _KEY_HEX,
         content_type: str = "application/json", method: str = "PUT"):
    data = raw if raw is not None else json.dumps(payload or {}).encode("utf-8")
    signature = sig if sig is not None else _sign(data, key_hex)
    return client.open(
        "/api/channel/functions",
        method=method,
        data=data,
        headers={"x-signature": signature, "Content-Type": content_type},
    )


def _dump(obj) -> str:
    return json.dumps(obj, ensure_ascii=False)


def _assert_no_pii(blob: str) -> None:
    for value in _PII_VALUES:
        assert value not in blob, f"PII leak: {value!r} in {blob!r}"


def _make_user(*, is_active: bool = True, role: str = "STAFF") -> User:
    n = next(_counter)
    user = User(username=f"cf-user-{n}", password="x", role=role,
                name=f"user-{n}", is_active=is_active)
    db_session.add(user)
    db_session.commit()
    return user


def _link(manager_id: str, user: User, *, is_active: bool = True) -> ChannelManagerLink:
    link = ChannelManagerLink(channel_manager_id=manager_id, user_id=user.id, is_active=is_active)
    db_session.add(link)
    db_session.commit()
    return link


def _make_order() -> Order:
    order = Order(
        received_date="2026-03-26", customer_name=_CUSTOMER, phone=_PHONE,
        address=_ADDRESS, product=_PRODUCT, status="RECEIVED", manager_name=_MANAGER,
        structured_data={"schedule": {"measurement": {"date": "2026-03-28"},
                                      "construction": {"date": "2026-04-01"}}},
    )
    db_session.add(order)
    db_session.commit()
    return order


# --------------------------------------------------------------------------
# disable gate (provider-first) → 404, provider 미호출
# --------------------------------------------------------------------------
def test_disabled_returns_404_and_never_calls_provider(app, client, monkeypatch):
    monkeypatch.setenv("CHANNEL_FUNCTION_ENABLED", "false")
    calls = []
    monkeypatch.setattr(
        "foms.services.channel_quick_actions.process_foms_command",
        lambda *a, **k: calls.append((a, k)) or {"result": {}},
    )
    for method in ("PUT", "POST", "GET"):
        resp = _put(client, _body(), method=method)
        assert resp.status_code == 404, f"{method}: {resp.status_code}"
    assert calls == [], "provider 호출 중 flag false (fail-start 위반)"


def test_unset_flag_defaults_disabled(app, client, monkeypatch):
    monkeypatch.delenv("CHANNEL_FUNCTION_ENABLED", raising=False)
    resp = _put(client, _body())
    assert resp.status_code == 404


# --------------------------------------------------------------------------
# method gate: 공식 PUT 만, POST/GET → 405
# --------------------------------------------------------------------------
def test_enabled_post_and_get_are_405(app, client, monkeypatch):
    _enable(monkeypatch)
    for method in ("POST", "GET"):
        resp = _put(client, _body(), method=method)
        assert resp.status_code == 405, f"{method}: {resp.status_code}"


# --------------------------------------------------------------------------
# 서명 검증 (401)
# --------------------------------------------------------------------------
def test_missing_signature_is_401(app, client, monkeypatch):
    _enable(monkeypatch)
    body = json.dumps(_body()).encode()
    resp = client.put("/api/channel/functions", data=body,
                      headers={"Content-Type": "application/json"})
    assert resp.status_code == 401


def test_forged_signature_is_401(app, client, monkeypatch):
    _enable(monkeypatch)
    resp = _put(client, _body(), sig="not-a-valid-signature")
    assert resp.status_code == 401


def test_wrong_key_signature_is_401(app, client, monkeypatch):
    _enable(monkeypatch)
    resp = _put(client, _body(), key_hex="cd" * 32)  # 다른 key 로 서명 → 위조
    assert resp.status_code == 401


def test_hex_digest_instead_of_base64_is_401(app, client, monkeypatch):
    """digest 를 hex 로 보내면 거부(Base64 강제)."""
    _enable(monkeypatch)
    body = json.dumps(_body()).encode()
    hex_sig = hmac.new(bytes.fromhex(_KEY_HEX), body, hashlib.sha256).hexdigest()
    resp = _put(client, raw=body, sig=hex_sig)
    assert resp.status_code == 401


def test_raw_utf8_key_signature_is_401(app, client, monkeypatch):
    """key 를 raw UTF-8 로 쓴 서명은 거부(hex-decode 강제)."""
    _enable(monkeypatch)
    body = json.dumps(_body()).encode()
    raw_key_sig = base64.b64encode(
        hmac.new(_KEY_HEX.encode("utf-8"), body, hashlib.sha256).digest()
    ).decode()
    resp = _put(client, raw=body, sig=raw_key_sig)
    assert resp.status_code == 401


# --------------------------------------------------------------------------
# invalid JSON (400) — 서명은 유효
# --------------------------------------------------------------------------
def test_invalid_json_is_400(app, client, monkeypatch):
    _enable(monkeypatch)
    bad = b'{"method": "foms", not valid json'
    resp = _put(client, raw=bad)  # 서명은 bad 원본 위에서 유효하게 계산됨
    assert resp.status_code == 400


# --------------------------------------------------------------------------
# signed context channel exact (401)
# --------------------------------------------------------------------------
def test_channel_mismatch_is_401(app, client, monkeypatch):
    _enable(monkeypatch)
    resp = _put(client, _body(channel_id="SOME-OTHER-CHANNEL"))
    assert resp.status_code == 401


def test_missing_context_channel_is_401(app, client, monkeypatch):
    _enable(monkeypatch)
    body = {"method": "foms", "params": {"text": "주문 1"}}  # context 없음
    resp = _put(client, body)
    assert resp.status_code == 401


# --------------------------------------------------------------------------
# 정상 경로: 올바른 서명 + channel + manager caller + read scope → 200 {result}
# --------------------------------------------------------------------------
def test_valid_put_returns_200_result_with_detail(app, client, monkeypatch):
    _enable(monkeypatch)
    with app.app_context():
        oid = _make_order().id
        _link("mgr-ok", _make_user())
    resp = _put(client, _body(text=f"주문 {oid}", manager_id="mgr-ok"))
    assert resp.status_code == 200
    data = resp.get_json()
    assert "result" in data
    assert _CUSTOMER in _dump(data)  # 권한 있는 caller 에게는 상세 반환


# --------------------------------------------------------------------------
# caller exact: manager caller 만 인증 주체(비-manager/누락 → deny·PII 0)
# --------------------------------------------------------------------------
def test_non_manager_caller_denied_no_pii(app, client, monkeypatch):
    _enable(monkeypatch)
    with app.app_context():
        oid = _make_order().id
        _link("mgr-ok", _make_user())
    # caller.type 이 manager 가 아니면 manager_id 채택 안 함 → no-data
    resp = _put(client, _body(text=f"주문 {oid}", caller_type="user", manager_id="mgr-ok"))
    assert resp.status_code == 200
    _assert_no_pii(_dump(resp.get_json()))


# --------------------------------------------------------------------------
# deny/nonexistent generic 동일 · PII 0
# --------------------------------------------------------------------------
def test_deny_and_nonexistent_are_identical_no_pii(app, client, monkeypatch):
    _enable(monkeypatch)
    with app.app_context():
        _make_order()
        user = _make_user()
        _link("mgr-exists", user)
    denied = _put(client, _body(text="주문 99999", manager_id="mgr-exists")).get_json()
    unmapped = _put(client, _body(text="주문 99999", manager_id="no-such-mgr")).get_json()
    assert denied == unmapped
    _assert_no_pii(_dump(denied))


def test_unknown_method_is_generic_200_no_pii(app, client, monkeypatch):
    _enable(monkeypatch)
    resp = _put(client, _body(method="not_registered"))
    assert resp.status_code == 200
    body = resp.get_json()
    assert "error" in body
    _assert_no_pii(_dump(body))


def test_read_only_no_mutation(app, client, monkeypatch):
    _enable(monkeypatch)
    with app.app_context():
        order = _make_order()
        oid = order.id
        user = _make_user()
        _link("mgr-ro", user)
        before = db_session.query(Order).count()
    for cmd in ("주문", "일정", "담당"):
        _put(client, _body(text=f"{cmd} {oid}", manager_id="mgr-ro"))
    with app.app_context():
        assert db_session.query(Order).count() == before


# --------------------------------------------------------------------------
# 서명 helper 단위 검증 (hex-decode·raw body·Base64·constant-time)
# --------------------------------------------------------------------------
def test_verify_helper_accepts_valid_and_rejects_forged(monkeypatch):
    monkeypatch.setenv("CHANNEL_FUNCTION_SIGNING_KEY", _KEY_HEX)
    body = b'{"method":"foms"}'
    assert cf.verify_function_signature(body, _sign(body)) is True
    assert cf.verify_function_signature(body, _sign(body)[:-2] + "==") is False
    assert cf.verify_function_signature(body, "") is False
    # body 1 byte 변조 → 거부(raw body 무결성)
    assert cf.verify_function_signature(body + b" ", _sign(body)) is False


def test_verify_helper_does_not_reuse_webhook_scheme(monkeypatch):
    """Function helper 는 Webhook(raw UTF-8 key·hex digest)과 다른 서명을 만든다."""
    monkeypatch.setenv("CHANNEL_FUNCTION_SIGNING_KEY", _KEY_HEX)
    body = b'{"x":1}'
    webhook_style = hmac.new(_KEY_HEX.encode("utf-8"), body, hashlib.sha256).hexdigest()
    assert cf.verify_function_signature(body, webhook_style) is False


def test_signature_module_does_not_bind_webhook_helper():
    """CHANNEL-FUNCTION-CONTRACT-01: Webhook helper 재사용 금지, 전용 helper 소유."""
    assert hasattr(cf, "verify_function_signature")
    assert not hasattr(cf, "require_channel_signature")


# --------------------------------------------------------------------------
# hex-decode ≥32 byte 강제
# --------------------------------------------------------------------------
def test_short_key_rejected(monkeypatch):
    _enable(monkeypatch, key_hex="ab" * 16)  # 16 byte < 32
    with pytest.raises(RuntimeError):
        cf.validate_function_config()


def test_non_hex_key_rejected(monkeypatch):
    _enable(monkeypatch, key_hex="zzzz")  # hex 아님
    with pytest.raises(RuntimeError):
        cf.validate_function_config()


# --------------------------------------------------------------------------
# fail-start: enable + key/channel 미설정
# --------------------------------------------------------------------------
def test_validate_config_raises_when_key_missing(monkeypatch):
    monkeypatch.setenv("CHANNEL_FUNCTION_ENABLED", "true")
    monkeypatch.delenv("CHANNEL_FUNCTION_SIGNING_KEY", raising=False)
    monkeypatch.setenv("CHANNEL_FUNCTION_CHANNEL_ID", _CHANNEL_ID)
    with pytest.raises(RuntimeError):
        cf.validate_function_config()


def test_validate_config_raises_when_channel_missing(monkeypatch):
    monkeypatch.setenv("CHANNEL_FUNCTION_ENABLED", "true")
    monkeypatch.setenv("CHANNEL_FUNCTION_SIGNING_KEY", _KEY_HEX)
    monkeypatch.delenv("CHANNEL_FUNCTION_CHANNEL_ID", raising=False)
    with pytest.raises(RuntimeError):
        cf.validate_function_config()


def test_validate_config_noop_when_disabled(monkeypatch):
    monkeypatch.setenv("CHANNEL_FUNCTION_ENABLED", "false")
    monkeypatch.delenv("CHANNEL_FUNCTION_SIGNING_KEY", raising=False)
    monkeypatch.delenv("CHANNEL_FUNCTION_CHANNEL_ID", raising=False)
    cf.validate_function_config()  # no raise (provider-first)


def _import_app_returncode(env_overrides: dict) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env.update(env_overrides)
    env["DATABASE_URL"] = "sqlite:///:memory:"
    env.setdefault("SECRET_KEY", "test-secret-key")
    return subprocess.run(
        [sys.executable, "-c", "import app"],
        env=env, cwd=str(_REPO_ROOT), capture_output=True, text=True, timeout=120,
    )


def test_app_fails_to_start_when_enabled_without_key():
    """실제 앱 기동(import app) 이 enable+key 미설정에서 실패한다(fail-start)."""
    proc = _import_app_returncode({
        "CHANNEL_FUNCTION_ENABLED": "true",
        "CHANNEL_FUNCTION_SIGNING_KEY": "",
        "CHANNEL_FUNCTION_CHANNEL_ID": "",
    })
    assert proc.returncode != 0, proc.stdout + proc.stderr
    assert "CHANNEL_FUNCTION_SIGNING_KEY" in (proc.stdout + proc.stderr)


def test_app_starts_when_enabled_with_config():
    """key/channel 설정 시 import app 성공(APP_OK)."""
    proc = _import_app_returncode({
        "CHANNEL_FUNCTION_ENABLED": "true",
        "CHANNEL_FUNCTION_SIGNING_KEY": _KEY_HEX,
        "CHANNEL_FUNCTION_CHANNEL_ID": _CHANNEL_ID,
    })
    assert proc.returncode == 0, proc.stdout + proc.stderr


# --------------------------------------------------------------------------
# fixture / method schema manifest — 실등록 method 반영 (stale 0, accept-all 금지)
# --------------------------------------------------------------------------
def test_method_schema_manifest_matches_registered_methods():
    schema = json.loads((_FIXTURE_DIR / "function_method_schema.json").read_text("utf-8"))
    registered = schema["registered_methods"]
    assert registered == cf.REGISTERED_FUNCTION_METHODS, "manifest 가 실등록 method 와 불일치(stale)"
    assert "*" not in registered, "wildcard method(accept-all) 금지"
    for name, params in registered.items():
        assert params, f"{name}: params 스키마 비어있음(accept-all 추정 금지)"
        assert "*" not in params, f"{name}: wildcard params(accept-all) 금지"


def test_provider_fixture_reflects_signed_context_shape():
    fx = json.loads((_FIXTURE_DIR / "function_command_foms.json").read_text("utf-8"))
    assert fx["method"] in cf.REGISTERED_FUNCTION_METHODS
    # channel/caller 는 서명이 덮는 context 안에 있어야 한다(stale top-level 금지).
    assert "channel" in fx["context"] and "caller" in fx["context"]
    assert "channel" not in fx and "caller" not in fx
    assert set(fx["params"]) <= set(cf.REGISTERED_FUNCTION_METHODS[fx["method"]])
