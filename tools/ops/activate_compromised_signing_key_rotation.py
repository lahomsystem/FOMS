"""compromised signing key emergency rotation activate (operation SIGNING_COMPROMISE_ACTIVATE, §2.1 line 245).

    python tools/ops/activate_compromised_signing_key_rotation.py \
        --rollout-artifact <active+NEXT rescue all-serving artifact> \
        --quiescence-artifact <30s counters0 quiescence artifact> \
        --expected-version <n> --expected-generation <g> \
        --approval-token-file <under-control-root>.json --apply

active=new(fresh NEXT), previous/pending null, 모든 old/legacy deadline=DB now, epoch+1, WAM
cutoff=now 을 한 commit 에 쓴다(compromised verify/old rollback 0). maintenance 는 유지되며
private current smoke 뒤 exit 로 OFF 한다. 기본 dry-run — ``--apply`` 일 때만 commit.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from foms.services.security.signing import activate_ops  # noqa: E402
from foms.services.security.signing.activation_cli import run_activation  # noqa: E402

OPS_APPROVAL_OPERATION_ID = "SIGNING_COMPROMISE_ACTIVATE"


def main(argv: "list[str] | None" = None) -> int:
    parser = argparse.ArgumentParser(description="Activate compromised-key emergency rotation.")
    parser.add_argument("--rollout-artifact", required=True, help="active+NEXT rescue all-serving artifact")
    parser.add_argument("--quiescence-artifact", required=True, help="30s counters0 quiescence artifact")
    parser.add_argument("--expected-version", type=int, required=True)
    parser.add_argument("--expected-generation", type=int, required=True)
    parser.add_argument("--approval-token-file", required=True, help="control root 아래 approval 토큰")
    parser.add_argument("--apply", action="store_true", help="전이를 commit(기본 dry-run)")
    args = parser.parse_args(argv)

    rollout_sha = activate_ops.sha256_file(args.rollout_artifact)
    quiescence_sha = activate_ops.sha256_file(args.quiescence_artifact)

    def _mut(session, approver_id):
        return activate_ops.activate_compromise(
            session, prepared_rollout_artifact_sha256=rollout_sha,
            quiescence_artifact_sha256=quiescence_sha,
            expected_version=args.expected_version, updated_by_admin_user_id=approver_id,
        )

    return run_activation(
        operation_id=OPS_APPROVAL_OPERATION_ID, phase="compromise_activate",
        artifact_path=args.rollout_artifact, expected_version=args.expected_version,
        expected_generation=args.expected_generation, token_path=args.approval_token_file,
        apply=args.apply, mutation_builder=_mut,
    )


if __name__ == "__main__":
    raise SystemExit(main())
