"""수집 링크의 매칭 축 사본(수령인명·전화)을 기존 행에 채운다 (NAVER-INGEST-BACKFILL).

왜: "오늘 실측인데 안 붙은 집" 매칭은 축 사본이 있는 행만 SQL 로 좁힌다. 사본이 없는 옛
행은 최신 300행 스캔으로 폴백하는데, 미연결이 그보다 많아지면 그 폴백이 잘린다. 컬럼을
만든 뒤 **한 번** 돌려 옛 행을 채우면 폴백 갈래가 비어 간다.

읽기·쓰기 대상은 ``external_order_links`` 의 사본 컬럼 3개뿐이다. 정본(``raw_snapshot``)은
건드리지 않는다. 값 추출은 화면·매칭과 **같은 함수**(``ingest._match_key_values``)를 쓴다 —
규칙을 여기 복제하면 한쪽만 고쳐지는 날 두 화면이 다른 집을 짚는다.

사용:

    python tools/ops/backfill_link_match_keys.py --dry-run
    python tools/ops/backfill_link_match_keys.py --batch 500
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

logger = logging.getLogger(__name__)


def main() -> int:
    """사본이 빈 링크를 배치로 훑어 채운다.

    Returns:
        종료 코드(0=성공).
    """
    parser = argparse.ArgumentParser(description="수집 링크 매칭 축 사본 채우기")
    parser.add_argument("--batch", type=int, default=500, help="한 번에 처리할 행 수")
    parser.add_argument("--limit", type=int, default=0, help="총 처리 상한(0=제한 없음)")
    parser.add_argument("--dry-run", action="store_true", help="세기만 하고 쓰지 않는다")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(message)s")

    from db import db_session
    from foms.services.integrations.naver_commerce.constants import CHANNEL
    from foms.services.integrations.naver_commerce.ingest import _match_key_values
    from models import ExternalOrderLink

    session = db_session()
    total = filled = 0
    try:
        while True:
            rows = (
                session.query(ExternalOrderLink)
                .filter(ExternalOrderLink.channel == CHANNEL,
                        ExternalOrderLink.recipient_name.is_(None),
                        ExternalOrderLink.recipient_phone_digits.is_(None),
                        ExternalOrderLink.orderer_phone_digits.is_(None))
                .order_by(ExternalOrderLink.id.asc())
                .limit(int(args.batch))
                .all()
            )
            if not rows:
                break
            progressed = False
            for row in rows:
                total += 1
                keys = _match_key_values(row.raw_snapshot or {})
                if not any(keys.values()):
                    # 셋 다 못 뽑는 행은 다음 배치에서 또 걸린다 — 표식이 없으면 무한 루프다.
                    # 빈 문자열로 채워 "봤지만 값이 없다"를 남긴다.
                    keys = {"recipient_name": "", "recipient_phone_digits": "",
                            "orderer_phone_digits": ""}
                else:
                    filled += 1
                if args.dry_run:
                    continue
                row.recipient_name = keys["recipient_name"]
                row.recipient_phone_digits = keys["recipient_phone_digits"]
                row.orderer_phone_digits = keys["orderer_phone_digits"]
                progressed = True
            if args.dry_run:
                logger.info("[dry-run] 사본 없는 행 %d개 확인(값 추출 성공 %d)", total, filled)
                break
            session.commit()
            logger.info("채움 진행 — 누적 %d행(값 있음 %d)", total, filled)
            if not progressed:
                break
            if args.limit and total >= int(args.limit):
                break
    finally:
        session.close()
        db_session.remove()
    logger.info("끝 — 훑은 행 %d · 값 채운 행 %d", total, filled)
    return 0


if __name__ == "__main__":
    sys.exit(main())
