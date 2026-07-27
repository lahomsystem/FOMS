"""channel receipt recovery IGNORE CLI (operation CHANNEL_RECOVERY_IGNORE).

    python tools/ops/channel_recovery_ignore.py \
        --receipt-id <id> --evidence-artifact <json> \
        --approval-token-file <under-control-root>.json --apply

RECOVERY_REQUIRED receipt 를 승인 후 IGNORED 로 전이한다. legal hold 가 걸린 receipt 는 거부한다
(조용한 clear 금지). owner-only approval 토큰을 소비하며 기본 dry-run.
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

OPS_APPROVAL_OPERATION_ID = "CHANNEL_RECOVERY_IGNORE"


def main(argv: "list[str] | None" = None) -> int:
    """CLI 진입점 — RECOVERY_REQUIRED receipt 를 승인 후 IGNORED 로 전이한다."""
    parser = argparse.ArgumentParser(description="Recovery-ignore a stuck receipt (approved).")
    parser.add_argument("--receipt-id", type=int, required=True)
    parser.add_argument("--evidence-artifact", required=True, help="justification json")
    parser.add_argument("--approval-token-file", required=True)
    parser.add_argument("--apply", action="store_true", help="commit the transition (default dry-run)")
    args = parser.parse_args(argv)

    control_root = root_store.resolve_control_root()
    art_sha = consume.sha256_file(args.evidence_artifact)
    scope = receipt_ops.build_scope(OPS_APPROVAL_OPERATION_ID, "ignore", art_sha, args.receipt_id)

    def _build(session, approver_id):
        return receipt_ops.recovery_ignore(
            session, receipt_id=args.receipt_id, actor_user_id=approver_id)

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
