"""backfill artifact 암호화 (§7.3 line 1249-1251): DPAPI key-envelope + AES-256-GCM payload.

* **key-envelope**: run 별 random 32-byte AES data key 를 Windows DPAPI CurrentUser 로
  wrap 해 ``key-envelope.json`` 에 저장한다. optional entropy 로 packet/phase/db/dir 를
  바인딩하므로 동일 Windows account/host + 동일 파라미터에서만 unwrap 된다. 다른
  account/host/provider mismatch/entropy drift 는 fail-closed(audit 시작 0). 비-Windows
  는 지원 provider 부재로 fail-closed.
* **payload envelope**: safe/ambiguous/unmapped/manual csv 를 AES-256-GCM(nonce 12 random)
  으로 암호화해 exact ``.enc`` JSON envelope 로 저장한다. AAD 가 packet/phase/relative_path/
  db_instance/source_fingerprint/column_schema 를 length-prefix 결합해 payload 를 그 논리
  위치에 바인딩한다(재배치·오분류·파라미터 drift 를 복호화 단계에서 거부).

raw data key 와 plaintext 는 반환값(메모리)으로만 다루고 파일/DB/argv 에 남기지 않는다.
"""
from __future__ import annotations

import base64
import hashlib
import os
import struct
from typing import Any, Optional

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from foms.services.datetime_kst import now_utc_naive

KEY_ENVELOPE_VERSION = 1
DPAPI_PROVIDER = "WINDOWS_DPAPI_CURRENT_USER_V1"
PAYLOAD_VERSION = 1
PAYLOAD_ALG = "AES-256-GCM"

_DATA_KEY_BYTES = 32  # AES-256
_NONCE_BYTES = 12  # GCM standard nonce
_KEY_WRAP_PREFIX = b"FOMS_BACKFILL_KEY_WRAP_V1\0"
_PAYLOAD_AAD_PREFIX = b"FOMS_BACKFILL_PAYLOAD_V1\0"
_CRYPTPROTECT_UI_FORBIDDEN = 0x1  # 대화형 프롬프트 금지(무인 실행).


class BackfillCryptoError(RuntimeError):
    """key wrap/unwrap 또는 payload encrypt/decrypt 가 계약을 위반할 때(fail-closed)."""


def _b64url(raw: bytes) -> str:
    """padding 없는 base64url 인코딩."""
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _b64url_decode(text: str) -> bytes:
    """padding 없는 base64url 을 raw bytes 로 strict decode."""
    pad = "=" * (-len(text) % 4)
    return base64.urlsafe_b64decode(text + pad)


def lp(*parts: str) -> bytes:
    """length-prefixed 결합: 각 part = 4-byte big-endian 길이 + UTF-8 bytes.

    SSOT 의 ``LP(...)`` exact 바이트 표현. 모든 소비 도구가 이 library 를 공유하므로
    표현 일관성만 보장하면 되며, 길이 접두 덕에 필드 경계가 모호하지 않다(구분자 주입
    으로 서로 다른 튜플이 같은 바이트열을 만드는 것을 차단).
    """
    out = bytearray()
    for part in parts:
        b = part.encode("utf-8")
        out += struct.pack(">I", len(b))
        out += b
    return bytes(out)


def key_wrap_entropy(
    packet_id: str, phase: str, db_instance_id: str, artifact_dir_id: str
) -> bytes:
    """DPAPI OptionalEntropy = ``SHA256(prefix + LP(packet_id,phase,db_instance_id,artifact_dir_id))``."""
    return hashlib.sha256(
        _KEY_WRAP_PREFIX + lp(packet_id, phase, db_instance_id, artifact_dir_id)
    ).digest()


def _dpapi_protect(data: bytes, entropy: bytes) -> bytes:
    """CurrentUser DPAPI 로 ``data`` 를 wrap. 비-Windows fail-closed."""
    if os.name != "nt":
        raise BackfillCryptoError(
            "DPAPI is Windows-only (WINDOWS_DPAPI_CURRENT_USER_V1); other OS fail-closed."
        )
    import win32crypt  # 지연 import(비-Windows 에서 모듈 부재).

    return win32crypt.CryptProtectData(
        data, None, entropy, None, None, _CRYPTPROTECT_UI_FORBIDDEN
    )


def _dpapi_unprotect(wrapped: bytes, entropy: bytes) -> bytes:
    """CurrentUser DPAPI unwrap. 다른 account/host/tamper 는 fail-closed. 비-Windows fail-closed."""
    if os.name != "nt":
        raise BackfillCryptoError("DPAPI is Windows-only; other OS fail-closed.")
    import pywintypes
    import win32crypt

    try:
        _descr, data = win32crypt.CryptUnprotectData(
            wrapped, entropy, None, None, _CRYPTPROTECT_UI_FORBIDDEN
        )
    except pywintypes.error as exc:  # 다른 account/host/entropy/변조 → OS 가 거부.
        raise BackfillCryptoError(
            "DPAPI unwrap failed (different Windows account/host, wrong entropy, or tampered envelope)."
        ) from exc
    return data


def create_key_envelope(
    *,
    packet_id: str,
    phase: str,
    db_instance_id: str,
    artifact_dir_id: str,
    now: Optional[Any] = None,
) -> tuple[dict, bytes]:
    """새 random data key 를 DPAPI 로 wrap 하고 ``(key-envelope dict, raw data key)`` 반환.

    raw data key 는 호출자가 메모리에서만 payload 암호화에 쓰고 저장하지 않는다. dict 는
    ``key-envelope.json`` 으로 저장한다.

    :returns: ``(envelope, data_key)`` — envelope 은 exact schema, data_key 는 32 bytes.
    :raises BackfillCryptoError: 비-Windows(fail-closed).
    """
    data_key = os.urandom(_DATA_KEY_BYTES)
    entropy = key_wrap_entropy(packet_id, phase, db_instance_id, artifact_dir_id)
    wrapped = _dpapi_protect(data_key, entropy)
    envelope = {
        "version": KEY_ENVELOPE_VERSION,
        "provider": DPAPI_PROVIDER,
        "key_id": os.urandom(16).hex(),
        "wrapped_data_key_b64url": _b64url(wrapped),
        "entropy_sha256": hashlib.sha256(entropy).hexdigest(),
        "created_at": (now or now_utc_naive()).isoformat() + "Z",
    }
    return envelope, data_key


def load_data_key(
    envelope: dict,
    *,
    packet_id: str,
    phase: str,
    db_instance_id: str,
    artifact_dir_id: str,
) -> bytes:
    """key-envelope 를 검증하고 DPAPI 로 data key 를 복원(동일 account/host/params 에서만).

    :raises BackfillCryptoError: version/provider mismatch, entropy check 불일치(파라미터
        drift), unwrap 실패(다른 account/host/변조), 잘못된 key 길이. 모두 fail-closed.
    """
    if not isinstance(envelope, dict):
        raise BackfillCryptoError("key-envelope must be a JSON object.")
    if envelope.get("version") != KEY_ENVELOPE_VERSION:
        raise BackfillCryptoError("unsupported key-envelope version.")
    if envelope.get("provider") != DPAPI_PROVIDER:
        raise BackfillCryptoError(
            f"key-envelope provider mismatch (only {DPAPI_PROVIDER} supported)."
        )
    entropy = key_wrap_entropy(packet_id, phase, db_instance_id, artifact_dir_id)
    if hashlib.sha256(entropy).hexdigest() != envelope.get("entropy_sha256"):
        raise BackfillCryptoError(
            "key-envelope entropy check mismatch (packet/phase/db/dir params changed)."
        )
    wrapped = _b64url_decode(envelope["wrapped_data_key_b64url"])
    data_key = _dpapi_unprotect(wrapped, entropy)
    if len(data_key) != _DATA_KEY_BYTES:
        raise BackfillCryptoError("unwrapped data key has wrong length (expected 32 bytes).")
    return data_key


def payload_aad(
    *,
    packet_id: str,
    phase: str,
    relative_path: str,
    db_instance_id: str,
    source_fingerprint: str,
    column_schema_sha256: str,
) -> bytes:
    """payload AAD = ``prefix + LP(packet_id,phase,relative_path,db_instance_id,source_fingerprint,column_schema_sha256)``."""
    return _PAYLOAD_AAD_PREFIX + lp(
        packet_id,
        phase,
        relative_path,
        db_instance_id,
        source_fingerprint,
        column_schema_sha256,
    )


def encrypt_payload(
    plaintext: bytes,
    data_key: bytes,
    *,
    key_id: str,
    packet_id: str,
    phase: str,
    relative_path: str,
    db_instance_id: str,
    source_fingerprint: str,
    column_schema_sha256: str,
) -> dict:
    """plaintext 를 AES-256-GCM 으로 암호화해 exact ``.enc`` envelope dict 반환.

    :raises BackfillCryptoError: data key 길이 오류.
    """
    if len(data_key) != _DATA_KEY_BYTES:
        raise BackfillCryptoError("data key must be 32 bytes (AES-256).")
    aad = payload_aad(
        packet_id=packet_id,
        phase=phase,
        relative_path=relative_path,
        db_instance_id=db_instance_id,
        source_fingerprint=source_fingerprint,
        column_schema_sha256=column_schema_sha256,
    )
    nonce = os.urandom(_NONCE_BYTES)
    ciphertext = AESGCM(data_key).encrypt(nonce, plaintext, aad)
    return {
        "version": PAYLOAD_VERSION,
        "alg": PAYLOAD_ALG,
        "key_id": key_id,
        "nonce_b64url": _b64url(nonce),
        "aad_sha256": hashlib.sha256(aad).hexdigest(),
        "ciphertext_b64url": _b64url(ciphertext),
    }


def decrypt_payload(
    envelope: dict,
    data_key: bytes,
    *,
    packet_id: str,
    phase: str,
    relative_path: str,
    db_instance_id: str,
    source_fingerprint: str,
    column_schema_sha256: str,
) -> bytes:
    """``.enc`` envelope 를 복호화. AAD 재계산 불일치/GCM 인증 실패는 fail-closed.

    :raises BackfillCryptoError: version/alg mismatch, AAD 불일치(재배치/파라미터 drift),
        GCM 인증 실패(ciphertext/nonce/key 변조).
    """
    if not isinstance(envelope, dict):
        raise BackfillCryptoError("payload envelope must be a JSON object.")
    if envelope.get("version") != PAYLOAD_VERSION or envelope.get("alg") != PAYLOAD_ALG:
        raise BackfillCryptoError("unsupported payload envelope version/alg.")
    aad = payload_aad(
        packet_id=packet_id,
        phase=phase,
        relative_path=relative_path,
        db_instance_id=db_instance_id,
        source_fingerprint=source_fingerprint,
        column_schema_sha256=column_schema_sha256,
    )
    if hashlib.sha256(aad).hexdigest() != envelope.get("aad_sha256"):
        raise BackfillCryptoError(
            "payload AAD mismatch (artifact relocated/misclassified or params drift)."
        )
    nonce = _b64url_decode(envelope["nonce_b64url"])
    ciphertext = _b64url_decode(envelope["ciphertext_b64url"])
    try:
        return AESGCM(data_key).decrypt(nonce, ciphertext, aad)
    except InvalidTag as exc:
        raise BackfillCryptoError(
            "AES-GCM authentication failed (tampered ciphertext/nonce or wrong key)."
        ) from exc
