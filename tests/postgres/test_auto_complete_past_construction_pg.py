"""매일 자동 완료 밤 단계 PostgreSQL 계약 (설계서 docs/specs/2026-11-23-daily-backlog-auto-complete_SPEC.md).

잠그는 계약:

* 행위자 env 없음 · 대상이 상한 초과 · ``--apply`` 없음 → 쓰기 0.
* main 건은 stage·status 완료, AS 건은 stage 만(status·as_axis_status 그대로), 보류 건(음성 대조군) 불변.
* 이벤트 batch 가 ``auto-<오늘>`` 이고 payload ``before`` 에 이전값이 실린다.
* 같은 날 두 번째 실행은 대상 0(멱등).
* ``rollback --from-events`` 경로(``snapshot_rows_from_events`` + ``rollback_one``)가 stage·status·workflow 를 되돌린다.
"""
from __future__ import annotations

import importlib.util
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from sqlalchemy import text

psycopg = pytest.importorskip("psycopg")

_ROOT = Path(__file__).resolve().parents[2]


def _load(name: str, rel: str):
    spec = importlib.util.spec_from_file_location(name, _ROOT / rel)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


auto = _load("auto_complete_past_construction_pg", "tools/cron/auto_complete_past_construction.py")
cli = _load("bulk_complete_cli_for_auto_pg", "tools/ops/bulk_complete_past_construction.py")

ACTOR = 900101
TODAY = auto.today_kst()
PAST = (TODAY - timedelta(days=3)).isoformat()
WF = {"stage": "", "stage_updated_at": "2026-08-01T00:00:00", "history": [{"k": 1}]}
SEED = [
    # id, status, stage, as_axis
    (301, "DRAWING", "DRAWING", None),
    (302, "AS_RECEIVED", "PRODUCTION", "RECEIVED"),
    (303, "ON_HOLD", "DRAWING", None),   # 음성 대조군 — 보류는 손대지 않는다
]


def _seed(engine) -> None:
    with engine.begin() as conn:
        conn.execute(text("""
            INSERT INTO users(id, username, password, name, role, is_active)
            VALUES (:id, 'auto_actor', 'x', 'auto', 'ADMIN', true) ON CONFLICT (id) DO NOTHING
        """), {"id": ACTOR})
        for oid, status, stage, as_axis in SEED:
            sd = {"workflow": {**WF, "stage": stage}, "meta": {}}
            conn.execute(text("""
                INSERT INTO orders(id, received_date, customer_name, phone, address, product,
                                   status, is_erp_order, erp_stage_code, erp_construction_date,
                                   as_axis_status, structured_data, mutation_version, structured_schema_version)
                VALUES (:id, '2026-08-01', :name, '010', 'addr', 'p', :status, true, :stage, :cons,
                        :as_axis, CAST(:sd AS jsonb), 1, 1)
            """), {"id": oid, "name": f"자동{oid}", "status": status, "stage": stage, "cons": PAST,
                   "as_axis": as_axis, "sd": json.dumps(sd, ensure_ascii=False)})


def _state(engine) -> dict[int, tuple]:
    with engine.connect() as conn:
        res = conn.execute(text("""
            SELECT id, status, erp_stage_code, as_axis_status, structured_data->'workflow' AS wf
              FROM orders WHERE id BETWEEN 301 AND 303 ORDER BY id
        """))
        return {r.id: (r.status, r.erp_stage_code, r.as_axis_status, r.wf) for r in res}


@pytest.fixture(scope="module")
def dsn(pg_engine) -> str:
    _seed(pg_engine)
    return pg_engine.url.set(drivername="postgresql").render_as_string(hide_password=False)


def _run(dsn: str, **kwargs):
    conn = auto._connect(dsn, readonly=False)
    try:
        return auto.run(conn, **kwargs)
    finally:
        conn.close()


def test_guards_write_nothing(pg_engine, dsn):
    before = _state(pg_engine)
    code, out = _run(dsn, apply=False, actor=ACTOR, max_rows=200)
    assert code == 0 and out["planned"] == 2 and out["applied"] == 0
    code, out = _run(dsn, apply=True, actor=None, max_rows=200)
    assert code == auto.GUARD_EXIT and out["applied"] == 0
    code, out = _run(dsn, apply=True, actor=ACTOR, max_rows=1)
    assert code == auto.GUARD_EXIT and out["applied"] == 0
    assert _state(pg_engine) == before


def test_apply_is_idempotent_and_rolls_back_from_events(pg_engine, dsn):
    before = _state(pg_engine)
    code, out = _run(dsn, apply=True, actor=ACTOR, max_rows=200)
    assert code == 0 and out["applied"] == 2 and out["batch"] == f"auto-{TODAY.isoformat()}"
    after = _state(pg_engine)
    assert after[301][:2] == ("COMPLETED", "COMPLETED")
    assert after[302][:3] == ("AS_RECEIVED", "COMPLETED", "RECEIVED")   # AS 는 stage 만
    assert after[303] == before[303]                                    # 보류 불변

    with pg_engine.connect() as conn:
        payloads = [r.payload for r in conn.execute(text(
            "SELECT payload FROM order_events WHERE event_type='STAGE_OVERRIDE' AND order_id IN (301,302)"))]
    assert {p["batch"] for p in payloads} == {out["batch"]}
    assert {p["before"]["status"] for p in payloads} == {"DRAWING", "AS_RECEIVED"}

    code, again = _run(dsn, apply=True, actor=ACTOR, max_rows=200)
    assert code == 0 and again["planned"] == 0 and again["applied"] == 0

    conn = cli._connect(dsn, readonly=False)
    try:
        rows = cli.snapshot_rows_from_events(conn, out["batch"])
        assert [r["id"] for r in rows] == [301, 302]
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        with conn.cursor(row_factory=cli.dict_row) as cur:
            results = [cli.rollback_one(cur, r, actor_user_id=ACTOR, now=now, batch=out["batch"]) for r in rows]
        conn.commit()
    finally:
        conn.close()
    assert results == ["applied", "applied"]
    restored = _state(pg_engine)
    assert restored == before
