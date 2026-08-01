"""SESSION-SIGNING-STATE-00 pure 계약 테스트: signing_key_format golden + 거부 규칙.

PG 불필요(순수). golden vector(env decode·5 파생 label·key ID 고정), 잘못된 길이/미등록
label 거부, artifact 에 비밀값 0(key ID/encoding only)을 검증한다. 커밋 파일에 root/subkey/
secret 값은 넣지 않는다(알려진 테스트 root 의 파생 hex 는 module GOLDEN_VECTOR 가 소유).
"""
from __future__ import annotations

import base64

import pytest

from foms.services.security.signing import signing_key_format as fmt


# --------------------------------------------------------------------------- #
# 1. golden vector — env decode · 5 파생 label · key ID 고정
# --------------------------------------------------------------------------- #
def test_golden_vector_decode_derive_key_id():
    gv = fmt.GOLDEN_VECTOR
    root = fmt.decode_root_key(gv["root_b64url"])
    assert len(root) == fmt.ROOT_KEY_BYTES == 32

    derived = fmt.derive_all(root)
    assert set(derived) == set(fmt.DERIVED_LABELS)
    assert fmt.DERIVED_LABELS == (
        "flask-session", "wam-launch-token", "wam-entry-token",
        "wam-short-link", "wam-session-token",
    )
    for label, expected_hex in gv["derived_hex"].items():
        assert derived[label].hex() == expected_hex, f"golden mismatch: {label}"
        assert len(derived[label]) == fmt.HKDF_LENGTH == 32

    assert fmt.key_id_from_root(root) == gv["key_id"]
    assert fmt.key_id_from_env(gv["root_b64url"]) == gv["key_id"]


def test_module_selfcheck_runs():
    fmt._selfcheck()  # no raise (재계산 대조 통과)


def test_derivation_is_deterministic():
    root = fmt.decode_root_key(fmt.GOLDEN_VECTOR["root_b64url"])
    assert fmt.derive_subkey(root, "flask-session") == fmt.derive_subkey(root, "flask-session")


# --------------------------------------------------------------------------- #
# 2. 잘못된 길이/인코딩 거부
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("bad", [
    "",                                                    # 빈 값
    base64.urlsafe_b64encode(b"\x00" * 31).rstrip(b"=").decode(),  # 31 bytes
    base64.urlsafe_b64encode(b"\x00" * 33).rstrip(b"=").decode(),  # 33 bytes
])
def test_decode_rejects_wrong_length(bad):
    with pytest.raises(fmt.SigningKeyFormatError):
        fmt.decode_root_key(bad)


@pytest.mark.parametrize("bad", [
    "AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8=",  # padding 포함
    " AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8",  # 선행 공백
    "AAECAwQFBgcICQoLDA0ODxAREhMUF+YXGBkaGxwdHh8",   # 표준(비 url) 알파벳 '+'
])
def test_decode_rejects_non_canonical_encoding(bad):
    with pytest.raises(fmt.SigningKeyFormatError):
        fmt.decode_root_key(bad)


# --------------------------------------------------------------------------- #
# 3. 미등록 label 거부
# --------------------------------------------------------------------------- #
def test_derive_rejects_unregistered_label():
    root = fmt.decode_root_key(fmt.GOLDEN_VECTOR["root_b64url"])
    with pytest.raises(fmt.SigningKeyFormatError):
        fmt.derive_subkey(root, "not-a-label")
    with pytest.raises(fmt.SigningKeyFormatError):
        fmt.derive_subkey(root, "flask-session-typo")


def test_derive_rejects_bad_root_length():
    with pytest.raises(fmt.SigningKeyFormatError):
        fmt.derive_subkey(b"\x00" * 31, "flask-session")


# --------------------------------------------------------------------------- #
# 4. 비밀값 0 — surface 되는 값은 key ID/encoding 뿐
# --------------------------------------------------------------------------- #
def test_key_id_does_not_reveal_root():
    root = fmt.decode_root_key(fmt.GOLDEN_VECTOR["root_b64url"])
    kid = fmt.key_id_from_root(root)
    # key ID 는 16 byte fingerprint 의 base64url(22 char), root/subkey hex 를 포함하지 않는다.
    assert root.hex() not in kid
    for sub in fmt.derive_all(root).values():
        assert sub.hex() not in kid
    assert len(base64.urlsafe_b64decode(kid + "==")) == fmt.KEY_ID_BYTES == 16


def test_inspect_artifact_carries_no_secret():
    from tools.ops.inspect_signing_key_slot import build_artifact
    root = fmt.decode_root_key(fmt.GOLDEN_VECTOR["root_b64url"])
    art = build_artifact("CURRENT", fmt.GOLDEN_VECTOR["root_b64url"])
    assert art["key_id"] == fmt.GOLDEN_VECTOR["key_id"]
    assert set(art) == {"schema_version", "slot", "key_id", "encoding", "byte_length", "captured_at"}
    blob = repr(art)
    assert root.hex() not in blob
    assert fmt.GOLDEN_VECTOR["root_b64url"] not in blob  # raw root b64 는 artifact 에 없다
    for sub in fmt.derive_all(root).values():
        assert sub.hex() not in blob


def test_prepare_artifact_reader_rejects_secret_fields(tmp_path):
    import json

    from foms.services.security.signing import prepare_ops

    good = tmp_path / "good.json"
    good.write_text(json.dumps({
        "schema_version": 1, "slot": "CURRENT", "key_id": "kid",
        "encoding": "base64url-nopad", "byte_length": 32,
    }), encoding="utf-8")
    assert prepare_ops.read_key_artifact(good)["key_id"] == "kid"

    leaky = tmp_path / "leaky.json"
    leaky.write_text(json.dumps({
        "schema_version": 1, "slot": "CURRENT", "key_id": "kid",
        "encoding": "base64url-nopad", "byte_length": 32, "root": "deadbeef",
    }), encoding="utf-8")
    with pytest.raises(prepare_ops.SigningPrepareError):
        prepare_ops.read_key_artifact(leaky)
