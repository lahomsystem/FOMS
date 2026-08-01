"""signing legacy finalize CLI — ACTIVE→CURRENT_ONLY (operation SIGNING_LEGACY_FINALIZE, §2.1 line 243).

    python tools/ops/finalize_signing_legacy_cutover.py \
        --rollout-artifact <current-only all-serving artifact> \
        --expected-version <n> --expected-generation <g> \
        --approval-token-file <under-control-root>.json --apply

두 legacy deadline 경과+legacy env 제거(all-serving)를 확인해 ACTIVE→CURRENT_ONLY 로 전이한다.
기본 dry-run — ``--apply`` 일 때만 commit.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from foms.services.security.signing import activate_ops  # noqa: E402
from foms.services.security.signing.activation_cli import run_activation  # noqa: E402

OPS_APPROVAL_OPERATION_ID = "SIGNING_LEGACY_FINALIZE"


def main(argv: "list[str] | None" = None) -> int:
    parser = argparse.ArgumentParser(description="Finalize legacy cutover (ACTIVE->CURRENT_ONLY).")
    parser.add_argument("--rollout-artifact", required=True, help="current-only all-serving artifact")
    parser.add_argument("--expected-version", type=int, required=True)
    parser.add_argument("--expected-generation", type=int, required=True)
    parser.add_argument("--approval-token-file", required=True, help="control root 아래 approval 토큰")
    parser.add_argument("--apply", action="store_true", help="전이를 commit(기본 dry-run)")
    args = parser.parse_args(argv)

    rollout_sha = activate_ops.sha256_file(args.rollout_artifact)

    def _mut(session, approver_id):
        return activate_ops.finalize_legacy(
            session, prepared_rollout_artifact_sha256=rollout_sha,
            expected_version=args.expected_version, updated_by_admin_user_id=approver_id,
        )

    return run_activation(
        operation_id=OPS_APPROVAL_OPERATION_ID, phase="legacy_finalize",
        artifact_path=args.rollout_artifact, expected_version=args.expected_version,
        expected_generation=args.expected_generation, token_path=args.approval_token_file,
        apply=args.apply, mutation_builder=_mut,
    )


if __name__ == "__main__":
    raise SystemExit(main())
