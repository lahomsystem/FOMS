"""
Phase C 5.5: lat/lng가 NULL인 기존 주문에 geocode job enqueue.

전제: migrations/versions/add_geocode_columns_to_orders.py 마이그레이션 적용 완료.

사용법:
  python scripts/maintenance/geocode_backfill.py [--dry-run] [--limit N] [--delay SEC]

환경변수:
  USE_RQ_WORKER=1, REDIS_URL 필요 (미설정 시 enqueue 실패).

예:
  python scripts/maintenance/geocode_backfill.py --dry-run
  python scripts/maintenance/geocode_backfill.py --limit 50 --delay 2
"""
import sys
import os
import time
import argparse

# Repo root (was one level up from scripts/; now scripts/maintenance/)
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from app import app  # noqa: F401 — 서비스 모듈 import 순서 보장(단독 실행 시 foms.services 순환 import 회피)
from db import db_session
from models import Order
from foms.services.geocode_helpers import extract_address_from_order
from foms.services.measurement_read_model import apply_measurement_dashboard_order_scope


def get_orders_needing_geocode(limit=None):
    """
    lat 또는 lng가 NULL인 주문 중 주소가 있는 것 반환.
    DELETED 제외. 지도 대상 범위는 실측 대시보드 SSOT(apply_measurement_dashboard_order_scope)와
    동일 — 지방주문(is_regional) 포함(3471502a에서 지도 범위가 확장됨, 구 제외 필터는 낡은 스코프).
    """
    db = db_session()
    query = (
        db.query(Order)
        .filter(Order.active_filter())
        .filter(
            (Order.lat.is_(None)) | (Order.lng.is_(None))
        )
    )
    query = apply_measurement_dashboard_order_scope(query).order_by(Order.id.desc())
    if limit:
        query = query.limit(limit)
    try:
        return query.all()
    finally:
        db.close()
        db_session.remove()


def main():
    parser = argparse.ArgumentParser(description="Phase C: Geocode backfill - enqueue jobs for orders without lat/lng")
    parser.add_argument('--dry-run', action='store_true', help="Enqueue하지 않고 대상 건수만 출력")
    parser.add_argument('--limit', type=int, default=None, help="처리할 최대 주문 수 (기본: 전체)")
    parser.add_argument('--delay', type=float, default=0.5, help="배치 간 대기 초 (rate limit, 기본 0.5)")
    args = parser.parse_args()

    orders = get_orders_needing_geocode(limit=args.limit)
    to_enqueue = []
    for o in orders:
        addr = extract_address_from_order(o)
        if addr and addr.strip() and addr.strip() != '-':
            to_enqueue.append(o.id)

    print(f"lat/lng NULL인 주문: {len(orders)}건, 주소 있는 건: {len(to_enqueue)}건")

    if args.dry_run:
        if to_enqueue:
            print(f"[DRY-RUN] enqueue 대상 order_ids (최대 20개 표시): {to_enqueue[:20]}{'...' if len(to_enqueue) > 20 else ''}")
        return

    if not to_enqueue:
        print("처리할 주문이 없습니다.")
        return

    try:
        from importlib import import_module
        from foms.services.jobs.queue import enqueue_geocode_order_address
    except ImportError as e:
        print(f"Import 실패: {e}")
        return

    q = import_module("foms.services.jobs.queue").get_rq_queue()
    if not q:
        print("RQ 비활성화 상태입니다. USE_RQ_WORKER=1, REDIS_URL을 설정한 뒤 실행하세요.")
        return

    enqueued = 0
    failed = 0
    for i, oid in enumerate(to_enqueue):
        try:
            if enqueue_geocode_order_address(oid):
                enqueued += 1
                if (enqueued % 20) == 0:
                    print(f"  enqueued {enqueued}/{len(to_enqueue)}...")
            else:
                failed += 1
        except Exception as e:
            failed += 1
            print(f"  order_id={oid} enqueue 실패: {e}")
        if args.delay > 0 and i < len(to_enqueue) - 1:
            time.sleep(args.delay)

    print(f"완료: enqueued={enqueued}, failed={failed}")


if __name__ == '__main__':
    main()
