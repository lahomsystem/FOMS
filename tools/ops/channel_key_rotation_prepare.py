"""channel key rotation prepare CLI (operation CHANNEL_KEY_ROTATION_PREPARE).

    python tools/ops/channel_key_rotation_prepare.py \
        --pending-key-file <encrypted envelope json> \
        --expected-version <state version> --expected-generation <state generation> \
        --approval-token-file <under-control-root>.json --apply

pending key 는 offline 에서 생성·AES-256-GCM 으로 봉인된 envelope(``crypto.encrypt_key_material``
결과) json 파일로 넘긴다. CLI 는 raw key material 을 다루지 않고 envelope 의 key_id 와 artifact
sha 만 기록해 deadline-null EMPTY→READY 또는 ACTIVE→ROTATION_READY 전이만 한다(activation 은
별도). owner-only approval 토큰을 소비하며 기본 dry-run, ``--apply`` 일 때만 commit 한다.
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

OPS_APPROVAL_OPERATION_ID = "CHANNEL_KEY_ROTATION_PREPARE"


def main(argv: "list[str] | None" = None) -> int:
    """CLI 진입점 — pending key envelope 를 stage 하고 approval 을 소비한다."""
    parser = argparse.ArgumentParser(description="Prepare channel key rotation (pending stage).")
    parser.add_argument("--pending-key-file", required=True, help="AES-GCM envelope json")
    parser.add_argument("--expected-version", type=int, required=True)
    parser.add_argument("--expected-generation", type=int, required=True)
    parser.add_argument("--approval-token-file", required=True)
    parser.add_argument("--apply", action="store_true", help="commit the transition (default dry-run)")
    args = parser.parse_args(argv)

    control_root = root_store.resolve_control_root()
    envelope = json.loads(Path(args.pending_key_file).read_text(encoding="utf-8"))
    key_id = envelope["key_id"]
    ct_json = json.dumps(envelope, sort_keys=True, separators=(",", ":"))
    art_sha = consume.sha256_file(args.pending_key_file)
    scope = state_ops.build_scope(
        OPS_APPROVAL_OPERATION_ID, "prepare", art_sha,
        args.expected_version, args.expected_generation)

    def _build(session, approver_id):
        return state_ops.key_rotation_prepare(
            session, pending_key_id=key_id, pending_key_ciphertext=ct_json,
            prepared_key_artifact_sha256=art_sha, expected_version=args.expected_version,
            updated_by_admin_user_id=approver_id)

    session = sessionmaker(bind=engine)()
    try:
        result_sha = consume.consume_channel_operation(
            session, operation_id=OPS_APPROVAL_OPERATION_ID, control_root=control_root,
            token_path=args.approval_token_file, scope=scope, mutation_builder=_build)
        session.commit() if args.apply else session.rollback()
    finally:
        session.close()
    print(json.dumps({"operation": OPS_APPROVAL_OPERATION_ID, "pending_key_id": key_id,
                      "applied": bool(args.apply), "result_sha256": result_sha}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
