"""PARTNER-04 백필: 이미 있는 협력사 주문의 담당을 주문을 올린 협력사 직원으로 옮긴다.

2026-10-11 전 협력사 주문은 담당이 "협력사를 맡는 우리 영업 직원"(``partner_orgs.owner_user_id``)이었다.
새 규칙(스펙 docs/specs/2026-10-08-partner-portal_SPEC.md §16)은 담당 = 등록한 협력사 직원
(``partner_intake.submitted_by_user_id``)이다. 앱과 같은 함수(:func:`reassign_partner_order`)로 바꾼다 —
SALES 배정 교체(앞 담당은 비활성 이력) · 담당 칸(``이름 (회사명)`` · 연락처) · quest owner · manager_name.

기본은 dry-run(무엇을 몇 건 바꿀지만 출력). ``--apply`` 를 줘야 쓴다. 주문마다 커밋하고, 이미 맞는 주문은
건너뛰므로 다시 돌려도 남은 것만 바꾼다(멱등). 등록한 직원이 없거나 꺼진 계정이면 건드리지 않고 보고한다.

사용:
    python tools/ops/backfill_partner_order_manager.py --dsn "$DSN"
    python tools/ops/backfill_partner_order_manager.py --dsn "$DSN" --apply
"""

from __future__ import annotations

import argparse
import os
import sys
from typing import Any

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from sqlalchemy import create_engine, select  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from foms.services.db_url_resolver import sqlalchemy_url  # noqa: E402
from foms.services.orders.revision import lock_order_row  # noqa: E402
from foms.services.partners.manager import manager_party, reassign_partner_order  # noqa: E402
from models import Order, OrderAssignment, PartnerOrg, User  # noqa: E402

REASON = "협력사 담당 규칙 변경 백필(담당 = 등록한 협력사 직원)"


def _plan(session: Session) -> list[dict[str, Any]]:
    """협력사 주문마다 (지금 담당, 옮길 담당, 판정)을 만든다."""
    orders = session.execute(
        select(Order).where(Order.partner_org_id.isnot(None), Order.deleted_at.is_(None)).order_by(Order.id)
    ).scalars().all()
    orgs = {o.id: o for o in session.execute(select(PartnerOrg)).scalars().all()}
    plan = []
    for order in orders:
        intake = (order.structured_data or {}).get("partner_intake") or {}
        target = session.get(User, intake.get("submitted_by_user_id")) if intake.get("submitted_by_user_id") else None
        owner = session.execute(
            select(OrderAssignment.user_id).where(
                OrderAssignment.order_id == order.id, OrderAssignment.domain == "SALES",
                OrderAssignment.active.is_(True))
        ).scalar()
        org = orgs.get(order.partner_org_id)
        if target is None or not target.is_active or target.partner_org_id != order.partner_org_id:
            verdict = "SKIP_NO_ACTIVE_SUBMITTER"
        elif owner == target.id and ((order.structured_data or {}).get("parties") or {}).get("manager") == \
                manager_party(target, org):
            verdict = "ALREADY_OK"
        else:
            verdict = "CHANGE"
        plan.append({"order_id": order.id, "org": org.name if org else None, "owner_user_id": owner,
                     "target_user_id": target.id if target else None, "verdict": verdict})
    return plan


def backfill(session: Session, *, apply: bool) -> dict[str, Any]:
    """열린 세션으로 백필(또는 dry-run)한다. 반환은 판정별 건수와 줄 목록. 바꾼 주문마다 commit 한다."""
    plan = _plan(session)
    if apply:
        for row in plan:
            if row["verdict"] != "CHANGE":
                continue
            order = lock_order_row(session, row["order_id"])
            target = session.get(User, row["target_user_id"])
            org = session.get(PartnerOrg, order.partner_org_id)
            reassign_partner_order(session, order, target, org, actor_user_id=target.id, reason=REASON)
            session.commit()
            row["verdict"] = "CHANGED"
    counts: dict[str, int] = {}
    for row in plan:
        counts[row["verdict"]] = counts.get(row["verdict"], 0) + 1
    return {"counts": counts, "rows": plan}


def run(dsn: str, *, apply: bool) -> dict[str, Any]:
    """DSN 으로 접속해 :func:`backfill` 을 돌린다."""
    engine = create_engine(sqlalchemy_url(dsn), future=True)
    with Session(engine) as session:
        return backfill(session, apply=apply)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("--dsn", default=os.environ.get("DATABASE_URL"), help="PostgreSQL 접속 문자열")
    parser.add_argument("--apply", action="store_true", help="실제로 바꾼다(기본 dry-run)")
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")  # PS-ENC-01: Windows cp949 콘솔에서도 한글 출력
    if not args.dsn:
        print("--dsn 또는 DATABASE_URL 이 필요합니다.", file=sys.stderr)
        return 2
    result = run(args.dsn, apply=args.apply)
    for row in result["rows"]:
        print(f"#{row['order_id']} [{row['org']}] {row['owner_user_id']} -> {row['target_user_id']}: {row['verdict']}")
    print(("APPLY" if args.apply else "DRY-RUN"), result["counts"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
