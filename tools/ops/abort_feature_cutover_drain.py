"""cutover drain 중단(복구) CLI (§8.2 line 1522, operation CUTOVER_DRAIN_ABORT).

    python tools/ops/abort_feature_cutover_drain.py \
        --family UPLOAD --artifact <all-serving.json> \
        --approval-token-file <under-control-root>.json \
        --expected-version <n> --expected-generation <n> --apply

marker 가 아직 없음(marker0)과 fence mode==DRAINING 을 확인한 뒤 ``DRAINING→OPEN`` 으로
복구한다. marker 뒤에는 abort 할 수 없다(irreversible). operation-bound Admin approval
토큰을 소비한다(owner-only). 기본 dry-run — ``--apply`` 일 때만 commit.
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
from foms.services.security.cutover import mark_ops  # noqa: E402
from foms.services.security.cutover.cli_support import (  # noqa: E402
    build_scope, consume_cutover_operation, sha256_file,
)

OPS_APPROVAL_OPERATION_ID = "CUTOVER_DRAIN_ABORT"


def main(argv: "list[str] | None" = None) -> int:
    parser = argparse.ArgumentParser(description="Abort cutover drain (DRAINING→OPEN, marker0 required).")
    parser.add_argument("--family", required=True)
    parser.add_argument("--artifact", required=True, help="unresolved-effect0 readiness artifact 경로")
    parser.add_argument("--approval-token-file", required=True, help="control root 아래 approval 토큰")
    parser.add_argument("--expected-version", type=int, required=True, help="fence row_version")
    parser.add_argument("--expected-generation", type=int, required=True, help="compatibility generation")
    parser.add_argument("--apply", action="store_true", help="복구를 commit(기본 dry-run)")
    args = parser.parse_args(argv)

    try:
        control_root = root_store.resolve_control_root()
    except root_store.OpsControlRootError as exc:
        raise SystemExit(f"control root error: {exc}")

    artifact_sha = sha256_file(args.artifact)
    scope = build_scope(
        OPS_APPROVAL_OPERATION_ID, args.family, "drain_abort",
        artifact_sha, args.expected_version, args.expected_generation,
    )

    def _mut(session):
        return mark_ops.abort_drain(session, args.family, args.expected_version)

    session = sessionmaker(bind=engine)()
    try:
        result_sha = consume_cutover_operation(
            session, operation_id=OPS_APPROVAL_OPERATION_ID, control_root=control_root,
            token_path=args.approval_token_file, scope=scope, target_mutation=_mut,
        )
        if args.apply:
            session.commit()
        else:
            session.rollback()
    finally:
        session.close()

    print(json.dumps({
        "family": args.family, "operation": OPS_APPROVAL_OPERATION_ID,
        "applied": bool(args.apply), "result_sha256": result_sha,
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
