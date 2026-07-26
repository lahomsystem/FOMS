"""auth-rate key material 암호화 (AUTH-ACCOUNT-01, BACKFILL AES-256-GCM 패턴).

BACKFILL crypto(``foms/services/security/backfill/crypto.py``)의 payload envelope
패턴(AES-256-GCM·nonce-12·AAD length-prefix 바인딩·InvalidTag fail-closed)을
그대로 따르되, data key 를 DPAPI 대신 **env master key** 에서 얻는다. auth-rate key 는
로그인/telemetry rate limiter 가 **모든 (Linux) replica** 에서 runtime 에 복호화해야
하는데 DPAPI CurrentUser 는 Windows 전용·per-host 라 배포 환경에 맞지 않기 때문이다.

* AAD 는 payload 를 그 key 의 **fingerprint(key_id)** 에 바인딩한다. fingerprint 는
  key material 의 sha256 이므로 slot(active/previous/pending)이나 generation 이 바뀌어도
  같은 key 는 같은 AAD 를 유지한다(rotation 으로 active→previous 이동해도 복호화 성립).
  다른 key 의 ciphertext 를 어떤 key_id 로 위장해 밀어넣으면 GCM 인증이 실패한다.
* rate key plaintext(32 random bytes)는 반환값(메모리)으로만 다루고 파일/DB/로그/argv 에
  절대 남기지 않는다. DB 에는 오직 envelope(nonce+ciphertext+aad hash)만 저장한다.

env master key 는 ``FOMS_AUTH_RATE_MASTER_KEY_B64URL`` (32 byte base64url) 로만 주입하며
코드/커밋에 하드코딩하지 않는다(fail-closed 부재 시).
"""
from __future__ import annotations

import base64
import hashlib
import os
from typing import Optional

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

# length-prefix 결합은 BACKFILL crypto 와 같은 표현을 재사용(경계 모호성 차단).
from foms.services.security.backfill.crypto import lp

ENV_MASTER = "FOMS_AUTH_RATE_MASTER_KEY_B64URL"

PAYLOAD_VERSION = 1
PAYLOAD_ALG = "AES-256-GCM"
PACKET_ID = "AUTH-ACCOUNT-01"

_KEY_BYTES = 32  # AES-256 / rate key material
_NONCE_BYTES = 12  # GCM standard nonce
_AAD_PREFIX = b"FOMS_AUTH_RATE_KEY_V1\0"


class AuthRateCryptoError(RuntimeError):
    """master key 해석 또는 key material encrypt/decrypt 계약 위반(fail-closed)."""


def _b64url(raw: bytes) -> str:
    """padding 없는 base64url 인코딩."""
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _b64url_decode(text: str) -> bytes:
    """padding 없는 base64url 을 raw bytes 로 strict decode."""
    pad = "=" * (-len(text) % 4)
    return base64.urlsafe_b64decode(text + pad)


def sha256_hex(data: bytes) -> str:
    """bytes 의 sha256 hex(artifact sha 계산용)."""
    return hashlib.sha256(data).hexdigest()


def resolve_master_key(*, master_b64url: Optional[str] = None) -> bytes:
    """env(또는 명시 인자)에서 32-byte AES master key 를 해석한다.

    :param master_b64url: 명시 master(테스트/CLI 주입). None 이면 env ``FOMS_AUTH_RATE_MASTER_KEY_B64URL``.
    :returns: 32-byte master key.
    :raises AuthRateCryptoError: 부재 또는 잘못된 길이(fail-closed; 하드코딩 fallback 없음).
    """
    raw = master_b64url if master_b64url is not None else os.environ.get(ENV_MASTER)
    raw = (raw or "").strip()
    if not raw:
        raise AuthRateCryptoError(
            f"{ENV_MASTER} is not set; auth-rate key material cannot be decrypted "
            "(fail-closed; no hardcoded master fallback)."
        )
    try:
        key = _b64url_decode(raw)
    except (ValueError, TypeError) as exc:
        raise AuthRateCryptoError(f"{ENV_MASTER} is not valid base64url.") from exc
    if len(key) != _KEY_BYTES:
        raise AuthRateCryptoError(
            f"{ENV_MASTER} must decode to {_KEY_BYTES} bytes (got {len(key)})."
        )
    return key


def new_key_material() -> bytes:
    """새 random rate key material(32 bytes). 저장/로그 금지 — 즉시 암호화한다."""
    return os.urandom(_KEY_BYTES)


def fingerprint(material: bytes) -> str:
    """rate key material 의 sha256 fingerprint(= key_id, DB 저장용). raw 노출 0(one-way)."""
    return sha256_hex(material)


def _aad(key_id: str) -> bytes:
    """payload AAD = ``prefix + LP(packet_id, key_id)`` — ciphertext 를 fingerprint 에 바인딩."""
    return _AAD_PREFIX + lp(PACKET_ID, key_id)


def encrypt_key_material(material: bytes, master: bytes, *, key_id: str) -> dict:
    """rate key material 을 AES-256-GCM 으로 암호화해 exact envelope dict 반환.

    :param key_id: material 의 fingerprint(AAD 바인딩). :func:`fingerprint` 결과여야 한다.
    :raises AuthRateCryptoError: master 길이 오류 또는 key_id 가 fingerprint 와 불일치.
    """
    if len(master) != _KEY_BYTES:
        raise AuthRateCryptoError("master key must be 32 bytes (AES-256).")
    if fingerprint(material) != key_id:
        raise AuthRateCryptoError("key_id must equal the fingerprint of the material.")
    aad = _aad(key_id)
    nonce = os.urandom(_NONCE_BYTES)
    ciphertext = AESGCM(master).encrypt(nonce, material, aad)
    return {
        "version": PAYLOAD_VERSION,
        "alg": PAYLOAD_ALG,
        "key_id": key_id,
        "nonce_b64url": _b64url(nonce),
        "aad_sha256": sha256_hex(aad),
        "ciphertext_b64url": _b64url(ciphertext),
    }


def decrypt_key_material(envelope: dict, master: bytes, *, key_id: str) -> bytes:
    """envelope 를 복호화해 rate key material 반환. AAD/GCM 불일치는 fail-closed.

    :raises AuthRateCryptoError: version/alg mismatch, key_id/AAD 불일치(위장/재배치),
        GCM 인증 실패(ciphertext/nonce/master 변조), 복호화 후 fingerprint 불일치.
    """
    if not isinstance(envelope, dict):
        raise AuthRateCryptoError("payload envelope must be a JSON object.")
    if envelope.get("version") != PAYLOAD_VERSION or envelope.get("alg") != PAYLOAD_ALG:
        raise AuthRateCryptoError("unsupported payload envelope version/alg.")
    if envelope.get("key_id") != key_id:
        raise AuthRateCryptoError("envelope key_id does not match the requested key_id.")
    aad = _aad(key_id)
    if sha256_hex(aad) != envelope.get("aad_sha256"):
        raise AuthRateCryptoError("payload AAD mismatch (key_id drift).")
    nonce = _b64url_decode(envelope["nonce_b64url"])
    ciphertext = _b64url_decode(envelope["ciphertext_b64url"])
    try:
        material = AESGCM(master).decrypt(nonce, ciphertext, aad)
    except InvalidTag as exc:
        raise AuthRateCryptoError(
            "AES-GCM authentication failed (tampered ciphertext/nonce or wrong master)."
        ) from exc
    if fingerprint(material) != key_id:
        raise AuthRateCryptoError("decrypted material fingerprint does not match key_id.")
    return material


def demo() -> None:
    """self-check: round-trip + tamper fail-closed + key_id 위장 거부."""
    master = os.urandom(_KEY_BYTES)
    mat = new_key_material()
    kid = fingerprint(mat)
    env = encrypt_key_material(mat, master, key_id=kid)
    assert decrypt_key_material(env, master, key_id=kid) == mat
    # tamper ciphertext → InvalidTag.
    bad = dict(env)
    ct = _b64url_decode(bad["ciphertext_b64url"])
    bad["ciphertext_b64url"] = _b64url(bytes([ct[0] ^ 1]) + ct[1:])
    try:
        decrypt_key_material(bad, master, key_id=kid)
        raise AssertionError("tampered ciphertext must fail")
    except AuthRateCryptoError:
        pass
    # 다른 key_id 로 위장 → 거부.
    try:
        decrypt_key_material(env, master, key_id="0" * 64)
        raise AssertionError("key_id spoof must fail")
    except AuthRateCryptoError:
        pass
    print("auth_rate.crypto demo OK")


if __name__ == "__main__":  # pragma: no cover
    demo()
