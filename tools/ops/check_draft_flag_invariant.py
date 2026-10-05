"""초안 표식 규칙을 어긴 주문(숨은 초안 모양)을 **읽기만** 해서 센다.

규칙(:mod:`foms.services.orders.draft_guard`): ``meta.draft`` 가 참인 ERP 주문의 status 는
DRAFT 또는 DELETED 뿐이다. 어긴 행은 status 가 실제 단계(MEASURE·RECEIVED 등)인데 표식이 남아
대시보드·검색·목록 어디에도 나오지 않는다(2026-10-05 운영 7건, 5주 동안 아무도 몰랐다).
정리 크론은 ``status='DRAFT'`` 행만 지우므로 이 모양은 저절로 사라지지 않는다.

출력은 주문 번호·status·휴지통 여부·만든 날짜뿐이다(고객 이름·전화·주소 없음). 고치지 않는다 —
자동 수정은 원인을 가린다.

종료 코드: ``0`` = 0건, ``3`` = 1건 이상(다른 실패와 구별), ``1`` = 실행 실패.

사용법(Flask 앱을 띄우지 않는다 — ``tools/cron/cleanup_order_drafts.py`` 머리말과 같은 이유)::

    DATABASE_URL=... python tools/ops/check_draft_flag_invariant.py          # 사람이 읽는 요약
    DATABASE_URL=... python tools/ops/check_draft_flag_invariant.py --json   # JSON 한 줄

**매일 밤 단계로는 아직 걸지 않았다(사용자 결정, 2026-10-05).** 운영에 이 모양 7건이 남아 있어
지금 걸면 매일 밤 실패로 울린다. 운영 7건 정리(설계서 §5·§7 7번)를 마친 뒤
``tools/cron/nightly.py`` 의 ``NIGHTLY_STEPS`` 에서 ``cleanup_order_drafts`` 바로 다음에
``NightlyStep("check_draft_flag_invariant", "tools/ops/check_draft_flag_invariant.py", ())`` 를 넣고,
``tests/domains/test_draft_flag_invariant_monitor.py`` 의 "아직 안 걸림" 단언을 뒤집는다.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

# 저장소 루트를 import 경로에 넣는다 — 직접 실행하면 tools/ops 만 들어간다.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

EXIT_CLEAN = 0
EXIT_FAILED = 1
EXIT_VIOLATIONS = 3


def find_hidden_draft_orders(session: Any) -> list[dict[str, Any]]:
    """규칙을 어긴 행을 번호 순으로 모은다(휴지통 행 포함, 쓰기 없음).

    Args:
        session: SQLAlchemy 세션(시험은 요청 세션, 운영은 읽기 전용 세션).

    Returns:
        ``[{'id', 'status', 'trashed', 'created_day'}]`` — 고객 정보 칸은 고르지 않는다.
    """
    from foms.services.orders.draft_guard import hidden_draft_shape_filter
    from models import Order

    rows = (
        session.query(Order.id, Order.status, Order.deleted_at, Order.created_at)
        .filter(hidden_draft_shape_filter())
        .order_by(Order.id)
        .all()
    )
    return [
        {
            "id": int(row.id),
            "status": row.status,
            "trashed": row.deleted_at is not None,
            "created_day": row.created_at.date().isoformat() if row.created_at else None,
        }
        for row in rows
    ]


def _make_readonly_session(url: str):
    """DATABASE_URL 로 읽기 전용 세션을 연다(PostgreSQL 은 트랜잭션 자체를 읽기 전용으로)."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from foms.services.db_url_resolver import sqlalchemy_url

    url = sqlalchemy_url(url)
    engine_kwargs: dict[str, Any] = {"pool_pre_ping": True}
    if "sqlite" not in url:
        engine_kwargs["connect_args"] = {
            "connect_timeout": 10,
            "options": "-c default_transaction_read_only=on",
        }
    engine = create_engine(url, **engine_kwargs)
    return sessionmaker(bind=engine)(), engine


def render_report(rows: list[dict[str, Any]]) -> str:
    """사람이 읽는 요약(번호·상태·휴지통 여부·만든 날짜만)."""
    lines = [f"[DRAFT-FLAG-CHECK] 표식 참인데 status 가 DRAFT·DELETED 가 아닌 주문 {len(rows)}건"]
    for row in rows:
        place = "휴지통" if row["trashed"] else "살아 있음"
        lines.append(f"  주문 #{row['id']} status={row['status']} {place} 만든 날 {row['created_day']}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    """한 번 세고 종료 코드를 낸다(0=없음, 3=있음, 1=실패)."""
    parser = argparse.ArgumentParser(description="초안 표식 규칙 위반 주문 수(읽기 전용)")
    parser.add_argument("--json", action="store_true", help="결과를 JSON 한 줄로 출력")
    args = parser.parse_args(argv)
    url = os.environ.get("DATABASE_URL")
    if not url:
        print("[DRAFT-FLAG-CHECK] 실패: DATABASE_URL 이 없습니다.", file=sys.stderr)
        return EXIT_FAILED
    try:
        session, engine = _make_readonly_session(url)
        try:
            rows = find_hidden_draft_orders(session)
        finally:
            session.close()
            engine.dispose()
    except Exception as exc:  # 점검 실패는 '0건'과 구별돼야 한다
        print(f"[DRAFT-FLAG-CHECK] 실패: {exc.__class__.__name__}", file=sys.stderr)
        return EXIT_FAILED
    if args.json:
        print(json.dumps({"violations": len(rows), "rows": rows}, ensure_ascii=False))
    else:
        print(render_report(rows))
    return EXIT_VIOLATIONS if rows else EXIT_CLEAN


if __name__ == "__main__":
    raise SystemExit(main())
