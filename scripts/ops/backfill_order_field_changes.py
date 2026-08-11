"""ORDER-DIFF-01: 1안이 남긴 detail.changes 를 변경 원장 테이블로 옮긴다(멱등·dry-run 기본).

ORDER-DIFF-00 배포 이후 ``security_logs.detail['changes']`` 에 쌓인 변경들은 화면에서는
보이지만 **필드 기준 질의**가 안 된다. 같은 내용을 ``order_field_changes`` 로 옮겨 두면
"실측일이 바뀐 주문 전부" 질의가 그 기간까지 닿는다.

멱등 규칙: change set id 가 이미 있으면(detail 에 ``change_set`` 이 있거나 원장에 같은 id 가
있으면) 건너뛴다. 1안 시기 행에는 ``change_set`` 이 없으므로 **결정적 대체 id** ``seclog:{id}``
를 쓴다 — 몇 번을 다시 돌려도 중복이 생기지 않는다.

사용:
    python scripts/ops/backfill_order_field_changes.py            # dry-run(기본)
    python scripts/ops/backfill_order_field_changes.py --apply    # 실제 반영
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))


def _change_set_id_of(entry) -> str:
    """행의 change set id(없으면 결정적 대체 id).

    :param entry: ``SecurityLog`` 행.
    :return: change set 문자열.
    """
    detail = entry.detail if isinstance(entry.detail, dict) else {}
    return str(detail.get("change_set") or f"seclog:{entry.id}")


def main() -> int:
    """detail.changes 를 원장으로 백필한다.

    :return: 프로세스 종료 코드(0 = 정상).
    """
    parser = argparse.ArgumentParser(description="ORDER-DIFF-01 변경 원장 백필")
    parser.add_argument("--apply", action="store_true",
                        help="실제로 반영한다(기본은 dry-run — 건수만 센다)")
    parser.add_argument("--batch", type=int, default=500, help="한 번에 처리할 감사 행 수")
    args = parser.parse_args()

    from db import db_session
    from foms.services.orders.order_field_change_writer import build_change_rows
    from models import OrderFieldChange, SecurityLog

    session = db_session()
    scanned = inserted = skipped = 0
    try:
        query = (
            session.query(SecurityLog)
            .filter(SecurityLog.action == "ORDER_STRUCTURED_SAVED")
            .filter(SecurityLog.target_type == "order")
            .order_by(SecurityLog.id)
        )
        for entry in query.yield_per(args.batch):
            detail = entry.detail if isinstance(entry.detail, dict) else {}
            changes = detail.get("changes")
            if not isinstance(changes, list) or not changes:
                continue
            scanned += 1

            change_set_id = _change_set_id_of(entry)
            exists = (
                session.query(OrderFieldChange.id)
                .filter(OrderFieldChange.change_set_id == change_set_id)
                .first()
            )
            if exists:
                skipped += 1
                continue

            rows = build_change_rows(
                changes,
                order_id=int(entry.target_id),
                actor_user_id=entry.user_id,
                change_set_id=change_set_id,
            )
            for row in rows:
                # 원장의 시간축은 감사 행의 시각이다(백필 실행 시각이 아니다).
                row.created_at = entry.timestamp
            inserted += len(rows)
            if args.apply:
                session.add_all(rows)

        if args.apply:
            session.commit()
        else:
            session.rollback()
    finally:
        session.close()

    mode = "반영" if args.apply else "dry-run"
    print(f"[ORDER-DIFF-01 백필/{mode}] 대상 감사행={scanned} 신규 원장행={inserted} 건너뜀={skipped}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
