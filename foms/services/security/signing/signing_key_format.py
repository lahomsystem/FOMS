"""Pure signing key-format helper — decode / derive / key-ID only (§2.1 line 225).

Root env value 를 strict base64url 로 decode(정확히 32 bytes) 하고, ``HKDF-SHA256`` 로
5 개의 versioned subkey 를 유도하며, root 의 one-way key ID 를 계산한다. **이 모듈은
sign/verify 를 하지 않는다** — provider·serializer·runtime 상태와 무관한 순수 format
계약이다(runtime 서명 전환은 SESSION-SIGNING-SECRET-01).

보안 불변식:

* root/subkey **raw bytes 는 절대 로그·artifact·예외 메시지에 넣지 않는다.** 밖으로 내보내도
  안전한 유일한 값은 key ID(root 의 SHA256 fingerprint)뿐이다.
* base64url 은 padding 없는 canonical 형식만 허용(비정규/공백/패딩 거부).
* HKDF label 은 5 개 exact 집합만 허용(미등록 label 은 거부).

golden vector(:data:`GOLDEN_VECTOR`)가 env decode·5 파생 bytes·key ID 를 고정해 salt/
label/length 의 우발적 변경을 잡는다.
"""
from __future__ import annotations

import base64
import hashlib
import re

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

ROOT_KEY_BYTES = 32
HKDF_SALT = b"FOMS_SIGNING_V1"
HKDF_LENGTH = 32
KEY_ID_DOMAIN = b"FOMS_KEY_ID_V1\0"
KEY_ID_BYTES = 16

# exact 5 versioned info labels (§2.1 line 225). 순서 고정, 중복/미등록은 거부.
DERIVED_LABELS = (
    "flask-session",
    "wam-launch-token",
    "wam-entry-token",
    "wam-short-link",
    "wam-session-token",
)
_LABEL_SET = frozenset(DERIVED_LABELS)

# padding 없는 base64url 알파벳(공백/패딩 불허).
_B64URL_RE = re.compile(r"\A[A-Za-z0-9_-]+\Z")


class SigningKeyFormatError(ValueError):
    """root env decode / HKDF label / length 계약 위반."""


def _b64url_decode_strict(value: str) -> bytes:
    """padding 없는 canonical base64url 문자열을 raw bytes 로 strict decode.

    :param value: padding·공백 없는 base64url 문자열.
    :returns: decode 된 raw bytes.
    :raises SigningKeyFormatError: 빈 값·비 base64url 알파벳·비정규(round-trip 불일치).
    """
    if not isinstance(value, str) or not value:
        raise SigningKeyFormatError("root key env value must be a non-empty string.")
    if not _B64URL_RE.match(value):
        raise SigningKeyFormatError(
            "root key must be padding-free base64url (alphabet A-Za-z0-9_-, no padding/whitespace)."
        )
    pad = "=" * (-len(value) % 4)
    raw = base64.urlsafe_b64decode(value + pad)
    # round-trip guard: 비정규(잉여 trailing bit)로 만든 문자열을 거부.
    if base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii") != value:
        raise SigningKeyFormatError("root key base64url is not canonical.")
    return raw


def decode_root_key(env_value: str) -> bytes:
    """base64url root env 값을 정확히 32 raw bytes 로 strict decode.

    :param env_value: ``FOMS_SIGNING_KEY_*`` env 의 padding 없는 base64url 값.
    :returns: 32 byte root(호출자는 이 값을 로그/artifact 에 남기지 않는다).
    :raises SigningKeyFormatError: 인코딩 위반 또는 길이 != 32.
    """
    raw = _b64url_decode_strict(env_value)
    if len(raw) != ROOT_KEY_BYTES:
        raise SigningKeyFormatError(
            f"root key must decode to exactly {ROOT_KEY_BYTES} bytes (got {len(raw)})."
        )
    return raw


def derive_subkey(root: bytes, label: str) -> bytes:
    """등록된 label 하나의 HKDF-SHA256 subkey 를 유도.

    :param root: 32 byte root(:func:`decode_root_key` 결과).
    :param label: :data:`DERIVED_LABELS` 중 하나.
    :returns: 32 byte 파생 subkey(secret — 로그/저장 금지).
    :raises SigningKeyFormatError: 미등록 label 또는 root 길이 오류.
    """
    if label not in _LABEL_SET:
        raise SigningKeyFormatError(f"unregistered HKDF label {label!r}.")
    if not isinstance(root, (bytes, bytearray)) or len(root) != ROOT_KEY_BYTES:
        raise SigningKeyFormatError("root must be 32 raw bytes (call decode_root_key first).")
    hkdf = HKDF(
        algorithm=hashes.SHA256(), length=HKDF_LENGTH, salt=HKDF_SALT,
        info=label.encode("ascii"),
    )
    return hkdf.derive(bytes(root))


def derive_all(root: bytes) -> "dict[str, bytes]":
    """5 개 등록 label 의 파생 subkey 를 label→bytes 로 반환(secret — 로그/저장 금지)."""
    return {label: derive_subkey(root, label) for label in DERIVED_LABELS}


def key_id_from_root(root: bytes) -> str:
    """root 의 one-way key ID = ``base64url(SHA256("FOMS_KEY_ID_V1\\0"+root)[:16])``.

    key ID 는 root 를 되돌릴 수 없는 fingerprint 이므로 밖으로 내보내도 안전한 유일한 값이다.
    """
    if not isinstance(root, (bytes, bytearray)) or len(root) != ROOT_KEY_BYTES:
        raise SigningKeyFormatError("root must be 32 raw bytes.")
    digest = hashlib.sha256(KEY_ID_DOMAIN + bytes(root)).digest()[:KEY_ID_BYTES]
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


def key_id_from_env(env_value: str) -> str:
    """env 값을 decode 하고 key ID 를 반환(artifact 에 쓸 수 있는 유일한 값)."""
    return key_id_from_root(decode_root_key(env_value))


# --------------------------------------------------------------------------- #
# Golden vector — 알려진 root 에 대한 고정 출력. salt/label/length/order 의 우발적
# 변경은 이 vector 를 깨뜨린다. root 는 bytes(range(32)) (테스트 전용 상수, 비밀 아님).
# 파생 subkey 는 hex 로 고정하되 이것은 "알려진 테스트 root 의" 값이므로 secret 이 아니다
# (운영 root 의 subkey 는 어디에도 남기지 않는다).
# --------------------------------------------------------------------------- #
GOLDEN_VECTOR = {
    "root_b64url": "AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8",
    "derived_hex": {
        "flask-session": "2ddb43ff8df0762ce9a95d62e57a7539374f26846e158b2a0dc6130a4fe7780d",
        "wam-launch-token": "64ef3fd3ed9d6cde90d53e13c217880b6bc5b7bf6f69965f715e230a48f0cbdb",
        "wam-entry-token": "531013ad7cea9add7ccca78a8eeda348030d47decc55adc697b9b730596ec180",
        "wam-short-link": "ae580f641c11ecfd2a311ae195527339b96ccba79f729cb2f55c96b82a46b22d",
        "wam-session-token": "89925df69c560947737384164f9034e303caf783f95931d1c2f4f61f6cc65ca8",
    },
    "key_id": "2rFCxPgnSga75Qat5uzTqA",
}


def _selfcheck() -> None:
    """golden vector 를 재계산해 대조(파생 bytes 는 출력하지 않고 key ID 만 출력)."""
    root = decode_root_key(GOLDEN_VECTOR["root_b64url"])
    assert len(root) == ROOT_KEY_BYTES
    derived = derive_all(root)
    assert set(derived) == set(DERIVED_LABELS)
    for label, expected_hex in GOLDEN_VECTOR["derived_hex"].items():
        assert derived[label].hex() == expected_hex, f"golden mismatch: {label}"
    assert key_id_from_root(root) == GOLDEN_VECTOR["key_id"]
    # 잘못된 길이·미등록 label 거부.
    for bad in ("", "AAAA", base64.urlsafe_b64encode(b"\x00" * 31).rstrip(b"=").decode()):
        try:
            decode_root_key(bad)
        except SigningKeyFormatError:
            pass
        else:
            raise AssertionError(f"decode_root_key should reject {bad!r}")
    try:
        derive_subkey(root, "not-a-label")
    except SigningKeyFormatError:
        pass
    else:
        raise AssertionError("derive_subkey should reject unknown label")
    # key ID 만 출력(subkey/root 는 절대 출력 금지).
    print(f"signing_key_format selfcheck OK; golden key_id={GOLDEN_VECTOR['key_id']}")


if __name__ == "__main__":
    _selfcheck()
