"""네이버 수집 주문의 **도크 게이트 표식**(``structured_data['naver_linked']``) 백필 — 1회성.

**2026-08-28 개명·용도 변경**: 예전 이름은 ``backfill_naver_source_marker.py`` 였고
``structured_data['source']`` 에 ``NAVER_SMARTSTORE`` 를 찍었다. 그 키가 뜻 두 개를 지고
있었기 때문이다 — ① 주문 **출처** ② 도크 **렌더 게이트**. 그래서 ERP 에서 직접 등록한
주문(예약금 건)에 이 스크립트가 닿으면 **그 주문이 네이버 출신으로 뒤집혔다**.
2026-08-28 에 둘을 갈랐다(``constants.LINKED_MARKER_KEY``): ``source`` 는 출처 전용이고
작성자는 매핑(네이버가 만든 주문) 하나뿐이며, 도크 게이트는 ``naver_linked`` 가 진다.

**이 스크립트를 옛 형태로 되돌리지 마라.** ``source`` 를 다시 찍으면 이번에 없앤 오염을
그대로 재생산한다 — 설계서 `2026-08-28-naver-repay-origin-cancel_SPEC.md` §7 이 금지한
휴리스틱 출처 추정과 같은 술어다. ``naver_linked`` 는 출처를 주장하지 않으므로 안전하다.

**문제(원래 맥락)**: 주문 편집 화면은 게이트 표식이 있을 때만 네이버 원본 도크를 렌더하고
(``foms/web/orders/edit.py``), 붙이기가 기록한 추가결제(``pricing.extra_payments``)를 읽는
코드는 그 도크 하나뿐이다(``naver_commerce/dock.py._extra_payment_summary``). 그래서 표식이
없으면 **붙이기는 성공했는데 사람이 볼 자리가 없다.**

표식이 사라진 경로는 둘이었고 둘 다 코드에서 고쳤다:

1. ``attach_link_to_order`` 가 표식을 안 찍었다 → ``promotion._stamp_link_marker`` 추가.
2. ERP 폼 저장이 표식을 지웠다 → ``_OPERATIONAL_TOP_LEVEL_KEYS`` 에 보존 키 추가
   (``source``·``naver``·``pricing``·``naver_linked``).

**코드 수정만으로는 이미 잃은 주문이 돌아오지 않는다.** 이 스크립트가 그 몫이다.
2026-08-24 스테이징 실측: 네이버 링크가 붙은 주문 9건 중 ERP 편집 흔적이 있는 5건이 전부
표식을 잃었고(편집이 없던 4건은 전부 보존), 그중 주문 4485 는 REPAY 6건·1,610,780원이
기록돼 있는데 화면에 아무것도 없었다.

대상: ``external_order_links.channel='NAVER'`` 링크가 하나 이상 붙어 있고 ``naver_linked``
가 비어 있는 살아 있는 주문. 조회는 인덱스 ``ix_external_order_link_order``(order_id) 를
타며 JSONB 스캔이 없다. 재실행하면 ``written=0`` 이어야 정상이다(멱등).

기본은 ``--dry-run``(집계만). 실제로 쓰려면 ``--execute`` 를 명시한다. JSONB 쓰기는
프로젝트 규칙대로 ``copy.deepcopy`` + ``flag_modified`` 를 쓰고 배치마다 중간 커밋한다.

사용법::

    python tools/ops/backfill_naver_link_marker.py --dry-run
    python tools/ops/backfill_naver_link_marker.py --execute
    python tools/ops/backfill_naver_link_marker.py --dry-run   # 재실행: 0건이어야 정상
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
    LINKED_MARKER_KEY,
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
        ``{"candidates", "written", "already_marked", "gone", "written_order_ids"}``.
        옛 ``other_source`` 칸은 없앴다 — 게이트 표식은 출처를 보지 않으므로 그 갈래가
        영영 0 이고, 움직이지 않는 계수는 읽는 사람을 속인다.
    """
    summary = {"candidates": 0, "written": 0, "already_marked": 0,
               "gone": 0, "written_order_ids": []}
    pending = 0
    for order_id in _candidate_order_ids(session):
        summary["candidates"] += 1
        order = session.get(Order, order_id)
        if order is None or order.deleted_at is not None or order.status == "DELETED":
            summary["gone"] += 1
            continue
        data = order.structured_data
        if isinstance(data, dict) and data.get(LINKED_MARKER_KEY):
            summary["already_marked"] += 1
            continue
        # 출처(``source``)는 보지도 건드리지도 않는다 — 이 표식은 게이트 전용이라
        # 다른 채널 출처가 적힌 주문에도 그대로 얹을 수 있다.
        summary["written"] += 1
        summary["written_order_ids"].append(order_id)
        if not execute:
            continue
        updated = copy.deepcopy(data) if isinstance(data, dict) else {}
        updated[LINKED_MARKER_KEY] = True
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
