"""STARTUP-BACKFILL-01 — SAFE ERP flat 컬럼 재동기 backfill CLI (operator maintenance).

암호화 audit artifact 의 SAFE 대상만 flat 컬럼을 재동기한다(structured_data 가 SSOT).
app startup 이 자동 실행하지 않는다 — operator 가 명시 실행하는 유지보수 단계다(startup
fallback 금지, §5.2 / report line 1367-1368).

    # dry-run (기본·approval 불필요):
    python tools/ops/backfill_erp_flat_columns.py \
        --artifact-dir "$ROOT/startup-flat" --phase STARTUP_FLAT \
        --db-instance-id <db-id> --dry-run --batch-size 500

    # apply (operation-bound approval 필수):
    python tools/ops/backfill_erp_flat_columns.py \
        --artifact-dir "$ROOT/startup-flat" --phase STARTUP_FLAT \
        --db-instance-id <db-id> --approval-token-file <path> --apply --batch-size 500 --verify

**bare ``--apply``(approval-token 없이)는 거부**하고 아무 것도 쓰지 않는다(exit 2). dry-run
은 대상 수만 보고한다. apply 는 BACKFILL_APPLY OPS approval 을 소비해 batch/checkpoint/
resume 으로 재동기하고 before/after drift 를 검증한다. exit 0=성공, 그 외=비정상(nonzero).
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from sqlalchemy.orm import sessionmaker  # noqa: E402

from db import engine  # noqa: E402
from foms.services.orders import erp_flat_audit  # noqa: E402
from foms.services.orders.erp_flat_artifact import load_audit_artifact  # noqa: E402
from foms.services.orders.erp_flat_backfill import (  # noqa: E402
    ApplyAuthorizationError,
    count_flat_drift,
    resolve_apply_mode,
    run_backfill,
)
from foms.services.security.backfill import artifact_root, runs  # noqa: E402
from foms.services.security.backfill.manifest import BACKFILL_APPLY_OPERATION_ID  # noqa: E402

# 고위험 token CLI 규약(ops_approval_manifest): --approval-token-file 를 받는 CLI 는 자기가
# 소비하는 OPS operation 을 선언해야 한다. 이 CLI 의 --apply 는 consume_backfill_apply 로
# BACKFILL_APPLY 를 소비한다(BACKFILL-ARTIFACT-00 owner operation). literal 필수(AST 스캔).
OPS_APPROVAL_OPERATION_ID = "BACKFILL_APPLY"
assert OPS_APPROVAL_OPERATION_ID == BACKFILL_APPLY_OPERATION_ID  # 공유 operation id drift 가드


def _load_token(path: str) -> tuple[str, bytes]:
    """approval token 파일 → ``(approval_id, raw_secret)``. secret 은 argv 에 노출 안 함."""
    with open(path, encoding="utf-8") as fh:
        token = json.load(fh)
    approval_id = token["approval_id"]
    secret_b64 = token["one_time_secret_b64url"]
    pad = "=" * (-len(secret_b64) % 4)
    raw_secret = base64.urlsafe_b64decode(secret_b64 + pad)
    return approval_id, raw_secret


def _assert_under_root(artifact_dir: Path, root: Path) -> None:
    try:
        artifact_dir.resolve().relative_to(root)
    except ValueError:
        raise SystemExit(
            f"--artifact-dir must live under {artifact_root.ENV_VAR} ({root}); got {artifact_dir}."
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Resync SAFE ERP flat columns from an encrypted audit artifact (operator)."
    )
    parser.add_argument("--artifact-dir", required=True, help="audit artifact dir under the root")
    parser.add_argument("--phase", required=True, help="must be STARTUP_FLAT")
    parser.add_argument("--db-instance-id", required=True, help="target DB identifier")
    parser.add_argument("--batch-size", type=int, default=500)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--approval-token-file", default=None)
    parser.add_argument("--verify", action="store_true", help="before/after drift verify")
    parser.add_argument("--owner-identity", default=None)
    args = parser.parse_args(argv)

    if args.phase != erp_flat_audit.PHASE:
        print(f"[ERROR] --phase must be {erp_flat_audit.PHASE!r} (got {args.phase!r}).")
        return 2

    try:
        apply = resolve_apply_mode(
            apply=args.apply, dry_run=args.dry_run, approval_token_file=args.approval_token_file
        )
    except ApplyAuthorizationError as exc:
        print(f"[REFUSED] {exc}")
        return 2

    try:
        root = artifact_root.resolve_artifact_root()
    except artifact_root.ArtifactRootError as exc:
        print(f"[ERROR] artifact root error: {exc}")
        return 2

    artifact_dir = Path(args.artifact_dir)
    _assert_under_root(artifact_dir, root)

    loaded = load_audit_artifact(artifact_dir, db_instance_id=args.db_instance_id)
    safe_ids = [oid for oid, _ in loaded.safe_targets]

    session = sessionmaker(bind=engine)()
    try:
        before = count_flat_drift(session, safe_ids)
        session.rollback()
        print(json.dumps({
            "phase": args.phase,
            "safe_targets": len(safe_ids),
            "drift_before": before,
            "mode": "apply" if apply else "dry-run",
        }, ensure_ascii=False))

        if not apply:
            print("[DRY-RUN] no rows written; approval + --apply required to resync.")
            return 0

        approval_id, raw_secret = _load_token(args.approval_token_file)
        from models import OpsApprovalRequest

        approval_row = (
            session.query(OpsApprovalRequest).filter(OpsApprovalRequest.id == approval_id).one()
        )
        admin_principal_version = approval_row.approved_principal_version

        def _activate(sess, run):
            runs.consume_backfill_apply(
                sess,
                run.run_id,
                approval_scope=loaded.approval_scope,
                approval_id=approval_id,
                admin_principal_version=admin_principal_version,
                raw_secret=raw_secret,
            )

        report = run_backfill(
            session,
            db_instance_id=args.db_instance_id,
            owner_identity=args.owner_identity or os.environ.get("USERNAME") or "operator",
            safe_targets=loaded.safe_targets,
            manifest_sha256=loaded.manifest_sha256,
            mapping_sha256=loaded.mapping_sha256,
            batch_size=args.batch_size,
            activate_approval=_activate,
        )

        after = count_flat_drift(session, safe_ids) if args.verify else None
        print(json.dumps({
            "run_id": report.run_id,
            "state": report.state,
            "batches": report.batches,
            "resynced_orders": report.resynced_orders,
            "completed_rows": report.completed_rows,
            "drift_after": after,
        }, ensure_ascii=False))

        if report.stopped_drift:
            print("[STOPPED] source fingerprint drift; re-run audit and retry.")
            return 3
        if args.verify and after:
            print(f"[VERIFY-FAIL] {after} SAFE orders still drift after apply.")
            return 4
        return 0
    finally:
        session.close()


if __name__ == "__main__":
    raise SystemExit(main())
