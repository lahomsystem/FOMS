"""irreversible cutover marker 생성 CLI (§8.2 line 1518-1522, operation CUTOVER_MARK).

    python tools/ops/mark_feature_cutover.py \
        --family ASSIGNMENT --artifact <readiness.json> \
        --approval-token-file <under-control-root>.json \
        --expected-version <n> --commit-sha <sha> --apply

fence 를 ``FOR UPDATE`` 로 in-flight business tx 를 drain 한 뒤, 같은 tx 에 marker 를
**최초 1회** insert 하고 fence 를 CUTOVER 로 전이한다(marker insert + DRAINING/OPEN→
CUTOVER 원자). all-serving state-aware generation(build_compatibility.json)+operation-
bound Admin approval+readiness artifact 를 검증한다. ``approved_by_admin_user_id`` 는 CLI
입력이 아니라 소비된 approval row 에서 복사한다. marker 는 update/delete/downgrade 불가.
기본 dry-run — ``--apply`` 일 때만 commit.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from sqlalchemy.orm import sessionmaker  # noqa: E402

from db import engine  # noqa: E402
from models import OpsApprovalRequest  # noqa: E402
from foms.services.security import ops_control_root as root_store  # noqa: E402
from foms.services.security.ops_approval import nonce_hash_from_secret  # noqa: E402
from foms.services.security.cutover import mark_ops  # noqa: E402
from foms.services.security.cutover.cli_support import (  # noqa: E402
    build_scope, consume_cutover_operation, sha256_file,
)
from foms.services.security.cutover.mode_manifest import load_manifest  # noqa: E402
from tools.harness.verify_build_compatibility import (  # noqa: E402
    load_build_compatibility, validate_structure,
)

OPS_APPROVAL_OPERATION_ID = "CUTOVER_MARK"


def main(argv: "list[str] | None" = None) -> int:
    parser = argparse.ArgumentParser(description="Mark an irreversible feature cutover (first insert only).")
    parser.add_argument("--family", required=True)
    parser.add_argument("--artifact", required=True, help="readiness artifact 경로(sha256 이 marker/approval 에 바인딩)")
    parser.add_argument("--approval-token-file", required=True, help="control root 아래 approval 토큰")
    parser.add_argument("--expected-version", type=int, required=True, help="fence row_version")
    parser.add_argument("--commit-sha", default=os.environ.get("RAILWAY_GIT_COMMIT_SHA"),
                        help="cutover 커밋 SHA(기본 RAILWAY_GIT_COMMIT_SHA)")
    parser.add_argument("--apply", action="store_true", help="marker/CUTOVER 를 commit(기본 dry-run)")
    args = parser.parse_args(argv)

    if not args.commit_sha:
        raise SystemExit("--commit-sha (or RAILWAY_GIT_COMMIT_SHA) is required for the cutover marker.")

    try:
        control_root = root_store.resolve_control_root()
    except root_store.OpsControlRootError as exc:
        raise SystemExit(f"control root error: {exc}")

    # in-image compatibility generation = all-serving state-aware generation 정본.
    build_compat = load_build_compatibility()
    validate_structure(build_compat)
    image_generation = build_compat["generation"]
    if args.family not in build_compat["state_aware_families"]:
        raise SystemExit(
            f"family {args.family!r} is not in the in-image state_aware_families "
            "(image is not state-aware for this family; refuse to mark)."
        )

    manifest = load_manifest()
    fam_row = manifest.get("families", {}).get(args.family)
    if fam_row is None:
        raise SystemExit(f"family {args.family!r} not found in mode manifest.")
    minimum_compatibility_generation = fam_row["minimum_compatibility_generation"]

    artifact_sha = sha256_file(args.artifact)
    scope = build_scope(
        OPS_APPROVAL_OPERATION_ID, args.family, "mark",
        artifact_sha, args.expected_version, image_generation,
    )

    raw_nonce_probe = {}  # populated in _mut via token; approval row read there.

    def _mut(session):
        # approval row 는 consume_same_db 가 이미 FOR UPDATE 로 잠갔다 — 같은 tx 에서
        # 재조회해 id/approver 를 marker 로 복사한다(CLI 입력 아님).
        secret = root_store.read_token(Path(args.approval_token_file), control_root)
        raw = root_store.decode_secret_b64url(secret["one_time_secret_b64url"])
        approval = (
            session.query(OpsApprovalRequest)
            .filter(OpsApprovalRequest.nonce_hash == nonce_hash_from_secret(raw))
            .one()
        )
        raw_nonce_probe["approval_id"] = approval.id
        return mark_ops.mark_cutover(
            session, args.family, args.expected_version,
            cutover_sha=args.commit_sha,
            cutover_generation=image_generation,
            minimum_compatibility_generation=minimum_compatibility_generation,
            readiness_artifact_sha256=artifact_sha,
            ops_approval_id=approval.id,
            approved_by_admin_user_id=approval.approved_by_user_id,
        )

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
        "applied": bool(args.apply), "cutover_generation": image_generation,
        "minimum_compatibility_generation": minimum_compatibility_generation,
        "approval_id": raw_nonce_probe.get("approval_id"),
        "result_sha256": result_sha,
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
