"""channel receipt retention EXTEND CLI (operation CHANNEL_RETENTION_EXTEND).

    python tools/ops/channel_retention_extend.py \
        --receipt-id <id> --new-deadline <ISO-8601> --evidence-artifact <json> \
        --approval-token-file <under-control-root>.json --apply

미생성 receipt 의 retention deadline 을 **명시·유계** 미래로 연장한다(무기한 보관 금지 —
deadline 필수·미래여야 함). owner-only approval 토큰을 소비하며 기본 dry-run.
"""
from __future__ import annotations

import argparse
import datetime
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from sqlalchemy.orm import sessionmaker  # noqa: E402

from db import engine  # noqa: E402
from foms.services.security import ops_control_root as root_store  # noqa: E402
from foms.services.security.channel_order import consume, receipt_ops  # noqa: E402

OPS_APPROVAL_OPERATION_ID = "CHANNEL_RETENTION_EXTEND"


def main(argv: "list[str] | None" = None) -> int:
    """CLI 진입점 — receipt retention deadline 을 유계 미래로 연장한다."""
    parser = argparse.ArgumentParser(description="Extend a receipt retention deadline (bounded).")
    parser.add_argument("--receipt-id", type=int, required=True)
    parser.add_argument("--new-deadline", required=True, help="ISO-8601 (naive UTC)")
    parser.add_argument("--evidence-artifact", required=True, help="justification json")
    parser.add_argument("--approval-token-file", required=True)
    parser.add_argument("--apply", action="store_true", help="commit the transition (default dry-run)")
    args = parser.parse_args(argv)

    control_root = root_store.resolve_control_root()
    new_deadline = datetime.datetime.fromisoformat(args.new_deadline)
    art_sha = consume.sha256_file(args.evidence_artifact)
    scope = receipt_ops.build_scope(OPS_APPROVAL_OPERATION_ID, "extend", art_sha, args.receipt_id)

    def _build(session, approver_id):
        return receipt_ops.retention_extend(
            session, receipt_id=args.receipt_id, new_deadline=new_deadline,
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
