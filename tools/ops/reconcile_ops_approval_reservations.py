"""cross-DB RESERVED reservation 조정 CLI (§2.1 line 207).

primary 와 target DB 를 **read-only** 대조해 RESERVED 를 finalize(CONSUMED) 하거나
만료된 것을 EXPIRED 로 표시하고, 불일치를 alert 한다. 취소 불가 snapshot 을 임의로
rollback 하지 않는다.

    python tools/ops/reconcile_ops_approval_reservations.py \
        --primary-url <primary DSN> --target-url <target DSN> [--apply]

기본은 dry-run(요약만 출력). ``--apply`` 일 때만 finalize/expire 를 commit 한다.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from foms.services.security.ops_approval import reconcile_reservations  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Reconcile cross-DB ops approval reservations.")
    parser.add_argument("--primary-url", required=True)
    parser.add_argument("--target-url", required=True)
    parser.add_argument("--apply", action="store_true", help="finalize/expire 를 commit(기본 dry-run)")
    args = parser.parse_args(argv)

    primary_engine = create_engine(args.primary_url)
    target_engine = create_engine(args.target_url)
    primary = sessionmaker(bind=primary_engine)()
    target = sessionmaker(bind=target_engine)()
    try:
        result = reconcile_reservations(primary, target)
        if args.apply:
            primary.commit()
        else:
            primary.rollback()
    finally:
        primary.close()
        target.close()

    print(json.dumps(result, ensure_ascii=False))
    # 불일치/pending 이 있으면 nonzero 로 alert 신호.
    return 0 if not result["pending"] else 4


if __name__ == "__main__":
    raise SystemExit(main())
