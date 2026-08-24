"""네이버 수집 주문의 출처 표식(``structured_data['source']``) 백필 — 1회성.

**문제**: 주문 편집 화면은 ``structured_data['source'] == 'NAVER_SMARTSTORE'`` 일 때만
네이버 원본 도크를 렌더하고(``foms/web/orders/edit.py``), 붙이기가 기록한 추가결제
(``pricing.extra_payments``)를 읽는 코드는 그 도크 하나뿐이다
(``naver_commerce/dock.py._extra_payment_summary``). 대시보드의 채널 취급도 같은 표식을
본다(``foms/services/orders/dashboard_read_model.py``). 그래서 표식이 없으면 **붙이기는
성공했는데 사람이 볼 자리가 없다.**

표식이 사라진 경로는 둘이었고 둘 다 코드에서 고쳤다:

1. ``attach_link_to_order`` 가 표식을 안 찍었다 → ``promotion._stamp_source_marker`` 추가.
2. ERP 폼 저장이 표식을 지웠다 — 보존 목록에 없었고 allowlist 는 빠진 옛 키를 되살리지
   않아 로그조차 남지 않았다 → ``_OPERATIONAL_TOP_LEVEL_KEYS`` 에 ``source``·``naver``·
   ``pricing`` 추가.

**코드 수정만으로는 이미 잃은 주문이 돌아오지 않는다.** 이 스크립트가 그 몫이다.
2026-08-24 스테이징 실측: 네이버 링크가 붙은 주문 9건 중 ERP 편집 흔적이 있는 5건이 전부
표식을 잃었고(편집이 없던 4건은 전부 보존), 그중 주문 4485 는 REPAY 6건·1,610,780원이
기록돼 있는데 화면에 아무것도 없었다.

대상: ``external_order_links.channel='NAVER'`` 링크가 하나 이상 붙어 있고
``structured_data->>'source'`` 가 비어 있는 살아 있는 주문. 조회는 인덱스
``ix_external_order_link_order``(order_id) 를 타며 JSONB 스캔이 없다.

**있는 값은 덮지 않는다** — 다른 채널 표식을 네이버로 바꾸면 그 주문의 출처가 거짓이 된다.
비어 있는 주문에만 찍으므로 재실행하면 ``written=0`` 이어야 정상이다(멱등).

기본은 ``--dry-run``(집계만). 실제로 쓰려면 ``--execute`` 를 명시한다. JSONB 쓰기는
프로젝트 규칙대로 ``copy.deepcopy`` + ``flag_modified`` 를 쓰고 배치마다 중간 커밋한다.

사용법::

    python tools/ops/backfill_naver_source_marker.py --dry-run
    python tools/ops/backfill_naver_source_marker.py --execute
    python tools/ops/backfill_naver_source_marker.py --dry-run   # 재실행: 0건이어야 정상
"""
from __future__ import annotations

import argparse
import copy
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from sqlalchemy.orm import Session, sessionmaker  # noqa: E402
from sqlalchemy.orm.attributes import flag_modified  # noqa: E402

from db import engine  # noqa: E402
from foms.services.integrations.naver_commerce.constants import (  # noqa: E402
    CHANNEL,
    SOURCE_MARKER,
)
from models import ExternalOrderLink, Order  # noqa: E402

DEFAULT_BATCH_SIZE = 200


def _candidate_order_ids(session: Session) -> list[int]:
    """네이버 링크가 붙은 살아 있는 주문 id (인덱스 조회, JSONB 스캔 없음).

    Args:
        session: DB 세션.

    Returns:
        주문 id 목록(오름차순).
    """
    rows = (
        session.query(ExternalOrderLink.order_id)
        .filter(ExternalOrderLink.channel == CHANNEL,
                ExternalOrderLink.order_id.isnot(None))
        .distinct()
        .all()
    )
    return sorted({int(row[0]) for row in rows})


def run_backfill(session: Session, *, execute: bool = False,
                 batch_size: int = DEFAULT_BATCH_SIZE) -> dict:
    """표식이 빈 주문에만 ``source`` 를 찍는다.

    Args:
        session: DB 세션.
        execute: True 면 실제로 쓴다. False(기본)면 집계만 한다.
        batch_size: 중간 커밋 간격.

    Returns:
        ``{"candidates", "written", "already_marked", "other_source", "gone",
        "written_order_ids"}``.
    """
    summary = {"candidates": 0, "written": 0, "already_marked": 0,
               "other_source": 0, "gone": 0, "written_order_ids": []}
    pending = 0
    for order_id in _candidate_order_ids(session):
        summary["candidates"] += 1
        order = session.get(Order, order_id)
        if order is None or order.deleted_at is not None or order.status == "DELETED":
            summary["gone"] += 1
            continue
        data = order.structured_data
        current = data.get("source") if isinstance(data, dict) else None
        if current == SOURCE_MARKER:
            summary["already_marked"] += 1
            continue
        if current:
            # 다른 채널이 자기 출처를 적어 둔 주문 — 손대지 않는다.
            summary["other_source"] += 1
            continue
        summary["written"] += 1
        summary["written_order_ids"].append(order_id)
        if not execute:
            continue
        updated = copy.deepcopy(data) if isinstance(data, dict) else {}
        updated["source"] = SOURCE_MARKER
        order.structured_data = updated
        flag_modified(order, "structured_data")
        pending += 1
        if pending >= batch_size:
            session.commit()
            pending = 0
    if execute and pending:
        session.commit()
    return summary


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """CLI 인자 파싱 — 기본 dry-run, ``--execute`` 로만 실제 쓰기."""
    parser = argparse.ArgumentParser(
        description="Backfill structured_data['source'] for NAVER-linked orders "
                    "(default: dry-run).")
    parser.add_argument("--dry-run", action="store_true",
                        help="Explicit dry-run alias (default behavior).")
    parser.add_argument("--execute", action="store_true",
                        help="Actually write markers. Without this, count only.")
    parser.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """CLI entrypoint. Exit 0 on success, 1 on misuse."""
    args = _parse_args(argv)
    if args.dry_run and args.execute:
        print("[ERROR] --dry-run and --execute are mutually exclusive")
        return 1

    Session = sessionmaker(bind=engine)
    session = Session()
    try:
        summary = run_backfill(session, execute=args.execute, batch_size=args.batch_size)
    finally:
        session.close()

    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
