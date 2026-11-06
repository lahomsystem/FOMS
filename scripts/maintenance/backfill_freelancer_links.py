"""주문 ↔ 프리랜서 연결 표(``order_freelancer_links``) 되채우기 (FCOMM-01 T13 · 설계서 §5).

마이그레이션 ``fcomm_02`` 는 표만 만든다. 이미 있는 주문의 연결은 이 스크립트가 지금 설정(맞출 이름 · 켜진
프리랜서) 기준으로 채운다 — 주문 저장 훅이 켜진 뒤 새로 저장되는 주문은 훅이 맞춘다. 같은 규칙
(:func:`foms.services.sales_commission.links.sync_links_for_orders`)을 쓰므로 여러 번 돌려도 결과가 같다(멱등).

- 기본은 **미리 보기**다(쓰기 0). ``--apply`` 를 줘야 쓴다(덩어리마다 커밋).
- 배정 알림을 내지 않는다.
- 숫자만 찍는다(고객 이름 · 주소 같은 주문 내용은 찍지 않는다).

사용법::

    python scripts/maintenance/backfill_freelancer_links.py
    python scripts/maintenance/backfill_freelancer_links.py --apply
    python scripts/maintenance/backfill_freelancer_links.py --apply --chunk-size 200
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from typing import Any, Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

logger = logging.getLogger("backfill_freelancer_links")


def run(session: Any, *, apply: bool = False, chunk_size: Optional[int] = None) -> dict[str, int]:
    """연결을 다시 맞춘다(미리 보기면 세기만 하고 롤백).

    Args:
        session: DB 세션.
        apply: True 면 쓴다(덩어리마다 커밋). False 면 쓰기 0.
        chunk_size: 한 번에 읽는 주문 수(기본 :data:`~foms.services.sales_commission.links.DEFAULT_CHUNK_SIZE`).

    Returns:
        ``{"orders", "added", "removed", "freelancers"}`` 숫자.
    """
    from foms.services.sales_commission.links import DEFAULT_CHUNK_SIZE, sync_links_for_orders

    stats = sync_links_for_orders(session, notify=False, dry_run=not apply, commit=apply,
                                  chunk_size=chunk_size or DEFAULT_CHUNK_SIZE)
    if not apply:
        session.rollback()
    return stats


def main(argv: Optional[list[str]] = None) -> int:
    """CLI 진입점.

    Returns:
        종료 코드(0=성공).
    """
    parser = argparse.ArgumentParser(description="주문 ↔ 프리랜서 연결 표 되채우기(기본 미리 보기)")
    parser.add_argument("--apply", action="store_true", help="실제로 쓴다(없으면 미리 보기 — 쓰기 0)")
    parser.add_argument("--chunk-size", type=int, default=None, help="한 번에 읽는 주문 수")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    from db import db_session

    try:
        stats = run(db_session, apply=args.apply, chunk_size=args.chunk_size)
    finally:
        db_session.remove()
    mode = "" if args.apply else "[미리 보기] "
    logger.info("%s켜진 프리랜서 %d명 · 본 주문 %d건 · 더한 연결 %d · 지운 연결 %d",
                mode, stats["freelancers"], stats["orders"], stats["added"], stats["removed"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
