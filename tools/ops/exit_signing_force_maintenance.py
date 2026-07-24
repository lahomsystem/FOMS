"""signing FORCE maintenance exit — maintenance_mode AUTH_ONLY→OFF (operation SIGNING_FORCE_EXIT, §2.1 line 235).

    python tools/ops/exit_signing_force_maintenance.py \
        --smoke-artifact <private current-key cookie/WAM smoke artifact> \
        --expected-version <n> --expected-generation <g> \
        --approval-token-file <under-control-root>.json --apply

private current-key smoke green 뒤 정상 업무를 복구한다(smoke 전 OFF 금지). 기본 dry-run —
``--apply`` 일 때만 commit.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from foms.services.security.signing import activate_ops  # noqa: E402
from foms.services.security.signing.activation_cli import run_activation  # noqa: E402

OPS_APPROVAL_OPERATION_ID = "SIGNING_FORCE_EXIT"


def main(argv: "list[str] | None" = None) -> int:
    parser = argparse.ArgumentParser(description="Exit signing FORCE maintenance (AUTH_ONLY->OFF).")
    parser.add_argument("--smoke-artifact", required=True, help="private current-key smoke artifact")
    parser.add_argument("--expected-version", type=int, required=True)
    parser.add_argument("--expected-generation", type=int, required=True)
    parser.add_argument("--approval-token-file", required=True, help="control root 아래 approval 토큰")
    parser.add_argument("--apply", action="store_true", help="전이를 commit(기본 dry-run)")
    args = parser.parse_args(argv)

    smoke_sha = activate_ops.sha256_file(args.smoke_artifact)

    def _mut(session, approver_id):
        return activate_ops.exit_force_maintenance(
            session, smoke_artifact_sha256=smoke_sha,
            expected_version=args.expected_version, updated_by_admin_user_id=approver_id,
        )

    return run_activation(
        operation_id=OPS_APPROVAL_OPERATION_ID, phase="force_exit",
        artifact_path=args.smoke_artifact, expected_version=args.expected_version,
        expected_generation=args.expected_generation, token_path=args.approval_token_file,
        apply=args.apply, mutation_builder=_mut,
    )


if __name__ == "__main__":
    raise SystemExit(main())
