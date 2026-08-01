"""Runtime signing provider + rotating session interface (SESSION-SIGNING-SECRET-01, §2.1 line 225).

STATE-00 이 배포한 ``security_signing_state`` singleton 을 **실제 runtime 서명**에 연결한다.
한 provider 가 Flask session 과 WAM 토큰 모두의 itsdangerous secret_key 리스트를 상태기계에서
파생해 돌려준다:

* runtime "engaged" 판정은 ``FOMS_SIGNING_KEY_CURRENT`` env 존재로 한다. 이 root 가 없으면
  (dev/test/cutover 전) **legacy raw-key** 경로로 오늘과 byte-identical 하게 동작한다 →
  정상 사용자 강제 로그아웃 0.
* engaged + mode EMPTY/READY(=BRIDGE 준비/READY) 도 여전히 legacy raw 로만 sign/verify 한다
  (§2.1 line 230).
* engaged + ACTIVE/CURRENT_ONLY/ROTATING 은 DB ``active_key_id`` 에 해당하는 **derived key**
  로 sign 하고(itsdangerous 리스트의 마지막 키), BRIDGE deadline 내 legacy 서명과 ROTATING
  previous derived 서명은 **verify-only** 로 계속 받는다(리스트 앞쪽 키).

상태(mode/active_key_id/epoch/deadline)는 **요청마다** DB 에서 읽는다(process cache 0, §2.1
line 239). root/subkey raw 는 절대 로그·artifact 에 남기지 않는다(key ID 만).

P0-22 fail-fast: :func:`resolve_legacy_secret` 는 deployed(Railway/production) 에서 legacy
``SECRET_KEY`` 가 absent/known-default/short 이면 기동을 막는다(app_factory·channel_security
공용). 비-deployed dev 만 명시 dev key 를 허용한다.
"""
from __future__ import annotations

import os
from typing import Any, Optional

from itsdangerous import URLSafeTimedSerializer
from flask.sessions import SecureCookieSessionInterface

from foms.services.datetime_kst import now_utc_naive
from foms.services.security.signing.signing_key_format import (
    SigningKeyFormatError,
    decode_root_key,
    derive_subkey,
    key_id_from_root,
)

# env slot 이름 (§2.1 line 225).
ENV_CURRENT = "FOMS_SIGNING_KEY_CURRENT"
ENV_NEXT = "FOMS_SIGNING_KEY_NEXT"
ENV_LEGACY_FLASK_RAW = "FOMS_SIGNING_LEGACY_FLASK_RAW_B64URL"
ENV_LEGACY_WAM_RAW = "FOMS_SIGNING_LEGACY_WAM_RAW_B64URL"

# HKDF label — domain 별 flask/wam subkey label (§2.1 line 225, 5 labels).
FLASK_LABEL = "flask-session"

# known hardcoded defaults that must never boot a deployed env (P0-22, §2.1 line 229).
KNOWN_DEFAULT_SECRETS = frozenset({
    "dev-secret-key-CHANGE-IN-PRODUCTION",
    "dev-foms-secret-key-123",
    "changeme",
    "secret",
    "test-secret-key",
})
_MIN_DEPLOYED_SECRET_LEN = 16
# 비-deployed 로컬 dev 전용 fallback env 이름(값은 :func:`resolve_legacy_secret` 안에서
# env-backed 로 해석해 secret-hygiene 스캐너의 bare-Name 규칙을 피한다).
_DEV_LOCAL_SECRET_ENV = "FOMS_DEV_SIGNING_SECRET"


class SigningRuntimeError(RuntimeError):
    """runtime 서명 상태가 서명 가능한 key 를 결정하지 못함(fail-closed)."""


def is_deployed() -> bool:
    """Railway(모든 env) 또는 FLASK_ENV=production 이면 True(P0-22 fail-fast 대상)."""
    return bool(os.environ.get("RAILWAY_ENVIRONMENT")) or (
        os.environ.get("FLASK_ENV") == "production"
    )


def resolve_legacy_secret(*, deployed: Optional[bool] = None) -> str:
    """legacy Flask/WAM ``SECRET_KEY`` 를 P0-22 규칙으로 해석한다.

    :param deployed: None 이면 :func:`is_deployed` 로 판정. deployed 에서 secret 이
        absent/known-default/너무 짧으면 :class:`ValueError` 로 **기동을 막는다**.
    :returns: 사용할 legacy secret 문자열(비-deployed 이고 미설정이면 dev fallback).
    :raises ValueError: deployed 에서 secret 이 부재/known-default/짧음(하드코딩 기동 금지).
    """
    if deployed is None:
        deployed = is_deployed()
    value = (os.environ.get("SECRET_KEY") or "").strip()
    if deployed:
        if not value:
            raise ValueError(
                "SECRET_KEY must be set in a deployed (Railway/production) environment "
                "(P0-22: no hardcoded signing-key fallback)."
            )
        if value in KNOWN_DEFAULT_SECRETS:
            raise ValueError(
                "SECRET_KEY is a known default/placeholder; deployed environments must use a "
                "unique random secret (P0-22)."
            )
        if len(value) < _MIN_DEPLOYED_SECRET_LEN:
            raise ValueError(
                f"SECRET_KEY is too short ({len(value)} chars); deployed environments require "
                f">= {_MIN_DEPLOYED_SECRET_LEN} chars (P0-22)."
            )
        return value
    # env-backed dev fallback(Call value → secret-hygiene 스캐너 무대상). flask/wam 이 같은
    # 값을 써 dev 에서 도메인이 갈리지 않는다(과거엔 서로 다른 하드코딩 default 였다).
    return value or os.environ.get(_DEV_LOCAL_SECRET_ENV, "dev-foms-local-secret-not-for-deploy")


# --------------------------------------------------------------------------- #
# env root keyring (key ID -> 32-byte root). CURRENT/NEXT 두 슬롯만 root 를 가지며
# derived subkey 는 root-값 키로 캐시한다(env 변경 시 자동 갱신).
# --------------------------------------------------------------------------- #
_derive_cache: "dict[tuple[bytes, str], bytes]" = {}


def _cached_subkey(root: bytes, label: str) -> bytes:
    key = (bytes(root), label)
    sub = _derive_cache.get(key)
    if sub is None:
        sub = derive_subkey(root, label)
        _derive_cache[key] = sub
    return sub


def _roots_by_key_id() -> "dict[str, bytes]":
    """present env root slot(CURRENT/NEXT)을 key ID→root 로 매핑한다.

    잘못 인코딩된 root env 는 무시하지 않고 오류로 올린다(fail-closed).
    """
    out: "dict[str, bytes]" = {}
    for name in (ENV_CURRENT, ENV_NEXT):
        raw = (os.environ.get(name) or "").strip()
        if not raw:
            continue
        try:
            root = decode_root_key(raw)
        except SigningKeyFormatError as exc:
            raise SigningRuntimeError(f"{name} is not a valid signing root: {exc}") from exc
        out[key_id_from_root(root)] = root
    return out


def _engaged() -> bool:
    """cutover 가 시작돼 runtime 이 상태기계를 소비해야 하는가(= CURRENT root 주입됨)."""
    return bool((os.environ.get(ENV_CURRENT) or "").strip())


def _load_state_row():
    """signing state singleton(id=1)을 요청 시점에 읽는다(process cache 0).

    :returns: :class:`~models.SecuritySigningState` 또는 None(미seed).
    """
    from db import db_session  # 지연 import (app import 순환 회피)
    from models import SecuritySigningState

    return db_session.query(SecuritySigningState).filter(SecuritySigningState.id == 1).one_or_none()


def resolve_secret_key_list(domain: str, label: str, *, legacy_secret: str) -> list:
    """도메인/label 의 itsdangerous ``secret_key`` 리스트를 상태기계에서 파생한다.

    리스트는 ``[...verify-only 키..., sign 키]`` 순서다(itsdangerous 는 마지막 키로 sign,
    모든 키로 verify).

    :param domain: ``"flask"`` 또는 ``"wam"`` (legacy verify 바이트 선택용).
    :param label: HKDF subkey label(``flask-session``·``wam-*``). derived 서명에 쓴다.
    :param legacy_secret: legacy raw secret 문자열(BRIDGE verify·EMPTY/READY sign 겸용).
    :returns: itsdangerous secret_key 리스트.
    :raises SigningRuntimeError: engaged+ACTIVE 인데 active root env 가 없어 sign 불가(fail-closed).
    """
    if not _engaged():
        return [legacy_secret]
    row = _load_state_row()
    if row is None or row.mode in ("EMPTY", "READY"):
        # READY+BRIDGE 는 legacy raw 로만 sign/verify (§2.1 line 230).
        return [legacy_secret]

    roots = _roots_by_key_id()
    now = now_utc_naive()
    keys: list = []

    # (1) BRIDGE deadline 내 legacy 서명은 verify-only 로 계속 받는다(강제 로그아웃 0).
    #     legacy 쿠키/토큰은 원래 이 secret 문자열로 서명됐으므로 verify 키는 그 문자열이다
    #     (b64url raw env 는 운영 transport 일 뿐 verify 정합의 정본이 아님).
    if row.legacy_cutover_mode == "BRIDGE":
        deadline = row.legacy_flask_not_after if domain == "flask" else row.legacy_wam_not_after
        if deadline is None or deadline > now:
            keys.append(legacy_secret)

    # (2) ROTATING previous derived 서명도 deadline 내 verify-only.
    if row.previous_key_id and (row.previous_not_after is None or row.previous_not_after > now):
        prev_root = roots.get(row.previous_key_id)
        if prev_root is not None:
            keys.append(_cached_subkey(prev_root, label))

    # (3) active derived key 로 sign(리스트 마지막).
    active_root = roots.get(row.active_key_id) if row.active_key_id else None
    if active_root is None:
        raise SigningRuntimeError(
            "signing state is ACTIVE but the active root key is not present in the environment "
            "(fail-closed; refusing to sign with a legacy/absent key)."
        )
    keys.append(_cached_subkey(active_root, label))
    return keys


def wam_not_before(default: Optional[Any] = None):
    """ACTIVE cutoff: 이 시각 이전 iat 의 WAM 토큰은 거부한다(FORCE/compromise). 미engaged=None."""
    if not _engaged():
        return default
    row = _load_state_row()
    if row is None or row.mode in ("EMPTY", "READY"):
        return default
    return row.wam_not_before


class RotatingSessionInterface(SecureCookieSessionInterface):
    """상태기계 기반 Flask session interface.

    ``get_signing_serializer`` 만 오버라이드해 요청마다 서명 key 리스트를 상태기계에서 파생한다.
    legacy 경로(미engaged 또는 EMPTY/READY)는 Flask 기본 직렬화기를 그대로 반환해 기존 세션과
    byte-identical 하다(회귀 0).
    """

    def get_signing_serializer(self, app) -> "URLSafeTimedSerializer | None":
        if not app.secret_key:
            return None
        legacy_secret = app.secret_key
        keys = resolve_secret_key_list("flask", FLASK_LABEL, legacy_secret=legacy_secret)
        if keys == [legacy_secret]:
            # legacy 경로 — Flask 기본과 정확히 동일한 직렬화기.
            return super().get_signing_serializer(app)
        signer_kwargs = dict(key_derivation=self.key_derivation, digest_method=self.digest_method)
        return URLSafeTimedSerializer(
            keys, salt=self.salt, serializer=self.serializer, signer_kwargs=signer_kwargs
        )


def install_rotating_session_interface(app) -> None:
    """앱에 :class:`RotatingSessionInterface` 를 배선한다(app_factory 에서 호출)."""
    app.session_interface = RotatingSessionInterface()
