"""데이터 사고 복구 도구(data doctor) — 사고 창 조사 → 복구안 dry-run → 트랜잭션 적용.

DATA-DOCTOR-01. 2026-08-14 사고(일괄 완료처리로 AS 대시보드 55건 증발)를 손으로 복구한
절차를 도구로 굳힌 것이다. 복구 대상은 v1 에서 **주문 상태 축**(``orders.status`` +
``erp_stage_code`` + ``structured_data.workflow.stage``)이다.

근거(증거) 우선순위 — 높은 쪽이 이기고, 각 항목에 confidence 가 붙는다:

1. ``exact``    : PITR fork DB 스냅샷(:mod:`tools.ops.railway_pitr` 로 뜬 사고 직전 사본)
2. ``logged``   : ``security_logs.detail.before`` (ORDER_STATUS_CHANGED 감사행)
3. ``event``    : ``order_events`` STAGE_OVERRIDE ``from_status`` / STAGE_CHANGED ``from``
4. ``inferred`` : AS 이벤트 이력(AS_REGISTERED/AS_COMPLETED)에서 유도 — 사람이 확인해야 한다

안전 규율:

* 기본은 조회·계획뿐. 쓰기는 ``apply`` 서브커맨드 + ``--yes`` 를 동시에 줘야 한다.
* ``plan``/``inspect`` 는 read-only 세션으로 붙는다.
* 적용 직전 현재값이 계획의 ``after``(사고가 남긴 값)와 다르면 그 행은 **건너뛴다** —
  사고 후 사람이 이미 고친 행을 덮지 않기 위해서다.
* 적용 전 상태를 스냅샷 JSON 으로 남기고, ``rollback`` 으로 되돌릴 수 있다.
* 복구 자체도 ``order_events``/``security_logs`` 에 기록한다(복구가 유령 변경이 되지 않게).

사용:
    python tools/ops/data_doctor.py inspect --dsn "$DSN" \
        --since 2026-08-14T06:25:00 --until 2026-08-14T07:00:00
    python tools/ops/data_doctor.py plan --dsn "$DSN" \
        --since ... --until ... --actor 38 --only-as --out plan.json
    python tools/ops/data_doctor.py apply --dsn "$DSN" --plan plan.json --yes
    python tools/ops/data_doctor.py rollback --dsn "$DSN" --snapshot snapshot.json --yes

시각은 DB 저장 규약과 같은 **naive UTC** 로 준다(KST 아님).
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from typing import Any, Iterable

try:
    import psycopg2
    import psycopg2.extras
except ImportError:  # pragma: no cover - 실행 환경 안내용
    psycopg2 = None  # type: ignore[assignment]

AS_OVERLAY_STATUSES = ("AS", "AS_RECEIVED", "AS_COMPLETED")

#: 복구 근거 신뢰도 — 값이 클수록 우선한다.
CONFIDENCE_RANK = {"inferred": 1, "event": 2, "logged": 3, "exact": 4}

#: 한 번에 손댈 수 있는 행 상한(오조작 폭발 방지). 넘으면 중단하고 범위를 좁히게 한다.
MAX_TARGETS = 500

#: 복구 감사행에 남길 행위자(운영 측정 계정). ``--actor-user-id`` 로 덮을 수 있다.
DEFAULT_RESTORE_ACTOR = 57


def _connect(dsn: str, *, readonly: bool):
    """DSN 으로 접속한다(계획 단계는 read-only 세션).

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
    """딕셔너리 커서로 조회한다.

    Args:
        conn: 접속.
        sql: SQL 문.
        params: 바인딩 파라미터.

    Returns:
        행 dict 목록.
    """
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(sql, params or {})
        return [dict(row) for row in cur.fetchall()]


def _window_targets(conn, since: str, until: str, actor: int | None) -> list[int]:
    """사고 창에서 상태가 건드려진 주문 id 를 모은다.

    감사행(ORDER_STATUS_CHANGED)과 이벤트(STAGE_OVERRIDE/STAGE_CHANGED)를 합집합으로 본다 —
    경로마다 남기는 흔적이 다르기 때문이다(2026-08-14 사고는 두 경로가 섞여 있었다).

    Args:
        conn: 접속.
        since: 시작 시각(naive UTC).
        until: 종료 시각(naive UTC).
        actor: 행위자 user id 로 좁히려면 지정.

    Returns:
        오름차순 주문 id 목록.
    """
    actor_log = "AND l.user_id = %(actor)s" if actor is not None else ""
    actor_evt = "AND e.created_by_user_id = %(actor)s" if actor is not None else ""
    params = {"since": since, "until": until, "actor": actor}
    logged = _rows(conn, f"""
        SELECT DISTINCT l.target_id AS oid FROM security_logs l
         WHERE l.action = 'ORDER_STATUS_CHANGED' AND l.target_id IS NOT NULL
           AND l.timestamp >= %(since)s AND l.timestamp <= %(until)s {actor_log}
    """, params)
    evented = _rows(conn, f"""
        SELECT DISTINCT e.order_id AS oid FROM order_events e
         WHERE e.event_type IN ('STAGE_OVERRIDE','STAGE_CHANGED')
           AND e.created_at >= %(since)s AND e.created_at <= %(until)s {actor_evt}
    """, params)
    return sorted({int(r["oid"]) for r in logged + evented if r["oid"] is not None})


def _evidence_from_logs(conn, ids: list[int], since: str, until: str) -> dict[int, dict[str, Any]]:
    """감사행에서 사고 창 최초의 before/after 상태를 뽑는다(confidence=logged).

    Args:
        conn: 접속.
        ids: 대상 주문 id.
        since: 창 시작(naive UTC).
        until: 창 종료(naive UTC).

    Returns:
        order_id → {before, after, confidence, source}.
    """
    if not ids:
        return {}
    rows = _rows(conn, """
        SELECT DISTINCT ON (l.target_id) l.target_id AS oid,
               l.detail->>'before' AS before_status, l.detail->>'after' AS after_status
          FROM security_logs l
         WHERE l.action = 'ORDER_STATUS_CHANGED' AND l.target_id = ANY(%(ids)s)
           AND l.timestamp >= %(since)s AND l.timestamp <= %(until)s
         ORDER BY l.target_id, l.timestamp ASC
    """, {"ids": ids, "since": since, "until": until})
    out: dict[int, dict[str, Any]] = {}
    for row in rows:
        if not row["before_status"]:
            continue
        out[int(row["oid"])] = {
            "before": row["before_status"], "after": row["after_status"],
            "confidence": "logged", "source": "security_logs.detail.before",
        }
    return out


def _evidence_from_events(conn, ids: list[int], since: str, until: str) -> dict[int, dict[str, Any]]:
    """이벤트 payload 에서 이전 상태를 뽑는다(confidence=event).

    ``from_status`` 는 2026-08-14 사고 후 추가된 필드다(그전 이벤트는 ``from`` = stage 라
    상태축과 다를 수 있어 stage 로만 쓴다).

    Args:
        conn: 접속.
        ids: 대상 주문 id.
        since: 창 시작(naive UTC).
        until: 창 종료(naive UTC).

    Returns:
        order_id → {before?, stage_before, confidence, source}.
    """
    if not ids:
        return {}
    rows = _rows(conn, """
        SELECT DISTINCT ON (e.order_id) e.order_id AS oid, e.payload
          FROM order_events e
         WHERE e.event_type IN ('STAGE_OVERRIDE','STAGE_CHANGED') AND e.order_id = ANY(%(ids)s)
           AND e.created_at >= %(since)s AND e.created_at <= %(until)s
         ORDER BY e.order_id, e.created_at ASC
    """, {"ids": ids, "since": since, "until": until})
    out: dict[int, dict[str, Any]] = {}
    for row in rows:
        payload = row["payload"] or {}
        entry: dict[str, Any] = {
            "stage_before": payload.get("from"), "confidence": "event",
            "source": "order_events.payload",
        }
        if payload.get("from_status"):
            entry["before"] = payload["from_status"]
        elif payload.get("as_overlay_cleared"):
            entry["before"] = payload["as_overlay_cleared"]
        out[int(row["oid"])] = entry
    return out


def _evidence_from_as_history(conn, ids: list[int], since: str) -> dict[int, dict[str, Any]]:
    """사고 직전 마지막 AS 이벤트로 상태를 유도한다(confidence=inferred).

    AS 접수(AS_REGISTERED)가 마지막이면 ``AS_RECEIVED``, AS 완료가 마지막이면
    ``AS_COMPLETED`` 였다고 본다. 근거가 약하므로 사람 확인용으로만 쓴다.

    Args:
        conn: 접속.
        ids: 대상 주문 id.
        since: 사고 창 시작(이 시각 이전 이벤트만 본다).

    Returns:
        order_id → {before, confidence, source}.
    """
    if not ids:
        return {}
    rows = _rows(conn, """
        SELECT DISTINCT ON (e.order_id) e.order_id AS oid, e.event_type, e.created_at
          FROM order_events e
         WHERE e.event_type IN ('AS_REGISTERED','AS_COMPLETED') AND e.order_id = ANY(%(ids)s)
           AND e.created_at < %(since)s
         ORDER BY e.order_id, e.created_at DESC
    """, {"ids": ids, "since": since})
    mapping = {"AS_REGISTERED": "AS_RECEIVED", "AS_COMPLETED": "AS_COMPLETED"}
    return {
        int(row["oid"]): {
            "before": mapping[row["event_type"]], "confidence": "inferred",
            "source": f"order_events.{row['event_type']}@{row['created_at']}",
        }
        for row in rows if row["event_type"] in mapping
    }


def _evidence_from_snapshot(snapshot_dsn: str, ids: list[int]) -> dict[int, dict[str, Any]]:
    """PITR fork DB 에서 사고 직전 원본값을 읽는다(confidence=exact).

    Args:
        snapshot_dsn: fork DB DSN(:mod:`tools.ops.railway_pitr` fork 산출물).
        ids: 대상 주문 id.

    Returns:
        order_id → {before, stage_before, workflow_stage, confidence, source}.
    """
    if not ids:
        return {}
    conn = _connect(snapshot_dsn, readonly=True)
    try:
        rows = _rows(conn, """
            SELECT id, status, erp_stage_code, structured_data->'workflow'->>'stage' AS wf_stage
              FROM orders WHERE id = ANY(%(ids)s)
        """, {"ids": ids})
    finally:
        conn.close()
    return {
        int(row["id"]): {
            "before": row["status"], "stage_before": row["erp_stage_code"],
            "workflow_stage": row["wf_stage"], "confidence": "exact",
            "source": "pitr_snapshot.orders",
        }
        for row in rows
    }


def _merge_evidence(*layers: dict[int, dict[str, Any]]) -> dict[int, dict[str, Any]]:
    """여러 증거 층을 confidence 우선순위로 합친다.

    Args:
        *layers: order_id → 증거 dict 매핑들.

    Returns:
        order_id → 최고 신뢰 증거(부족한 필드는 하위 층에서 보충).
    """
    merged: dict[int, dict[str, Any]] = {}
    for layer in layers:
        for oid, evidence in layer.items():
            current = merged.get(oid)
            if current is None:
                merged[oid] = dict(evidence)
                continue
            new_rank = CONFIDENCE_RANK.get(evidence.get("confidence", ""), 0)
            old_rank = CONFIDENCE_RANK.get(current.get("confidence", ""), 0)
            if new_rank > old_rank:
                merged[oid] = {**current, **evidence}
            else:
                merged[oid] = {**evidence, **current}
    return merged


def _current_rows(conn, ids: list[int]) -> dict[int, dict[str, Any]]:
    """대상 주문의 현재 상태를 읽는다.

    Args:
        conn: 접속.
        ids: 주문 id 목록.

    Returns:
        order_id → 현재 컬럼 dict.
    """
    if not ids:
        return {}
    rows = _rows(conn, """
        SELECT id, customer_name, status, erp_stage_code, deleted_at,
               structured_data->'workflow'->>'stage' AS wf_stage
          FROM orders WHERE id = ANY(%(ids)s)
    """, {"ids": ids})
    return {int(row["id"]): row for row in rows}


def _build_plan_items(
    current: dict[int, dict[str, Any]],
    evidence: dict[int, dict[str, Any]],
    *,
    only_as: bool,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """복구 항목과 제외 항목을 만든다.

    Args:
        current: 주문 현재 상태.
        evidence: 합쳐진 증거.
        only_as: True 면 이전 상태가 AS overlay 인 항목만 복구 대상으로 둔다.

    Returns:
        (복구 항목 목록, 제외 항목 목록).
    """
    items: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    for oid in sorted(current):
        row = current[oid]
        found = evidence.get(oid) or {}
        before = found.get("before")
        if not before:
            skipped.append({"order_id": oid, "reason": "이전 상태 근거 없음"})
            continue
        if before == row["status"]:
            skipped.append({"order_id": oid, "reason": "이미 이전 상태 그대로"})
            continue
        if only_as and before not in AS_OVERLAY_STATUSES:
            skipped.append({"order_id": oid, "reason": f"AS 대상 아님(before={before})"})
            continue
        items.append({
            "order_id": oid,
            "customer_name": row.get("customer_name"),
            "restore_status": before,
            "observed_status": row["status"],
            "restore_stage": found.get("stage_before") or found.get("workflow_stage") or before,
            "observed_stage": row.get("erp_stage_code"),
            "confidence": found.get("confidence"),
            "evidence": found.get("source"),
        })
    return items, skipped


def _print_plan(items: list[dict[str, Any]], skipped: list[dict[str, Any]]) -> None:
    """복구안을 사람이 읽는 표로 출력한다.

    Args:
        items: 복구 항목.
        skipped: 제외 항목.
    """
    print(f"복구 대상 {len(items)}건 / 제외 {len(skipped)}건")
    by_confidence: dict[str, int] = {}
    for item in items:
        by_confidence[item["confidence"]] = by_confidence.get(item["confidence"], 0) + 1
    if by_confidence:
        print("근거 신뢰도:", ", ".join(f"{k}={v}" for k, v in sorted(by_confidence.items())))
    for item in items[:50]:
        print(f"  #{item['order_id']} {item.get('customer_name') or ''} "
              f"{item['observed_status']} → {item['restore_status']} "
              f"(stage {item['observed_stage']} → {item['restore_stage']}, {item['confidence']})")
    if len(items) > 50:
        print(f"  ... 외 {len(items) - 50}건 (plan JSON 참조)")
    if skipped:
        reasons: dict[str, int] = {}
        for entry in skipped:
            reasons[entry["reason"]] = reasons.get(entry["reason"], 0) + 1
        print("제외 사유:", ", ".join(f"{k}={v}" for k, v in reasons.items()))


def cmd_inspect(args: argparse.Namespace) -> int:
    """사고 창에서 무슨 변경이 몇 건 있었는지 요약한다(읽기 전용).

    Args:
        args: ``dsn``·``since``·``until``·``actor`` 를 갖는 인자.

    Returns:
        종료 코드 0.
    """
    conn = _connect(args.dsn, readonly=True)
    try:
        actor_clause = "AND l.user_id = %(actor)s" if args.actor is not None else ""
        params = {"since": args.since, "until": args.until, "actor": args.actor}
        print("=== 감사행(security_logs) ===")
        for row in _rows(conn, f"""
            SELECT l.action, count(*) AS cnt, min(l.timestamp) AS first_at, max(l.timestamp) AS last_at
              FROM security_logs l
             WHERE l.timestamp >= %(since)s AND l.timestamp <= %(until)s {actor_clause}
             GROUP BY l.action ORDER BY cnt DESC LIMIT 15
        """, params):
            print(f"  {row['action']}\t{row['cnt']}건\t{row['first_at']} ~ {row['last_at']}")
        print("=== 이벤트(order_events) ===")
        for row in _rows(conn, """
            SELECT event_type, count(*) AS cnt FROM order_events
             WHERE created_at >= %(since)s AND created_at <= %(until)s
             GROUP BY event_type ORDER BY cnt DESC LIMIT 15
        """, params):
            print(f"  {row['event_type']}\t{row['cnt']}건")
        targets = _window_targets(conn, args.since, args.until, args.actor)
        print(f"상태가 건드려진 주문: {len(targets)}건")
    finally:
        conn.close()
    return 0


def cmd_plan(args: argparse.Namespace) -> int:
    """복구안을 계산해 표로 보여주고 JSON 으로 저장한다(쓰기 없음).

    Args:
        args: ``dsn``·``since``·``until``·``actor``·``only_as``·``snapshot_dsn``·``out`` 인자.

    Returns:
        종료 코드(0=성공, 2=대상 상한 초과).
    """
    conn = _connect(args.dsn, readonly=True)
    try:
        ids = _window_targets(conn, args.since, args.until, args.actor)
        if len(ids) > args.max_targets:
            print(f"대상 {len(ids)}건 > 상한 {args.max_targets}건 — 창을 좁히거나 --max-targets 를 올려라.")
            return 2
        evidence_layers = [
            _evidence_from_as_history(conn, ids, args.since),
            _evidence_from_events(conn, ids, args.since, args.until),
            _evidence_from_logs(conn, ids, args.since, args.until),
        ]
        if args.snapshot_dsn:
            evidence_layers.append(_evidence_from_snapshot(args.snapshot_dsn, ids))
        evidence = _merge_evidence(*evidence_layers)
        current = _current_rows(conn, ids)
        items, skipped = _build_plan_items(current, evidence, only_as=args.only_as)
    finally:
        conn.close()
    _print_plan(items, skipped)
    plan = {
        "created_at": datetime.now(timezone.utc).replace(tzinfo=None).isoformat(),
        "window": {"since": args.since, "until": args.until, "actor": args.actor},
        "only_as": args.only_as,
        "snapshot_used": bool(args.snapshot_dsn),
        "items": items,
        "skipped": skipped,
    }
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(plan, fh, ensure_ascii=False, indent=1)
    print(f"복구안 저장: {args.out} — 검토 후 apply --plan 으로 적용하라(기본은 아무것도 안 바꾼다).")
    return 0


def _apply_one(cur, item: dict[str, Any], *, actor_user_id: int, now: datetime, reason: str) -> str:
    """복구 1건을 적용한다(호출부가 트랜잭션·락 소유).

    Args:
        cur: 커서(RealDictCursor).
        item: 복구 항목.
        actor_user_id: 복구 감사행 행위자.
        now: 기록 시각(naive UTC).
        reason: 복구 사유 문자열.

    Returns:
        ``applied`` 또는 ``skipped:<사유>``.
    """
    oid = int(item["order_id"])
    cur.execute("SELECT status, structured_data FROM orders WHERE id = %s FOR UPDATE", (oid,))
    row = cur.fetchone()
    if row is None:
        return "skipped:주문 없음"
    if row["status"] != item["observed_status"]:
        return f"skipped:현재 상태 {row['status']} (계획과 다름)"
    structured = dict(row["structured_data"] or {})
    workflow = dict(structured.get("workflow") or {})
    workflow["stage"] = item["restore_stage"]
    workflow["stage_updated_at"] = now.isoformat()
    workflow["stage_updated_by"] = "data_doctor 복구"
    structured["workflow"] = workflow
    cur.execute("""
        UPDATE orders SET status = %s, erp_stage_code = %s, erp_stage_updated_at = %s,
               structured_data = %s WHERE id = %s
    """, (item["restore_status"], item["restore_stage"], now,
          psycopg2.extras.Json(structured), oid))
    cur.execute("""
        INSERT INTO order_events(order_id, event_type, payload, created_by_user_id, created_at)
        VALUES (%s, 'STAGE_OVERRIDE', %s, %s, %s)
    """, (oid, psycopg2.extras.Json({
        "from": item["observed_stage"], "to": item["restore_stage"], "mode": "restore",
        "manual": True, "reason": reason, "from_status": item["observed_status"],
        "restored_status": item["restore_status"], "confidence": item.get("confidence"),
        "evidence": item.get("evidence"),
    }), actor_user_id, now))
    cur.execute("""
        INSERT INTO security_logs(timestamp, user_id, message, action, target_type, target_id, detail)
        VALUES (%s, %s, %s, 'ORDER_STATUS_CHANGED', 'order', %s, %s)
    """, (now, actor_user_id,
          f"주문 #{oid} ({item.get('customer_name') or ''}) — 상태 복구: "
          f"{item['observed_status']} → {item['restore_status']} ({reason})", oid,
          psycopg2.extras.Json({
              "field": "status", "before": item["observed_status"],
              "after": item["restore_status"], "restore": True, "reason": reason,
              "confidence": item.get("confidence"), "evidence": item.get("evidence"),
          })))
    return "applied"


def cmd_apply(args: argparse.Namespace) -> int:
    """복구안을 단일 트랜잭션으로 적용한다(--yes 필수).

    Args:
        args: ``dsn``·``plan``·``yes``·``reason``·``actor_user_id``·``snapshot_out`` 인자.

    Returns:
        종료 코드(0=적용, 2=미승인).
    """
    with open(args.plan, encoding="utf-8") as fh:
        plan = json.load(fh)
    items: list[dict[str, Any]] = plan.get("items") or []
    if not items:
        print("복구 항목이 없습니다.")
        return 0
    if not args.yes:
        print(f"복구 대상 {len(items)}건 — 실제 적용하려면 --yes 를 붙여라(지금은 아무것도 안 바꿨다).")
        return 2
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    conn = _connect(args.dsn, readonly=False)
    try:
        ids = [int(item["order_id"]) for item in items]
        snapshot = _current_rows(conn, ids)
        with open(args.snapshot_out, "w", encoding="utf-8") as fh:
            json.dump({"created_at": now.isoformat(),
                       "rows": [{k: str(v) if v is not None else None for k, v in row.items()}
                                for row in snapshot.values()]}, fh, ensure_ascii=False, indent=1)
        results: dict[str, int] = {}
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            for item in items:
                outcome = _apply_one(cur, item, actor_user_id=args.actor_user_id,
                                     now=now, reason=args.reason)
                key = outcome.split(":", 1)[0]
                results[key] = results.get(key, 0) + 1
                if outcome != "applied":
                    print(f"  #{item['order_id']} {outcome}")
        conn.commit()
    finally:
        conn.close()
    print("적용 결과:", ", ".join(f"{k}={v}" for k, v in sorted(results.items())))
    print(f"되돌리기용 스냅샷: {args.snapshot_out}")
    return 0


def cmd_rollback(args: argparse.Namespace) -> int:
    """스냅샷 파일 상태로 되돌린다(--yes 필수).

    Args:
        args: ``dsn``·``snapshot``·``yes`` 인자.

    Returns:
        종료 코드(0=적용, 2=미승인).
    """
    with open(args.snapshot, encoding="utf-8") as fh:
        snapshot = json.load(fh)
    rows: list[dict[str, Any]] = snapshot.get("rows") or []
    if not args.yes:
        print(f"되돌릴 행 {len(rows)}건 — 실제 실행하려면 --yes 를 붙여라.")
        return 2
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    conn = _connect(args.dsn, readonly=False)
    try:
        with conn.cursor() as cur:
            for row in rows:
                cur.execute("""
                    UPDATE orders SET status = %s, erp_stage_code = %s, erp_stage_updated_at = %s
                     WHERE id = %s
                """, (row["status"], row.get("erp_stage_code"), now, int(row["id"])))
        conn.commit()
    finally:
        conn.close()
    print(f"되돌리기 완료: {len(rows)}건")
    return 0


def _add_window_args(parser: argparse.ArgumentParser) -> None:
    """사고 창 공통 인자를 붙인다.

    Args:
        parser: 대상 서브파서.
    """
    parser.add_argument("--dsn", required=True, help="PostgreSQL DSN(운영은 DATABASE_PUBLIC_URL)")
    parser.add_argument("--since", required=True, help="사고 창 시작(naive UTC, 예: 2026-08-14T06:25:00)")
    parser.add_argument("--until", required=True, help="사고 창 종료(naive UTC)")
    parser.add_argument("--actor", type=int, default=None, help="행위자 user id 로 좁히기")


def build_parser() -> argparse.ArgumentParser:
    """CLI 파서를 만든다.

    Returns:
        서브커맨드가 붙은 파서.
    """
    parser = argparse.ArgumentParser(description="데이터 사고 복구 도구(조사 → 계획 → 적용)")
    sub = parser.add_subparsers(dest="command", required=True)

    p_inspect = sub.add_parser("inspect", help="사고 창 변경 요약(읽기 전용)")
    _add_window_args(p_inspect)
    p_inspect.set_defaults(func=cmd_inspect)

    p_plan = sub.add_parser("plan", help="복구안 산출(쓰기 없음)")
    _add_window_args(p_plan)
    p_plan.add_argument("--only-as", action="store_true", help="AS 상태 복구만 대상으로")
    p_plan.add_argument("--snapshot-dsn", default=None, help="PITR fork DB DSN(정확값 근거)")
    p_plan.add_argument("--max-targets", type=int, default=MAX_TARGETS)
    p_plan.add_argument("--out", default="data_doctor_plan.json")
    p_plan.set_defaults(func=cmd_plan)

    p_apply = sub.add_parser("apply", help="복구안 적용(--yes 필수)")
    p_apply.add_argument("--dsn", required=True)
    p_apply.add_argument("--plan", required=True)
    p_apply.add_argument("--yes", action="store_true")
    p_apply.add_argument("--reason", default="데이터 사고 복구(data doctor)")
    p_apply.add_argument("--actor-user-id", type=int, default=DEFAULT_RESTORE_ACTOR)
    p_apply.add_argument("--snapshot-out", default="data_doctor_snapshot.json")
    p_apply.set_defaults(func=cmd_apply)

    p_rollback = sub.add_parser("rollback", help="스냅샷으로 되돌리기(--yes 필수)")
    p_rollback.add_argument("--dsn", required=True)
    p_rollback.add_argument("--snapshot", required=True)
    p_rollback.add_argument("--yes", action="store_true")
    p_rollback.set_defaults(func=cmd_rollback)
    return parser


def main(argv: list[str] | None = None) -> int:
    """엔트리포인트.

    Args:
        argv: 인자 목록(기본 ``sys.argv[1:]``).

    Returns:
        프로세스 종료 코드.
    """
    args = build_parser().parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main())
