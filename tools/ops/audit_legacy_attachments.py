"""FILE-LEGACY-AUDIT-00 — legacy attachment/key read-only 감사 CLI(operator maintenance).

모든 :class:`~models.OrderAttachment` row 를 읽어 exact mapping CSV 와 ambiguous quarantine CSV
로 분류 출력한다. **read-only**: 어떤 DB write·파일 삭제·R2 접근도 하지 않는다(session.rollback).
추정 backfill·정정은 하류 FILE-LEGACY-BACKFILL-01 몫이며 이 tool 은 감사(분류)만 한다.

    python tools/ops/audit_legacy_attachments.py --output-dir ./legacy-audit

exit 0=성공. exact→``legacy_attachments_exact.csv``, ambiguous→``legacy_attachments_quarantine.csv``.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from sqlalchemy.orm import sessionmaker  # noqa: E402

from db import engine  # noqa: E402
from foms.services.files.legacy_attachment_audit import (  # noqa: E402
    audit_legacy_attachments,
    to_exact_csv,
    to_quarantine_csv,
)

EXACT_CSV = "legacy_attachments_exact.csv"
QUARANTINE_CSV = "legacy_attachments_quarantine.csv"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Audit legacy OrderAttachment rows/keys and write exact + quarantine CSV (read-only)."
    )
    parser.add_argument(
        "--output-dir", default=".", help="CSV 출력 디렉토리(기본: 현재 디렉토리)"
    )
    args = parser.parse_args(argv)

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    session = sessionmaker(bind=engine)()
    try:
        audit = audit_legacy_attachments(session)
        session.rollback()  # read-only: 어떤 write 도 커밋하지 않는다.
    finally:
        session.close()

    (output_dir / EXACT_CSV).write_text(to_exact_csv(audit), encoding="utf-8")
    (output_dir / QUARANTINE_CSV).write_text(to_quarantine_csv(audit), encoding="utf-8")

    print(json.dumps({
        "output_dir": str(output_dir),
        "total": audit.total,
        "exact": len(audit.exact),
        "ambiguous": len(audit.ambiguous),
        "exact_csv": EXACT_CSV,
        "quarantine_csv": QUARANTINE_CSV,
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
