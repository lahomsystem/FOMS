"""BACKFILL-ARTIFACT-00 순수(비-PG) 계약 테스트: root guard · DPAPI · AES-GCM · manifest.

PG 불필요. DPAPI round-trip 은 Windows 에서만 실행하고 비-Windows 는 skip 한다(이 plan 의
exact provider 는 Windows DPAPI CurrentUser v1 뿐이며 비-Windows 는 fail-closed). 커밋
파일에는 비밀번호/secret 을 넣지 않는다.
"""
from __future__ import annotations

import copy
import json
import os
import tempfile
from pathlib import Path

import pytest

from foms.services.security.backfill import artifact_root, crypto, manifest

_WINDOWS = os.name == "nt"
_dpapi_only = pytest.mark.skipif(not _WINDOWS, reason="DPAPI is Windows-only (other OS fail-closed)")

_KW = dict(packet_id="ASSIGN-PKT", phase="ASSIGNMENT", db_instance_id="db-1", artifact_dir_id="dir-1")
_AAD = dict(
    packet_id="ASSIGN-PKT", phase="ASSIGNMENT", relative_path="safe.csv.enc",
    db_instance_id="db-1", source_fingerprint="fp-src", column_schema_sha256="c" * 64,
)


# --------------------------------------------------------------------------- #
# 1. artifact root guard — fail-closed 증명
# --------------------------------------------------------------------------- #
def test_root_not_set_fail_closed(monkeypatch):
    monkeypatch.delenv(artifact_root.ENV_VAR, raising=False)
    with pytest.raises(artifact_root.ArtifactRootError):
        artifact_root.resolve_artifact_root()


def test_root_non_windows_fail_closed(monkeypatch):
    """Linux/다른 host 는 별도 KEK spec 전 fail-closed."""
    monkeypatch.setenv(artifact_root.ENV_VAR, os.path.abspath(os.sep + "some_root"))
    monkeypatch.setattr(artifact_root.os, "name", "posix")
    with pytest.raises(artifact_root.ArtifactRootError):
        artifact_root.resolve_artifact_root()


def test_root_relative_path_rejected(monkeypatch):
    monkeypatch.setenv(artifact_root.ENV_VAR, "relative/artifact/root")
    monkeypatch.setattr(artifact_root.os, "name", "nt")
    with pytest.raises(artifact_root.ArtifactRootError):
        artifact_root.resolve_artifact_root()


def test_root_repo_internal_rejected():
    repo_internal = artifact_root._repo_root() / "docs"
    with pytest.raises(artifact_root.ArtifactRootError):
        artifact_root._assert_outside_repo_profile_sync(repo_internal)


def test_root_onedrive_marker_rejected():
    onedrive_path = Path(os.path.abspath(os.sep + "OneDriveRoot" + os.sep + "artifacts"))
    with pytest.raises(artifact_root.ArtifactRootError):
        artifact_root._assert_outside_repo_profile_sync(onedrive_path)


def test_root_user_profile_rejected(monkeypatch):
    profile = os.environ.get("USERPROFILE") or os.environ.get("HOME")
    if not profile:
        pytest.skip("no user profile env on this host")
    under_profile = Path(profile) / "foms_artifacts_should_be_refused"
    with pytest.raises(artifact_root.ArtifactRootError):
        artifact_root._assert_outside_repo_profile_sync(under_profile)


@_dpapi_only
def test_root_network_share_rejected():
    with pytest.raises(artifact_root.ArtifactRootError):
        artifact_root._assert_outside_repo_profile_sync(Path(r"\\server\share\artifacts"))


def test_root_reparse_point_rejected(monkeypatch):
    """reparse-point(symlink/junction) 하위는 거부(가드가 판정 헬퍼를 실제로 참조)."""
    monkeypatch.setattr(artifact_root, "_is_reparse_point", lambda p: True)
    benign = Path(os.path.abspath(os.sep + "clean_root" + os.sep + "artifacts"))
    with pytest.raises(artifact_root.ArtifactRootError):
        artifact_root._assert_outside_repo_profile_sync(benign)


@_dpapi_only
def test_root_valid_smoke(monkeypatch):
    """repo/profile/sync/network/reparse 밖의 실존 dir 는 통과(ACL 검증 제외)."""
    base = tempfile.mkdtemp(dir="C:/tmp", prefix="foms_artifact_root_")
    try:
        monkeypatch.setenv(artifact_root.ENV_VAR, base)
        resolved = artifact_root.resolve_artifact_root(require_acl=False)
        assert resolved == Path(base).resolve()
    finally:
        os.rmdir(base)


# --------------------------------------------------------------------------- #
# 2. DPAPI key-envelope (Windows only)
# --------------------------------------------------------------------------- #
@_dpapi_only
def test_dpapi_key_envelope_round_trip():
    envelope, data_key = crypto.create_key_envelope(**_KW)
    assert envelope["provider"] == crypto.DPAPI_PROVIDER
    assert envelope["version"] == 1
    assert len(data_key) == 32
    # 동일 account/host/params → 복원.
    restored = crypto.load_data_key(envelope, **_KW)
    assert restored == data_key
    # raw data key/entropy 는 envelope 에 평문으로 없음.
    blob = json.dumps(envelope)
    assert data_key.hex() not in blob
    assert "wrapped_data_key_b64url" in envelope and "entropy_sha256" in envelope


@_dpapi_only
def test_dpapi_provider_mismatch_rejected():
    envelope, _ = crypto.create_key_envelope(**_KW)
    bad = copy.deepcopy(envelope)
    bad["provider"] = "SOME_OTHER_PROVIDER"
    with pytest.raises(crypto.BackfillCryptoError):
        crypto.load_data_key(bad, **_KW)


@_dpapi_only
def test_dpapi_entropy_param_drift_rejected():
    envelope, _ = crypto.create_key_envelope(**_KW)
    drift = dict(_KW, phase="DIFFERENT_PHASE")
    with pytest.raises(crypto.BackfillCryptoError):
        crypto.load_data_key(envelope, **drift)


@_dpapi_only
def test_dpapi_tampered_wrapped_key_rejected():
    envelope, _ = crypto.create_key_envelope(**_KW)
    bad = copy.deepcopy(envelope)
    raw = crypto._b64url_decode(bad["wrapped_data_key_b64url"])
    flipped = bytes([raw[0] ^ 0xFF]) + raw[1:]
    bad["wrapped_data_key_b64url"] = crypto._b64url(flipped)
    with pytest.raises(crypto.BackfillCryptoError):
        crypto.load_data_key(bad, **_KW)


def test_dpapi_non_windows_fail_closed(monkeypatch):
    monkeypatch.setattr(crypto.os, "name", "posix")
    with pytest.raises(crypto.BackfillCryptoError):
        crypto.create_key_envelope(**_KW)


# --------------------------------------------------------------------------- #
# 3. AES-256-GCM payload envelope + AAD
# --------------------------------------------------------------------------- #
def test_aes_gcm_round_trip():
    key = os.urandom(32)
    env = crypto.encrypt_payload(b"a,b,c\n1,2,3\n", key, key_id="kid", **_AAD)
    assert env["alg"] == "AES-256-GCM" and env["version"] == 1
    assert crypto.decrypt_payload(env, key, **_AAD) == b"a,b,c\n1,2,3\n"


def test_aes_gcm_aad_mismatch_rejected():
    key = os.urandom(32)
    env = crypto.encrypt_payload(b"payload", key, key_id="kid", **_AAD)
    relocated = dict(_AAD, relative_path="ambiguous.csv.enc")
    with pytest.raises(crypto.BackfillCryptoError):
        crypto.decrypt_payload(env, key, **relocated)


def test_aes_gcm_nonce_tamper_rejected():
    key = os.urandom(32)
    env = crypto.encrypt_payload(b"payload", key, key_id="kid", **_AAD)
    tampered = copy.deepcopy(env)
    tampered["nonce_b64url"] = crypto._b64url(b"\x00" * 12)
    with pytest.raises(crypto.BackfillCryptoError):
        crypto.decrypt_payload(tampered, key, **_AAD)


def test_aes_gcm_wrong_key_rejected():
    env = crypto.encrypt_payload(b"payload", os.urandom(32), key_id="kid", **_AAD)
    with pytest.raises(crypto.BackfillCryptoError):
        crypto.decrypt_payload(env, os.urandom(32), **_AAD)


# --------------------------------------------------------------------------- #
# 4. manifest / sha.txt — payload hash 자기참조 0
# --------------------------------------------------------------------------- #
def test_payload_hash_self_reference_zero(tmp_path):
    # allowlist 대상 + 제외 대상 파일을 모두 만든다.
    (tmp_path / "summary.json").write_bytes(b'{"counts":1}')
    (tmp_path / "safe.csv.enc").write_bytes(b"cipher-safe")
    (tmp_path / "ambiguous.csv.enc").write_bytes(b"cipher-amb")
    (tmp_path / "manifest.json").write_bytes(b'{"schema":1}')
    (tmp_path / "sha.txt").write_bytes(b"deadbeef\n")
    (tmp_path / "manual.csv.enc").write_bytes(b"cipher-manual")
    (tmp_path / "approval-scope.json").write_bytes(b'{"schema_version":1}')

    hashes = manifest.compute_payload_hashes(tmp_path)
    assert set(hashes.keys()) == {"summary.json", "safe.csv.enc", "ambiguous.csv.enc"}
    # 자기참조 0: manifest/sha/manual/approval 은 절대 hash 목록에 없다.
    for excluded in ("manifest.json", "sha.txt", "manual.csv.enc", "approval-scope.json"):
        assert excluded not in hashes


def test_sha_txt_matches_manifest_raw_bytes():
    m = {"schema_version": 1, "tool_version": "1.0.0", "db_instance_id": "db-1"}
    import hashlib
    expected = hashlib.sha256(manifest.manifest_bytes(m)).hexdigest()
    assert manifest.sha_txt_contents(m) == expected + "\n"
    assert manifest.compute_manifest_sha256(m) == expected


# --------------------------------------------------------------------------- #
# 5. mapping_sha256 — 결정성 · PII 0
# --------------------------------------------------------------------------- #
def test_mapping_sha256_order_independent():
    a = [
        {"identity_fields": {"order_id": 2}, "decision": "safe", "target_ids": [9], "reason_code": "MATCH"},
        {"identity_fields": {"order_id": 1}, "decision": "safe", "target_ids": [8], "reason_code": "MATCH"},
    ]
    b = list(reversed(a))
    assert manifest.compute_mapping_sha256(a) == manifest.compute_mapping_sha256(b)


def test_mapping_rejects_pii_field():
    with pytest.raises(manifest.BackfillManifestError):
        manifest.compute_mapping_sha256([
            {"identity_fields": {"order_id": 1}, "decision": "safe", "target_ids": [1],
             "reason_code": "R", "customer_name": "홍길동"},
        ])


def test_mapping_rejects_float():
    with pytest.raises(manifest.BackfillManifestError):
        manifest.compute_mapping_sha256([
            {"identity_fields": {"amount": 1.5}, "decision": "safe", "target_ids": [1], "reason_code": "R"},
        ])


# --------------------------------------------------------------------------- #
# 6. approval-scope.json — exact schema
# --------------------------------------------------------------------------- #
def test_approval_scope_exact_schema_and_sha():
    scope = manifest.build_approval_scope(
        packet_id="ASSIGN-PKT", phase="ASSIGNMENT", manifest_sha256="m" * 64,
        mapping_sha256="p" * 64, db_instance_id="db-1", source_composite_sha256="s" * 64,
        expected_run_row_version=1, masked_counts={"safe": 10, "ambiguous": 2},
    )
    assert scope["operation_id"] == "BACKFILL_APPLY"
    assert set(scope.keys()) == manifest._APPROVAL_SCOPE_FIELDS
    # 전체 scope 를 커밋하는 단일 해시(drift 시 값 변화).
    base = manifest.compute_approval_scope_sha256(scope)
    drifted = dict(scope, mapping_sha256="q" * 64)
    assert manifest.compute_approval_scope_sha256(drifted) != base


def test_approval_scope_rejects_pii_counts():
    with pytest.raises(manifest.BackfillManifestError):
        manifest.build_approval_scope(
            packet_id="P", phase="ASSIGNMENT", manifest_sha256="m" * 64, mapping_sha256="p" * 64,
            db_instance_id="db-1", source_composite_sha256="s" * 64, expected_run_row_version=1,
            masked_counts={"leak": "고객명"},
        )
