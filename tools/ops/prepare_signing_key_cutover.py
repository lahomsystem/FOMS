"""signing cutover prepare CLI — EMPTY→READY deadline-null 준비 (operation SIGNING_CUTOVER_PREPARE).

    python tools/ops/prepare_signing_key_cutover.py \
        --pending-key-artifact <inspect CURRENT redacted.json> \
        --expected-consumer-sha <sha> --legacy-audit <audit.json> \
        --expected-version <state row_version> --expected-generation <state generation> \
        --approval-token-file <under-control-root>.json --apply

inspect artifact 의 CURRENT key ID 를 CLI env(``FOMS_SIGNING_KEY_CURRENT``)의 key ID 와
대조한 뒤, pending key ID·artifact hash·global legacy mode(BRIDGE/FORCE_REAUTH)·grace·
expected consumer SHA 를 기록한 **deadline-null EMPTY→READY** 전이만 수행한다. activation
(active=pending·deadline·READY→ACTIVE)은 하지 않는다(SESSION-SIGNING-SECRET-01). owner-only
approval 토큰을 소비한다. 기본 dry-run — ``--apply`` 일 때만 commit.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from sqlalchemy.orm import sessionmaker  # noqa: E402

from db import engine  # noqa: E402
from foms.services.security import ops_control_root as root_store  # noqa: E402
from foms.services.security.signing import prepare_ops  # noqa: E402
from foms.services.security.signing.signing_key_format import (  # noqa: E402
    SigningKeyFormatError,
    key_id_from_env,
)

# 고위험 token CLI 규약(ops approval manifest AST inventory 가 스캔).
OPS_APPROVAL_OPERATION_ID = "SIGNING_CUTOVER_PREPARE"

_LEGACY_MODES = ("BRIDGE", "FORCE_REAUTH")


def _load_legacy_audit(path: str) -> "tuple[str, int]":
    """legacy audit artifact 에서 (legacy_cutover_mode, grace_seconds)를 읽는다."""
    with open(path, encoding="utf-8") as fh:
        audit = json.load(fh)
    mode = audit.get("legacy_cutover_mode")
    if mode not in _LEGACY_MODES:
        raise SystemExit(f"legacy audit legacy_cutover_mode must be one of {_LEGACY_MODES}.")
    grace = audit.get("grace_seconds")
    if not isinstance(grace, int) or grace < 0:
        raise SystemExit("legacy audit grace_seconds must be a non-negative integer.")
    return mode, grace


def main(argv: "list[str] | None" = None) -> int:
    parser = argparse.ArgumentParser(description="Prepare signing cutover (EMPTY→READY, deadline-null).")
    parser.add_argument("--pending-key-artifact", required=True, help="inspect CURRENT artifact")
    parser.add_argument("--expected-consumer-sha", required=True, help="READY bridge consumer SHA")
    parser.add_argument("--legacy-audit", required=True, help="legacy material audit artifact")
    parser.add_argument("--expected-version", type=int, required=True, help="state row_version")
    parser.add_argument("--expected-generation", type=int, required=True, help="state generation")
    parser.add_argument("--approval-token-file", required=True, help="control root 아래 approval 토큰")
    parser.add_argument("--apply", action="store_true", help="전이를 commit(기본 dry-run)")
    args = parser.parse_args(argv)

    try:
        control_root = root_store.resolve_control_root()
    except root_store.OpsControlRootError as exc:
        raise SystemExit(f"control root error: {exc}")

    artifact = prepare_ops.read_key_artifact(args.pending_key_artifact)
    artifact_sha = prepare_ops.sha256_file(args.pending_key_artifact)
    legacy_mode, grace = _load_legacy_audit(args.legacy_audit)

    # CLI env CURRENT key ID 와 artifact key ID 대조(env↔artifact 일치 강제).
    try:
        env_key_id = key_id_from_env(_require_env("FOMS_SIGNING_KEY_CURRENT"))
    except SigningKeyFormatError as exc:
        raise SystemExit(f"FOMS_SIGNING_KEY_CURRENT format error: {exc}")
    if env_key_id != artifact["key_id"]:
        raise SystemExit("CURRENT env key ID does not match the inspected artifact key ID.")

    scope = prepare_ops.build_scope(
        OPS_APPROVAL_OPERATION_ID, "cutover_prepare", artifact_sha,
        args.expected_version, args.expected_generation,
    )

    def _build(session, approver_id):
        return prepare_ops.prepare_cutover(
            session,
            pending_key_id=artifact["key_id"],
            prepared_key_artifact_sha256=artifact_sha,
            legacy_cutover_mode=legacy_mode,
            grace_seconds=grace,
            prepared_consumer_sha=args.expected_consumer_sha,
            expected_version=args.expected_version,
            updated_by_admin_user_id=approver_id,
        )

    session = sessionmaker(bind=engine)()
    try:
        result_sha = prepare_ops.consume_prepare_operation(
            session, operation_id=OPS_APPROVAL_OPERATION_ID, control_root=control_root,
            token_path=args.approval_token_file, scope=scope, mutation_builder=_build,
        )
        if args.apply:
            session.commit()
        else:
            session.rollback()
    finally:
        session.close()

    print(json.dumps({
        "operation": OPS_APPROVAL_OPERATION_ID, "pending_key_id": artifact["key_id"],
        "legacy_cutover_mode": legacy_mode, "grace_seconds": grace,
        "applied": bool(args.apply), "result_sha256": result_sha,
    }, ensure_ascii=False))
    return 0


def _require_env(name: str) -> str:
    import os
    value = os.environ.get(name, "").strip()
    if not value:
        raise SystemExit(f"env {name} is not set.")
    return value


if __name__ == "__main__":
    raise SystemExit(main())
