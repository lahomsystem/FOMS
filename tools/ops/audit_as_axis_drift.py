"""AS-AXIS-01 드리프트 감사: 투영 컬럼 ``as_axis_status`` 가 정본과 어긋난 행을 찾는다(읽기 전용).

AS-AXIS-01 롤아웃 2단(술어 스위치) 전에 **0건**이어야 한다. 이후에도 주기적으로 돌려
동기화를 안 거치는 새 write 경로를 잡는다.

세 가지를 본다:

1. 컬럼값 ≠ 유도값(:func:`~foms.services.orders.state_axes.derive_as_axis_status`)
2. AS 흔적(접수일·완료일·as_lifecycle)이 있는데 컬럼이 NULL
3. legacy ``status`` 는 AS 계열인데 컬럼이 NULL (구 술어와 신 술어의 건수 차)

사용:
    python tools/ops/audit_as_axis_drift.py --dsn "$DSN"
    python tools/ops/audit_as_axis_drift.py --dsn "$DSN" --json

집계 로직의 정본은 :func:`foms.services.orders.audit_as_axis_drift.audit_session`
**하나뿐**이다. 이 CLI 는 DSN 으로 엔진을 여는 얇은 껍데기이고, admin 조회 엔드포인트
(:mod:`foms.api.ops_drift`)는 앱 세션을 그대로 넘긴다 — 어느 쪽도 집계를 복제하지 않는다.
집계가 이 파일에 살면 웹 런타임이 ``tools/`` 트리에 묶이므로 서비스 계층에 둔다.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from foms.services.orders.audit_as_axis_drift import (  # noqa: E402
    AS_LEGACY_STATUSES,
    SAMPLE_LIMIT,
    audit_session,
)

__all__ = ["AS_LEGACY_STATUSES", "SAMPLE_LIMIT", "audit", "audit_session", "main"]


def audit(dsn: str) -> dict[str, Any]:
    """DSN 으로 엔진을 열어 :func:`audit_session` 을 돌린다(CLI 껍데기, 쓰기 없음).

    Args:
        dsn: PostgreSQL 접속 문자열.

    Returns:
        :func:`audit_session` 과 동일한 요약 dict.
    """
    engine = create_engine(dsn, future=True)
    with Session(engine) as session:
        return audit_session(session)


def main(argv: list[str] | None = None) -> int:
    """엔트리포인트.

    Args:
        argv: 인자 목록(기본 ``sys.argv[1:]``).

    Returns:
        드리프트가 없으면 0, 있으면 1(CI/스크립트 게이트용).
    """
    parser = argparse.ArgumentParser(description="AS 축 투영 드리프트 감사(읽기 전용)")
    parser.add_argument("--dsn", required=True)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    result = audit(args.dsn)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=1))
    else:
        print(f"검사 {result['checked']}건 / 불일치 {result['mismatch']}건 / "
              f"투영 누락 {result['missing_projection']}건 / legacy 전용 {result['legacy_only']}건")
        for sample in result["samples"]:
            print(f"  #{sample['order_id']} 컬럼={sample['column']} 유도={sample['derived']} "
                  f"status={sample['status']}")
        if result["mismatch"]:
            print("백필 재실행: python tools/ops/backfill_as_axis_status.py --dsn ... --apply")
    return 1 if result["mismatch"] else 0


if __name__ == "__main__":
    sys.exit(main())
