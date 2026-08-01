"""backfill artifact manifest·mapping·approval-scope 조립 (§7.3 line 1251-1255).

순수(비-crypto, 비-PG) artifact 조립·해시 계층:

* **mapping_sha256** = ``SHA256(RFC8785_JCS([{identity_fields,decision,target_ids,
  reason_code}] sorted by UTF-8 identity tuple))``. mapping object 에는 display text/PII 가
  0 이어야 한다(exact fields 강제).
* **manifest.json / sha.txt**: ``sha.txt`` 는 manifest raw bytes 의 lowercase SHA-256 + LF.
  payload hash 목록은 summary + audit ciphertext 만 포함하고 manifest/sha/manual/approval/
  checkpoint/export 는 제외해 **자기참조 0**.
* **approval-scope.json**: OPS DB record 가 authority 이고 Admin UI 는 이 값만 본다. exact
  schema 를 강제하며, 전체 scope 를 단일 sha256 으로 커밋해 OPS approval artifact_sha256 에
  바인딩한다(manifest/mapping/composite drift → consume 거부).

RFC 8785 JCS 는 str/int/bool/None/list/object 만 다루는 근사(ops_approval 과 동일 규약).
float 는 표현 모호성 때문에 거부한다.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

BACKFILL_APPLY_OPERATION_ID = "BACKFILL_APPLY"

# payload hash 대상 allowlist(§7.3 line 1251): summary + audit ciphertext 뿐. manual/
# manifest/sha/approval/checkpoint/export 는 목록에 없으므로 자기참조가 구조적으로 0 이다.
_PAYLOAD_HASH_NAMES = ("summary.json", "safe.csv.enc", "ambiguous.csv.enc", "unmapped.csv.enc")

_MAPPING_ENTRY_FIELDS = frozenset({"identity_fields", "decision", "target_ids", "reason_code"})

_APPROVAL_SCOPE_FIELDS = frozenset({
    "schema_version", "operation_id", "packet_id", "phase", "manifest_sha256",
    "mapping_sha256", "db_instance_id", "source_composite_sha256",
    "expected_run_row_version", "masked_counts",
})


class BackfillManifestError(RuntimeError):
    """manifest/mapping/approval-scope 조립이 계약(exact fields/PII0/직렬화)을 위반할 때."""


def _assert_json_safe(obj: Any) -> None:
    """float(및 비직렬화 타입)를 재귀 거부 — JCS 근사의 결정성 보장."""
    if isinstance(obj, float):
        raise BackfillManifestError("float values are not allowed (ambiguous JCS number form).")
    if isinstance(obj, dict):
        for k, v in obj.items():
            if not isinstance(k, str):
                raise BackfillManifestError("object keys must be strings.")
            _assert_json_safe(v)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            _assert_json_safe(v)
    elif not isinstance(obj, (str, int, bool, type(None))):
        raise BackfillManifestError(f"unsupported JCS value type: {type(obj).__name__}.")


def canonical_json_bytes(obj: Any) -> bytes:
    """RFC 8785 JCS 근사: sorted-key compact JSON UTF-8 bytes(float 거부)."""
    _assert_json_safe(obj)
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def compute_mapping_sha256(entries: list) -> str:
    """mapping 결정 목록의 canonical sha256(§7.3 line 1254).

    각 entry 는 정확히 ``{identity_fields,decision,target_ids,reason_code}`` 만 가진다
    (display text/PII 필드 삽입은 거부). UTF-8 identity tuple(identity_fields 의 canonical
    bytes)로 정렬한 뒤 JCS 직렬화해 순서 무관 결정성을 만든다.

    :raises BackfillManifestError: entry 필드 불일치, float/비직렬화 값.
    """
    if not isinstance(entries, list):
        raise BackfillManifestError("mapping entries must be a list.")
    normalized = []
    for entry in entries:
        if not isinstance(entry, dict) or set(entry.keys()) != _MAPPING_ENTRY_FIELDS:
            raise BackfillManifestError(
                f"mapping entry fields must be exactly {sorted(_MAPPING_ENTRY_FIELDS)} "
                "(no PII/display fields)."
            )
        _assert_json_safe(entry)
        normalized.append(entry)
    normalized.sort(key=lambda e: canonical_json_bytes(e["identity_fields"]))
    return hashlib.sha256(canonical_json_bytes(normalized)).hexdigest()


def manifest_bytes(manifest: dict) -> bytes:
    """manifest dict 의 canonical raw bytes(파일로 쓰는 exact 바이트, sha.txt 대상)."""
    return canonical_json_bytes(manifest)


def compute_manifest_sha256(manifest: dict) -> str:
    """manifest raw bytes 의 lowercase sha256 hex."""
    return hashlib.sha256(manifest_bytes(manifest)).hexdigest()


def sha_txt_contents(manifest: dict) -> str:
    """``sha.txt`` 파일 내용 = manifest raw bytes lowercase SHA-256 + LF(§7.3 line 1253)."""
    return compute_manifest_sha256(manifest) + "\n"


def payload_hash_targets(artifact_dir: Path) -> list:
    """artifact dir 에서 payload hash 대상 파일 목록(존재하는 것만, 정렬된 allowlist)."""
    return [artifact_dir / name for name in _PAYLOAD_HASH_NAMES if (artifact_dir / name).is_file()]


def compute_payload_hashes(artifact_dir: Path) -> dict:
    """payload 파일별 sha256 매핑(자기참조 0 — allowlist 밖 파일은 절대 포함하지 않음).

    :returns: ``{filename: sha256_hex}`` (summary/safe/ambiguous/unmapped 중 존재하는 것).
    """
    out: dict = {}
    for path in payload_hash_targets(Path(artifact_dir)):
        out[path.name] = hashlib.sha256(path.read_bytes()).hexdigest()
    return out


def build_approval_scope(
    *,
    packet_id: str,
    phase: str,
    manifest_sha256: str,
    mapping_sha256: str,
    db_instance_id: str,
    source_composite_sha256: str,
    expected_run_row_version: int,
    masked_counts: dict,
) -> dict:
    """``approval-scope.json`` exact schema dict 생성(§7.3 line 1255).

    ``masked_counts`` 는 정수 카운트만 허용한다(원문/PII 삽입 거부).

    :raises BackfillManifestError: masked_counts 에 비정수/PII 값.
    """
    if not isinstance(masked_counts, dict) or any(
        not isinstance(v, int) or isinstance(v, bool) for v in masked_counts.values()
    ):
        raise BackfillManifestError("masked_counts must map to plain integer counts (no PII).")
    scope = {
        "schema_version": 1,
        "operation_id": BACKFILL_APPLY_OPERATION_ID,
        "packet_id": packet_id,
        "phase": phase,
        "manifest_sha256": manifest_sha256,
        "mapping_sha256": mapping_sha256,
        "db_instance_id": db_instance_id,
        "source_composite_sha256": source_composite_sha256,
        "expected_run_row_version": expected_run_row_version,
        "masked_counts": masked_counts,
    }
    return scope


def compute_approval_scope_sha256(approval_scope: dict) -> str:
    """approval-scope 전체를 커밋하는 단일 sha256(OPS approval artifact_sha256 바인딩용).

    manifest/mapping/composite/expected_version 중 하나라도 drift 하면 이 해시가 바뀌어
    OPS consume 이 거부된다.

    :raises BackfillManifestError: exact fields 불일치.
    """
    if set(approval_scope.keys()) != _APPROVAL_SCOPE_FIELDS:
        raise BackfillManifestError(
            f"approval-scope fields mismatch; expected exactly {sorted(_APPROVAL_SCOPE_FIELDS)}."
        )
    return hashlib.sha256(canonical_json_bytes(approval_scope)).hexdigest()
