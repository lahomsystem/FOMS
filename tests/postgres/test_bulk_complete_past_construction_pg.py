"""BACKLOG-COMPLETE-01 apply/rollback PostgreSQL 계약 (PGTEST-00 lane).

``tools/ops/bulk_complete_past_construction.py`` 의 쓰기 경로를 실 PostgreSQL 로 검증한다.
스크립트는 psycopg2 로 **자기 접속**을 열므로 ``pg_session``(롤백 트랜잭션)이 아니라
``pg_engine`` 으로 커밋된 시드를 쓴다(모듈 종료 시 conftest 가 DB 를 초기화한다).

잠그는 계약:

* main 건: stage·status·평면 컬럼 모두 COMPLETED, 이벤트·감사행 1건씩.
* AS 탭 건(미완료·완료): stage 만 COMPLETED — ``status``·``as_axis_status``·``as_lifecycle``·
  ``as_completed_date`` 바이트 동일. AS 대시보드 두 탭 술어의 모집단이 적용 전후 같다.
* 제외(보류·물류·열린 네이버 클레임·시공일 미래·시공일 없음)는 plan 에 사유로만 남고 안 건드린다.
* plan 뒤 바뀐 행은 apply 가 stale 로 건너뛴다.
* rollback 후 status·erp_stage_code·workflow dict 가 시드와 같다.
* 운영 지문 가드: TESTCLR 고객이 있으면 ``--expect-env production`` 이 중단한다.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest
from sqlalchemy import text

from foms.services.as_dashboard_helpers import (
    _erp_as_completed_condition,
    _erp_as_incomplete_condition,
)
from models import Order

_MODULE_PATH = Path(__file__).resolve().parents[2] / "tools" / "ops" / "bulk_complete_past_construction.py"
_spec = importlib.util.spec_from_file_location("bulk_complete_past_construction_pg", _MODULE_PATH)
mod = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(mod)

psycopg2 = pytest.importorskip("psycopg2")

ACTOR = 900001
CUTOFF = "2026-09-15"
PAST = "2026-08-20"
FUTURE = "2026-12-01"


def _wf(stage: str, **extra) -> dict:
    return {"stage": stage, "stage_updated_at": "2026-08-01T00:00:00", "history": [{"k": 1}], **extra}


def _sd(stage: str, *, as_axis: str | None = None, quests=None) -> dict:
    sd = {"workflow": _wf(stage), "meta": {}, "parties": {"orderer": {"name": "x"}}}
    if as_axis:
        sd["as_lifecycle"] = {"current_cycle_id": "c1", "cycles": [{"cycle_id": "c1", "status": as_axis}]}
    if quests is not None:
        sd["quests"] = quests
    return sd


SEED = [
    # id, status, stage, cons_date, as_axis, sd, as_completed_date
    (101, "MEASURE", "MEASURE", PAST, None, _sd("MEASURE", quests=[{"status": "OPEN"}]), None),
    (102, "DRAWING", "DRAWING", PAST, None, _sd("DRAWING"), None),
    (103, "AS_RECEIVED", "MEASURE", PAST, "RECEIVED", _sd("MEASURE", as_axis="RECEIVED"), None),
    (104, "AS_COMPLETED", "MEASURE", PAST, "COMPLETED", _sd("MEASURE", as_axis="COMPLETED"), "2026-08-30"),
    (105, "ON_HOLD", "MEASURE", PAST, None, _sd("MEASURE"), None),
    (106, "SCHEDULED", "DRAWING", PAST, None, _sd("DRAWING"), None),
    (107, "MEASURE", "MEASURE", PAST, None, _sd("MEASURE"), None),   # 네이버 클레임 열림
    (108, "MEASURE", "MEASURE", FUTURE, None, _sd("MEASURE"), None),
    (109, "MEASURE", "MEASURE", None, None, _sd("MEASURE"), None),
    (110, "AS_RECEIVED", "AS_RECEIVED", PAST, "RECEIVED", _sd("AS_RECEIVED", as_axis="RECEIVED"), None),
]


def _seed(engine) -> None:
    with engine.begin() as conn:
        conn.execute(text("""
            INSERT INTO users(id, username, password, name, role, is_active)
            VALUES (:id, 'bulk_actor', 'x', 'bulk', 'ADMIN', true)
            ON CONFLICT (id) DO NOTHING
        """), {"id": ACTOR})
        for oid, status, stage, cons, as_axis, sd, as_done in SEED:
            conn.execute(text("""
                INSERT INTO orders(id, received_date, customer_name, phone, address, product,
                                   status, is_erp_order, erp_stage_code, erp_construction_date,
                                   as_axis_status, as_completed_date, structured_data, mutation_version,
                                   structured_schema_version)
                VALUES (:id, '2026-08-01', :name, '010', 'addr', 'p', :status, true, :stage, :cons,
                        :as_axis, :as_done, CAST(:sd AS jsonb), 1, 1)
            """), {"id": oid, "name": f"고객{oid}", "status": status, "stage": stage, "cons": cons,
                   "as_axis": as_axis, "as_done": as_done, "sd": json.dumps(sd, ensure_ascii=False)})
        conn.execute(text("""
            INSERT INTO external_order_links(channel, external_id, order_id, sync_status, relation,
                                             triage_state, created_at, updated_at)
            VALUES ('NAVER', 'ext-107', 107, 'LINKED', 'NEW',
                    CAST(:ts AS jsonb), now(), now())
        """), {"ts": json.dumps({"claim_sync": {"last_status": "RETURN_REQUEST"}})})


def _rows(engine) -> dict[int, dict]:
    with engine.connect() as conn:
        res = conn.execute(text("""
            SELECT id, status, erp_stage_code, as_axis_status, as_completed_date,
                   structured_data->'workflow' AS wf, structured_data->'as_lifecycle' AS asl,
                   mutation_version
              FROM orders WHERE id BETWEEN 101 AND 110 ORDER BY id
        """))
        return {r.id: dict(r._mapping) for r in res}


def _as_tab_ids(session) -> tuple[set[int], set[int]]:
    inc = {o.id for o in session.query(Order.id).filter(_erp_as_incomplete_condition()).all()}
    done = {o.id for o in session.query(Order.id).filter(_erp_as_completed_condition()).all()}
    return inc, done


@pytest.fixture(scope="module")
def dsn(pg_engine) -> str:
    _seed(pg_engine)
    return pg_engine.url.set(drivername="postgresql").render_as_string(hide_password=False)


def test_plan_apply_rollback_roundtrip(pg_engine, pg_session, dsn, tmp_path):
    before = _rows(pg_engine)
    inc0, done0 = _as_tab_ids(pg_session)
    assert inc0 >= {103, 110} and 104 in done0

    conn = mod._connect(dsn, readonly=True)
    try:
        rows = mod.fetch_candidates(conn, cutoff=CUTOFF)
    finally:
        conn.close()
    plan = mod.build_plan(rows, cutoff=CUTOFF, today="2026-09-22", cutoff_days=7)

    by_id = {i["order_id"]: i for i in plan["items"]}
    assert set(by_id) == {101, 102, 103, 104}
    assert by_id[101]["mode"] == "main" and by_id[101]["flags"] == ["open_quests"]
    assert by_id[102]["mode"] == "main"
    assert by_id[103]["mode"] == "as_stage_only" and by_id[103]["to_status"] == "AS_RECEIVED"
    assert by_id[104]["mode"] == "as_stage_only" and by_id[104]["to_status"] == "AS_COMPLETED"
    skipped = {s["order_id"]: s["reason"] for s in plan["skipped"]}
    assert skipped == {105: "on_hold", 106: "logistics_in_flight", 107: "naver_claim_open",
                       110: "stage_not_main"}
    # 시공일 미래(108)·없음(109)은 SQL 단계에서 이미 후보 밖
    assert 108 not in skipped and 109 not in skipped

    # plan 뒤 사람이 만진 행 → stale 로 건너뛴다
    with pg_engine.begin() as c:
        c.execute(text("UPDATE orders SET status='ON_HOLD' WHERE id=102"))

    plan_path = tmp_path / "plan.json"
    plan_path.write_text(json.dumps(plan, ensure_ascii=False, default=str), encoding="utf-8")
    snap_path = tmp_path / "snap.json"
    rc = mod.main(["apply", "--dsn", dsn, "--plan", str(plan_path), "--actor", str(ACTOR),
                   "--yes", "--snapshot-out", str(snap_path)])
    assert rc == 0

    after = _rows(pg_engine)
    # main
    assert (after[101]["status"], after[101]["erp_stage_code"], after[101]["wf"]["stage"]) == \
        ("COMPLETED", "COMPLETED", "COMPLETED")
    assert after[101]["wf"]["stage_override"]["batch"] == mod.BATCH_ID
    assert after[101]["wf"]["history"] == [{"k": 1}]
    assert after[101]["mutation_version"] == 2
    # stale
    assert after[102]["status"] == "ON_HOLD" and after[102]["erp_stage_code"] == "DRAWING"
    # AS 탭 건 — stage 만
    for oid in (103, 104):
        assert after[oid]["erp_stage_code"] == "COMPLETED"
        assert after[oid]["wf"]["stage"] == "COMPLETED"
        for col in ("status", "as_axis_status", "as_completed_date", "asl"):
            assert after[oid][col] == before[oid][col], (oid, col)
    # 제외·후보 밖은 무접촉
    for oid in (105, 106, 107, 108, 109, 110):
        for col in ("status", "erp_stage_code", "wf", "mutation_version"):
            assert after[oid][col] == before[oid][col], (oid, col)

    pg_session.expire_all()
    assert _as_tab_ids(pg_session) == (inc0, done0)

    with pg_engine.connect() as c:
        ev = c.execute(text("""
            SELECT order_id, payload FROM order_events
             WHERE event_type='STAGE_OVERRIDE' AND created_by_user_id=:a ORDER BY order_id
        """), {"a": ACTOR}).all()
        logs = c.execute(text("""
            SELECT target_id, detail FROM security_logs
             WHERE action='ORDER_STATUS_CHANGED' AND user_id=:a ORDER BY target_id
        """), {"a": ACTOR}).all()
    assert [r.order_id for r in ev] == [101, 103, 104]
    ev_by = {r.order_id: r.payload for r in ev}
    assert ev_by[103]["from_status"] == "AS_RECEIVED" and ev_by[103]["to_status"] == "AS_RECEIVED"
    assert ev_by[103]["as_axis_status"] == "RECEIVED" and ev_by[103]["apply_mode"] == "as_stage_only"
    assert [r.target_id for r in logs] == [101, 103, 104]
    assert logs[0].detail["before"] == "MEASURE" and logs[0].detail["after"] == "COMPLETED"

    # rollback — 스냅샷 값(시드) 복원
    rc = mod.main(["rollback", "--dsn", dsn, "--snapshot", str(snap_path), "--actor", str(ACTOR), "--yes"])
    assert rc == 0
    restored = _rows(pg_engine)
    for oid in (101, 103, 104):
        for col in ("status", "erp_stage_code", "as_axis_status", "wf", "asl"):
            assert restored[oid][col] == before[oid][col], (oid, col)
    assert restored[102]["status"] == "ON_HOLD"  # 되돌리기는 이 배치 결과(COMPLETED)만 만진다


def test_expect_env_production_guard_refuses_test_fingerprint(pg_engine, dsn):
    """TESTCLR 고객이 있으면 운영 지문이 아니므로 중단한다."""
    with pg_engine.begin() as c:
        c.execute(text("""
            INSERT INTO orders(id, received_date, customer_name, phone, address, product, status,
                               structured_schema_version)
            VALUES (199, '2026-08-01', 'TESTCLR-guard', '010', 'a', 'p', 'RECEIVED', 1)
        """))
    conn = mod._connect(dsn, readonly=True)
    try:
        with pytest.raises(SystemExit, match="운영 DB 가 아니다"):
            mod.assert_env_fingerprint(conn, "production")
        mod.assert_env_fingerprint(conn, "staging")  # 스테이징 지문은 통과
    finally:
        conn.close()
