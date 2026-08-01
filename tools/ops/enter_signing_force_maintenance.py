"""signing FORCE maintenance enter — maintenance_mode OFF→AUTH_ONLY (operation SIGNING_FORCE_ENTER, §2.1 line 235).

    python tools/ops/enter_signing_force_maintenance.py \
        --rescue-rollout-artifact <FORCE_PREPARED rescue all-serving artifact> \
        --expected-version <n> --expected-generation <g> \
        --approval-token-file <under-control-root>.json --apply

공개 auth/session/WAM issue·verify 를 503 으로 닫고 health/private readiness+PII-free
maintenance 페이지만 서빙한다(replica quiescence 는 capture_signing_quiescence 가 별도 확인).
기본 dry-run — ``--apply`` 일 때만 commit.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from foms.services.security.signing import activate_ops  # noqa: E402
from foms.services.security.signing.activation_cli import run_activation  # noqa: E402

OPS_APPROVAL_OPERATION_ID = "SIGNING_FORCE_ENTER"


def main(argv: "list[str] | None" = None) -> int:
    parser = argparse.ArgumentParser(description="Enter signing FORCE maintenance (OFF->AUTH_ONLY).")
    parser.add_argument("--rescue-rollout-artifact", required=True, help="FORCE_PREPARED rescue artifact")
    parser.add_argument("--expected-version", type=int, required=True)
    parser.add_argument("--expected-generation", type=int, required=True)
    parser.add_argument("--approval-token-file", required=True, help="control root 아래 approval 토큰")
    parser.add_argument("--apply", action="store_true", help="전이를 commit(기본 dry-run)")
    args = parser.parse_args(argv)

    rescue_sha = activate_ops.sha256_file(args.rescue_rollout_artifact)

    def _mut(session, approver_id):
        return activate_ops.enter_force_maintenance(
            session, rescue_deployment_sha=rescue_sha,
            expected_version=args.expected_version, updated_by_admin_user_id=approver_id,
        )

    return run_activation(
        operation_id=OPS_APPROVAL_OPERATION_ID, phase="force_enter",
        artifact_path=args.rescue_rollout_artifact, expected_version=args.expected_version,
        expected_generation=args.expected_generation, token_path=args.approval_token_file,
        apply=args.apply, mutation_builder=_mut,
    )


if __name__ == "__main__":
    raise SystemExit(main())
