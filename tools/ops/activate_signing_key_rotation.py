"""signing rotation activate CLI — ROTATION_READY→ROTATING (operation SIGNING_ROTATION_ACTIVATE, §2.1 line 243).

    python tools/ops/activate_signing_key_rotation.py \
        --rollout-artifact <ROTATION_READY all-serving artifact> \
        --expected-version <n> --expected-generation <g> \
        --approval-token-file <under-control-root>.json --apply

previous=old active, active=new(pending), pending null, previous deadline=DB now+grace 를 한
commit 에 쓴다. 기본 dry-run — ``--apply`` 일 때만 commit.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from foms.services.security.signing import activate_ops  # noqa: E402
from foms.services.security.signing.activation_cli import run_activation  # noqa: E402

OPS_APPROVAL_OPERATION_ID = "SIGNING_ROTATION_ACTIVATE"


def main(argv: "list[str] | None" = None) -> int:
    parser = argparse.ArgumentParser(description="Activate signing rotation (ROTATION_READY->ROTATING).")
    parser.add_argument("--rollout-artifact", required=True, help="ROTATION_READY all-serving artifact")
    parser.add_argument("--expected-version", type=int, required=True)
    parser.add_argument("--expected-generation", type=int, required=True)
    parser.add_argument("--approval-token-file", required=True, help="control root 아래 approval 토큰")
    parser.add_argument("--apply", action="store_true", help="전이를 commit(기본 dry-run)")
    args = parser.parse_args(argv)

    rollout_sha = activate_ops.sha256_file(args.rollout_artifact)

    def _mut(session, approver_id):
        return activate_ops.activate_rotation(
            session, prepared_rollout_artifact_sha256=rollout_sha,
            expected_version=args.expected_version, updated_by_admin_user_id=approver_id,
        )

    return run_activation(
        operation_id=OPS_APPROVAL_OPERATION_ID, phase="rotation_activate",
        artifact_path=args.rollout_artifact, expected_version=args.expected_version,
        expected_generation=args.expected_generation, token_path=args.approval_token_file,
        apply=args.apply, mutation_builder=_mut,
    )


if __name__ == "__main__":
    raise SystemExit(main())
