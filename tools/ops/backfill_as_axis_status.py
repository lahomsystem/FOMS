"""AS-AXIS-01 백필: ``orders.as_axis_status`` 를 유도 규칙대로 채운다.

유도 규칙은 앱 SSOT(:func:`foms.services.orders.state_axes.derive_as_axis_status`)를 그대로
쓴다 — 백필이 규칙을 복제하면 나중에 둘이 갈라져 드리프트가 된다.

기본은 dry-run(무엇을 몇 건 바꿀지만 출력). ``--apply`` 를 줘야 쓴다. 배치 커밋이라 중간에
끊겨도 재실행하면 남은 것만 채운다(멱등).

사용:
    python tools/ops/backfill_as_axis_status.py --dsn "$DSN"
    python tools/ops/backfill_as_axis_status.py --dsn "$DSN" --apply
"""

from __future__ import annotations

import argparse
import os
import sys
from collections import Counter
from typing import Any

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from sqlalchemy import create_engine, select  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from foms.services.orders.state_axes import derive_as_axis_status  # noqa: E402
from models import Order  # noqa: E402


def _candidate_query():
    """AS 흔적이 있거나 이미 투영값이 있는 주문만 고른다.

    Returns:
        SQLAlchemy select 문(전체 행 스캔을 피하기 위한 후보 필터 포함).
    """
    return select(Order).where(
        (Order.as_axis_status.isnot(None))
        | (Order.status.in_(("AS", "AS_RECEIVED", "AS_COMPLETED")))
        | ((Order.as_received_date.isnot(None)) & (Order.as_received_date != ""))
        | ((Order.as_completed_date.isnot(None)) & (Order.as_completed_date != ""))
    )


def run(dsn: str, *, apply: bool, batch: int) -> dict[str, Any]:
    """백필을 실행(또는 dry-run)한다.

    Args:
        dsn: PostgreSQL 접속 문자열.
        apply: True 면 실제로 UPDATE 한다.
        batch: 커밋 배치 크기.

    Returns:
        {'scanned', 'changed', 'transitions'} 요약 dict.
    """
    engine = create_engine(dsn, future=True)
    scanned = 0
    changed = 0
    transitions: Counter[str] = Counter()
    with Session(engine) as session:
        for order in session.scalars(_candidate_query()).all():
            scanned += 1
            derived = derive_as_axis_status(order)
            if derived == order.as_axis_status:
                continue
            transitions[f"{order.as_axis_status or 'NULL'}→{derived or 'NULL'}"] += 1
            changed += 1
            if apply:
                order.as_axis_status = derived
                if changed % batch == 0:
                    session.commit()
        if apply:
            session.commit()
    return {"scanned": scanned, "changed": changed, "transitions": dict(transitions)}


def main(argv: list[str] | None = None) -> int:
    """엔트리포인트.

    Args:
        argv: 인자 목록(기본 ``sys.argv[1:]``).

    Returns:
        프로세스 종료 코드 0.
    """
    parser = argparse.ArgumentParser(description="AS 축 투영 컬럼 백필(기본 dry-run)")
    parser.add_argument("--dsn", required=True)
    parser.add_argument("--apply", action="store_true", help="실제 UPDATE 실행")
    parser.add_argument("--batch", type=int, default=200)
    args = parser.parse_args(argv)

    result = run(args.dsn, apply=args.apply, batch=args.batch)
    mode = "적용" if args.apply else "dry-run"
    print(f"[{mode}] 후보 {result['scanned']}건 / 변경 {result['changed']}건")
    for key, count in sorted(result["transitions"].items(), key=lambda kv: -kv[1]):
        print(f"  {key}: {count}")
    if not args.apply and result["changed"]:
        print("실제로 채우려면 --apply 를 붙여라.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
