"""실측 전에 들어와 도면 단계에 있는 협력사 주문을 '실측 예정'(MEASURE)으로 되돌린다(사용자 승인 2026-11-01).

2026-10-28 ~ 11-01 에는 협력사 주문이 저장하면 바로 도면 단계였다. 협력사가 실측 전에 미리 올린 주문(실측일이
등록일보다 뒤 · 가로 치수 없음)이 도면팀 큐에 섞였다. 새 규칙(docs/specs/2026-11-01-partner-measure-pending_SPEC.md
§4.7)에 맞춰 단계 강제 변경 경로(:func:`apply_stage_override`, regress)로 MEASURE 로 옮기고, 주관 팀 CS ·
``measurement_completed=False`` · 열린 도면 quest 를 실측 quest 로 바꾼다. 이미 나간 빈 영발 기록은 건드리지 않는다 —
도면 요청 때 "[실측 완료]" 재전송이 된다.

주문마다 조건을 다시 본다: 협력사 주문 · 도면 단계 · 보낸 도면 0 · 도면 담당 없음 · 가로 치수 0칸 · 실측일이 등록일보다 뒤.
하나라도 어긋나면 건드리지 않는다. 기본은 dry-run, ``--apply`` 때만 쓰고 주문마다 커밋한다(다시 돌려도 남은 것만).

사용(운영은 배포 뒤 ``railway ssh -s web`` 안에서):
    python tools/ops/partner_premeasure_revert.py --actor-user-id <관리자 id>
    python tools/ops/partner_premeasure_revert.py --actor-user-id <관리자 id> --apply
"""

from __future__ import annotations

import argparse
import copy
import os
import sys
from typing import Any

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from sqlalchemy import create_engine, select  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402
from sqlalchemy.orm.attributes import flag_modified  # noqa: E402

from foms.services.db_url_resolver import sqlalchemy_url  # noqa: E402
from foms.services.erp_policy import STAGE_NAME_TO_CODE, create_quest_from_template  # noqa: E402
from foms.services.erp_sync_columns import sync_erp_flat_columns  # noqa: E402
from foms.services.orders.drawing_customer_send import drawing_round_info  # noqa: E402
from foms.services.orders.revision import lock_order_row  # noqa: E402
from foms.services.orders.stage_override import apply_stage_override  # noqa: E402
from foms.services.partners.measure_ready import drawing_request_missing  # noqa: E402
from models import Order, OrderAssignment  # noqa: E402

REASON = "실측 전 등록 — 실측 예정으로(협력사 도면 요청 규칙 2026-11-01)"
_CODE_TO_NAME = {v: k for k, v in STAGE_NAME_TO_CODE.items()}


def _quest_code(quest: Any) -> str:
    stage = str((quest or {}).get("stage") or "")
    return STAGE_NAME_TO_CODE.get(stage, stage).upper()


def verdict_for(session: Session, order: Order) -> str:
    """되돌릴 주문이면 ``REVERT``, 아니면 건너뛰는 까닭."""
    sd = order.structured_data if isinstance(order.structured_data, dict) else {}
    intake = sd.get("partner_intake") if isinstance(sd.get("partner_intake"), dict) else {}
    if (order.erp_stage_code or "").upper() != "DRAWING":
        return "SKIP_NOT_DRAWING"
    if drawing_round_info(sd).transfer_count:
        return "SKIP_DRAWING_SENT"
    drawer = session.execute(select(OrderAssignment.id).where(
        OrderAssignment.order_id == order.id, OrderAssignment.domain == "DRAWING",
        OrderAssignment.active.is_(True))).first()
    if drawer is not None:
        return "SKIP_DRAWER_ASSIGNED"
    measured_on = str(intake.get("measured_on") or "")[:10]
    submitted = str(intake.get("submitted_at") or "")[:10]
    if not measured_on or not submitted or measured_on <= submitted:
        return "SKIP_NOT_PRE_MEASURE"
    widths = [m for m in drawing_request_missing(measured_on, sd.get("items"), today="9999-12-31") if "가로 치수" in m]
    if len(widths) != len(sd.get("items") or []):
        return "SKIP_HAS_WIDTH"
    return "REVERT"


def _revert(session: Session, order: Order, actor_user_id: int) -> None:
    """MEASURE 로 강제 변경(regress) · 주관 CS · 실측 미완 · 열린 도면 quest → 실측 quest."""
    apply_stage_override(order=order, to_stage="MEASURE", reason=REASON, user_id=actor_user_id, db=session)
    sd = copy.deepcopy(order.structured_data or {})
    quests = [q for q in (sd.get("quests") or []) if not (_quest_code(q) == "DRAWING" and q.get("status") == "OPEN")]
    if not any(_quest_code(q) == "MEASURE" and q.get("status") == "OPEN" for q in quests):
        quest = create_quest_from_template(_CODE_TO_NAME.get("MEASURE", "MEASURE"), "", sd)
        if quest:
            quests.append(quest)
    sd["quests"] = quests
    sd.setdefault("assignments", {})["owner_team"] = "CS"
    order.structured_data = sd
    flag_modified(order, "structured_data")
    order.measurement_completed = False
    sync_erp_flat_columns(order, sd)


def revert(session: Session, *, apply: bool, actor_user_id: int) -> dict[str, Any]:
    """열린 세션으로 되돌리기(또는 dry-run). 반환은 판정별 건수와 줄 목록. 바꾼 주문마다 commit 한다."""
    orders = session.execute(
        select(Order).where(Order.partner_org_id.isnot(None), Order.deleted_at.is_(None)).order_by(Order.id)
    ).scalars().all()
    rows = []
    for order in orders:
        intake = (order.structured_data or {}).get("partner_intake") or {}
        rows.append({"order_id": order.id, "customer": order.customer_name,
                     "measured_on": intake.get("measured_on"), "verdict": verdict_for(session, order)})
    if apply:
        for row in rows:
            if row["verdict"] != "REVERT":
                continue
            order = lock_order_row(session, row["order_id"])
            if verdict_for(session, order) != "REVERT":  # 잠근 뒤 다시 본다
                session.rollback()
                row["verdict"] = "SKIP_CHANGED"
                continue
            _revert(session, order, actor_user_id)
            session.commit()
            row["verdict"] = "REVERTED"
    counts: dict[str, int] = {}
    for row in rows:
        counts[row["verdict"]] = counts.get(row["verdict"], 0) + 1
    return {"counts": counts, "rows": rows}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("--dsn", default=os.environ.get("DATABASE_URL"), help="PostgreSQL 접속 문자열")
    parser.add_argument("--actor-user-id", type=int, required=True, help="기록에 남길 본사 관리자 id")
    parser.add_argument("--apply", action="store_true", help="실제로 바꾼다(기본 dry-run)")
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")  # PS-ENC-01: Windows cp949 콘솔에서도 한글 출력
    if not args.dsn:
        print("--dsn 또는 DATABASE_URL 이 필요합니다.", file=sys.stderr)
        return 2
    engine = create_engine(sqlalchemy_url(args.dsn), future=True)
    with Session(engine) as session:
        result = revert(session, apply=args.apply, actor_user_id=args.actor_user_id)
    for row in result["rows"]:
        print(f"#{row['order_id']} {row['customer']} 실측 {row['measured_on'] or '-'}: {row['verdict']}")
    print(("APPLY" if args.apply else "DRY-RUN"), result["counts"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
