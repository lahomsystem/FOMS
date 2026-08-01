"""channel 전역 주문 생성 DISABLE(cutoff) CLI (operation CHANNEL_CREATE_DISABLE).

    python tools/ops/channel_create_disable.py \
        --rollout-artifact <readiness json> --expected-version <flag version> \
        --approval-token-file <under-control-root>.json --apply

전역 create flag 를 ENABLED→DISABLED 로 전이하고(cutoff) ACCEPTED receipt 를 조용히 버리지 않고
PAUSED_ACCEPTED 로 보존한다(job PAUSED·유실 0). owner-only approval 토큰을 소비하며 기본 dry-run.
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
from foms.services.security.channel_order import consume, create_flag  # noqa: E402

OPS_APPROVAL_OPERATION_ID = "CHANNEL_CREATE_DISABLE"


def main(argv: "list[str] | None" = None) -> int:
    """CLI 진입점 — 전역 생성 flag 를 DISABLE(cutoff)하고 receipt 를 PAUSE 보존한다."""
    parser = argparse.ArgumentParser(description="Disable channel order creation (cutoff).")
    parser.add_argument("--rollout-artifact", required=True, help="readiness json")
    parser.add_argument("--expected-version", type=int, required=True, help="flag row version")
    parser.add_argument("--approval-token-file", required=True)
    parser.add_argument("--apply", action="store_true", help="commit the transition (default dry-run)")
    args = parser.parse_args(argv)

    control_root = root_store.resolve_control_root()
    art_sha = consume.sha256_file(args.rollout_artifact)
    scope = create_flag.build_scope(OPS_APPROVAL_OPERATION_ID, "disable", art_sha, args.expected_version)

    def _build(session, approver_id):
        return create_flag.disable(
            session, expected_version=args.expected_version, updated_by_admin_user_id=approver_id)

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
