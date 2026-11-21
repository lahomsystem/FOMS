"""지난 주문 일괄 완료 도구 — 부분 시공 중 주문 빼기 PostgreSQL 계약 (제품마다 '시공 끝' 2단계 N7).

``tools/ops/bulk_complete_past_construction.py`` 가 후보 질의에서 ``item_construction_done`` 칸을 읽어
부분 시공 중(먼저 끝낸 제품도 남은 제품도 있음)인 주문을 ``items_construction_open`` 사유로 빼는지,
plan 뒤에 '시공 끝'이 찍힌 주문을 apply 가 잠근 뒤 다시 보고 건너뛰는지 실 PostgreSQL 로 잰다.
스위치(``FOMS_ITEM_CONSTRUCTION_DONE_ENABLED``)와 상관없이 자료로만 판정한다 — 이 도구는 foms 를 import
하지 않는다. 시드는 ``pg_engine`` 커밋(모듈 끝에 conftest 가 DB 를 비운다).
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest
from sqlalchemy import text

_MODULE_PATH = Path(__file__).resolve().parents[2] / "tools" / "ops" / "bulk_complete_past_construction.py"
_spec = importlib.util.spec_from_file_location("bulk_complete_items_open_pg", _MODULE_PATH)
mod = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(mod)

psycopg = pytest.importorskip("psycopg")

ACTOR = 900101
CUTOFF = "2026-09-15"
PAST = "2026-08-20"
UID_A = "aaaaaaaa-0000-4000-8000-0000000000a1"
UID_B = "bbbbbbbb-0000-4000-8000-0000000000b2"
MARK = {"date": PAST, "at": f"{PAST}T17:00:00+09:00", "by_user_id": None, "by_name": "시공팀",
        "source": "visit", "attempt_id": None}


def _sd(done: list[str]) -> dict:
    sd = {"workflow": {"stage": "CONSTRUCTION", "stage_updated_at": "2026-08-01T00:00:00"},
          "schedule": {"construction": {"date": PAST}},
          "items": [{"uid": UID_A, "product_name": "화장대", "construction_date": "2026-08-19"},
                    {"uid": UID_B, "product_name": "부엌가구"}]}
    if done:
        sd["item_construction_done"] = {uid: MARK for uid in done}
    return sd


SEED = {
    201: _sd([UID_A]),          # 부분 시공 중 — 남은 날도 기준일 앞이지만 뺀다
    202: _sd([UID_A, UID_B]),   # 대조군 — 다 끝남
    203: _sd([]),               # 대조군 — '시공 끝' 없음
    204: _sd([]),               # plan 뒤에 '시공 끝'이 찍힌다
}


@pytest.fixture(scope="module")
def dsn(pg_engine) -> str:
    with pg_engine.begin() as conn:
        conn.execute(text("""
            INSERT INTO users(id, username, password, name, role, is_active)
            VALUES (:id, 'bulk_items_actor', 'x', 'bulk', 'ADMIN', true) ON CONFLICT (id) DO NOTHING
        """), {"id": ACTOR})
        for oid, sd in SEED.items():
            conn.execute(text("""
                INSERT INTO orders(id, received_date, customer_name, phone, address, product, status,
                                   is_erp_order, erp_stage_code, erp_construction_date, structured_data,
                                   mutation_version, structured_schema_version)
                VALUES (:id, '2026-08-01', :name, '010', 'addr', 'p', 'CONSTRUCTION', true, 'CONSTRUCTION',
                        :cons, CAST(:sd AS jsonb), 1, 1)
            """), {"id": oid, "name": f"고객{oid}", "cons": PAST, "sd": json.dumps(sd, ensure_ascii=False)})
    return pg_engine.url.set(drivername="postgresql").render_as_string(hide_password=False)


def _stages(engine) -> dict[int, tuple[str, str, int]]:
    with engine.connect() as conn:
        res = conn.execute(text("""
            SELECT id, status, erp_stage_code, mutation_version FROM orders WHERE id BETWEEN 201 AND 204
        """))
        return {r.id: (r.status, r.erp_stage_code, r.mutation_version) for r in res}


def test_plan_excludes_partial_open_and_apply_rechecks(pg_engine, dsn, tmp_path):
    conn = mod._connect(dsn, readonly=True)
    try:
        rows = mod.fetch_candidates(conn, cutoff=CUTOFF)
    finally:
        conn.close()
    rows = [r for r in rows if 201 <= int(r["id"]) <= 204]
    assert {int(r["id"]): bool(r["item_construction_done"]) for r in rows} == {
        201: True, 202: True, 203: False, 204: False}
    plan = mod.build_plan(rows, cutoff=CUTOFF, today="2026-09-22", cutoff_days=7)
    assert sorted(i["order_id"] for i in plan["items"]) == [202, 203, 204]
    assert [(s["order_id"], s["reason"]) for s in plan["skipped"]] == [(201, "items_construction_open")]

    # plan 뒤에 첫 방문 '시공 끝'이 찍혔다 — 상태 · 단계는 그대로라 stale 로는 못 가린다
    with pg_engine.begin() as c:
        c.execute(text("""
            UPDATE orders SET structured_data = jsonb_set(
                structured_data, '{item_construction_done}', CAST(:marks AS jsonb), true) WHERE id=204
        """), {"marks": json.dumps({UID_A: MARK})})

    plan_path = tmp_path / "plan.json"
    plan_path.write_text(json.dumps(plan, ensure_ascii=False, default=str), encoding="utf-8")
    rc = mod.main(["apply", "--dsn", dsn, "--plan", str(plan_path), "--actor", str(ACTOR), "--yes",
                   "--snapshot-out", str(tmp_path / "snap.json")])
    assert rc == 0
    after = _stages(pg_engine)
    assert after[201] == ("CONSTRUCTION", "CONSTRUCTION", 1)      # plan 에서 빠짐
    assert after[204] == ("CONSTRUCTION", "CONSTRUCTION", 1)      # 잠근 뒤 다시 보고 건너뜀(쓰기 0)
    assert after[202][:2] == after[203][:2] == ("COMPLETED", "COMPLETED")
