"""재결제(REPAY)가 붙은 주문 중 **살아 있는 옛 네이버 주문**이 있는지 점검한다.

2026-08-28 NVREPAY-01 후속. 워크벤치 관계 블록의 S2·S3 문구("옛 주문이 아직 살아
있습니다")는 **살아 있는 ``NEW`` 원 주문**이 있어야 뜬다. 그런데 그 표본은 운영에서
드물게 생기고, 생겼을 때 담당자가 네이버에서 옛 주문을 정리해야 한다. 이 스크립트는
그 상태를 **읽기 전용**으로 훑어서 "지금 정리할 옛 주문이 있는가"를 한 줄로 답한다.

판정은 화면과 **같은 코드**(:func:`order_candidates.origin_facts`)를 호출해서 낸다 —
술어를 두 벌로 쓰면 화면과 점검이 갈린다.

사용법::

    # DSN 을 환경변수로 주는 방식(권장 — 저장소에 비밀값을 두지 않는다)
    set FOMS_CHECK_DSN=postgresql://...    # PowerShell: $env:FOMS_CHECK_DSN = "..."
    python tools/ops/check_naver_repay_origin_alive.py

    # railway 가 덤프한 변수 JSON 에서 읽는 방식
    railway variables --service Postgres --json > pgvars.json
    python tools/ops/check_naver_repay_origin_alive.py --vars-json pgvars.json

종료 코드: ``0`` = 살아 있는 옛 주문 없음, ``2`` = 있음(사람이 볼 것), ``1`` = 실행 실패.
쓰기는 하지 않는다 — 세션을 ``default_transaction_read_only`` 로 연다.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

EXIT_NONE_ALIVE = 0
EXIT_FAILED = 1
EXIT_ALIVE_FOUND = 2


def resolve_dsn(vars_json: str | None) -> str:
    """DSN 을 환경변수 또는 railway 변수 덤프에서 고른다.

    Args:
        vars_json: ``railway variables --json`` 출력 파일 경로(없으면 None).

    Returns:
        PostgreSQL DSN 문자열.

    Raises:
        SystemExit: 어느 경로로도 DSN 을 못 찾은 경우.
    """
    dsn = os.environ.get("FOMS_CHECK_DSN") or os.environ.get("DATABASE_URL")
    if dsn:
        return dsn
    if vars_json:
        with open(vars_json, encoding="utf-8") as handle:
            data = json.load(handle)
        dsn = data.get("DATABASE_PUBLIC_URL") or data.get("DATABASE_URL")
        if dsn:
            return dsn
    raise SystemExit("DSN 을 찾지 못했습니다. FOMS_CHECK_DSN 환경변수나 --vars-json 을 주세요.")


def collect(dsn: str) -> list[dict[str, Any]]:
    """재결제가 붙은 주문마다 옛 주문 사실을 모은다.

    Args:
        dsn: 읽기 전용으로 열 DB DSN.

    Returns:
        주문별 판정 목록. 각 항목은
        ``{order_id, customer_name, status, claim_code, claim_label, alive_rows}``.
    """
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from foms.services.integrations.naver_commerce.order_candidates import origin_facts
    from models import ExternalOrderLink, Order

    engine = create_engine(
        dsn, connect_args={"options": "-c default_transaction_read_only=on"})
    session = sessionmaker(bind=engine)()
    try:
        order_ids = [row[0] for row in session.query(ExternalOrderLink.order_id)
                     .filter(ExternalOrderLink.relation == "REPAY",
                             ExternalOrderLink.order_id.isnot(None)).distinct().all()]
        results: list[dict[str, Any]] = []
        for order_id in sorted(order_ids):
            order = session.get(Order, order_id)
            links = session.query(ExternalOrderLink.id, ExternalOrderLink.external_order_no,
                                  ExternalOrderLink.relation, ExternalOrderLink.created_at) \
                .filter(ExternalOrderLink.order_id == order_id).all()
            # 지금 보고 있는 집(= 재결제 집)의 링크는 전부 뺀다 — 화면과 같은 규칙이다.
            repay_nos = {no for (_id, no, rel, _c) in links if rel == "REPAY"}
            exclude = {lid for (lid, no, _rel, _c) in links if no in repay_nos}
            since = max((c for (_i, no, _r, c) in links if no in repay_nos and c), default=None)
            facts = origin_facts(session, order_id, exclude_link_ids=exclude, since_at=since)
            results.append({
                "order_id": order_id,
                "customer_name": getattr(order, "customer_name", None),
                "status": getattr(order, "status", None),
                "link_count": facts["link_count"],
                "claim_code": facts["claim_code"],
                "claim_label": facts["claim_label"],
                "alive_rows": facts["alive_rows"],
            })
        return results
    finally:
        session.close()


def main() -> int:
    """점검을 실행하고 사람이 읽는 요약과 종료 코드를 낸다."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--vars-json", help="railway variables --json 출력 파일 경로")
    parser.add_argument("--json", action="store_true", help="결과를 JSON 으로만 출력")
    args = parser.parse_args()

    try:
        results = collect(resolve_dsn(args.vars_json))
    except SystemExit:
        raise
    except Exception as exc:  # 점검 실패는 '없음'과 구별돼야 한다
        print(f"[NVREPAY-CHECK] 실패: {exc}", file=sys.stderr)
        return EXIT_FAILED

    alive = [row for row in results if row["alive_rows"]]
    if args.json:
        print(json.dumps({"repay_orders": len(results), "alive_orders": len(alive),
                          "rows": results}, ensure_ascii=False, default=str))
        return EXIT_ALIVE_FOUND if alive else EXIT_NONE_ALIVE

    print(f"[NVREPAY-CHECK] 재결제 붙은 주문 {len(results)}건 · "
          f"살아 있는 옛 주문이 있는 주문 {len(alive)}건")
    for row in alive:
        for alive_row in row["alive_rows"]:
            action = "반품(발송 후)" if alive_row.get("dispatched") else "취소(발송 전)"
            print(f"  주문 #{row['order_id']} {row['customer_name']} — 옛 주문 "
                  f"{alive_row['external_order_no']} · 상품주문 "
                  f"{alive_row['product_order_count']}건 · "
                  f"{alive_row['amount_total']:,}원 → 네이버에서 {action} 필요"
                  f"{' · 새 결제 뒤로 미확인' if alive_row.get('stale') else ''}")
    if not alive:
        print("  살아 있는 옛 주문 없음 — 지금 네이버에서 정리할 건이 없습니다.")
    return EXIT_ALIVE_FOUND if alive else EXIT_NONE_ALIVE


if __name__ == "__main__":
    sys.exit(main())
