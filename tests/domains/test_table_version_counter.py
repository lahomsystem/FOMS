"""HB-S1 계약 — 테이블 단위 쓰기 버전 카운터.

스펙: ``docs/specs/2026-09-01-shell-heartbeat-cheap-revalidation_SPEC.md`` §4·§6(S1).
조사 근거: ``docs/plans/2026-08-31-settlement-dashboard-impl-ledger.md`` §P7.

여기서 고정하는 것 4가지:

1. **ORM 쓰기가 커밋되면 그 테이블 카운터가 오른다** — 신호원이 세션 훅이라는 설계의 심장.
2. **롤백은 카운터를 올리지 않는다** — 안 일어난 변경으로 화면을 무효화하지 않는다.
3. **Redis 가 없거나 오류여도 무해하다** — 쓰기 경로는 절대 못 죽인다(fail-safe).
   같은 상황에서 읽는 쪽은 ``None`` 을 받아 조건부 단축을 포기한다(느릴 뿐 정확).
4. **ORM 우회 쓰기는 스캔 게이트가 잡는다** — 신호 없는(``UNSIGNALED``) 우회 쓰기 0.

그리고 배선 2곳(web / worker)을 함께 고정한다. worker 는 ``rq worker`` 로 떠서
``app.py`` 를 import 하지 않으므로 훅 등록이 별도다.
"""

from __future__ import annotations

import ast
import importlib
import importlib.util
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from db import db_session
from models import Order
from foms.services.common import table_version_counter as tvc

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SCANNER_PATH = _REPO_ROOT / "tools" / "harness" / "orm_bypass_write_scan.py"
_INVENTORY_PATH = _REPO_ROOT / "docs" / "harness" / "foms_orm_bypass_write_inventory.json"


def _load_scanner():
    """standalone 스캐너 모듈 import (``tools/`` 는 패키지가 아니다)."""
    spec = importlib.util.spec_from_file_location("orm_bypass_write_scan", _SCANNER_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


scan_mod = _load_scanner()


class FakeRedis:
    """INCR/MGET/pipeline 만 흉내내는 최소 Redis 대역."""

    def __init__(self) -> None:
        self.store: dict[str, int] = {}

    def incr(self, key: str) -> int:
        self.store[key] = self.store.get(key, 0) + 1
        return self.store[key]

    def mget(self, keys):
        return [str(self.store[k]) if k in self.store else None for k in keys]

    def pipeline(self):
        return _FakePipeline(self)


class _FakePipeline:
    def __init__(self, redis: FakeRedis) -> None:
        self._redis = redis
        self._ops: list[str] = []

    def incr(self, key: str) -> None:
        self._ops.append(key)

    def execute(self) -> list[int]:
        return [self._redis.incr(k) for k in self._ops]


class BoomRedis(FakeRedis):
    """모든 호출이 터지는 Redis(장애 재현)."""

    def incr(self, key: str):
        raise RuntimeError("redis down")

    def mget(self, keys):
        raise RuntimeError("redis down")

    def pipeline(self):
        raise RuntimeError("redis down")


@pytest.fixture
def fake_redis():
    """카운터 모듈이 쓰는 Redis 클라이언트를 가짜로 바꾼다."""
    fake = FakeRedis()
    with patch.object(tvc, "_redis", return_value=fake):
        yield fake


def _new_order(customer_name: str) -> Order:
    """최소 ERP 주문 1건(커밋하지 않고 반환)."""
    return Order(
        received_date="2026-09-01",
        customer_name=customer_name,
        phone="010-0000-0000",
        address="Seoul",
        product="Wardrobe",
        status="RECEIVED",
        manager_name="HB",
        is_erp_order=True,
        structured_data={"workflow": {"stage": "RECEIVED"}},
    )


# --------------------------------------------------------------------------- #
# 1. 카운터 단위 동작
# --------------------------------------------------------------------------- #

def test_key_shape_is_table_scoped():
    """키는 패밀리가 아니라 테이블 단위다(설계 판정 1)."""
    assert tvc.table_version_key("orders") == "foms:tabver:v1:orders"


def test_bump_and_read_roundtrip(fake_redis):
    """bump 한 만큼 읽힌다. 없던 키는 0."""
    assert tvc.bump_table_versions("orders", "order_attachments") == 2
    assert tvc.bump_table_versions("orders") == 1
    assert tvc.get_table_versions(["orders", "order_attachments", "users"]) == {
        "orders": 2,
        "order_attachments": 1,
        "users": 0,
    }


def test_untracked_table_is_ignored(fake_redis):
    """VERSIONED_TABLES 밖 이름은 카운터를 만들지 않는다(Redis 왕복 낭비 금지)."""
    assert tvc.bump_table_versions("access_logs", "chat_messages") == 0
    assert fake_redis.store == {}
    assert tvc.get_table_versions(["access_logs"]) == {}


def test_no_redis_is_harmless_and_read_returns_none():
    """Redis 가 없으면 bump 는 0, 조회는 None(= 조건부 단축 포기 신호)."""
    with patch.object(tvc, "_redis", return_value=None):
        assert tvc.bump_table_versions("orders") == 0
        assert tvc.get_table_versions(["orders"]) is None


def test_redis_failure_never_raises():
    """Redis 가 터져도 예외가 새지 않는다 — 쓰기 경로를 죽이면 안 된다."""
    with patch.object(tvc, "_redis", return_value=BoomRedis()):
        assert tvc.bump_table_versions("orders") == 0
        assert tvc.get_table_versions(["orders"]) is None


# --------------------------------------------------------------------------- #
# 2. 세션 훅(신호원)
# --------------------------------------------------------------------------- #

def test_listener_is_registered_in_web_process():
    """``import app`` 이 도는 프로세스에는 훅이 이미 걸려 있다."""
    import app  # noqa: F401  (run_auto_init 배선 트리거)

    assert tvc.is_table_version_listener_registered() is True


def test_worker_entrypoint_registers_listener():
    """worker 진입 모듈 import 만으로 훅이 등록된다.

    worker 는 ``rq worker default --url $REDIS_URL`` 로 뜨느라 ``app.py`` 를 import
    하지 않는다(Procfile). 이 배선이 빠지면 썸네일·지오코딩 쓰기가 신호를 안 남긴다.
    """
    tasks = importlib.import_module("foms.services.jobs.tasks")
    source = Path(tasks.__file__).read_text(encoding="utf-8")
    assert "register_table_version_listener" in source
    tree = ast.parse(source)
    module_level_calls = [
        node.value.func.id
        for node in tree.body
        if isinstance(node, ast.Expr)
        and isinstance(node.value, ast.Call)
        and isinstance(node.value.func, ast.Name)
    ]
    assert "_register_worker_session_wiring" in module_level_calls, (
        "worker 진입 모듈이 import 시점에 세션 훅을 등록해야 한다"
    )
    assert tvc.is_table_version_listener_registered() is True


def test_orm_commit_bumps_table_counter(app, fake_redis):
    """ORM 쓰기가 커밋되면 그 테이블 카운터가 오른다(설계의 심장).

    ``app`` 을 ``fake_redis`` 보다 먼저 받는 것은 의도적이다 — 스키마 리셋 커밋이
    가짜 Redis 를 미리 더럽히지 않도록 순서를 고정한다.
    """
    order = _new_order("HB-S1-commit")
    db_session.add(order)
    db_session.commit()
    try:
        versions = tvc.get_table_versions(["orders"])
        assert versions is not None and versions["orders"] >= 1
    finally:
        db_session.delete(order)
        db_session.commit()


def test_rollback_does_not_bump(app, fake_redis):
    """롤백된 변경은 카운터를 올리지 않는다."""
    db_session.add(_new_order("HB-S1-rollback"))
    db_session.flush()
    db_session.rollback()
    assert fake_redis.store == {}


def test_mark_tables_dirty_bumps_on_commit(app, fake_redis):
    """ORM 우회 쓰기용 등재는 **커밋 시점**에만 카운터를 올린다."""
    tvc.mark_tables_dirty(db_session, "order_schedule_dates")
    assert fake_redis.store == {}, "등재만으로 올라가면 롤백된 쓰기도 무효화한다"
    db_session.commit()
    versions = tvc.get_table_versions(["order_schedule_dates"])
    assert versions is not None and versions["order_schedule_dates"] == 1


def test_mark_tables_dirty_dropped_on_rollback(app, fake_redis):
    """등재분은 롤백과 함께 폐기된다(다음 트랜잭션으로 안 샌다).

    실제 쓰기와 함께 등재한 뒤 롤백하는 형태로 검사한다 — 등재만 하고 DB 작업이
    전혀 없으면 트랜잭션 자체가 시작되지 않아 SQLAlchemy 가 ``after_soft_rollback``
    을 내지 않는다(그 경우 등재분이 다음 커밋까지 남지만 과다 증가라 안전하다).
    """
    db_session.add(_new_order("HB-S1-mark-rollback"))
    tvc.mark_tables_dirty(db_session, "order_attachments")
    db_session.flush()
    db_session.rollback()
    db_session.commit()
    assert fake_redis.store == {}


def test_collect_dirty_table_names_filters_to_versioned():
    """flush 후보에서 추적 대상 테이블만 골라낸다."""

    class _Session:
        new = [_new_order("HB-S1-collect")]
        dirty: list = []
        deleted: list = []

    assert tvc.collect_dirty_table_names(_Session()) == {"orders"}


# --------------------------------------------------------------------------- #
# 3. ORM 우회 쓰기 스캔 게이트
# --------------------------------------------------------------------------- #

def _kinds(source: str) -> list:
    """소스 조각의 모든 노드에 대한 우회-쓰기 종류 목록."""
    return [scan_mod.site_kind(n) for n in ast.walk(ast.parse(source))]


def test_scanner_detects_query_level_bulk_ops():
    """query-level update()/delete() 는 우회 쓰기다."""
    assert scan_mod.KIND_QUERY_UPDATE in _kinds(
        "db.query(M).filter(M.id == 1).update({M.c: 2}, synchronize_session=False)"
    )
    assert scan_mod.KIND_QUERY_DELETE in _kinds(
        "session.query(M).filter(M.id == 1).delete(synchronize_session=False)"
    )


def test_scanner_ignores_dict_update():
    """``dict.update({...})`` 는 동명이인이지 우회 쓰기가 아니다."""
    assert all(k is None for k in _kinds("pool.update({a: b})"))
    assert all(k is None for k in _kinds("MAP.update({'a': 1, 'b': 2})"))


def test_scanner_detects_raw_dml_only():
    """raw ``execute(text(...))`` 는 DML 일 때만 잡는다(SELECT·DDL 은 제외)."""
    assert scan_mod.KIND_RAW_DML in _kinds('db.execute(text("DELETE FROM orders WHERE id = 1"))')
    assert scan_mod.KIND_RAW_DML in _kinds('conn.execute(text(f"UPDATE {t} SET c = NULL"))')
    assert all(k is None for k in _kinds('db.execute(text("SELECT 1"))'))
    assert all(k is None for k in _kinds('db.execute(text("CREATE INDEX IF NOT EXISTS x ON y (z)"))'))


def test_scanner_detects_bulk_mappings():
    """``bulk_insert_mappings`` 류도 ORM 엔티티 상태를 안 거친다."""
    assert scan_mod.KIND_BULK_MAPPINGS in _kinds("db.bulk_insert_mappings(M, rows)")
    assert scan_mod.KIND_BULK_MAPPINGS in _kinds("db.bulk_save_objects(objs)")


def test_scanner_marks_function_that_registers():
    """등재 호출이 있는 함수의 우회 쓰기는 MARKED 로 분류된다."""
    records = scan_mod.scan()
    marked = {
        (r["path"], r["func"])
        for r in records if r["signal"] == scan_mod.SIGNAL_MARKED
    }
    assert ("foms/web/orders/trash.py", "reset_order_ids") in marked
    assert ("foms/services/orders/delete_retention.py", "_hard_delete") in marked


def test_no_unsignaled_bypass_write():
    """신호 없는 ORM 우회 쓰기 0 — 하나라도 남으면 낡은 304 가 나간다.

    새 우회 쓰기를 추가했다면 그 함수에서 ``mark_tables_dirty`` 를 부르거나,
    쓰는 테이블이 전부 ``VERSIONED_TABLES`` 밖임을 allowlist 에 사유와 함께 등재하라.
    """
    unsignaled = [r for r in scan_mod.scan() if r["signal"] == scan_mod.SIGNAL_UNSIGNALED]
    assert unsignaled == [], (
        "신호 없는 ORM 우회 쓰기: "
        + ", ".join(f"{r['path']}:{r['lineno']} ({r['func']})" for r in unsignaled)
    )


def _lineno_free(records):
    """``lineno`` 를 떼고 정렬 — 줄밀림만으로는 게이트가 red 가 되지 않는다."""
    stripped = [{k: v for k, v in r.items() if k != "lineno"} for r in records]
    return sorted(stripped, key=lambda r: json.dumps(r, sort_keys=True, ensure_ascii=False))


def test_inventory_matches_fresh_scan():
    """커밋된 인벤토리 == 새 스캔(줄번호 무관)."""
    inventory = json.loads(_INVENTORY_PATH.read_text(encoding="utf-8"))
    assert _lineno_free(inventory["sites"]) == _lineno_free(scan_mod.scan()), (
        "인벤토리가 낡았다; `python tools/harness/orm_bypass_write_scan.py` 로 재생성하라"
    )


def test_every_site_carries_a_valid_signal():
    """모든 사이트가 정의된 signal 값을 갖는다."""
    valid = set(scan_mod.SIGNALS)
    for record in scan_mod.scan():
        assert record["signal"] in valid, f"bad signal: {record}"
        assert record["kind"] in scan_mod.KINDS, f"bad kind: {record}"


def test_allowlist_entries_state_a_reason():
    """allowlist 는 "왜 신호가 없어도 되는가"를 반드시 적는다."""
    for entry in scan_mod.load_allowlist():
        assert entry["signal"] in scan_mod.ALLOWED_SIGNALS, entry
        assert entry.get("reason"), f"reason 없는 allowlist 엔트리: {entry}"
