#!/usr/bin/env python3
"""
3월 16일 필터 시 2건 미표시 진단.
이미주 등 검색하면 나오지만 날짜만 선택 시 안 나오는 주문의 OrderScheduleDate.date 형식 확인.

실행: DATABASE_URL 설정 후 python scripts/maintenance/diagnose_measurement_date_missing.py
"""
import os
import sys

sys.path.insert(
    0,
    os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")),
)

from sqlalchemy import create_engine, text
from urllib.parse import urlparse, urlunparse, quote, unquote


def _get_db_url():
    url = os.environ.get("RAILWAY_PUBLIC_DATABASE_URL") or os.environ.get("DATABASE_URL")
    if not url:
        print("DATABASE_URL 또는 RAILWAY_PUBLIC_DATABASE_URL 필요")
        sys.exit(1)
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]
    if "postgresql://" in url and "+psycopg2" not in url:
        url = url.replace("postgresql://", "postgresql+psycopg2://", 1)
    return url


def main():
    engine = create_engine(_get_db_url())

    with engine.connect() as conn:
        # 1) '이미주' 포함 주문 중 measurement 3월 16일 관련
        print("\n=== 1) '이미주' 검색 시 나오는 주문의 OrderScheduleDate (measurement) ===\n")
        r = conn.execute(text("""
            SELECT o.id, o.customer_name, o.status, osd.date AS osd_date,
                   length(osd.date) AS date_len, encode(osd.date::bytea, 'hex') AS date_hex
            FROM orders o
            JOIN order_schedule_dates osd ON o.id = osd.order_id AND osd.kind = 'measurement'
            WHERE (o.customer_name ILIKE '%이미주%' OR o.structured_data::text ILIKE '%이미주%')
              AND o.deleted_at IS NULL
            ORDER BY o.id DESC
        """))
        for row in r:
            print(dict(row._mapping))

        # 2) 3월 16일 해당 전체 OrderScheduleDate.date 값 종류 (실제 저장 형식)
        print("\n=== 2) measurement 3월 16일 해당 date 컬럼 실제 값 (DISTINCT) ===\n")
        r = conn.execute(text("""
            SELECT DISTINCT date, length(date) AS len,
                   date = '2026-03-16' AS eq_std,
                   date = '2026-3-16' AS eq_compact
            FROM order_schedule_dates
            WHERE kind = 'measurement'
              AND (date LIKE '2026%03%16%' OR date LIKE '2026%3%16%')
            ORDER BY date
        """))
        for row in r:
            print(dict(row._mapping))

        # 3) 2026-03-16 매칭 주문 수 (쿼리 조건과 동일)
        print("\n=== 3) date='2026-03-16' 매칭 주문 수 ===\n")
        r = conn.execute(text("""
            SELECT COUNT(DISTINCT o.id) AS cnt
            FROM orders o
            JOIN order_schedule_dates osd ON o.id = osd.order_id
            WHERE osd.kind = 'measurement' AND osd.date = '2026-03-16'
              AND o.deleted_at IS NULL
              AND ((o.is_regional IS NOT TRUE AND o.status NOT IN ('SELF_MEASUREMENT','SELF_MEASURED'))
                   OR o.is_self_measurement = TRUE)
        """))
        row = r.fetchone()
        try:
            print(dict(row._mapping) if row else None)
        except (TypeError, AttributeError):
            print({"cnt": row[0]} if row else None)

        # 4) 3월 16일 '비슷한' date를 가진 주문 (다른 형식 탐지)
        print("\n=== 4) 2026년 3월 16일로 보이는 모든 date (다른 형식) ===\n")
        r = conn.execute(text("""
            SELECT DISTINCT date FROM order_schedule_dates
            WHERE kind = 'measurement'
              AND regexp_replace(date, '[^0-9]', '', 'g') LIKE '20260316%'
        """))
        for row in r:
            print(row[0], repr(row[0]))

        # 5) manager_name: manager_filter 적용 시 담당자 불일치하면 build_measurement_snapshot에서 제외
        print("\n=== 5) 3/16 해당 주문의 manager_name (담당자 필터 확인) ===\n")
        r = conn.execute(text("""
            SELECT o.id, o.customer_name,
                   COALESCE((o.structured_data->'parties'->'manager'->>'name'), o.manager_name, '-') AS manager_name
            FROM orders o
            JOIN order_schedule_dates osd ON o.id = osd.order_id
            WHERE osd.kind = 'measurement' AND osd.date = '2026-03-16'
              AND o.deleted_at IS NULL
              AND ((o.is_regional IS NOT TRUE AND o.status NOT IN ('SELF_MEASUREMENT','SELF_MEASURED'))
                   OR o.is_self_measurement = TRUE)
            ORDER BY o.id DESC
        """))
        for row in r:
            print(dict(row._mapping))

        # 6) lat/lng
        print("\n=== 6) 3/16 해당 주문의 lat/lng ===\n")
        r = conn.execute(text("""
            SELECT o.id, o.customer_name, o.lat, o.lng, o.geocode_status, o.address
            FROM orders o
            JOIN order_schedule_dates osd ON o.id = osd.order_id
            WHERE osd.kind = 'measurement' AND osd.date = '2026-03-16'
              AND o.deleted_at IS NULL
              AND ((o.is_regional IS NOT TRUE AND o.status NOT IN ('SELF_MEASUREMENT','SELF_MEASURED'))
                   OR o.is_self_measurement = TRUE)
            ORDER BY (o.lat IS NULL OR o.lng IS NULL) DESC, o.id DESC
        """))
        no_coords = []
        for row in r:
            d = dict(row._mapping)
            if d.get('lat') is None or d.get('lng') is None:
                no_coords.append(d['id'])
            print(d)
        if no_coords:
            print(f"\n>>> 좌표 없음(지도 미표시): {no_coords}")

        # 7) self_measurement_four_checks_done
        print("\n=== 7) self_measurement_four_checks_done 제외 여부 ===\n")
        r = conn.execute(text("""
            SELECT o.id, o.customer_name, o.is_self_measurement,
                   o.measurement_completed, o.regional_sales_order_upload,
                   o.regional_blueprint_sent, o.regional_order_upload,
                   (o.is_self_measurement AND o.measurement_completed AND o.regional_sales_order_upload
                    AND o.regional_blueprint_sent AND o.regional_order_upload) AS four_done
            FROM orders o
            JOIN order_schedule_dates osd ON o.id = osd.order_id
            WHERE osd.kind = 'measurement' AND osd.date = '2026-03-16'
              AND o.deleted_at IS NULL
              AND ((o.is_regional IS NOT TRUE AND o.status NOT IN ('SELF_MEASUREMENT','SELF_MEASURED'))
                   OR o.is_self_measurement = TRUE)
            ORDER BY o.id DESC
        """))
        for row in r:
            d = dict(row._mapping)
            print(d)


if __name__ == "__main__":
    main()
