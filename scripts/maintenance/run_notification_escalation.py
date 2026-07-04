"""미확인 긴급 알림 에스컬레이션 스윕 실행 (알림 Phase 3C).

긴급(is_urgent) 알림이 일정 시간 내 확인(ack)되지 않으면 팀 매니저 → ADMIN 순으로
단계적 에스컬레이션한다. 코어 로직은 ``foms.services.notifications.escalation`` 참조.

주기 실행 배선(설계 결정): FOMS 는 in-process 주기 스케줄러가 없고, 새 인프라 의존성
(rq-scheduler 등) 추가는 금지다. 따라서 이 스윕은 **외부 스케줄러가 주기 호출하는 CLI**
로 제공한다. 배지/hot path 에 절대 넣지 않는다. 권장 간격은 60초 이상이며, 여러 replica
가 동시에 돌아도 idempotent(중복 알림/이벤트 없음)라 안전하다.

사용 예 (PowerShell 5.x)::

    python scripts/maintenance/run_notification_escalation.py
    python scripts/maintenance/run_notification_escalation.py --json
    python scripts/maintenance/run_notification_escalation.py --dry-run
"""
import argparse
import json
import os
import sys
from datetime import datetime

sys.path.append(
    os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
)

from app import app  # noqa: E402
from db import get_db  # noqa: E402
from foms.services.notifications.escalation import escalate_overdue_urgent  # noqa: E402


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Escalate overdue urgent notifications.")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="스윕을 실행하되 커밋하지 않고 롤백(집계만 확인).",
    )
    parser.add_argument("--json", action="store_true", help="기계 판독용 JSON 요약 출력.")
    return parser.parse_args()


def run() -> int:
    args = _parse_args()
    with app.app_context():
        db = get_db()
        try:
            result = escalate_overdue_urgent(db)
            if args.dry_run:
                db.rollback()
            else:
                db.commit()
        except Exception:
            db.rollback()
            raise

    result["dry_run"] = bool(args.dry_run)
    if args.json:
        print(json.dumps(result, ensure_ascii=False))
    else:
        ts = datetime.now().strftime("%H:%M:%S")
        print(
            f"[{ts}] escalation sweep: checked={result['checked']} "
            f"escalated={result['escalated']} operator_escalated={result['operator_escalated']} "
            f"dry_run={result['dry_run']}"
        )
    return 0


if __name__ == "__main__":
    sys.exit(run())
