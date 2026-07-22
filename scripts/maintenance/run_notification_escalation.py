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
import time
import traceback
from datetime import datetime

sys.path.append(
    os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
)

from app import app  # noqa: E402
from db import get_db  # noqa: E402
from foms.services.notifications.escalation import (  # noqa: E402
    escalate_overdue_urgent,
    finalize_escalation_delivery,
)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Escalate overdue urgent notifications.")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="스윕을 실행하되 커밋하지 않고 롤백(집계만 확인).",
    )
    parser.add_argument("--json", action="store_true", help="기계 판독용 JSON 요약 출력.")
    parser.add_argument(
        "--loop",
        action="store_true",
        help="장기 실행 루프 모드: 앱을 1회만 부팅하고 interval 간격으로 스윕을 반복. "
        "Railway worker 컨테이너 백그라운드 배선용 (start.sh 참조).",
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=60,
        help="--loop 모드 스윕 간격(초, 기본 60, 최소 15).",
    )
    return parser.parse_args()


def _sweep_once(dry_run: bool) -> dict:
    """단일 스윕 실행 후 결과 dict 반환 (호출측이 app_context 보유).

    commit 이후에만 finalize(badge/realtime/push). dry-run 은 롤백만 하고 배달 생략.
    """
    db = get_db()
    try:
        result = escalate_overdue_urgent(db)
        if dry_run:
            db.rollback()
            result["delivery"] = {"pushed": 0, "realtime_sent": 0, "recipients": 0}
            return result
        db.commit()
        result["delivery"] = finalize_escalation_delivery(
            db,
            created_notification_ids=result.get("created_notification_ids"),
            recipient_user_ids=result.get("recipient_user_ids"),
        )
        return result
    except Exception:
        db.rollback()
        raise


def _print_result(result: dict, as_json: bool) -> None:
    """스윕 결과를 사람/기계 판독 형식으로 출력."""
    if as_json:
        print(json.dumps(result, ensure_ascii=False), flush=True)
        return
    ts = datetime.now().strftime("%H:%M:%S")
    print(
        f"[{ts}] escalation sweep: checked={result['checked']} "
        f"escalated={result['escalated']} operator_escalated={result['operator_escalated']} "
        f"dry_run={result['dry_run']}",
        flush=True,
    )


def _run_loop(interval: int, dry_run: bool, as_json: bool) -> int:
    """앱 1회 부팅 후 interval 간격으로 스윕 반복. 스윕 실패는 기록 후 계속."""
    interval = max(15, interval)
    print(f"[escalation-loop] started (interval={interval}s)", flush=True)
    while True:
        try:
            with app.app_context():
                result = _sweep_once(dry_run)
            result["dry_run"] = bool(dry_run)
            _print_result(result, as_json)
        except Exception:
            # 스윕 1회 실패가 루프를 죽이면 escalation이 통째로 꺼진다.
            print("[escalation-loop] sweep failed:", flush=True)
            traceback.print_exc()
        time.sleep(interval)


def run() -> int:
    args = _parse_args()
    if args.loop:
        return _run_loop(args.interval, args.dry_run, args.json)

    with app.app_context():
        result = _sweep_once(args.dry_run)

    result["dry_run"] = bool(args.dry_run)
    _print_result(result, args.json)
    return 0


if __name__ == "__main__":
    sys.exit(run())
