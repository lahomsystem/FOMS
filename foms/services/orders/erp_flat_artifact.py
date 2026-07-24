"""STARTUP-BACKFILL-01 — 암호화 audit artifact 조립·검증(DPAPI + AES-256-GCM).

:mod:`~foms.services.orders.erp_flat_audit` 의 read-only 분류 결과를 BACKFILL 공용 crypto/
manifest/artifact_root 프리미티브(import 전용)로 **암호화 artifact** 로 직렬화하고, backfill
apply 가 그것을 검증·복호화해 SAFE 대상 목록을 복원한다. plaintext CSV·raw data key 는
디스크/DB/argv 에 남기지 않는다(repo/profile plaintext 금지).

artifact 파일(모두 ``artifact_dir`` 아래):

* ``key-envelope.json`` — run 별 AES data key 를 DPAPI CurrentUser 로 wrap.
* ``safe.csv.enc`` / ``ambiguous.csv.enc`` — CSV(order_id/사유/컬럼명만·PII 0)를 AES-256-GCM
  으로 암호화. AAD 가 packet/phase/relative_path/db/source_fingerprint/column_schema 를 바인딩.
* ``manifest.json`` / ``sha.txt`` — run identity manifest raw bytes + 그 sha256(무결성).
* ``approval-scope.json`` — OPS approval 이 커밋하는 exact scope(hash·정수 카운트만).
* ``summary.json`` — 사람이 읽는 masked 카운트(PII 0).
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from foms.services.datetime_kst import now_utc_naive
from foms.services.orders.erp_flat_audit import (
    PACKET_ID,
    PHASE,
    AuditReport,
    ambiguous_csv,
    column_schema_sha256,
    parse_safe_csv,
    safe_csv,
)
from foms.services.security.backfill import crypto, manifest

KEY_ENVELOPE_FILE = "key-envelope.json"
SAFE_ENC_FILE = "safe.csv.enc"
AMBIGUOUS_ENC_FILE = "ambiguous.csv.enc"
MANIFEST_FILE = "manifest.json"
SHA_FILE = "sha.txt"
APPROVAL_SCOPE_FILE = "approval-scope.json"
SUMMARY_FILE = "summary.json"


class ArtifactError(RuntimeError):
    """artifact 조립/검증 계약 위반(무결성·바인딩 실패)."""


@dataclass(frozen=True)
class LoadedArtifact:
    """복호화·검증된 artifact 의 apply 입력.

    Attributes:
        safe_targets: SAFE 주문 ``(order_id, expected_src_sha)`` 목록.
        manifest_sha256: run identity manifest sha(approval-scope 바인딩).
        mapping_sha256: run identity mapping sha.
        approval_scope: OPS approval 이 커밋하는 exact scope dict.
        masked_counts: 정수 카운트(PII 0).
    """

    safe_targets: List[Tuple[int, str]]
    manifest_sha256: str
    mapping_sha256: str
    approval_scope: Dict[str, Any]
    masked_counts: Dict[str, int]


def write_audit_artifact(
    artifact_dir: Path,
    report: AuditReport,
    *,
    db_instance_id: str,
    expected_run_row_version: int = 1,
    now: Optional[Any] = None,
) -> Dict[str, str]:
    """audit 결과를 암호화 artifact 로 ``artifact_dir`` 에 기록한다(디렉터리 존재 전제).

    Args:
        artifact_dir: artifact 를 쓸 디렉터리(호출자가 protected root 하위로 검증·생성).
        report: :func:`~foms.services.orders.erp_flat_audit.audit_orders` 결과.
        db_instance_id: target DB 식별자(entropy·AAD 바인딩).
        expected_run_row_version: apply 시 소비할 run row_version(fresh run=1).
        now: 결정적 타임스탬프(테스트 주입).

    Returns:
        ``{"manifest_sha256", "mapping_sha256", "source_composite_sha256"}``.
    """
    artifact_dir = Path(artifact_dir)
    artifact_dir_id = artifact_dir.name
    col_schema = column_schema_sha256()
    src_composite = report.source_composite_sha256()

    envelope, data_key = crypto.create_key_envelope(
        packet_id=PACKET_ID,
        phase=PHASE,
        db_instance_id=db_instance_id,
        artifact_dir_id=artifact_dir_id,
        now=now,
    )
    key_id = envelope["key_id"]

    for relative_path, plaintext in (
        (SAFE_ENC_FILE, safe_csv(report)),
        (AMBIGUOUS_ENC_FILE, ambiguous_csv(report)),
    ):
        payload_env = crypto.encrypt_payload(
            plaintext.encode("utf-8"),
            data_key,
            key_id=key_id,
            packet_id=PACKET_ID,
            phase=PHASE,
            relative_path=relative_path,
            db_instance_id=db_instance_id,
            source_fingerprint=src_composite,
            column_schema_sha256=col_schema,
        )
        _write_json(artifact_dir / relative_path, payload_env)

    manifest_dict = report.manifest_dict()
    (artifact_dir / MANIFEST_FILE).write_bytes(manifest.manifest_bytes(manifest_dict))
    (artifact_dir / SHA_FILE).write_text(manifest.sha_txt_contents(manifest_dict), encoding="utf-8")

    manifest_sha = manifest.compute_manifest_sha256(manifest_dict)
    mapping_sha = report.mapping_sha256()
    approval_scope = manifest.build_approval_scope(
        packet_id=PACKET_ID,
        phase=PHASE,
        manifest_sha256=manifest_sha,
        mapping_sha256=mapping_sha,
        db_instance_id=db_instance_id,
        source_composite_sha256=src_composite,
        expected_run_row_version=expected_run_row_version,
        masked_counts=report.masked_counts(),
    )
    _write_json(artifact_dir / APPROVAL_SCOPE_FILE, approval_scope)

    _write_json(
        artifact_dir / SUMMARY_FILE,
        {
            "packet_id": PACKET_ID,
            "phase": PHASE,
            "db_instance_id": db_instance_id,
            "column_schema_sha256": col_schema,
            "source_composite_sha256": src_composite,
            "masked_counts": report.masked_counts(),
            "generated_at": (now or now_utc_naive()).isoformat(),
        },
    )
    _write_json(artifact_dir / KEY_ENVELOPE_FILE, envelope)

    return {
        "manifest_sha256": manifest_sha,
        "mapping_sha256": mapping_sha,
        "source_composite_sha256": src_composite,
    }


def load_audit_artifact(artifact_dir: Path, *, db_instance_id: str) -> LoadedArtifact:
    """artifact 무결성을 검증하고 SAFE 대상 + approval-scope 를 복원한다(apply 입력).

    Args:
        artifact_dir: audit 가 기록한 artifact 디렉터리.
        db_instance_id: target DB 식별자(envelope entropy·AAD 재계산).

    Returns:
        :class:`LoadedArtifact`.

    Raises:
        ArtifactError: manifest sha 불일치(변조) 또는 approval-scope 바인딩 불일치.
        crypto.BackfillCryptoError: DPAPI unwrap/GCM 인증 실패(다른 host/변조/파라미터 drift).
    """
    artifact_dir = Path(artifact_dir)
    artifact_dir_id = artifact_dir.name

    manifest_bytes = (artifact_dir / MANIFEST_FILE).read_bytes()
    sha_txt = (artifact_dir / SHA_FILE).read_text(encoding="utf-8").strip()
    import hashlib

    disk_manifest_sha = hashlib.sha256(manifest_bytes).hexdigest()
    if sha_txt != disk_manifest_sha:
        raise ArtifactError("sha.txt does not match manifest.json bytes (tampered artifact).")

    manifest_dict = json.loads(manifest_bytes.decode("utf-8"))
    col_schema = manifest_dict.get("column_schema_sha256")

    approval_scope = json.loads((artifact_dir / APPROVAL_SCOPE_FILE).read_text(encoding="utf-8"))
    if approval_scope.get("manifest_sha256") != disk_manifest_sha:
        raise ArtifactError("approval-scope manifest_sha256 does not bind on-disk manifest.")
    src_composite = approval_scope["source_composite_sha256"]

    envelope = json.loads((artifact_dir / KEY_ENVELOPE_FILE).read_text(encoding="utf-8"))
    data_key = crypto.load_data_key(
        envelope,
        packet_id=PACKET_ID,
        phase=PHASE,
        db_instance_id=db_instance_id,
        artifact_dir_id=artifact_dir_id,
    )

    safe_env = json.loads((artifact_dir / SAFE_ENC_FILE).read_text(encoding="utf-8"))
    safe_plaintext = crypto.decrypt_payload(
        safe_env,
        data_key,
        packet_id=PACKET_ID,
        phase=PHASE,
        relative_path=SAFE_ENC_FILE,
        db_instance_id=db_instance_id,
        source_fingerprint=src_composite,
        column_schema_sha256=col_schema,
    ).decode("utf-8")

    return LoadedArtifact(
        safe_targets=parse_safe_csv(safe_plaintext),
        manifest_sha256=approval_scope["manifest_sha256"],
        mapping_sha256=approval_scope["mapping_sha256"],
        approval_scope=approval_scope,
        masked_counts=dict(approval_scope.get("masked_counts") or {}),
    )


def _write_json(path: Path, obj: Any) -> None:
    """dict 를 UTF-8 JSON 으로 기록(안정적 key 순서)."""
    path.write_text(json.dumps(obj, ensure_ascii=False, sort_keys=True), encoding="utf-8")


__all__ = [
    "ArtifactError",
    "LoadedArtifact",
    "KEY_ENVELOPE_FILE",
    "SAFE_ENC_FILE",
    "AMBIGUOUS_ENC_FILE",
    "MANIFEST_FILE",
    "SHA_FILE",
    "APPROVAL_SCOPE_FILE",
    "SUMMARY_FILE",
    "write_audit_artifact",
    "load_audit_artifact",
]
