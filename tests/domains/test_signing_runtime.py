"""SESSION-SIGNING-SECRET-01 runtime 서명 provider 단위 테스트 (domain lane).

DB 없이/SQLite 로 검증한다:

* P0-22 fail-fast: deployed 에서 legacy SECRET_KEY 가 absent/known-default/short 이면 기동 차단
  (``resolve_legacy_secret`` + ``build_app``).
* 기존 세션/WAM 호환: 미engaged/EMPTY/READY 는 legacy raw key(회귀 0), ACTIVE+BRIDGE 는 legacy
  서명을 verify-only 로 계속 받고 신규는 derived key 로 sign, FORCE_REAUTH 는 legacy 거부.
* WAM cutoff: ACTIVE ``wam_not_before`` 이전 iat 토큰 거부.

engaged 판정은 ``FOMS_SIGNING_KEY_CURRENT`` env, 상태는 ``security_signing_state`` singleton 에서
요청마다 읽는다(process cache 0).
"""
from __future__ import annotations

import base64
import os
import time
from datetime import timedelta

import pytest
from itsdangerous import BadTimeSignature, SignatureExpired, URLSafeTimedSerializer

from foms.services.datetime_kst import now_utc_naive
from foms.services.security.signing.signing_key_format import (
    decode_root_key,
    derive_subkey,
    key_id_from_root,
)
from foms.services.security.signing.signing_keys import (
    FLASK_LABEL,
    resolve_legacy_secret,
    resolve_secret_key_list,
)


def _root_b64() -> str:
    return base64.urlsafe_b64encode(os.urandom(32)).rstrip(b"=").decode("ascii")


def _set_state(**fields):
    """singleton(id=1)을 원하는 서명 상태로 갱신(app fixture 가 EMPTY 로 seed 해 둠)."""
    from db import db_session
    from models import SecuritySigningState

    row = db_session.query(SecuritySigningState).filter_by(id=1).one()
    for k, v in fields.items():
        setattr(row, k, v)
    db_session.commit()
    return row


def _cookie_serializer(secret_or_list):
    return URLSafeTimedSerializer(
        secret_or_list, salt="cookie-session", signer_kwargs=dict(key_derivation="hmac")
    )


# --------------------------------------------------------------------------- #
# 1. P0-22 fail-fast
# --------------------------------------------------------------------------- #
def test_resolve_legacy_secret_deployed_rejects_absent(monkeypatch):
    monkeypatch.delenv("SECRET_KEY", raising=False)
    with pytest.raises(ValueError):
        resolve_legacy_secret(deployed=True)


@pytest.mark.parametrize("bad", ["dev-secret-key-CHANGE-IN-PRODUCTION", "dev-foms-secret-key-123", "short"])
def test_resolve_legacy_secret_deployed_rejects_default_or_short(monkeypatch, bad):
    monkeypatch.setenv("SECRET_KEY", bad)
    with pytest.raises(ValueError):
        resolve_legacy_secret(deployed=True)


def test_resolve_legacy_secret_deployed_accepts_strong(monkeypatch):
    monkeypatch.setenv("SECRET_KEY", "a-strong-random-deployed-secret-01")
    assert resolve_legacy_secret(deployed=True) == "a-strong-random-deployed-secret-01"


def test_resolve_legacy_secret_non_deployed_dev_fallback(monkeypatch):
    monkeypatch.delenv("SECRET_KEY", raising=False)
    val = resolve_legacy_secret(deployed=False)
    assert val and val not in ("", None)


def test_build_app_deployed_fail_fast_on_missing_secret(monkeypatch):
    monkeypatch.setenv("RAILWAY_ENVIRONMENT", "production")
    monkeypatch.delenv("SECRET_KEY", raising=False)
    from foms.platform.app_factory import build_app

    with pytest.raises(ValueError):
        build_app(socketio_available=False)


# --------------------------------------------------------------------------- #
# 2. legacy 경로(미engaged/EMPTY) — 회귀 0
# --------------------------------------------------------------------------- #
def test_not_engaged_uses_legacy_only(monkeypatch):
    monkeypatch.delenv("FOMS_SIGNING_KEY_CURRENT", raising=False)
    assert resolve_secret_key_list("flask", FLASK_LABEL, legacy_secret="LEGACY") == ["LEGACY"]


def test_engaged_empty_mode_uses_legacy_only(app, monkeypatch):
    monkeypatch.setenv("FOMS_SIGNING_KEY_CURRENT", _root_b64())
    # app fixture seed = EMPTY.
    assert resolve_secret_key_list("flask", FLASK_LABEL, legacy_secret="LEGACY") == ["LEGACY"]


def test_engaged_ready_bridge_still_legacy_only(app, monkeypatch):
    monkeypatch.setenv("FOMS_SIGNING_KEY_CURRENT", _root_b64())
    _set_state(mode="READY", legacy_cutover_mode="BRIDGE")
    assert resolve_secret_key_list("flask", FLASK_LABEL, legacy_secret="LEGACY") == ["LEGACY"]


# --------------------------------------------------------------------------- #
# 3. ACTIVE+BRIDGE — 신규 derived sign, legacy verify-only(강제 로그아웃 0)
# --------------------------------------------------------------------------- #
def test_active_bridge_signs_derived_verifies_legacy(app, monkeypatch):
    root_b64 = _root_b64()
    root = decode_root_key(root_b64)
    kid = key_id_from_root(root)
    monkeypatch.setenv("FOMS_SIGNING_KEY_CURRENT", root_b64)
    _set_state(
        mode="ACTIVE", legacy_cutover_mode="BRIDGE", active_key_id=kid,
        legacy_flask_not_after=now_utc_naive() + timedelta(hours=1),
        legacy_wam_not_after=now_utc_naive() + timedelta(hours=1),
    )
    keys = resolve_secret_key_list("flask", FLASK_LABEL, legacy_secret="LEGACY")
    assert len(keys) == 2
    assert keys[-1] == derive_subkey(root, FLASK_LABEL)  # 신규는 derived key 로 sign

    # legacy raw-key 로 서명된 기존 세션은 ACTIVE 에서도 verify 성공(강제 로그아웃 0).
    legacy_tok = _cookie_serializer("LEGACY").dumps({"u": 1})
    active_ser = _cookie_serializer(keys)
    assert active_ser.loads(legacy_tok) == {"u": 1}

    # 신규 토큰은 derived key 로 서명 → legacy-only 로는 verify 불가.
    new_tok = active_ser.dumps({"u": 2})
    with pytest.raises((BadTimeSignature, SignatureExpired)):
        _cookie_serializer(["LEGACY"]).loads(new_tok)


def test_active_bridge_expired_legacy_deadline_drops_legacy_key(app, monkeypatch):
    root_b64 = _root_b64()
    kid = key_id_from_root(decode_root_key(root_b64))
    monkeypatch.setenv("FOMS_SIGNING_KEY_CURRENT", root_b64)
    _set_state(
        mode="ACTIVE", legacy_cutover_mode="BRIDGE", active_key_id=kid,
        legacy_flask_not_after=now_utc_naive() - timedelta(seconds=5),
        legacy_wam_not_after=now_utc_naive() - timedelta(seconds=5),
    )
    keys = resolve_secret_key_list("flask", FLASK_LABEL, legacy_secret="LEGACY")
    assert keys == [derive_subkey(decode_root_key(root_b64), FLASK_LABEL)]  # legacy deadline 지남 → 제외


def test_active_force_reauth_rejects_legacy(app, monkeypatch):
    root_b64 = _root_b64()
    root = decode_root_key(root_b64)
    kid = key_id_from_root(root)
    monkeypatch.setenv("FOMS_SIGNING_KEY_CURRENT", root_b64)
    _set_state(mode="ACTIVE", legacy_cutover_mode="FORCE_REAUTH", active_key_id=kid)
    keys = resolve_secret_key_list("flask", FLASK_LABEL, legacy_secret="LEGACY")
    assert keys == [derive_subkey(root, FLASK_LABEL)]  # FORCE_REAUTH 는 legacy verify-only 없음
    legacy_tok = _cookie_serializer("LEGACY").dumps({"u": 1})
    with pytest.raises((BadTimeSignature, SignatureExpired)):
        _cookie_serializer(keys).loads(legacy_tok)  # 기존 legacy 세션 무효 → 강제 재인증


def test_active_missing_active_root_fails_closed(app, monkeypatch):
    # ACTIVE 인데 active_key_id 에 맞는 root env 가 없으면 sign 불가 → fail-closed.
    from foms.services.security.signing.signing_keys import SigningRuntimeError

    monkeypatch.setenv("FOMS_SIGNING_KEY_CURRENT", _root_b64())
    _set_state(mode="ACTIVE", legacy_cutover_mode="BRIDGE", active_key_id="unknown" + "x" * 15)
    with pytest.raises(SigningRuntimeError):
        resolve_secret_key_list("flask", FLASK_LABEL, legacy_secret="LEGACY")


# --------------------------------------------------------------------------- #
# 4. WAM 런타임 — derived sign/legacy verify + cutoff
# --------------------------------------------------------------------------- #
def test_wam_launch_active_bridge_compat_and_derived(app, monkeypatch):
    import foms.services.channel_security as cs

    root_b64 = _root_b64()
    kid = key_id_from_root(decode_root_key(root_b64))
    monkeypatch.setenv("FOMS_SIGNING_KEY_CURRENT", root_b64)
    monkeypatch.setenv("SECRET_KEY", "wam-legacy-secret-abc-123456")

    # EMPTY 에서 legacy 로 서명된 기존 launch 토큰.
    monkeypatch.delenv("FOMS_SIGNING_KEY_CURRENT", raising=False)
    legacy_launch = cs.generate_wam_launch_token("mgr", 5, scopes=["page"])
    # ACTIVE+BRIDGE 로 전환 후에도 verify 성공(강제 만료 0).
    monkeypatch.setenv("FOMS_SIGNING_KEY_CURRENT", root_b64)
    _set_state(
        mode="ACTIVE", legacy_cutover_mode="BRIDGE", active_key_id=kid,
        legacy_flask_not_after=now_utc_naive() + timedelta(hours=1),
        legacy_wam_not_after=now_utc_naive() + timedelta(hours=1),
    )
    assert cs.verify_wam_launch_token(legacy_launch) is not None

    # 신규 launch 토큰은 derived key 로 서명 → legacy-only serializer 는 verify 불가.
    new_launch = cs.generate_wam_launch_token("mgr", 6, scopes=["page"])
    legacy_only = URLSafeTimedSerializer("wam-legacy-secret-abc-123456", salt="wam-launch-token")
    with pytest.raises((BadTimeSignature, SignatureExpired)):
        legacy_only.loads(new_launch)


def test_wam_cutoff_rejects_pre_cutoff_token(app, monkeypatch):
    import foms.services.channel_security as cs

    root_b64 = _root_b64()
    kid = key_id_from_root(decode_root_key(root_b64))
    monkeypatch.setenv("FOMS_SIGNING_KEY_CURRENT", root_b64)
    # cutoff 를 미래로 두면 지금(iat=now) 발급되는 토큰도 cutoff 이전 → 거부.
    _set_state(
        mode="ACTIVE", legacy_cutover_mode="FORCE_REAUTH", active_key_id=kid,
        wam_not_before=now_utc_naive() + timedelta(seconds=1000),
    )
    tok = cs.generate_wam_launch_token("mgr", 7)
    assert cs.verify_wam_launch_token(tok) is None  # predates active cutoff
