"""external_order_links 클레임 축 사본 컬럼 채우기 (NVMIRROR-01).

마이그레이션 ``nvmirror_00`` 은 컬럼만 만든다. 값 계산이 원본 파싱 코드
(:func:`mapping.extract_claim`)에 의존하는데, 마이그레이션이 그 코드를 import 하면 나중에
파싱 규칙이 바뀔 때 **과거 마이그레이션의 결과가 소급해서 달라진다**. 그래서 채우기는 이
스크립트가 따로 한다(``backfill_naver_group_key.py`` 와 같은 규약).

**안 돌려도 화면은 그대로다.** 사본이 ``NULL`` 인 행은 읽는 쪽이 스냅샷 경로로 폴백한다 —
다만 그 행만큼 TOAST 를 계속 읽으므로 느림이 남는다. 다 채우면 유령 스캔과 다시 읽기 판정이
``raw_snapshot`` 을 **아예 안 읽는다**(운영 실측 같은 스캔 50.5ms → 0.95ms).

``NULL`` 과 빈 문자열을 가른다 — ``NULL`` = 아직 계산 안 함, ``''`` = 계산했고 값 없음.
그래서 이 스크립트는 **``claim_status IS NULL`` 인 행만** 집는다(멱등).

사용법::

    python scripts/maintenance/backfill_link_claim_mirror.py --dry-run
    python scripts/maintenance/backfill_link_claim_mirror.py --limit 500
    python scripts/maintenance/backfill_link_claim_mirror.py

스펙: docs/specs/2026-09-13-naver-link-claim-mirror_SPEC.md
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from typing import Any

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

logger = logging.getLogger("backfill_link_claim_mirror")

#: 한 번에 커밋하는 행 수. 운영 DB 를 오래 잠그지 않으려고 나눠 커밋한다.
BATCH_SIZE = 500


def _iter_rows_missing_mirror(session: Any, limit: int | None) -> list[Any]:
    """사본이 아직 없는 링크를 오래된 순으로 가져온다.

    ``claim_status IS NULL`` 만 본다 — 빈 문자열은 "계산했고 클레임 없음" 이므로 대상이 아니다.

    Args:
        session: DB 세션.
        limit: 최대 처리 행 수(None 이면 전부).

    Returns:
        처리 대상 링크 목록.
    """
    from models import ExternalOrderLink

    query = (
        session.query(ExternalOrderLink)
        .filter(ExternalOrderLink.channel == "NAVER",
                ExternalOrderLink.claim_status.is_(None))
        .order_by(ExternalOrderLink.id)
    )
    if limit:
        query = query.limit(limit)
    return query.all()


def backfill(session: Any, *, dry_run: bool = False, limit: int | None = None) -> dict[str, int]:
    """빈 사본 컬럼을 원본에서 계산해 채운다.

    Args:
        session: DB 세션.
        dry_run: True 면 계산만 하고 쓰지 않는다.
        limit: 최대 처리 행 수.

    Returns:
        ``{"scanned", "filled", "skipped_no_snapshot", "skipped_unparsable"}`` 집계.
    """
    from foms.services.integrations.naver_commerce.link_mirror import claim_mirror_values

    stats = {"scanned": 0, "filled": 0, "skipped_no_snapshot": 0, "skipped_unparsable": 0}
    rows = _iter_rows_missing_mirror(session, limit)
    pending = 0

    for link in rows:
        stats["scanned"] += 1
        snapshot = link.raw_snapshot
        if not isinstance(snapshot, dict):
            # 원본이 없으면 계산할 근거가 없다 — 폴백에 맡긴다(빈 dict 는 "클레임 없음" 이라 센다).
            stats["skipped_no_snapshot"] += 1
            continue
        values = claim_mirror_values(snapshot)
        if values["claim_status"] is None:
            # `extract_claim` 이 못 읽은 행. 사본을 채우면 "클레임 없음" 으로 거짓말한다.
            stats["skipped_unparsable"] += 1
            continue

        stats["filled"] += 1
        if dry_run:
            continue
        for name, value in values.items():
            if value is not None:
                setattr(link, name, value)
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
    parser = argparse.ArgumentParser(description="네이버 수집 링크의 클레임 축 사본 채우기")
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
