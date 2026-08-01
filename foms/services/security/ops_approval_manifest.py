"""ops approval operation manifest 로드·seed 검증·CLI 양방향 비교 (§2.1 line 209).

``docs/harness/foms_ops_approval_operations.json`` 은 고위험 operation 의 exact SSOT 다.
OPS-APPROVAL-00 이 owner 표의 모든 operation_id 를 ``cli=null`` 로 seed 하고, 각 소비
packet 이 자기 operation 의 null 세부 필드만 채운다. 이 모듈은:

* seed 무결성(owner 표와 exact 일치, 추가/삭제/owner 변경 거부),
* manifest ↔ CLI AST inventory 양방향 비교(미등록 CLI·미구현 operation 모두 red)
를 제공한다.

고위험 token CLI 규약(AST inventory 대상):
    1. 모듈 레벨 ``OPS_APPROVAL_OPERATION_ID = "<OPERATION_ID>"`` 상수,
    2. ``--approval-token-file`` argparse 인자.
둘 다 있으면 그 CLI 는 해당 operation 의 consumer 로 등록되어야 한다.
"""
from __future__ import annotations

import ast
import json
import os
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[3]
_MANIFEST_PATH = _REPO_ROOT / "docs" / "harness" / "foms_ops_approval_operations.json"
_OPS_DIR = _REPO_ROOT / "tools" / "ops"

TOKEN_CLI_ARG = "--approval-token-file"
CLI_OPERATION_CONST = "OPS_APPROVAL_OPERATION_ID"

# owner 표 SSOT (§2.1 line 211-221). seed 는 이것과 exact 일치해야 한다.
EXPECTED_OWNER_OPERATIONS: dict[str, tuple[str, ...]] = {
    "BACKFILL-ARTIFACT-00": ("BACKFILL_APPLY", "BACKFILL_REAUTHORIZE", "BACKFILL_ARTIFACT_PURGE"),
    "CUTOVER-MODE-01": ("CUTOVER_DRAIN_BEGIN", "CUTOVER_DRAIN_ABORT", "CUTOVER_MARK"),
    "SESSION-SIGNING-STATE-00": (
        "SIGNING_CUTOVER_PREPARE", "SIGNING_ROTATION_PREPARE", "SIGNING_RECOVERY_PREPARE",
    ),
    "SESSION-SIGNING-SECRET-01": (
        "SIGNING_FORCE_ENTER", "SIGNING_CUTOVER_ACTIVATE", "SIGNING_FORCE_EXIT",
        "SIGNING_LEGACY_FINALIZE", "SIGNING_ROTATION_ACTIVATE", "SIGNING_ROTATION_FINALIZE",
        "SIGNING_COMPROMISE_ACTIVATE", "SIGNING_RESCUE_ROLLFORWARD",
    ),
    "AUTH-ACCOUNT-01": (
        "AUTH_RATE_BOOTSTRAP_PREPARE", "AUTH_RATE_BOOTSTRAP_ACTIVATE",
        "AUTH_RATE_ROTATION_PREPARE", "AUTH_RATE_ROTATION_ACTIVATE", "AUTH_RATE_ROTATION_FINALIZE",
    ),
    "CHANNEL-INBOUND-ORDER-01": (
        "CHANNEL_CREATE_ENABLE", "CHANNEL_CREATE_DISABLE", "CHANNEL_RECOVERY_CREATE",
        "CHANNEL_RECOVERY_IGNORE", "CHANNEL_RETENTION_EXTEND", "CHANNEL_KEY_ROTATION_PREPARE",
        "CHANNEL_KEY_ROTATION_ACTIVATE", "CHANNEL_KEY_ROTATION_FINALIZE",
    ),
    "WDC-LINK-FENCE-00": ("WDC_LINK_FREEZE", "WDC_LINK_ABORT", "WDC_LINK_CANONICAL"),
    "DELETE-RETENTION-01": ("DELETE_RETENTION_APPLY",),
    "OFFLINE-01": ("OFFLINE_LOCAL_RECOVERY_APPROVE",),
}

_OPERATION_FIELDS = frozenset({
    "owner_packet", "cli", "scope_schema", "artifact_source",
    "expected_version_source", "expected_generation_source", "db_mode", "consume_strategy",
})
_VALID_DB_MODES = frozenset({"SAME", "TARGET_RESERVED"})


class OpsManifestError(RuntimeError):
    """manifest seed/append/CLI 계약 위반."""


def load_operations_manifest() -> dict[str, Any]:
    """operation manifest(JSON)를 로드.

    :raises OSError: 파일 부재.
    :raises ValueError: JSON 파싱 실패.
    """
    with open(_MANIFEST_PATH, encoding="utf-8") as fh:
        return json.load(fh)


def expected_operation_owner() -> dict[str, str]:
    """operation_id → owner_packet 평면 매핑(SSOT owner 표에서 파생)."""
    out: dict[str, str] = {}
    for owner, opids in EXPECTED_OWNER_OPERATIONS.items():
        for opid in opids:
            out[opid] = owner
    return out


def assert_seed_integrity(manifest: dict[str, Any]) -> None:
    """manifest 가 owner 표와 exact 일치하고 각 operation 이 schema 완전한지 검증.

    :raises OpsManifestError: operation_id 누락/추가, owner 불일치, 필드 결손, 잘못된
        db_mode.
    """
    ops = manifest.get("operations")
    if not isinstance(ops, dict):
        raise OpsManifestError("manifest.operations must be an object.")

    expected = expected_operation_owner()
    manifest_ids = set(ops.keys())
    expected_ids = set(expected.keys())

    missing = sorted(expected_ids - manifest_ids)
    extra = sorted(manifest_ids - expected_ids)
    if missing:
        raise OpsManifestError(f"manifest is missing seeded operations: {missing}")
    if extra:
        raise OpsManifestError(f"manifest has unregistered operations (unauthorized add): {extra}")

    for opid, meta in ops.items():
        if not isinstance(meta, dict):
            raise OpsManifestError(f"operation {opid} must be an object.")
        keys = set(meta.keys())
        if keys != _OPERATION_FIELDS:
            raise OpsManifestError(
                f"operation {opid} fields mismatch; expected {sorted(_OPERATION_FIELDS)}, "
                f"got {sorted(keys)}."
            )
        if meta["owner_packet"] != expected[opid]:
            raise OpsManifestError(
                f"operation {opid} owner_packet must be {expected[opid]!r} "
                f"(got {meta['owner_packet']!r}); owner_packet is immutable."
            )
        if meta["db_mode"] not in _VALID_DB_MODES:
            raise OpsManifestError(f"operation {opid} db_mode invalid: {meta['db_mode']!r}.")


def assert_append_only(baseline: dict[str, Any], candidate: dict[str, Any]) -> None:
    """소비 packet 의 manifest 편집이 owner-only null→value append 인지 검증.

    허용: 자기 operation 의 현재 null 세부 필드(cli/scope_schema/...)를 value 로 채우기.
    금지: owner_packet/db_mode 변경, operation_id 추가/삭제, 타 packet 행 수정,
    이미 채운 값 재수정(value→다른 value).

    :raises OpsManifestError: append 규정 위반.
    """
    base_ops = baseline.get("operations", {})
    cand_ops = candidate.get("operations", {})
    if set(base_ops.keys()) != set(cand_ops.keys()):
        raise OpsManifestError("operation_id set changed (add/delete is forbidden).")
    for opid, base_meta in base_ops.items():
        cand_meta = cand_ops[opid]
        if base_meta["owner_packet"] != cand_meta["owner_packet"]:
            raise OpsManifestError(f"operation {opid} owner_packet changed (immutable).")
        if base_meta["db_mode"] != cand_meta["db_mode"]:
            raise OpsManifestError(f"operation {opid} db_mode changed (immutable).")
        for field in ("cli", "scope_schema", "artifact_source",
                      "expected_version_source", "expected_generation_source", "consume_strategy"):
            before = base_meta.get(field)
            after = cand_meta.get(field)
            if before is not None and before != after:
                raise OpsManifestError(
                    f"operation {opid} field {field} was already set; value→value edit forbidden."
                )


def _scan_cli_file(path: Path) -> str | None:
    """tools/ops 파일이 token CLI 규약을 만족하면 그 operation_id 를 반환.

    module-level ``OPS_APPROVAL_OPERATION_ID = "..."`` 상수 + ``--approval-token-file``
    문자열이 둘 다 있어야 한다. 하나만 있으면 계약 위반(예외).
    """
    source = path.read_text(encoding="utf-8")
    has_token_arg = TOKEN_CLI_ARG in source
    operation_id: str | None = None
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return None
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == CLI_OPERATION_CONST:
                    if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
                        operation_id = node.value.value
    if operation_id and not has_token_arg:
        raise OpsManifestError(
            f"{path.name} declares {CLI_OPERATION_CONST} but has no {TOKEN_CLI_ARG} argument."
        )
    if has_token_arg and not operation_id:
        # token 을 받는데 operation 을 선언하지 않은 CLI = 미등록 consumer.
        raise OpsManifestError(
            f"{path.name} accepts {TOKEN_CLI_ARG} but declares no {CLI_OPERATION_CONST}."
        )
    return operation_id


def discover_token_cli_operations() -> dict[str, str]:
    """tools/ops 를 AST 스캔해 operation_id → cli 상대경로 매핑을 만든다.

    :returns: 발견된 token CLI 매핑. 아직 소비 CLI 가 없으면 빈 dict.
    :raises OpsManifestError: 규약 위반 CLI(한쪽만 선언) 또는 중복 operation.
    """
    out: dict[str, str] = {}
    if not _OPS_DIR.is_dir():
        return out
    for path in sorted(_OPS_DIR.glob("*.py")):
        opid = _scan_cli_file(path)
        if opid is None:
            continue
        rel = os.path.relpath(path, _REPO_ROOT).replace(os.sep, "/")
        if opid in out:
            raise OpsManifestError(f"operation {opid} claimed by multiple CLIs: {out[opid]}, {rel}.")
        out[opid] = rel
    return out


def manifest_vs_cli_bidirectional(manifest: dict[str, Any]) -> dict[str, list[str]]:
    """manifest 와 CLI AST inventory 를 양방향 비교.

    :returns: ``{"unregistered_cli": [...], "unimplemented_operation": [...],
        "cli_path_mismatch": [...]}`` — 모두 비어 있어야 green.
    """
    ops = manifest.get("operations", {})
    manifest_cli = {opid: meta.get("cli") for opid, meta in ops.items() if meta.get("cli")}
    discovered = discover_token_cli_operations()

    unregistered_cli = sorted(op for op in discovered if op not in ops)
    unimplemented_operation = sorted(op for op in manifest_cli if op not in discovered)
    cli_path_mismatch = sorted(
        op for op in manifest_cli
        if op in discovered and manifest_cli[op] != discovered[op]
    )
    return {
        "unregistered_cli": unregistered_cli,
        "unimplemented_operation": unimplemented_operation,
        "cli_path_mismatch": cli_path_mismatch,
    }
