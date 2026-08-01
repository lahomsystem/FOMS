"""channel key rotation activate CLI (operation CHANNEL_KEY_ROTATION_ACTIVATE).

    python tools/ops/channel_key_rotation_activate.py \
        --rollout-artifact <all-serving readiness json> --grace-seconds 86400 \
        --expected-version <state version> --expected-generation <state generation> \
        --approval-token-file <under-control-root>.json --apply

READY→ACTIVE(첫 키 활성) 또는 ROTATION_READY→ROTATING(dual accept·grace) 전이. previous key 는
grace 동안 함께 accept 된다(기존 봉인 secret 강제 무효화 0). owner-only approval 토큰을 소비하며
기본 dry-run.
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
from foms.services.security.channel_order import consume, state_ops  # noqa: E402

OPS_APPROVAL_OPERATION_ID = "CHANNEL_KEY_ROTATION_ACTIVATE"


def main(argv: "list[str] | None" = None) -> int:
    """CLI 진입점 — pending key 를 활성화(rotation 이면 dual accept)한다."""
    parser = argparse.ArgumentParser(description="Activate channel key (bootstrap or rotation).")
    parser.add_argument("--rollout-artifact", required=True, help="all-serving readiness json")
    parser.add_argument("--grace-seconds", type=int, default=0, help="dual-accept grace (rotation)")
    parser.add_argument("--expected-version", type=int, required=True)
    parser.add_argument("--expected-generation", type=int, required=True)
    parser.add_argument("--approval-token-file", required=True)
    parser.add_argument("--apply", action="store_true", help="commit the transition (default dry-run)")
    args = parser.parse_args(argv)

    control_root = root_store.resolve_control_root()
    art_sha = consume.sha256_file(args.rollout_artifact)
    scope = state_ops.build_scope(
        OPS_APPROVAL_OPERATION_ID, "activate", art_sha,
        args.expected_version, args.expected_generation)

    def _build(session, approver_id):
        return state_ops.key_rotation_activate(
            session, grace_seconds=args.grace_seconds, prepared_rollout_artifact_sha256=art_sha,
            expected_version=args.expected_version, updated_by_admin_user_id=approver_id)

    session = sessionmaker(bind=engine)()
    try:
        result_sha = consume.consume_channel_operation(
            session, operation_id=OPS_APPROVAL_OPERATION_ID, control_root=control_root,
            token_path=args.approval_token_file, scope=scope, mutation_builder=_build)
        session.commit() if args.apply else session.rollback()
    finally:
        session.close()
    print(json.dumps({"operation": OPS_APPROVAL_OPERATION_ID, "applied": bool(args.apply),
                      "result_sha256": result_sha}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
