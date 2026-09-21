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
import re
import sys
from datetime import date, datetime, timedelta, timezone
from typing import Any, Iterable

try:
    import psycopg2
    import psycopg2.extras
except ImportError:  # pragma: no cover - 실행 환경 안내용
    psycopg2 = None  # type: ignore[assignment]

BATCH_ID = "2026-09-22-backlog"
DEFAULT_REASON = "2026-09 실측·도면 적체 정리(시공일 경과)"
DEFAULT_CUTOFF_DAYS = 7
CHUNK_SIZE = 500

#: 본공정 코드(한글 라벨 포함). 이 밖의 stage(AS_*·COMPLETED·레거시)는 대상 밖.
MAIN_STAGE_CODES = frozenset({
    "RECEIVED", "MEASURE", "DRAWING", "CONFIRM", "PRODUCTION", "CONSTRUCTION", "CS",
    "주문접수", "실측", "도면", "고객컨펌", "생산", "시공",
})
AS_OVERLAY_STATUSES = frozenset({"AS", "AS_RECEIVED", "AS_COMPLETED"})
HOLD_STATUSES = frozenset({"ON_HOLD"})
LOGISTICS_IN_FLIGHT_STATUSES = frozenset({"SCHEDULED", "SHIPPED_PENDING"})
#: 네이버 클레임 "열림" = 요청·처리중(``mapping.CLAIM_PHASES`` 의 REQUESTED·PROGRESS 와 동일).
OPEN_CLAIM_STATUSES = (
    "CANCEL_REQUEST", "CANCEL_REQUESTED", "RETURN_REQUEST", "RETURN_REQUESTED",
    "EXCHANGE_REQUEST", "CANCELING", "COLLECTING", "COLLECT_DONE",
)
#: 이 날짜보다 앞선 시공일은 입력 오류 가능성이 커 사람 확인 표식을 단다.
OLD_CONSTRUCTION_BEFORE = "2026-07-01"
CLOSED_QUEST_STATUSES = ("COMPLETED", "SUPERSEDED", "CANCELLED", "DONE")

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
KST = timezone(timedelta(hours=9))


# --------------------------------------------------------------------------- #
# 접속·조회
# --------------------------------------------------------------------------- #
def _connect(dsn: str, *, readonly: bool):
    """DSN 으로 접속한다(plan 은 read-only 세션).

    Args:
        dsn: PostgreSQL 접속 문자열.
        readonly: True 면 세션을 읽기 전용으로 고정한다.

    Returns:
        psycopg2 connection.

    Raises:
        SystemExit: psycopg2 미설치.
    """
    if psycopg2 is None:
        raise SystemExit("psycopg2 가 필요합니다: pip install psycopg2-binary")
    conn = psycopg2.connect(dsn)
    if readonly:
        conn.set_session(readonly=True)
    return conn


def _rows(conn, sql: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """딕셔너리 커서로 조회한다."""
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(sql, params or {})
        return [dict(row) for row in cur.fetchall()]


def today_kst() -> date:
    """KST 달력 오늘."""
    return datetime.now(KST).date()


def cutoff_iso(today: date, cutoff_days: int) -> str:
    """``today - cutoff_days`` 의 ISO 날짜. 시공일이 이 값 **미만**이면 후보."""
    return (today - timedelta(days=cutoff_days)).isoformat()


def assert_env_fingerprint(conn, expect_env: str | None) -> None:
    """데이터 지문으로 dev/staging/production 을 가른다(DSN 링크 오염 사고 방어).

    운영 DB 에는 ``TESTCLR%`` 고객이 0건, 스테이징에는 1건 이상이다(메모리 실측).

    Args:
        conn: 접속.
        expect_env: ``production`` | ``staging`` | None(검사 생략).

    Raises:
        SystemExit: 지문 불일치.
    """
    if not expect_env:
        return
    row = _rows(conn, "SELECT count(*) AS n FROM orders WHERE customer_name LIKE 'TESTCLR%%'")[0]
    n = int(row["n"])
    if expect_env == "production" and n != 0:
        raise SystemExit(f"지문 불일치: TESTCLR 고객 {n}건 — 운영 DB 가 아니다. 중단.")
    if expect_env == "staging" and n == 0:
        raise SystemExit("지문 불일치: TESTCLR 고객 0건 — 스테이징 DB 가 아니다. 중단.")


_CANDIDATE_SQL = """
SELECT o.id, o.customer_name, o.status, o.is_erp_order, o.erp_stage_code,
       o.erp_construction_date, o.erp_measurement_date, o.as_axis_status,
       o.erp_stage_updated_at,
       o.structured_data->'workflow' AS workflow,
       coalesce((o.structured_data->'meta'->>'draft') = 'true', false) AS meta_draft,
       (SELECT count(*) FROM jsonb_array_elements(
            CASE WHEN jsonb_typeof(o.structured_data->'quests') = 'array'
                 THEN o.structured_data->'quests' ELSE '[]'::jsonb END) q
         WHERE upper(coalesce(q->>'status','')) NOT IN %(closed_quest)s) AS open_quests,
       EXISTS (SELECT 1 FROM external_order_links l
                WHERE l.order_id = o.id
                  AND upper(coalesce(l.triage_state->'claim_sync'->>'last_status','')) IN %(open_claim)s
              ) AS naver_claim_open
  FROM orders o
 WHERE o.deleted_at IS NULL
   AND o.status <> 'DELETED'
   AND o.erp_construction_date IS NOT NULL
   AND o.erp_construction_date <> ''
   AND o.erp_construction_date < %(cutoff)s
   AND coalesce(o.erp_stage_code, '') NOT IN ('COMPLETED','완료','AS_COMPLETED','AS완료')
 ORDER BY o.id
"""


def fetch_candidates(conn, *, cutoff: str) -> list[dict[str, Any]]:
    """시공일이 ``cutoff`` 미만인 미종결 주문을 넓게 가져온다(분류는 :func:`classify_row`).

    제외 사유를 plan 에 전부 남기려고 SQL 에서는 최소만 거른다(삭제·종결 stage·시공일 없음).

    Args:
        conn: 접속(read-only).
        cutoff: ISO 날짜. 시공일이 이 값 미만이면 후보.

    Returns:
        행 dict 목록(id 오름차순).
    """
    return _rows(conn, _CANDIDATE_SQL, {
        "cutoff": cutoff,
        "closed_quest": CLOSED_QUEST_STATUSES,
        "open_claim": OPEN_CLAIM_STATUSES,
    })


_NO_CONSTRUCTION_SQL = """
SELECT o.id, o.customer_name, o.status, o.erp_stage_code, o.erp_measurement_date,
       o.as_axis_status, o.manager_name, o.created_at
  FROM orders o
 WHERE o.deleted_at IS NULL AND o.status <> 'DELETED' AND o.is_erp_order = true
   AND NOT (o.status = 'DRAFT' OR coalesce(o.structured_data->'meta'->>'draft','') = 'true')
   AND coalesce(o.erp_stage_code,'') IN ('MEASURE','실측','DRAWING','도면')
   AND (o.erp_construction_date IS NULL OR o.erp_construction_date = '')
 ORDER BY o.erp_stage_code, o.erp_measurement_date NULLS FIRST, o.id
"""


def fetch_no_construction(conn) -> list[dict[str, Any]]:
    """시공일 없는 실측·도면 주문(자동 판정 불가 — 영업팀 검토 목록)."""
    return _rows(conn, _NO_CONSTRUCTION_SQL)


# --------------------------------------------------------------------------- #
# 순수 판정
# --------------------------------------------------------------------------- #
def classify_row(row: dict[str, Any]) -> tuple[str | None, str | None, list[str]]:
    """행 하나를 ``(mode, skip_reason, flags)`` 로 판정한다.

    ``mode`` 는 ``main`` | ``as_stage_only`` | None(제외). 제외면 ``skip_reason`` 이 채워진다.
    ``flags`` 는 처리하되 사람이 한 번 봐야 하는 표식(옛 시공일·열린 quest).

    Args:
        row: :func:`fetch_candidates` 행(또는 같은 키를 가진 dict).

    Returns:
        (mode, skip_reason, flags).
    """
    status = str(row.get("status") or "").strip()
    stage = str(row.get("erp_stage_code") or "").strip()
    cons = str(row.get("erp_construction_date") or "").strip()
    as_axis = row.get("as_axis_status")

    if not row.get("is_erp_order"):
        return None, "non_erp", []
    if status == "DRAFT" or bool(row.get("meta_draft")):
        return None, "draft", []
    if not _DATE_RE.match(cons):
        return None, "construction_date_malformed", []
    if stage not in MAIN_STAGE_CODES:
        return None, "stage_not_main", []
    if status in HOLD_STATUSES:
        return None, "on_hold", []
    if status in LOGISTICS_IN_FLIGHT_STATUSES:
        return None, "logistics_in_flight", []
    if bool(row.get("naver_claim_open")):
        return None, "naver_claim_open", []

    flags: list[str] = []
    if cons < OLD_CONSTRUCTION_BEFORE:
        flags.append("old_construction_date")
    if int(row.get("open_quests") or 0) > 0:
        flags.append("open_quests")

    is_as = bool(as_axis) or status in AS_OVERLAY_STATUSES
    return ("as_stage_only" if is_as else "main"), None, flags


def build_plan(rows: Iterable[dict[str, Any]], *, cutoff: str, today: str,
               cutoff_days: int) -> dict[str, Any]:
    """후보 행을 plan JSON 구조로 접는다(쓰기 없음).

    Args:
        rows: :func:`fetch_candidates` 결과.
        cutoff: 후보 판정에 쓴 ISO 날짜.
        today: KST 오늘 ISO.
        cutoff_days: 여유일.

    Returns:
        ``{batch, today, cutoff, cutoff_days, items, skipped, summary}``.
    """
    items: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    for row in rows:
        mode, reason, flags = classify_row(row)
        base = {
            "order_id": int(row["id"]),
            "customer_name": row.get("customer_name") or "",
            "observed_status": str(row.get("status") or ""),
            "observed_stage": str(row.get("erp_stage_code") or ""),
            "observed_as_axis": row.get("as_axis_status"),
            "construction_date": row.get("erp_construction_date"),
        }
        if mode is None:
            skipped.append({**base, "reason": reason})
            continue
        items.append({
            **base,
            "mode": mode,
            "flags": flags,
            "open_quests": int(row.get("open_quests") or 0),
            "to_stage": "COMPLETED",
            "to_status": "COMPLETED" if mode == "main" else base["observed_status"],
        })
    summary = {
        "items": len(items),
        "main": sum(1 for i in items if i["mode"] == "main"),
        "as_stage_only": sum(1 for i in items if i["mode"] == "as_stage_only"),
        "flag_old_construction_date": sum(1 for i in items if "old_construction_date" in i["flags"]),
        "flag_open_quests": sum(1 for i in items if "open_quests" in i["flags"]),
        "skipped": {},
        "by_stage": {},
    }
    for s in skipped:
        summary["skipped"][s["reason"]] = summary["skipped"].get(s["reason"], 0) + 1
    for i in items:
        key = f"{i['observed_stage']}/{i['mode']}"
        summary["by_stage"][key] = summary["by_stage"].get(key, 0) + 1
    return {
        "batch": BATCH_ID, "today": today, "cutoff": cutoff, "cutoff_days": cutoff_days,
        "items": items, "skipped": skipped, "summary": summary,
    }


def completed_workflow(workflow: Any, *, now: datetime) -> dict[str, Any]:
    """``workflow`` dict 를 COMPLETED 로 옮긴 새 dict(원본 불변).

    ``stage_override`` 표식은 기존 강제 변경과 같은 이유로 남긴다 — 이후 폼 저장의
    "실측일 있으면 RECEIVED→MEASURE 자동 전진" 이 이 변경을 되돌리지 못하게.

    Args:
        workflow: 기존 ``structured_data.workflow``(dict 가 아니면 빈 것으로 본다).
        now: 기록 시각(naive UTC).

    Returns:
        새 workflow dict.
    """
    wf = dict(workflow) if isinstance(workflow, dict) else {}
    stamp = now.isoformat()
    wf["stage"] = "COMPLETED"
    wf["stage_updated_at"] = stamp
    wf["stage_override"] = {
        "at": stamp, "stage": "COMPLETED", "batch": BATCH_ID,
        "measurement_date": wf.get("measurement_date"),
    }
    return wf


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


def _snapshot_rows(conn, ids: list[int]) -> list[dict[str, Any]]:
    """되돌리기용 현재값(workflow dict 원본 포함)."""
    if not ids:
        return []
    rows = _rows(conn, """
        SELECT id, status, erp_stage_code, erp_stage_updated_at, as_axis_status,
               structured_data->'workflow' AS workflow
          FROM orders WHERE id = ANY(%(ids)s) ORDER BY id
    """, {"ids": ids})
    for r in rows:
        if r.get("erp_stage_updated_at") is not None:
            r["erp_stage_updated_at"] = r["erp_stage_updated_at"].isoformat()
    return rows


def apply_one(cur, item: dict[str, Any], *, actor_user_id: int, now: datetime,
              reason: str) -> str:
    """항목 1건을 적용한다(호출부가 트랜잭션 소유).

    Args:
        cur: RealDictCursor.
        item: plan 항목.
        actor_user_id: 이벤트·감사행 행위자.
        now: 기록 시각(naive UTC).
        reason: 사유 문자열.

    Returns:
        ``applied`` 또는 ``skipped:<사유>``.
    """
    oid = int(item["order_id"])
    cur.execute("""SELECT status, erp_stage_code, as_axis_status, structured_data
                     FROM orders WHERE id = %s FOR UPDATE""", (oid,))
    row = cur.fetchone()
    if row is None:
        return "skipped:주문 없음"
    if (str(row["status"] or "") != item["observed_status"]
            or str(row["erp_stage_code"] or "") != item["observed_stage"]
            or (row["as_axis_status"] or None) != (item.get("observed_as_axis") or None)):
        return (f"skipped:stale(status={row['status']} stage={row['erp_stage_code']} "
                f"as={row['as_axis_status']})")
    structured = dict(row["structured_data"] or {})
    structured["workflow"] = completed_workflow(structured.get("workflow"), now=now)
    mode = item["mode"]
    if mode == "main":
        cur.execute("""
            UPDATE orders SET status = 'COMPLETED', erp_stage_code = 'COMPLETED',
                   erp_stage_updated_at = %s, structured_data = %s,
                   mutation_version = mutation_version + 1
             WHERE id = %s
        """, (now, psycopg2.extras.Json(structured), oid))
    else:  # as_stage_only — status·AS 축은 손대지 않는다
        cur.execute("""
            UPDATE orders SET erp_stage_code = 'COMPLETED',
                   erp_stage_updated_at = %s, structured_data = %s,
                   mutation_version = mutation_version + 1
             WHERE id = %s
        """, (now, psycopg2.extras.Json(structured), oid))
    to_status = "COMPLETED" if mode == "main" else item["observed_status"]
    cur.execute("""
        INSERT INTO order_events(order_id, event_type, payload, created_by_user_id, created_at)
        VALUES (%s, 'STAGE_OVERRIDE', %s, %s, %s)
    """, (oid, psycopg2.extras.Json({
        "from": item["observed_stage"], "to": "COMPLETED", "mode": "skip",
        "manual": False, "batch": BATCH_ID, "reason": reason, "apply_mode": mode,
        "from_status": item["observed_status"], "to_status": to_status,
        "as_axis_status": item.get("observed_as_axis"), "flags": item.get("flags") or [],
    }), actor_user_id, now))
    cur.execute("""
        INSERT INTO security_logs(timestamp, user_id, message, action, target_type, target_id, detail)
        VALUES (%s, %s, %s, 'ORDER_STATUS_CHANGED', 'order', %s, %s)
    """, (now, actor_user_id,
          f"주문 #{oid} ({item.get('customer_name') or ''}) — 일괄 완료: "
          f"{item['observed_stage']} → COMPLETED / status {item['observed_status']} → {to_status}"
          f" ({reason})", oid,
          psycopg2.extras.Json({
              "field": "status", "before": item["observed_status"], "after": to_status,
              "stage_before": item["observed_stage"], "stage_after": "COMPLETED",
              "batch": BATCH_ID, "apply_mode": mode, "reason": reason,
          })))
    return "applied"


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


def rollback_one(cur, row: dict[str, Any], *, actor_user_id: int, now: datetime) -> str:
    """스냅샷 행 1건을 되돌린다(workflow dict 통째 + status + 평면 컬럼)."""
    oid = int(row["id"])
    cur.execute("SELECT status, erp_stage_code, structured_data FROM orders WHERE id = %s FOR UPDATE",
                (oid,))
    cur_row = cur.fetchone()
    if cur_row is None:
        return "skipped:주문 없음"
    if str(cur_row["erp_stage_code"] or "") != "COMPLETED":
        return f"skipped:현재 stage {cur_row['erp_stage_code']} (이 배치 결과가 아님)"
    structured = dict(cur_row["structured_data"] or {})
    workflow = row.get("workflow")
    if isinstance(workflow, dict):
        structured["workflow"] = workflow
    else:
        structured.pop("workflow", None)
    stage_updated = row.get("erp_stage_updated_at")
    cur.execute("""
        UPDATE orders SET status = %s, erp_stage_code = %s, erp_stage_updated_at = %s,
               structured_data = %s, mutation_version = mutation_version + 1
         WHERE id = %s
    """, (row["status"], row.get("erp_stage_code"), stage_updated,
          psycopg2.extras.Json(structured), oid))
    cur.execute("""
        INSERT INTO order_events(order_id, event_type, payload, created_by_user_id, created_at)
        VALUES (%s, 'STAGE_OVERRIDE', %s, %s, %s)
    """, (oid, psycopg2.extras.Json({
        "from": "COMPLETED", "to": row.get("erp_stage_code"), "mode": "restore",
        "manual": True, "batch": BATCH_ID, "reason": f"{BATCH_ID} 되돌리기",
        "from_status": cur_row["status"], "restored_status": row["status"],
    }), actor_user_id, now))
    return "applied"


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
