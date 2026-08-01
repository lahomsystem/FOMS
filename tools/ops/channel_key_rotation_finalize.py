"""channel key rotation finalize CLI (operation CHANNEL_KEY_ROTATION_FINALIZE).

    python tools/ops/channel_key_rotation_finalize.py \
        --rollout-artifact <current-only readiness json> \
        --expected-version <state version> --expected-generation <state generation> \
        --approval-token-file <under-control-root>.json --apply

ROTATING→ACTIVE 로 previous(구) key 를 폐기한다. grace 경과 **및 old-reference 0**(구 key 로
봉인된 secret 이 남아 있으면 거부 — rewrap 선행 강제)이어야 한다. old-reference 수는 소비 tx 안에서
``key_state.count_previous_key_references`` 로 산출한다. owner-only approval 토큰을 소비하며 기본
dry-run.
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
from foms.services.security.channel_order import consume, key_state, state_ops  # noqa: E402

OPS_APPROVAL_OPERATION_ID = "CHANNEL_KEY_ROTATION_FINALIZE"


def main(argv: "list[str] | None" = None) -> int:
    """CLI 진입점 — old-reference 0 확인 후 previous key 를 폐기한다."""
    parser = argparse.ArgumentParser(description="Finalize channel key rotation (drop previous).")
    parser.add_argument("--rollout-artifact", required=True, help="current-only readiness json")
    parser.add_argument("--expected-version", type=int, required=True)
    parser.add_argument("--expected-generation", type=int, required=True)
    parser.add_argument("--approval-token-file", required=True)
    parser.add_argument("--apply", action="store_true", help="commit the transition (default dry-run)")
    args = parser.parse_args(argv)

    control_root = root_store.resolve_control_root()
    art_sha = consume.sha256_file(args.rollout_artifact)
    scope = state_ops.build_scope(
        OPS_APPROVAL_OPERATION_ID, "finalize", art_sha,
        args.expected_version, args.expected_generation)

    def _build(session, approver_id):
        row = state_ops.load_singleton_for_update(session)
        old_refs = key_state.count_previous_key_references(session, row)
        return state_ops.key_rotation_finalize(
            session, old_reference_count=old_refs, prepared_rollout_artifact_sha256=art_sha,
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
