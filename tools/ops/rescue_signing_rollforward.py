"""signing rescue roll-forward — failed-smoke roll-forward staging (operation SIGNING_RESCUE_ROLLFORWARD, §2.1 line 237).

    python tools/ops/rescue_signing_rollforward.py \
        --rescue-deployment-artifact <fixed descendant / fresh-NEXT rescue deployment artifact> \
        --rollout-artifact <ACTIVE_RESCUE all-serving artifact> \
        --expected-version <n> --expected-generation <g> \
        --approval-token-file <under-control-root>.json --apply

post-activation smoke 실패 뒤 roll-forward 증거(rescue deployment/rollout SHA)를 기록한다. mode
는 바꾸지 않으며 known/legacy key·old image 로 되돌리지 않는다(roll-forward only). 기본
dry-run — ``--apply`` 일 때만 commit.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from foms.services.security.signing import activate_ops  # noqa: E402
from foms.services.security.signing.activation_cli import run_activation  # noqa: E402

OPS_APPROVAL_OPERATION_ID = "SIGNING_RESCUE_ROLLFORWARD"


def main(argv: "list[str] | None" = None) -> int:
    parser = argparse.ArgumentParser(description="Record signing rescue roll-forward staging.")
    parser.add_argument("--rescue-deployment-artifact", required=True, help="rescue deployment artifact")
    parser.add_argument("--rollout-artifact", required=True, help="ACTIVE_RESCUE all-serving artifact")
    parser.add_argument("--expected-version", type=int, required=True)
    parser.add_argument("--expected-generation", type=int, required=True)
    parser.add_argument("--approval-token-file", required=True, help="control root 아래 approval 토큰")
    parser.add_argument("--apply", action="store_true", help="전이를 commit(기본 dry-run)")
    args = parser.parse_args(argv)

    rescue_sha = activate_ops.sha256_file(args.rescue_deployment_artifact)
    rollout_sha = activate_ops.sha256_file(args.rollout_artifact)

    def _mut(session, approver_id):
        return activate_ops.rescue_rollforward(
            session, rescue_deployment_sha=rescue_sha, prepared_rollout_artifact_sha256=rollout_sha,
            expected_version=args.expected_version, updated_by_admin_user_id=approver_id,
        )

    return run_activation(
        operation_id=OPS_APPROVAL_OPERATION_ID, phase="rescue_rollforward",
        artifact_path=args.rollout_artifact, expected_version=args.expected_version,
        expected_generation=args.expected_generation, token_path=args.approval_token_file,
        apply=args.apply, mutation_builder=_mut,
    )


if __name__ == "__main__":
    raise SystemExit(main())
