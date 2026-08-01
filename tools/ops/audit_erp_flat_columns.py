"""STARTUP-BACKFILL-01 — ERP flat 컬럼 정합 read-only audit CLI (operator maintenance).

protected artifact root 아래에 암호화 audit artifact 를 기록한다(app startup 이 아니라
operator 가 명시 실행하는 유지보수 단계 — startup fallback 금지, §5.2 / report line 1366).
read-only: 주문을 mutate 하지 않는다.

    python tools/ops/audit_erp_flat_columns.py \
        --output-dir "$FOMS_REMEDIATION_ARTIFACT_ROOT/startup-flat" \
        --db-instance-id <db-id>

``FOMS_REMEDIATION_ARTIFACT_ROOT`` 은 repo/profile/sync/network/reparse 밖 + Windows ACL
잠금이어야 하며(artifact_root 가드), ``--output-dir`` 은 그 root 하위여야 한다. exit 0=성공.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from sqlalchemy.orm import sessionmaker  # noqa: E402

from db import engine  # noqa: E402
from foms.services.orders.erp_flat_audit import audit_orders  # noqa: E402
from foms.services.orders.erp_flat_artifact import write_audit_artifact  # noqa: E402
from foms.services.security.backfill import artifact_root  # noqa: E402


def _assert_under_root(output_dir: Path, root: Path) -> None:
    """``--output-dir`` 이 검증된 artifact root 하위인지 확인(밖이면 SystemExit)."""
    try:
        output_dir.resolve().relative_to(root)
    except ValueError:
        raise SystemExit(
            f"--output-dir must live under {artifact_root.ENV_VAR} ({root}); got {output_dir}."
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Audit ERP flat-column drift and write an encrypted artifact (read-only)."
    )
    parser.add_argument("--output-dir", required=True, help="artifact dir under the protected root")
    parser.add_argument("--db-instance-id", required=True, help="target DB identifier")
    parser.add_argument(
        "--no-require-acl",
        action="store_true",
        help="skip Windows ACL check (dev only; location guards still enforced)",
    )
    args = parser.parse_args(argv)

    try:
        root = artifact_root.resolve_artifact_root(require_acl=not args.no_require_acl)
    except artifact_root.ArtifactRootError as exc:
        raise SystemExit(f"artifact root error: {exc}")

    output_dir = Path(args.output_dir)
    _assert_under_root(output_dir, root)
    output_dir.mkdir(parents=True, exist_ok=True)

    session = sessionmaker(bind=engine)()
    try:
        report = audit_orders(session)
        session.rollback()  # read-only: 어떤 write 도 커밋하지 않는다.
    finally:
        session.close()

    result = write_audit_artifact(
        output_dir, report, db_instance_id=args.db_instance_id
    )

    print(json.dumps({
        "output_dir": str(output_dir),
        "counts": report.masked_counts(),
        "manifest_sha256": result["manifest_sha256"],
        "mapping_sha256": result["mapping_sha256"],
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
