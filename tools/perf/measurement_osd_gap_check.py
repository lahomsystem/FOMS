"""정식 실측일이 일정표(order_schedule_dates)에 빠진 주문을 센다 — 읽기 전용.

실측 화면의 보충 술어에서 ``CAST(structured_data AS VARCHAR) ILIKE`` 가지를 뺀 근거를
데이터로 다시 확인하는 도구다(2026-10-01 전체 성능 검사, 원장
``docs/plans/2026-10-01-full-perf-audit-ledger.md`` P1-1). 그 가지가 실제로 더해 줄 수
있던 것은 "정식 실측일(:func:`extract_all_measurement_dates` 의 JSON·legacy 원천)이 일정표에
없는 주문" 뿐이다. 그런 주문이 있으면 평평한 컬럼 안전망(``measurement_date`` ILIKE ·
``erp_measurement_date`` 일치)에 걸리는지도 같이 센다.

사용::

    FOMS_READONLY_DSN=postgresql://... python tools/perf/measurement_osd_gap_check.py
    python tools/perf/measurement_osd_gap_check.py --neg-control 3   # 검출기 음성 대조군

DSN 은 env 로만 받는다(인자·파일 금지). 세션은 읽기 전용으로 연다.
"""

from __future__ import annotations

import argparse
import collections
import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from foms.services.measurement_dates import extract_all_measurement_dates  # noqa: E402


def find_gaps(rows, osd_by_order):
    """일정표에 빠진 정식 실측일을 가진 주문 목록.

    Args:
        rows: ``(id, is_erp_order, measurement_date, erp_measurement_date, structured_data,
            status, deleted_at)`` 튜플들.
        osd_by_order: ``{order_id: {날짜, ...}}`` (kind='measurement').

    Returns:
        ``[(order_id, status, deleted_at, 빠진 날짜들, 안전망에 걸리는 날짜들), ...]``.
    """
    gaps = []
    for oid, is_erp, mdate, emd, sd, status, deleted_at in rows:
        if isinstance(sd, str):
            try:
                sd = json.loads(sd)
            except ValueError:
                sd = {}
        order = SimpleNamespace(id=oid, is_erp_order=is_erp, measurement_date=mdate,
                                structured_data=sd if isinstance(sd, dict) else {},
                                schedule_dates=[])
        canonical = set(extract_all_measurement_dates(order))
        missing = sorted(d for d in canonical if d not in osd_by_order.get(oid, set()))
        if missing:
            caught = [d for d in missing if (mdate and d in str(mdate)) or emd == d]
            gaps.append((oid, status, deleted_at, missing, caught))
    return gaps


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--neg-control", type=int, default=0,
                        help="일정표 행이 있는 주문 N건의 일정표를 메모리에서 지우고 검출되는지 본다")
    args = parser.parse_args(argv)
    dsn = os.environ.get("FOMS_READONLY_DSN", "").strip()
    if not dsn:
        print("FOMS_READONLY_DSN 이 비어 있다", file=sys.stderr)
        return 2

    import psycopg

    conn = psycopg.connect(dsn, connect_timeout=20, application_name="foms_osd_gap_check_readonly",
                           options="-c statement_timeout=60000 -c default_transaction_read_only=on")
    conn.read_only = True
    try:
        cur = conn.cursor()
        cur.execute("select current_setting('transaction_read_only')")
        if cur.fetchone()[0] != "on":
            print("읽기 전용 세션이 아니다 — 중단", file=sys.stderr)
            return 3
        cur.execute("select id, is_erp_order, measurement_date, erp_measurement_date, structured_data, "
                    "status, deleted_at from orders")
        rows = cur.fetchall()
        cur.execute("select order_id, date from order_schedule_dates where kind = 'measurement'")
        osd = collections.defaultdict(set)
        for order_id, date_value in cur.fetchall():
            osd[order_id].add(date_value)
    finally:
        conn.rollback()
        conn.close()

    if args.neg_control:
        dropped = list(osd)[: args.neg_control]
        for order_id in dropped:
            osd.pop(order_id)
        print(f"음성 대조군: 일정표를 지운 주문 {dropped}")

    gaps = find_gaps(rows, osd)
    lost = [g for g in gaps if set(g[3]) - set(g[4])]
    print(f"주문 {len(rows)}건 · 일정표 있는 주문 {len(osd)}건")
    print(f"정식 실측일이 일정표에 빠진 주문: {len(gaps)}건")
    print(f"그중 평평한 컬럼 안전망에도 안 걸리는 주문: {len(lost)}건")
    for gap in gaps[:50]:
        print(gap)
    return 1 if lost else 0


if __name__ == "__main__":
    sys.exit(main())
