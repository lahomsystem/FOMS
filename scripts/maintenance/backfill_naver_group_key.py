"""external_order_links.group_key 기존 행 채우기 (03 감사 결함 #1).

마이그레이션 ``navergroup_00`` 은 컬럼만 만든다. 값 계산이 원본 파싱 코드
(:func:`mapping.group_key_text`)에 의존하는데, 마이그레이션이 그 코드를 import 하면
나중에 파싱 규칙이 바뀔 때 **과거 마이그레이션의 결과가 소급해서 달라진다**.
그래서 채우기는 이 스크립트가 따로 한다.

컬럼이 빈 행은 읽는 쪽이 주문번호로 폴백하므로 이 스크립트를 안 돌려도 화면은 죽지
않는다 — 다만 분할배송에서 이력과 확인 큐의 집 수가 예전처럼 어긋난 채로 남는다.

사용법::

    python scripts/maintenance/backfill_naver_group_key.py --dry-run
    python scripts/maintenance/backfill_naver_group_key.py --limit 500
    python scripts/maintenance/backfill_naver_group_key.py

멱등이다 — 이미 값이 있는 행은 건드리지 않는다. 여러 번 돌려도 결과가 같다.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from typing import Any

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

logger = logging.getLogger("backfill_naver_group_key")

#: 한 번에 커밋하는 행 수. 운영 DB 를 오래 잠그지 않으려고 나눠 커밋한다.
BATCH_SIZE = 500


def _iter_rows_missing_group_key(session: Any, limit: int | None) -> list[Any]:
    """묶음키가 비어 있는 링크를 오래된 순으로 가져온다.

    Args:
        session: DB 세션.
        limit: 최대 처리 행 수(None 이면 전부).

    Returns:
        처리 대상 링크 목록.
    """
    from models import ExternalOrderLink

    query = (
        session.query(ExternalOrderLink)
        .filter(
            ExternalOrderLink.channel == "NAVER",
            (ExternalOrderLink.group_key.is_(None)) | (ExternalOrderLink.group_key == ""),
        )
        .order_by(ExternalOrderLink.id)
    )
    if limit:
        query = query.limit(limit)
    return query.all()


def backfill(session: Any, *, dry_run: bool = False, limit: int | None = None) -> dict[str, int]:
    """빈 ``group_key`` 를 원본에서 계산해 채운다.

    Args:
        session: DB 세션.
        dry_run: True 면 계산만 하고 쓰지 않는다.
        limit: 최대 처리 행 수.

    Returns:
        ``{"scanned", "filled", "skipped_no_snapshot", "skipped_unparsable"}`` 집계.
    """
    from foms.services.integrations.naver_commerce.mapping import group_key_text

    stats = {"scanned": 0, "filled": 0, "skipped_no_snapshot": 0, "skipped_unparsable": 0}
    rows = _iter_rows_missing_group_key(session, limit)
    pending = 0

    for link in rows:
        stats["scanned"] += 1
        snapshot = link.raw_snapshot
        if not isinstance(snapshot, dict) or not snapshot:
            # 원본이 없으면 계산할 근거가 없다 — 폴백(주문번호)에 맡긴다.
            stats["skipped_no_snapshot"] += 1
            continue
        try:
            value = group_key_text(snapshot)
        except (ValueError, TypeError, AttributeError, KeyError) as exc:
            logger.warning("링크 %s 묶음키 계산 실패(건너뜀): %s", link.id, exc)
            stats["skipped_unparsable"] += 1
            continue
        if not value:
            stats["skipped_unparsable"] += 1
            continue

        stats["filled"] += 1
        if dry_run:
            continue
        link.group_key = value
        pending += 1
        if pending >= BATCH_SIZE:
            session.commit()
            pending = 0

    if not dry_run and pending:
        session.commit()
    return stats


def main() -> int:
    """CLI 진입점.

    Returns:
        종료 코드(0=성공).
    """
    parser = argparse.ArgumentParser(description="네이버 수집 링크의 묶음키 채우기")
    parser.add_argument("--dry-run", action="store_true", help="계산만 하고 쓰지 않는다")
    parser.add_argument("--limit", type=int, default=None, help="최대 처리 행 수")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    from db import db_session

    stats = backfill(db_session, dry_run=args.dry_run, limit=args.limit)
    mode = "[DRY-RUN] " if args.dry_run else ""
    logger.info(
        "%s대상 %d행 · 채움 %d · 원본없음 %d · 계산불가 %d",
        mode, stats["scanned"], stats["filled"],
        stats["skipped_no_snapshot"], stats["skipped_unparsable"],
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
