"""Hard-purge soft-deleted, retention-elapsed orders under OPS-APPROVAL (DELETE-RETENTION-01).

    python tools/ops/apply_delete_retention.py \
        --plan-file <approved-plan.json> \
        --approval-token-file <under-control-root>.json \
        --apply

approved plan(:func:`foms.services.orders.delete_retention.build_delete_plan` 산출, admin 이
검토·승인한 것)을 live 상태로 재검증하고, ``DELETE_RETENTION_APPLY`` 승인 토큰(seq≥1 admin
재인증·one-time·control-root)을 소비한 뒤에야 정확히 그 주문들을 물리 삭제한다. 승인 없이
삭제 0, 검증 미통과 삭제 0, soft-delete 아닌 주문 삭제 0. 기본 dry-run — ``--apply`` 일 때만
commit(consume+delete 원자). 실패/dry-run 은 rollback 이라 토큰은 APPROVED 로 남아 재실행이
resume 다.

exit code: 0 성공(dry-run·apply), 1 오류(검증 실패·승인 위반·드리프트 포함).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from sqlalchemy import text  # noqa: E402
from sqlalchemy.exc import SQLAlchemyError  # noqa: E402
from sqlalchemy.orm import Session, sessionmaker  # noqa: E402

from db import engine  # noqa: E402
from foms.services.security import ops_control_root as root_store  # noqa: E402
from foms.services.orders.delete_retention import (  # noqa: E402
    DeleteRetentionError,
    apply_delete_retention,
)

OPS_APPROVAL_OPERATION_ID = "DELETE_RETENTION_APPLY"


def count_retained_order_events(session: Session, order_ids: "list[int]") -> int:
    """hard purge 대상 주문들의 ``order_events`` 잔존 건수를 센다(AUDIT-LOG T9 관측).

    T9(마이그레이션 ``auditlife_00``)가 ``order_events.order_id`` 의 ``orders`` FK
    (``ON DELETE CASCADE``)를 떼어냈다 — 주문이 물리 삭제돼도 **감사 이벤트는 남는 것이
    정상**이다(감사 원장이 감사 대상과 생명주기를 공유하지 않는다는 계약). 이 함수는 그
    계약이 실 DB 에서 지켜졌는지 보여주는 관측치일 뿐이며, 삭제·복구 등 어떤 상태 변경도
    하지 않는다. 노출은 건수뿐(이벤트 내용 미출력).

    Args:
        session: 삭제/dry-run 이 끝난(commit 또는 rollback 된) 세션.
        order_ids: 이번 실행이 대상으로 삼은 주문 id 목록.

    Returns:
        해당 주문들을 가리키는 ``order_events`` 행 수(대상이 없으면 0).
    """
    if not order_ids:
        return 0
    return int(session.execute(
        text("SELECT COUNT(*) FROM order_events WHERE order_id = ANY(:ids)"),
        {"ids": [int(x) for x in order_ids]},
    ).scalar() or 0)


def main(argv: "list[str] | None" = None) -> int:
    parser = argparse.ArgumentParser(
        description="Hard-purge soft-deleted retention-elapsed orders (OPS-APPROVAL gated)."
    )
    parser.add_argument("--plan-file", required=True, help="승인된 delete plan(JSON) 경로")
    parser.add_argument("--approval-token-file", required=True, help="control root 아래 approval 토큰")
    parser.add_argument("--batch-size", type=int, default=500, help="한 배치 삭제 주문 수(기본 500)")
    parser.add_argument("--apply", action="store_true", help="실제 소비·삭제(기본 dry-run)")
    args = parser.parse_args(argv)

    with open(args.plan_file, encoding="utf-8") as fh:
        approved_plan = json.load(fh)

    try:
        control_root = root_store.resolve_control_root()
    except root_store.OpsControlRootError as exc:
        raise SystemExit(f"control root error: {exc}")

    token = root_store.read_token(Path(args.approval_token_file), control_root)
    if token.get("operation_id") != OPS_APPROVAL_OPERATION_ID:
        raise SystemExit("token operation_id does not match DELETE_RETENTION_APPLY.")
    raw_secret = root_store.decode_secret_b64url(token["one_time_secret_b64url"])

    session = sessionmaker(bind=engine)()
    try:
        result = apply_delete_retention(
            session,
            approved_plan=approved_plan,
            raw_secret=raw_secret,
            apply=args.apply,
            batch_size=args.batch_size,
        )
        if args.apply:
            session.commit()
        else:
            session.rollback()
        # T9: 삭제가 끝난 뒤 감사 이벤트가 남아 있는지 확인한다(잔존이 정상 — FK 분리).
        try:
            retained_order_events = count_retained_order_events(
                session, list(approved_plan.get("exact_order_ids") or [])
            )
        except SQLAlchemyError as exc:
            # 관측 실패가 **이미 커밋된** 삭제 결과를 실패로 둔갑시키면 안 된다. 값은 null
            # 로 명시하고 원인을 그대로 출력한다(조용한 무시 아님).
            retained_order_events = None
            print(
                f"[delete-retention] order_events 잔존 확인 실패(삭제 결과에는 영향 없음): {exc}",
                file=sys.stderr,
            )
    except DeleteRetentionError as exc:
        session.rollback()
        raise SystemExit(f"delete-retention refused: {exc}")
    finally:
        session.close()

    if retained_order_events is not None:
        print(
            f"[delete-retention] 대상 주문의 order_events 잔존 {retained_order_events}건 "
            "(AUDIT-LOG T9: 감사 원장은 주문 hard purge 후에도 남는 것이 정상).",
            file=sys.stderr,
        )
    print(json.dumps({
        "operation": OPS_APPROVAL_OPERATION_ID,
        "applied": result.applied,
        "consumed": result.consumed,
        "target_count": result.target_count,
        "deleted": result.deleted,
        "retained_order_events": retained_order_events,
        "plan_sha256": result.plan_sha256,
        "count_sha256": result.count_sha256,
        "result_sha256": result.result_sha256,
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
