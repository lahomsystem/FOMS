"""시공일 지난 적체 주문 일괄 완료 처리 — plan(dry-run) → apply(스냅샷) → rollback.

BACKLOG-COMPLETE-01 (스펙 ``docs/plans/2026-09-22-past-construction-bulk-complete-spec.md``).
실측·도면 타일에 이미 끝난 주문이 섞여 "진짜 도면을 만들어야 하는 건"이 안 보이는 것을
정리한다. 판정 기준은 ``erp_construction_date`` 가 오늘(KST) 기준 ``--cutoff-days``(기본 7일)
이상 지난 ERP 본공정 주문이다.

기존 「단계 강제 변경」 일괄 경로(``foms/services/orders/stage_override.py``)를 쓰지 않는 이유:
그 경로는 ``order.status`` 를 통째 덮어 AS 접수·완료 건이 AS 대시보드에서 사라진다
(2026-08-14 사고 55건). 여기서는 두 축을 갈라 쓴다.

* ``main``          : AS 축 없음 → ``workflow.stage`` + ``status`` + 평면 컬럼 모두 ``COMPLETED``.
* ``as_stage_only`` : AS 탭 건(``as_axis_status`` 있음 또는 status 가 AS overlay)
                      → ``workflow.stage`` 와 평면 ``erp_stage_code`` 만 ``COMPLETED``.
                      **``status``·``as_lifecycle``·``as_axis_status``·``as_completed_date`` 는 읽기만 한다.**

부르지 않는 것(의도): 퀘스트·알림 부수효과(``_handle_stage_transition``), 알림톡·웹푸시·채널톡,
도면 이관 이력, ``mutation_version`` 외 다른 스칼라. 열린 quest 는 그대로 둔다(사용자 결정).

안전 규율(``tools/ops/data_doctor.py`` 와 같다):

* ``plan`` 은 read-only 세션. 쓰기는 ``apply --yes`` 만.
* ``apply`` 직전 행의 ``status``/``erp_stage_code``/``as_axis_status`` 가 plan 시점과 다르면
  그 행은 건너뛴다(plan 뒤 사람이 만진 행 보호).
* 적용 전 상태(``workflow`` dict 원본 포함)를 스냅샷 JSON 으로 남기고 ``rollback`` 으로 되돌린다.
* ``--expect-env`` 데이터 지문 가드: 운영은 ``TESTCLR%`` 고객 0건, 스테이징은 1건 이상.
* 이벤트(``order_events STAGE_OVERRIDE``)와 감사행(``security_logs ORDER_STATUS_CHANGED``)에
  이전값을 실어 ``data_doctor`` 가 ``logged`` 근거로 읽을 수 있게 한다.

사용:
    python tools/ops/bulk_complete_past_construction.py plan --dsn "$DSN" \
        --expect-env production --cutoff-days 7 --out plan.json
    python tools/ops/bulk_complete_past_construction.py plan --dsn "$DSN" \
        --expect-env production --list-no-construction no_cons.csv
    python tools/ops/bulk_complete_past_construction.py apply --dsn "$DSN" \
        --expect-env production --plan plan.json --actor <user_id> --yes \
        --snapshot-out snapshot.json
    python tools/ops/bulk_complete_past_construction.py rollback --dsn "$DSN" \
        --expect-env production --snapshot snapshot.json --actor <user_id> --yes

시각은 DB 저장 규약과 같은 **naive UTC** 로 기록한다. 시공일 비교만 KST 달력이다.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from datetime import datetime, timezone
from typing import Any

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bulk_complete_past_construction_core import (  # noqa: E402
    psycopg2,
    BATCH_ID,
    DEFAULT_CUTOFF_DAYS,
    DEFAULT_REASON,
    CHUNK_SIZE,
    MAIN_STAGE_CODES,
    AS_OVERLAY_STATUSES,
    OPEN_CLAIM_STATUSES,
    OLD_CONSTRUCTION_BEFORE,
    _connect,
    _rows,
    _snapshot_rows,
    apply_one,
    assert_env_fingerprint,
    build_plan,
    classify_row,
    completed_workflow,
    cutoff_iso,
    fetch_candidates,
    fetch_no_construction,
    rollback_one,
    today_kst,
)

__all__ = [
    "BATCH_ID", "DEFAULT_CUTOFF_DAYS", "DEFAULT_REASON", "CHUNK_SIZE", "MAIN_STAGE_CODES",
    "AS_OVERLAY_STATUSES", "OPEN_CLAIM_STATUSES", "OLD_CONSTRUCTION_BEFORE",
    "_connect", "_rows", "_snapshot_rows", "apply_one", "assert_env_fingerprint", "build_plan",
    "classify_row", "completed_workflow", "cutoff_iso", "fetch_candidates",
    "fetch_no_construction", "rollback_one", "today_kst", "main", "build_parser",
]


def _print_summary(plan: dict[str, Any]) -> None:
    s = plan["summary"]
    print(f"오늘(KST) {plan['today']} · 시공일 < {plan['cutoff']} (여유 {plan['cutoff_days']}일)")
    print(f"대상 {s['items']}건 = main {s['main']} + as_stage_only {s['as_stage_only']}")
    print(f"  표식: 옛 시공일 {s['flag_old_construction_date']} · 열린 quest {s['flag_open_quests']}")
    for key, n in sorted(s["by_stage"].items()):
        print(f"  {key}: {n}")
    print("제외:", ", ".join(f"{k}={v}" for k, v in sorted(s["skipped"].items())) or "없음")


# --------------------------------------------------------------------------- #
# 명령
# --------------------------------------------------------------------------- #
def cmd_plan(args: argparse.Namespace) -> int:
    """대상·제외·분류를 JSON 으로 낸다(쓰기 없음)."""
    conn = _connect(args.dsn, readonly=True)
    try:
        assert_env_fingerprint(conn, args.expect_env)
        if args.list_no_construction:
            rows = fetch_no_construction(conn)
            with open(args.list_no_construction, "w", encoding="utf-8-sig", newline="") as fh:
                writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()) if rows else
                                        ["id", "customer_name", "status", "erp_stage_code",
                                         "erp_measurement_date", "as_axis_status", "manager_name",
                                         "created_at"])
                writer.writeheader()
                for r in rows:
                    writer.writerow({k: ("" if v is None else str(v)) for k, v in r.items()})
            print(f"시공일 없는 실측·도면 {len(rows)}건 → {args.list_no_construction}")
            return 0
        today = today_kst()
        cutoff = cutoff_iso(today, args.cutoff_days)
        rows = fetch_candidates(conn, cutoff=cutoff)
    finally:
        conn.close()
    plan = build_plan(rows, cutoff=cutoff, today=today.isoformat(), cutoff_days=args.cutoff_days)
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(plan, fh, ensure_ascii=False, indent=1, default=str)
    _print_summary(plan)
    print(f"plan → {args.out}")
    return 0


def cmd_apply(args: argparse.Namespace) -> int:
    """plan 을 청크 트랜잭션으로 적용한다(--yes 필수)."""
    with open(args.plan, encoding="utf-8") as fh:
        plan = json.load(fh)
    items: list[dict[str, Any]] = plan.get("items") or []
    if not items:
        print("적용 항목이 없습니다.")
        return 0
    if not args.yes:
        print(f"대상 {len(items)}건 — 실제 적용하려면 --yes 를 붙여라(지금은 아무것도 안 바꿨다).")
        return 2
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    conn = _connect(args.dsn, readonly=False)
    try:
        assert_env_fingerprint(conn, args.expect_env)
        ids = [int(i["order_id"]) for i in items]
        snapshot = _snapshot_rows(conn, ids)
        with open(args.snapshot_out, "w", encoding="utf-8") as fh:
            json.dump({"batch": BATCH_ID, "created_at": now.isoformat(), "plan": args.plan,
                       "rows": snapshot}, fh, ensure_ascii=False, indent=1, default=str)
        results: dict[str, int] = {}
        for start in range(0, len(items), CHUNK_SIZE):
            chunk = items[start:start + CHUNK_SIZE]
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                for item in chunk:
                    outcome = apply_one(cur, item, actor_user_id=args.actor, now=now,
                                        reason=args.reason)
                    key = outcome.split(":", 1)[0]
                    results[key] = results.get(key, 0) + 1
                    if outcome != "applied":
                        print(f"  #{item['order_id']} {outcome}")
            conn.commit()
            print(f"  커밋 {start + len(chunk)}/{len(items)}")
    finally:
        conn.close()
    print("적용 결과:", ", ".join(f"{k}={v}" for k, v in sorted(results.items())))
    print(f"되돌리기용 스냅샷: {args.snapshot_out}")
    return 0


def cmd_rollback(args: argparse.Namespace) -> int:
    """스냅샷 파일 상태로 되돌린다(--yes 필수)."""
    with open(args.snapshot, encoding="utf-8") as fh:
        snapshot = json.load(fh)
    rows: list[dict[str, Any]] = snapshot.get("rows") or []
    if args.only_ids:
        keep = {int(x) for x in args.only_ids.split(",") if x.strip()}
        rows = [r for r in rows if int(r["id"]) in keep]
    if not args.yes:
        print(f"되돌릴 행 {len(rows)}건 — 실제 실행하려면 --yes 를 붙여라.")
        return 2
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    conn = _connect(args.dsn, readonly=False)
    try:
        assert_env_fingerprint(conn, args.expect_env)
        results: dict[str, int] = {}
        for start in range(0, len(rows), CHUNK_SIZE):
            chunk = rows[start:start + CHUNK_SIZE]
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                for row in chunk:
                    outcome = rollback_one(cur, row, actor_user_id=args.actor, now=now)
                    key = outcome.split(":", 1)[0]
                    results[key] = results.get(key, 0) + 1
                    if outcome != "applied":
                        print(f"  #{row['id']} {outcome}")
            conn.commit()
    finally:
        conn.close()
    print("되돌리기 결과:", ", ".join(f"{k}={v}" for k, v in sorted(results.items())))
    return 0


def build_parser() -> argparse.ArgumentParser:
    """CLI 파서."""
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    sub = parser.add_subparsers(dest="command", required=True)

    def _common(p: argparse.ArgumentParser) -> None:
        p.add_argument("--dsn", required=True, help="PostgreSQL DSN(운영은 DATABASE_PUBLIC_URL)")
        p.add_argument("--expect-env", choices=["production", "staging"], default=None,
                       help="데이터 지문 가드(TESTCLR 고객 수)")

    p_plan = sub.add_parser("plan", help="대상·제외·분류 JSON(쓰기 없음)")
    _common(p_plan)
    p_plan.add_argument("--cutoff-days", type=int, default=DEFAULT_CUTOFF_DAYS)
    p_plan.add_argument("--out", default="bulk_complete_plan.json")
    p_plan.add_argument("--list-no-construction", default=None,
                        help="시공일 없는 실측·도면 검토 CSV 경로(이걸 주면 plan 대신 CSV 만 낸다)")
    p_plan.set_defaults(func=cmd_plan)

    p_apply = sub.add_parser("apply", help="plan 적용(--yes 필수)")
    _common(p_apply)
    p_apply.add_argument("--plan", required=True)
    p_apply.add_argument("--actor", type=int, required=True, help="이벤트·감사행 행위자 user id")
    p_apply.add_argument("--reason", default=DEFAULT_REASON)
    p_apply.add_argument("--snapshot-out", default="bulk_complete_snapshot.json")
    p_apply.add_argument("--yes", action="store_true")
    p_apply.set_defaults(func=cmd_apply)

    p_rb = sub.add_parser("rollback", help="스냅샷으로 되돌리기(--yes 필수)")
    _common(p_rb)
    p_rb.add_argument("--snapshot", required=True)
    p_rb.add_argument("--actor", type=int, required=True)
    p_rb.add_argument("--only-ids", default=None, help="쉼표 구분 주문 id — 일부만 되돌릴 때")
    p_rb.add_argument("--yes", action="store_true")
    p_rb.set_defaults(func=cmd_rollback)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main())
