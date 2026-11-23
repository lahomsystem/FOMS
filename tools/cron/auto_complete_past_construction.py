"""매일 밤 — 시공일이 어제까지인 미완료 ERP 주문을 완료로 (설계서 docs/specs/2026-11-23-daily-backlog-auto-complete_SPEC.md).

판정·쓰기는 손 도구 ``tools/ops/bulk_complete_past_construction.py`` 와 같은 core 함수다
(``--cutoff-days 0``: 시공일 < 오늘 KST). AS 주문은 stage 만 바꾸고 status·AS 칸은 그대로다.

* ``--apply`` 가 없으면 대상만 세어 한 줄 찍고 아무것도 안 바꾼다(다른 밤 단계와 같은 계약).
* 대상이 ``--max-rows`` 를 넘으면 하나도 안 바꾸고 exit 3 — 시공일 일괄 오입력 같은 사고를 사람이 보게.
* 행위자는 env ``FOMS_AUTO_COMPLETE_ACTOR_ID``. 없거나 숫자가 아니면 exit 3.
* 스냅샷 파일이 남지 않는 컨테이너라 이전값은 이벤트 payload ``before`` 에 싣는다. 되돌리기:
  ``python tools/ops/bulk_complete_past_construction.py rollback --dsn … --from-events auto-YYYY-MM-DD --actor … --yes``.

로그에는 주문 id 만 찍는다(고객 이름·전화 없음).
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "tools" / "ops"))

from bulk_complete_past_construction_core import (  # noqa: E402
    CHUNK_SIZE,
    _connect,
    _rows,
    apply_one,
    build_plan,
    cutoff_iso,
    dict_row,
    fetch_candidates,
    today_kst,
)

ACTOR_ENV = "FOMS_AUTO_COMPLETE_ACTOR_ID"
DEFAULT_MAX_ROWS = 200
REASON = "매일 자동 완료(시공일이 어제까지)"
GUARD_EXIT = 3


def batch_name(today_iso: str) -> str:
    """그날 배치 이름 — 되돌리기(``--from-events``)의 열쇠."""
    return f"auto-{today_iso}"


def actor_from_env(environ: dict[str, str] | None = None) -> int | None:
    """행위자 user id(없거나 숫자가 아니면 None)."""
    raw = str((environ if environ is not None else os.environ).get(ACTOR_ENV) or "").strip()
    return int(raw) if raw.isdigit() and int(raw) > 0 else None


def dsn_from_env() -> str:
    """``DATABASE_URL`` 을 psycopg 가 읽는 ``postgresql://`` 로."""
    from foms.services.db_url_resolver import _strip_postgres_driver

    url = os.environ.get("DATABASE_URL") or ""
    if not url:
        raise SystemExit("DATABASE_URL is not set")
    return _strip_postgres_driver(url)


def env_label(conn) -> str:
    """데이터 지문(손 도구와 같은 TESTCLR 규칙) — 로그 표시용."""
    n = int(_rows(conn, "SELECT count(*) AS n FROM orders WHERE customer_name LIKE 'TESTCLR%%'")[0]["n"])
    return "staging" if n else "production"


def run(conn, *, apply: bool, actor: int | None, max_rows: int,
        now: datetime | None = None) -> tuple[int, dict[str, Any]]:
    """plan → (상한·행위자 검사) → apply. ``(exit code, 요약)`` 을 돌려준다. 호출부가 conn 을 닫는다."""
    today = today_kst().isoformat()
    cutoff = cutoff_iso(today_kst(), 0)
    plan = build_plan(fetch_candidates(conn, cutoff=cutoff), cutoff=cutoff, today=today, cutoff_days=0)
    conn.rollback()  # 읽기 트랜잭션을 닫는다
    s = plan["summary"]
    out: dict[str, Any] = {"env": env_label(conn), "today": today, "cutoff": cutoff,
                           "planned": s["items"], "main": s["main"], "as_stage_only": s["as_stage_only"],
                           "skipped": s["skipped"], "applied": 0, "other": {}}
    conn.rollback()
    if not apply or not plan["items"]:
        return 0, out
    if actor is None:
        out["error"] = f"{ACTOR_ENV} 없음"
        return GUARD_EXIT, out
    if s["items"] > max_rows:
        out["error"] = f"대상 {s['items']}건 > 상한 {max_rows} — 아무것도 안 바꿈"
        return GUARD_EXIT, out
    batch = batch_name(today)
    now = now or datetime.now(timezone.utc).replace(tzinfo=None)
    items = plan["items"]
    for start in range(0, len(items), CHUNK_SIZE):
        with conn.cursor(row_factory=dict_row) as cur:
            for item in items[start:start + CHUNK_SIZE]:
                outcome = apply_one(cur, item, actor_user_id=actor, now=now, reason=REASON,
                                    cutoff=cutoff, batch=batch, keep_before=True)
                if outcome == "applied":
                    out["applied"] += 1
                else:
                    out["other"][f"#{item['order_id']}"] = outcome
        conn.commit()
    out["batch"] = batch
    return 0, out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("--apply", action="store_true", help="실제로 바꾼다(없으면 세기만)")
    parser.add_argument("--max-rows", type=int, default=DEFAULT_MAX_ROWS)
    args = parser.parse_args(argv)
    conn = _connect(dsn_from_env(), readonly=False)
    try:
        code, out = run(conn, apply=args.apply, actor=actor_from_env(), max_rows=args.max_rows)
    finally:
        conn.close()
    print("[auto_complete] " + " ".join(f"{k}={v}" for k, v in out.items()), flush=True)
    return code


if __name__ == "__main__":
    sys.exit(main())
