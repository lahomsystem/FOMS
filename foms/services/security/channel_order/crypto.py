"""channel key material 암호화 + per-receipt secret sealing/rewrap (CHANNEL-INBOUND-ORDER-01).

AUTH-ACCOUNT-01 ``auth_rate/crypto.py`` 의 AES-256-GCM envelope 패턴을 그대로 따르되 **도메인
분리**를 지킨다(report §signing: auth-rate/session key 를 channel 도메인에 재사용 금지). 따라서
channel 은 자기 master env(``FOMS_CHANNEL_INBOUND_MASTER_KEY_B64URL``)와 자기 AAD prefix/packet
id 를 쓴다.

두 층의 암호화:

1. **key-at-rest**: channel key material(32 random bytes)을 master key 로 암호화해 key_state
   ciphertext 컬럼에 봉투로 저장한다(:func:`encrypt_key_material`). fingerprint(key_id)만 노출.
2. **per-receipt secret sealing**: 활성 channel key 로 receipt 별 secret 를 봉인한다
   (:func:`seal_secret`). key rotation 시 :func:`rewrap_secret` 로 구 key→새 key 재봉인한다.
   재봉인이 끝나기 전에는 구 key 참조가 남아 finalize(구 key 제거)가 거부된다(old-reference 0 전
   제거 0).

어느 층이든 **plaintext 키 material 은 파일/DB/로그/argv 에 남기지 않는다**. DB 에는 오직
envelope(nonce+ciphertext+aad hash)만 저장한다.
"""
from __future__ import annotations

import base64
import hashlib
import os
from typing import Optional

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

# length-prefix 결합은 다른 crypto 모듈과 같은 표현을 재사용(경계 모호성 차단).
from foms.services.security.backfill.crypto import lp

ENV_MASTER = "FOMS_CHANNEL_INBOUND_MASTER_KEY_B64URL"

PAYLOAD_VERSION = 1
PAYLOAD_ALG = "AES-256-GCM"
PACKET_ID = "CHANNEL-INBOUND-ORDER-01"

_KEY_BYTES = 32  # AES-256 / channel key material
_NONCE_BYTES = 12  # GCM standard nonce
_AAD_KEY_PREFIX = b"FOMS_CHANNEL_INBOUND_KEY_V1\0"
_AAD_SECRET_PREFIX = b"FOMS_CHANNEL_INBOUND_SECRET_V1\0"


class ChannelCryptoError(RuntimeError):
    """master key 해석 또는 material/secret encrypt/decrypt 계약 위반(fail-closed)."""


def _b64url(raw: bytes) -> str:
    """padding 없는 base64url 인코딩."""
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _b64url_decode(text: str) -> bytes:
    """padding 없는 base64url 을 raw bytes 로 strict decode."""
    pad = "=" * (-len(text) % 4)
    return base64.urlsafe_b64decode(text + pad)


def sha256_hex(data: bytes) -> str:
    """bytes 의 sha256 hex(artifact/fingerprint 계산용)."""
    return hashlib.sha256(data).hexdigest()


def resolve_master_key(*, master_b64url: Optional[str] = None) -> bytes:
    """env(또는 명시 인자)에서 32-byte AES master key 를 해석한다(fail-closed).

    :param master_b64url: 명시 master(테스트/CLI 주입). None 이면 env ``ENV_MASTER``.
    :returns: 32-byte master key.
    :raises ChannelCryptoError: 부재 또는 잘못된 길이(하드코딩 fallback 없음).
    """
    raw = master_b64url if master_b64url is not None else os.environ.get(ENV_MASTER)
    raw = (raw or "").strip()
    if not raw:
        raise ChannelCryptoError(
            f"{ENV_MASTER} is not set; channel key material cannot be decrypted "
            "(fail-closed; no hardcoded master fallback)."
        )
    try:
        key = _b64url_decode(raw)
    except (ValueError, TypeError) as exc:
        raise ChannelCryptoError(f"{ENV_MASTER} is not valid base64url.") from exc
    if len(key) != _KEY_BYTES:
        raise ChannelCryptoError(
            f"{ENV_MASTER} must decode to {_KEY_BYTES} bytes (got {len(key)})."
        )
    return key


def new_key_material() -> bytes:
    """새 random channel key material(32 bytes). 저장/로그 금지 — 즉시 암호화한다."""
    return os.urandom(_KEY_BYTES)


def fingerprint(material: bytes) -> str:
    """channel key material 의 sha256 fingerprint(= key_id, DB 저장용). raw 노출 0."""
    return sha256_hex(material)


def _aad(prefix: bytes, key_id: str) -> bytes:
    """payload AAD = ``prefix + LP(packet_id, key_id)`` — ciphertext 를 fingerprint 에 바인딩."""
    return prefix + lp(PACKET_ID, key_id)


def _encrypt(plaintext: bytes, key: bytes, *, key_id: str, prefix: bytes) -> dict:
    """AES-256-GCM 봉투 dict 생성(key_id 를 AAD 로 바인딩)."""
    if len(key) != _KEY_BYTES:
        raise ChannelCryptoError("encryption key must be 32 bytes (AES-256).")
    aad = _aad(prefix, key_id)
    nonce = os.urandom(_NONCE_BYTES)
    ciphertext = AESGCM(key).encrypt(nonce, plaintext, aad)
    return {
        "version": PAYLOAD_VERSION,
        "alg": PAYLOAD_ALG,
        "key_id": key_id,
        "nonce_b64url": _b64url(nonce),
        "aad_sha256": sha256_hex(aad),
        "ciphertext_b64url": _b64url(ciphertext),
    }


def _decrypt(envelope: dict, key: bytes, *, key_id: str, prefix: bytes) -> bytes:
    """AES-256-GCM 봉투 복호화(version/alg/key_id/AAD/GCM 불일치는 fail-closed)."""
    if not isinstance(envelope, dict):
        raise ChannelCryptoError("payload envelope must be a JSON object.")
    if envelope.get("version") != PAYLOAD_VERSION or envelope.get("alg") != PAYLOAD_ALG:
        raise ChannelCryptoError("unsupported payload envelope version/alg.")
    if envelope.get("key_id") != key_id:
        raise ChannelCryptoError("envelope key_id does not match the requested key_id.")
    aad = _aad(prefix, key_id)
    if sha256_hex(aad) != envelope.get("aad_sha256"):
        raise ChannelCryptoError("payload AAD mismatch (key_id drift).")
    nonce = _b64url_decode(envelope["nonce_b64url"])
    ciphertext = _b64url_decode(envelope["ciphertext_b64url"])
    try:
        return AESGCM(key).decrypt(nonce, ciphertext, aad)
    except InvalidTag as exc:
        raise ChannelCryptoError(
            "AES-GCM authentication failed (tampered ciphertext/nonce or wrong key)."
        ) from exc


def encrypt_key_material(material: bytes, master: bytes, *, key_id: str) -> dict:
    """channel key material 을 master 로 암호화해 at-rest envelope dict 반환.

    :param key_id: material 의 fingerprint(AAD 바인딩). :func:`fingerprint` 결과여야 한다.
    :raises ChannelCryptoError: key_id 가 fingerprint 와 불일치.
    """
    if fingerprint(material) != key_id:
        raise ChannelCryptoError("key_id must equal the fingerprint of the material.")
    return _encrypt(material, master, key_id=key_id, prefix=_AAD_KEY_PREFIX)


def decrypt_key_material(envelope: dict, master: bytes, *, key_id: str) -> bytes:
    """at-rest envelope 를 master 로 복호화해 channel key material 반환(fail-closed).

    :raises ChannelCryptoError: 봉투 불일치·GCM 실패·복호화 후 fingerprint 불일치.
    """
    material = _decrypt(envelope, master, key_id=key_id, prefix=_AAD_KEY_PREFIX)
    if fingerprint(material) != key_id:
        raise ChannelCryptoError("decrypted material fingerprint does not match key_id.")
    return material


def seal_secret(plaintext: bytes, channel_key: bytes, *, key_id: str) -> dict:
    """per-receipt secret 를 활성 channel key 로 봉인한 envelope dict 반환.

    :param key_id: 봉인에 쓴 channel key 의 fingerprint(rotation 시 어느 세대 key 인지 식별).
    """
    return _encrypt(plaintext, channel_key, key_id=key_id, prefix=_AAD_SECRET_PREFIX)


def unseal_secret(envelope: dict, channel_key: bytes, *, key_id: str) -> bytes:
    """봉인된 secret 를 channel key 로 복호화(fail-closed)."""
    return _decrypt(envelope, channel_key, key_id=key_id, prefix=_AAD_SECRET_PREFIX)


def rewrap_secret(
    envelope: dict, old_key: bytes, new_key: bytes, *, old_key_id: str, new_key_id: str
) -> dict:
    """봉인된 secret 를 구 channel key→새 channel key 로 재봉인한다(rewrap).

    구 key 로 복호화 후 새 key 로 재봉인하며, 중간 plaintext 는 메모리로만 다룬다. 이 함수가
    모든 참조 secret 에 적용돼 구 key 참조가 0 이 되어야 :func:`state_ops.rotation_finalize`
    가 구 key 를 제거할 수 있다(old-reference 0 전 제거 0).

    :raises ChannelCryptoError: 구 key 로 복호화 실패(변조/잘못된 key).
    """
    plaintext = unseal_secret(envelope, old_key, key_id=old_key_id)
    return seal_secret(plaintext, new_key, key_id=new_key_id)


def demo() -> None:
    """self-check: key-at-rest round-trip + secret seal/rewrap + tamper fail-closed."""
    master = os.urandom(_KEY_BYTES)
    mat = new_key_material()
    kid = fingerprint(mat)
    env = encrypt_key_material(mat, master, key_id=kid)
    assert decrypt_key_material(env, master, key_id=kid) == mat

    # per-receipt secret seal → unseal round-trip.
    secret = b"receipt-42-contact-token"
    sealed = seal_secret(secret, mat, key_id=kid)
    assert unseal_secret(sealed, mat, key_id=kid) == secret

    # rewrap to a new channel key generation.
    new_mat = new_key_material()
    new_kid = fingerprint(new_mat)
    rewrapped = rewrap_secret(sealed, mat, new_mat, old_key_id=kid, new_key_id=new_kid)
    assert unseal_secret(rewrapped, new_mat, key_id=new_kid) == secret
    try:
        unseal_secret(rewrapped, mat, key_id=kid)  # old key must no longer open it
        raise AssertionError("rewrapped secret must not open under the old key")
    except ChannelCryptoError:
        pass

    # tamper ciphertext → InvalidTag.
    bad = dict(env)
    ct = _b64url_decode(bad["ciphertext_b64url"])
    bad["ciphertext_b64url"] = _b64url(bytes([ct[0] ^ 1]) + ct[1:])
    try:
        decrypt_key_material(bad, master, key_id=kid)
        raise AssertionError("tampered ciphertext must fail")
    except ChannelCryptoError:
        pass
    print("channel_order.crypto demo OK")


if __name__ == "__main__":  # pragma: no cover
    demo()
