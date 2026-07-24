"""signing emergency recovery prepare CLI (operation SIGNING_RECOVERY_PREPARE).

    python tools/ops/prepare_signing_emergency_recovery.py \
        --next-key-artifact <inspect NEXT redacted.json> \
        --expected-consumer-sha <sha> --rescue-deployment-sha <sha> \
        --expected-version <state row_version> --expected-generation <state generation> \
        --approval-token-file <under-control-root>.json --apply

active root 손상 시 fresh NEXT rescue key 자료(pending key ID·artifact hash·rescue
deployment SHA·expected consumer SHA)를 **stage** 만 한다(mode 불변, deadline·activation
0). 실제 active=new·deadlines=now·epoch+1 activation 은 SESSION-SIGNING-SECRET-01 의
``activate_compromised_signing_key_rotation.py`` 몫이다. inspect artifact 의 NEXT key ID 를
env(``FOMS_SIGNING_KEY_NEXT``)와 대조한다. owner-only approval 토큰을 소비한다. 기본
dry-run — ``--apply`` 일 때만 commit.
"""
from __future__ import annotations

import argparse
import json
import os
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
OPS_APPROVAL_OPERATION_ID = "SIGNING_RECOVERY_PREPARE"


def main(argv: "list[str] | None" = None) -> int:
    parser = argparse.ArgumentParser(
        description="Prepare signing emergency recovery (stage fresh NEXT rescue key material).")
    parser.add_argument("--next-key-artifact", required=True, help="inspect NEXT artifact")
    parser.add_argument("--expected-consumer-sha", required=True, help="rescue consumer SHA")
    parser.add_argument("--rescue-deployment-sha", required=True, help="rescue deployment SHA")
    parser.add_argument("--expected-version", type=int, required=True, help="state row_version")
    parser.add_argument("--expected-generation", type=int, required=True, help="state generation")
    parser.add_argument("--approval-token-file", required=True, help="control root 아래 approval 토큰")
    parser.add_argument("--apply", action="store_true", help="전이를 commit(기본 dry-run)")
    args = parser.parse_args(argv)

    try:
        control_root = root_store.resolve_control_root()
    except root_store.OpsControlRootError as exc:
        raise SystemExit(f"control root error: {exc}")

    artifact = prepare_ops.read_key_artifact(args.next_key_artifact)
    artifact_sha = prepare_ops.sha256_file(args.next_key_artifact)

    next_env = os.environ.get("FOMS_SIGNING_KEY_NEXT", "").strip()
    if not next_env:
        raise SystemExit("env FOMS_SIGNING_KEY_NEXT is not set.")
    try:
        env_key_id = key_id_from_env(next_env)
    except SigningKeyFormatError as exc:
        raise SystemExit(f"FOMS_SIGNING_KEY_NEXT format error: {exc}")
    if env_key_id != artifact["key_id"]:
        raise SystemExit("NEXT env key ID does not match the inspected artifact key ID.")

    scope = prepare_ops.build_scope(
        OPS_APPROVAL_OPERATION_ID, "recovery_prepare", artifact_sha,
        args.expected_version, args.expected_generation,
    )

    def _build(session, approver_id):
        return prepare_ops.prepare_recovery(
            session,
            pending_key_id=artifact["key_id"],
            prepared_key_artifact_sha256=artifact_sha,
            rescue_deployment_sha=args.rescue_deployment_sha,
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
        "applied": bool(args.apply), "result_sha256": result_sha,
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
