"""GEO-BACKFILL-01 — 좌표 없는 주문 지오코딩 백필 CLI (operator maintenance).

주소→좌표 변환은 주문 생성/수정(`enqueue_order_address_geocode`)과 지도 열람
(`/api/map_data?enqueue=1`)에서만 걸린다. 그 계보가 생기기 전에 들어온 주문은
`lat/lng`가 비어 있고 `geocode_status`도 NULL(=한 번도 시도 안 함)로 남는다.
2026-08-10 운영 확인: `lat IS NULL` 217건 중 182건이 미시도였고, 그 때문에
실측 동선 스트립이 "실측 10곳 / 동선 4곳"처럼 조용히 비었다.

    # 대상만 세기(기본·쓰기 없음)
    python tools/ops/backfill_geocode_missing.py

    # 워커에 위임(운영 권장 — 쓰기는 RQ worker 가 한다)
    python tools/ops/backfill_geocode_missing.py --apply --mode enqueue --limit 200

    # 이 프로세스에서 직접 변환(워커 없는 환경/로컬)
    python tools/ops/backfill_geocode_missing.py --apply --mode sync --limit 50

기본은 미시도(`geocode_status IS NULL`)만 대상으로 한다. `failed` 재시도는
`--include-failed`로 명시해야 한다(주소 자체가 틀린 건이 대부분이라 반복 호출은
쿼터만 태운다). exit 0=성공, 그 외=비정상.
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from sqlalchemy import or_  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from db import engine  # noqa: E402
from models import Order  # noqa: E402

# 동기 모드에서 카카오 지오코딩 API 를 연타하지 않도록 건당 최소 간격(초).
SYNC_SLEEP_SEC = 0.15


def _candidate_query(session, include_failed: bool):
    """좌표 없는 주문 쿼리 (활성 주문만, 주소 있는 건만)."""
    query = session.query(Order).filter(
        Order.active_filter(),
        or_(Order.lat.is_(None), Order.lng.is_(None)),
        Order.address.isnot(None),
        Order.address != '',
        Order.address != '-',
    )
    if include_failed:
        return query.filter(
            or_(Order.geocode_status.is_(None), Order.geocode_status == 'failed')
        )
    return query.filter(Order.geocode_status.is_(None))


def _run_enqueue(orders: list[Order]) -> tuple[int, int]:
    """RQ 큐에 `geocode_order_address` 를 넣는다. 반환 `(성공, 실패)`."""
    from foms.services.jobs.queue import enqueue_geocode_order_address

    queued = failed = 0
    for order in orders:
        if enqueue_geocode_order_address(order.id):
            queued += 1
        else:
            failed += 1
    return queued, failed


def _run_sync(orders: list[Order]) -> tuple[int, int]:
    """이 프로세스에서 직접 변환한다(워커 부재 환경). 반환 `(성공, 실패)`."""
    from foms.services.jobs.tasks import geocode_order_address

    done = failed = 0
    for order in orders:
        try:
            geocode_order_address(order.id)
            done += 1
        except Exception as exc:  # noqa: BLE001 - 한 건 실패로 배치를 멈추지 않는다
            failed += 1
            print(f"  ! order {order.id} 실패: {exc}", file=sys.stderr)
        time.sleep(SYNC_SLEEP_SEC)
    return done, failed


def main() -> int:
    """CLI 진입점. 반환값이 프로세스 exit code."""
    parser = argparse.ArgumentParser(description="좌표 없는 주문 지오코딩 백필")
    parser.add_argument('--apply', action='store_true', help="실제 실행(미지정 시 집계만)")
    parser.add_argument('--mode', choices=('enqueue', 'sync'), default='enqueue',
                        help="enqueue=RQ 워커 위임(기본), sync=이 프로세스에서 직접 변환")
    parser.add_argument('--limit', type=int, default=100, help="한 번에 처리할 최대 건수")
    parser.add_argument('--include-failed', action='store_true',
                        help="geocode_status='failed' 건도 재시도 대상에 포함")
    args = parser.parse_args()

    session = sessionmaker(bind=engine)()
    try:
        query = _candidate_query(session, args.include_failed)
        total = query.count()
        orders = query.order_by(Order.id.desc()).limit(max(1, args.limit)).all()
        print(f"대상 {total}건 (이번 실행 {len(orders)}건, mode={args.mode})")
        if not args.apply:
            for order in orders[:10]:
                print(f"  - #{order.id} {order.customer_name} / {order.address}")
            print("dry-run (쓰기 없음). 실행하려면 --apply")
            return 0

        if args.mode == 'enqueue':
            ok, failed = _run_enqueue(orders)
            print(f"큐 등록 {ok}건, 등록 실패 {failed}건 (실제 좌표 기록은 worker 담당)")
        else:
            ok, failed = _run_sync(orders)
            print(f"변환 완료 {ok}건, 실패 {failed}건")
        return 0 if failed == 0 else 1
    finally:
        session.close()


if __name__ == '__main__':
    raise SystemExit(main())
