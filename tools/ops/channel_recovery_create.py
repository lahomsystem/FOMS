"""channel receipt recovery CREATE CLI (operation CHANNEL_RECOVERY_CREATE).

    python tools/ops/channel_recovery_create.py \
        --receipt-id <id> --owner-user-id <active SALES id> --evidence-artifact <json> \
        --approval-token-file <under-control-root>.json --apply

RECOVERY_REQUIRED receipt 를 승인 후 canonical ``create_order`` 로 생성한다(1회·멱등). owner 는
활성 SALES 여야 한다(default Admin 금지). owner-only approval 토큰을 소비하며 기본 dry-run.
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
from foms.services.security.channel_order import consume, receipt_ops  # noqa: E402

OPS_APPROVAL_OPERATION_ID = "CHANNEL_RECOVERY_CREATE"


def main(argv: "list[str] | None" = None) -> int:
    """CLI 진입점 — RECOVERY_REQUIRED receipt 를 승인 후 주문 생성한다."""
    parser = argparse.ArgumentParser(description="Recovery-create an order from a stuck receipt.")
    parser.add_argument("--receipt-id", type=int, required=True)
    parser.add_argument("--owner-user-id", type=int, required=True, help="active SALES owner")
    parser.add_argument("--evidence-artifact", required=True, help="justification json")
    parser.add_argument("--approval-token-file", required=True)
    parser.add_argument("--apply", action="store_true", help="commit the transition (default dry-run)")
    args = parser.parse_args(argv)

    control_root = root_store.resolve_control_root()
    art_sha = consume.sha256_file(args.evidence_artifact)
    scope = receipt_ops.build_scope(OPS_APPROVAL_OPERATION_ID, "create", art_sha, args.receipt_id)

    def _build(session, approver_id):
        return receipt_ops.recovery_create(
            session, receipt_id=args.receipt_id, owner_user_id=args.owner_user_id,
            actor_user_id=approver_id)

    session = sessionmaker(bind=engine)()
    try:
        result_sha = consume.consume_channel_operation(
            session, operation_id=OPS_APPROVAL_OPERATION_ID, control_root=control_root,
            token_path=args.approval_token_file, scope=scope, mutation_builder=_build)
        session.commit() if args.apply else session.rollback()
    finally:
        session.close()
    print(json.dumps({"operation": OPS_APPROVAL_OPERATION_ID, "receipt_id": args.receipt_id,
                      "applied": bool(args.apply), "result_sha256": result_sha}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
