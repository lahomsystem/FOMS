"""AUDIT-LOG T9: 감사 원장 수명주기 실 PostgreSQL 계약 (PGTEST-00 lane).

SQLite/도메인 레인이 **구조적으로 증명할 수 없는 것**만 실 PG 로 고정한다.

1. **FK drop 마이그레이션 왕복** — ``auditlife_00`` 이 ``order_events_order_id_fkey`` 를
   정확히 걷어내고 ``downgrade`` 가 CASCADE FK 를 원상복구한다(2 사이클 = 멱등). 이 과정에서
   ``order_id`` 의 NOT NULL·인덱스는 불변이어야 한다.
2. **고아 상태의 downgrade 는 PG 가 스스로 막는다** — 전용 차단 로직 없이 제약 검증만으로
   fail-closed 라는 설계 전제(스펙 §4 T9)의 실증.
3. **주문 hard purge 후 order_events 잔존** — T9 의 존재 이유. FK 가 붙어 있던 시절에는
   CASCADE 로 함께 사라졌다.
4. **retention purge 경계** — dry-run 카운트가 실제 삭제 수와 같고, 보존기간 안쪽 행은
   살아남으며, 자기참조 FK(``channel_delivery_logs.parent_delivery_id``)를 깨지 않는다.
5. **keyset 배치 + advisory lock** — 배치 분할·재실행 idempotent·동시 실행 skip.

``FOMS_TEST_DATABASE_URL`` 미설정이면 lane 자체가 skip 된다(conftest). 커밋 파일에는
비밀번호·DSN 을 넣지 않는다(env 주입).
"""

from __future__ import annotations

import importlib.util
import pathlib
from datetime import timedelta
from typing import Iterator

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import text
from sqlalchemy.engine import Connection
from sqlalchemy.exc import IntegrityError

from foms.services.datetime_kst import now_utc_naive
from tools.ops import purge_audit_logs as pal

_MIGRATION_PATH = (
    pathlib.Path(__file__).resolve().parents[2]
    / "migrations" / "versions" / "auditlife_00_order_events_fk_drop.py"
)
_spec = importlib.util.spec_from_file_location("auditlife_00", _MIGRATION_PATH)
mig = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mig)  # top-level import only — no DB side effects

TABLE = mig.TABLE
FK_NAME = mig.FK_NAME
ORDER_ID_INDEX = "ix_order_events_order_id"


# --------------------------------------------------------------------------- #
# catalog helpers
# --------------------------------------------------------------------------- #
def _fk_names(conn: Connection) -> set[str]:
    rows = conn.execute(
        text("SELECT conname FROM pg_constraint "
             "WHERE conrelid = 'order_events'::regclass AND contype = 'f'")
    ).fetchall()
    return {r[0] for r in rows}


def _fk_definition(conn: Connection, name: str) -> str:
    return conn.execute(
        text("SELECT pg_get_constraintdef(oid) FROM pg_constraint "
             "WHERE conrelid = 'order_events'::regclass AND conname = :n"),
        {"n": name},
    ).scalar_one()


def _indexes(conn: Connection) -> set[str]:
    rows = conn.execute(
        text("SELECT indexname FROM pg_indexes WHERE tablename = :t"), {"t": TABLE}
    ).fetchall()
    return {r[0] for r in rows}


def _order_id_is_not_null(conn: Connection) -> bool:
    return conn.execute(
        text("SELECT is_nullable FROM information_schema.columns "
             "WHERE table_name = :t AND column_name = 'order_id'"),
        {"t": TABLE},
    ).scalar_one() == "NO"


@pytest.fixture
def ddl_conn(pg_engine) -> Iterator[Connection]:
    """DDL 전용 커넥션 — 트랜잭션 안에서만 돌고 항상 rollback(스키마 무오염)."""
    connection = pg_engine.connect()
    trans = connection.begin()
    connection.execute(text("SET LOCAL lock_timeout = '10s'"))
    try:
        yield connection
    finally:
        if trans.is_active:
            trans.rollback()
        connection.close()


def _run(conn: Connection, direction: str) -> None:
    """마이그레이션 ``upgrade``/``downgrade`` 를 이 커넥션에 실행한다(alembic op 프록시)."""
    context = MigrationContext.configure(conn)
    with Operations.context(context):
        getattr(mig, direction)()


def _make_order(conn: Connection, *, customer: str = "홍길동") -> int:
    """최소 주문 1건 삽입 후 id 반환(raw SQL — ORM cascade 개입 없이 순수 DB 계약 관찰)."""
    # structured_schema_version 은 파이썬 측 default 라 raw INSERT 에서는 직접 채운다.
    return conn.execute(
        text("INSERT INTO orders "
             "(received_date, customer_name, phone, address, product, "
             " structured_schema_version) "
             "VALUES ('2026-08-01', :c, '010-0000-0000', '서울', '침대', 1) RETURNING id"),
        {"c": customer},
    ).scalar_one()


def _make_event(conn: Connection, order_id: int, *, event_type: str = "STAGE_CHANGED") -> int:
    return conn.execute(
        text("INSERT INTO order_events (order_id, event_type, created_at) "
             "VALUES (:o, :e, now()) RETURNING id"),
        {"o": order_id, "e": event_type},
    ).scalar_one()


# --------------------------------------------------------------------------- #
# 1. FK drop 마이그레이션 왕복
# --------------------------------------------------------------------------- #
def test_create_all_lane_has_no_orders_fk(ddl_conn):
    """모델(create_all) baseline 에 orders FK 가 없다 — models.py 동기 수정 확인."""
    assert FK_NAME not in _fk_names(ddl_conn)
    # created_by_user_id FK 는 그대로 남아야 한다(이 마이그레이션의 사정권 밖).
    assert "order_events_created_by_user_id_fkey" in _fk_names(ddl_conn)


def test_migration_roundtrip_drops_and_restores_fk(ddl_conn):
    """downgrade 가 CASCADE FK 를 되살리고 upgrade 가 다시 걷어낸다(2 사이클)."""
    baseline_fks = _fk_names(ddl_conn)
    assert FK_NAME not in baseline_fks

    for cycle in range(2):
        _run(ddl_conn, "downgrade")
        assert _fk_names(ddl_conn) - baseline_fks == {FK_NAME}, cycle
        definition = _fk_definition(ddl_conn, FK_NAME)
        assert "REFERENCES orders(id)" in definition, definition
        assert "ON DELETE CASCADE" in definition, definition

        _run(ddl_conn, "upgrade")
        assert _fk_names(ddl_conn) == baseline_fks, cycle


def test_upgrade_is_idempotent_when_fk_already_absent(ddl_conn):
    """``DROP CONSTRAINT IF EXISTS`` — 제약이 이미 없는 DB 에서도 upgrade 가 통과한다."""
    assert FK_NAME not in _fk_names(ddl_conn)
    _run(ddl_conn, "upgrade")
    _run(ddl_conn, "upgrade")
    assert FK_NAME not in _fk_names(ddl_conn)


def test_order_id_keeps_not_null_and_index_across_roundtrip(ddl_conn):
    """FK 만 오간다 — ``order_id`` 의 NOT NULL 과 조회 인덱스는 어느 시점에도 불변."""
    for step in ("baseline", "downgrade", "upgrade"):
        if step != "baseline":
            _run(ddl_conn, step)
        assert _order_id_is_not_null(ddl_conn), step
        assert ORDER_ID_INDEX in _indexes(ddl_conn), step


# --------------------------------------------------------------------------- #
# 2. 고아 이벤트 + downgrade = PG 제약 검증이 스스로 막는다
# --------------------------------------------------------------------------- #
def test_downgrade_fails_when_orphan_events_exist(ddl_conn):
    """고아 이벤트가 있으면 FK 재부착이 PG 검증에서 실패한다(전용 차단 로직 불필요)."""
    order_id = _make_order(ddl_conn)
    _make_event(ddl_conn, order_id)
    ddl_conn.execute(text("DELETE FROM orders WHERE id = :id"), {"id": order_id})
    # FK 가 없으므로 이벤트가 고아로 남는다(그 자체가 T9 의 의도).
    assert ddl_conn.execute(
        text("SELECT count(*) FROM order_events WHERE order_id = :id"), {"id": order_id}
    ).scalar_one() == 1

    with pytest.raises(IntegrityError):
        _run(ddl_conn, "downgrade")


def test_downgrade_succeeds_when_no_orphans(ddl_conn):
    """고아가 없으면 같은 downgrade 가 정상 통과한다(실패 원인이 고아임을 증명)."""
    order_id = _make_order(ddl_conn)
    _make_event(ddl_conn, order_id)

    _run(ddl_conn, "downgrade")

    assert FK_NAME in _fk_names(ddl_conn)


# --------------------------------------------------------------------------- #
# 3. 주문 hard purge 후 order_events 잔존 (T9 의 존재 이유)
# --------------------------------------------------------------------------- #
def test_order_hard_delete_leaves_events_behind(ddl_conn):
    """주문을 물리 삭제해도 감사 이벤트는 남는다 — FK 시절에는 CASCADE 로 사라졌다."""
    order_id = _make_order(ddl_conn, customer="감사대상")
    event_id = _make_event(ddl_conn, order_id, event_type="PAYMENT_CHANGED")

    ddl_conn.execute(text("DELETE FROM orders WHERE id = :id"), {"id": order_id})

    surviving = ddl_conn.execute(
        text("SELECT order_id, event_type FROM order_events WHERE id = :id"),
        {"id": event_id},
    ).one()
    assert surviving == (order_id, "PAYMENT_CHANGED")


def test_cascade_still_deletes_events_when_fk_is_restored(ddl_conn):
    """대조군: downgrade 로 FK 를 되살리면 예전 동작(CASCADE 동반 삭제)이 돌아온다."""
    _run(ddl_conn, "downgrade")
    order_id = _make_order(ddl_conn)
    event_id = _make_event(ddl_conn, order_id)

    ddl_conn.execute(text("DELETE FROM orders WHERE id = :id"), {"id": order_id})

    assert ddl_conn.execute(
        text("SELECT count(*) FROM order_events WHERE id = :id"), {"id": event_id}
    ).scalar_one() == 0


# --------------------------------------------------------------------------- #
# 4-5. retention purge (커밋되는 다중 트랜잭션 — pg_engine 직접 사용)
# --------------------------------------------------------------------------- #
_AUDIT_TABLES = {spec.table: spec for spec in pal.AUDIT_TABLES}


def _clean_audit(pg_engine) -> None:
    """purge 대상 테이블 + 부모(notifications)를 비워 카운트를 결정적으로 만든다."""
    with pg_engine.begin() as conn:
        conn.execute(text("DELETE FROM notification_events"))
        conn.execute(text("DELETE FROM notifications"))
        # 자기참조 FK 는 NO ACTION(문 끝 검증) — 한 문장으로 전량 삭제하면 안전하다.
        conn.execute(text("DELETE FROM channel_delivery_logs"))
        conn.execute(text("DELETE FROM security_logs"))
        conn.execute(text("DELETE FROM access_logs"))
        conn.execute(text("DELETE FROM order_events"))


def _insert_security_log(conn, ts) -> int:
    return conn.execute(
        text("INSERT INTO security_logs (message, timestamp) VALUES ('감사행', :ts) "
             "RETURNING id"), {"ts": ts},
    ).scalar_one()


def _insert_access_log(conn, ts) -> int:
    return conn.execute(
        text("INSERT INTO access_logs (action, timestamp) VALUES ('FILE_VIEW', :ts) "
             "RETURNING id"), {"ts": ts},
    ).scalar_one()


def _insert_notification(conn, ts) -> int:
    return conn.execute(
        text("INSERT INTO notifications "
             "(notification_type, target_type, is_urgent, title, is_read, created_at) "
             "VALUES ('TEST', 'ALL', false, '알림', false, :ts) RETURNING id"),
        {"ts": ts},
    ).scalar_one()


def _insert_notification_event(conn, notification_id: int, ts) -> int:
    return conn.execute(
        text("INSERT INTO notification_events (notification_id, event_type, created_at) "
             "VALUES (:n, 'CREATED', :ts) RETURNING id"),
        {"n": notification_id, "ts": ts},
    ).scalar_one()


def _insert_delivery_log(conn, ts, *, key: str, parent_id: int | None = None) -> int:
    return conn.execute(
        text("INSERT INTO channel_delivery_logs "
             "(event_key, source_type, source_id, target_type, target_id, status, "
             " retry_count, parent_delivery_id, created_at) "
             "VALUES (:k, 'ORDER', 1, 'GROUP', 'g1', 'sent', 0, :p, :ts) RETURNING id"),
        {"k": key, "p": parent_id, "ts": ts},
    ).scalar_one()


def _counts(pg_engine) -> dict[str, int]:
    with pg_engine.connect() as conn:
        return {
            table: conn.execute(text(f"SELECT count(*) FROM {table}")).scalar_one()
            for table in _AUDIT_TABLES
        }


def _expired(now, table: str, *, extra_days: int = 5):
    """``table`` 의 보존기간을 확실히 넘긴 시각.

    보존기간 상수(``AUDIT_TABLES``)는 정책 결정이라 바뀐다 — 날짜를 리터럴로 박으면
    정책을 조정할 때마다 이 스위트가 "아무것도 만료되지 않아" 조용히 0건을 세고 red 가
    된다(실제 사고: 보존기간 3년 상향 후 PG 레인 5건 red). 항상 상수에서 파생시킨다.

    :param now: 기준 시각.
    :param table: 대상 테이블명.
    :param extra_days: 보존기간을 넘기는 여유 일수(체인 순서를 만들 때 크게 준다).
    :return: 만료 시각.
    """
    return now - timedelta(days=_AUDIT_TABLES[table].default_retention_days + extra_days)


def _within(now, table: str, *, margin_days: int = 5):
    """``table`` 의 보존기간 안쪽(삭제 대상이 아닌) 시각.

    :param now: 기준 시각.
    :param table: 대상 테이블명.
    :param margin_days: 보존기간 경계에서 앞당길 일수.
    :return: 보존 대상 시각.
    """
    days = max(_AUDIT_TABLES[table].default_retention_days - margin_days, 0)
    return now - timedelta(days=days)


def _seed_one_expired_and_one_fresh(pg_engine, now) -> None:
    """대상 4종 각각에 '보존기간 초과' 1건 + '보존기간 내' 1건을 심는다."""
    with pg_engine.begin() as conn:
        for table, spec in _AUDIT_TABLES.items():
            old = now - timedelta(days=spec.default_retention_days + 5)
            fresh = now - timedelta(days=spec.default_retention_days - 5)
            if table == "security_logs":
                _insert_security_log(conn, old)
                _insert_security_log(conn, fresh)
            elif table == "access_logs":
                _insert_access_log(conn, old)
                _insert_access_log(conn, fresh)
            elif table == "notification_events":
                parent = _insert_notification(conn, old)
                _insert_notification_event(conn, parent, old)
                _insert_notification_event(conn, parent, fresh)
            elif table == "channel_delivery_logs":
                _insert_delivery_log(conn, old, key="old-1")
                _insert_delivery_log(conn, fresh, key="fresh-1")


def test_dry_run_counts_expired_rows_and_deletes_nothing(pg_engine):
    """dry-run 은 테이블별 대상 수만 보고하고 한 행도 지우지 않는다."""
    _clean_audit(pg_engine)
    now = now_utc_naive()
    _seed_one_expired_and_one_fresh(pg_engine, now)
    before = _counts(pg_engine)

    with pg_engine.connect() as conn:
        result = pal.run(conn, apply=False, now=now)

    assert result.applied is False
    assert result.locked is False
    assert {t.table: t.scanned for t in result.tables} == {t: 1 for t in _AUDIT_TABLES}
    assert result.deleted == 0
    assert _counts(pg_engine) == before


def test_apply_deletes_only_retention_elapsed_rows(pg_engine):
    """--apply 는 보존기간 초과 행만 지우고 보존기간 안쪽 행은 남긴다(경계)."""
    _clean_audit(pg_engine)
    now = now_utc_naive()
    _seed_one_expired_and_one_fresh(pg_engine, now)

    with pg_engine.connect() as conn:
        result = pal.run(conn, apply=True, now=now)

    assert result.applied is True
    assert {t.table: t.deleted for t in result.tables} == {t: 1 for t in _AUDIT_TABLES}
    assert _counts(pg_engine) == {t: 1 for t in _AUDIT_TABLES}

    # 재실행은 idempotent — 남은 대상 0.
    with pg_engine.connect() as conn:
        again = pal.run(conn, apply=True, now=now)
    assert again.scanned == 0 and again.deleted == 0


def test_purge_never_touches_order_events_or_orders(pg_engine):
    """order_events·orders 는 purge 사정권 밖 — 아무리 오래된 행도 살아남는다."""
    _clean_audit(pg_engine)
    now = now_utc_naive()
    with pg_engine.begin() as conn:
        order_id = _make_order(conn, customer="퍼지제외")
        conn.execute(
            text("INSERT INTO order_events (order_id, event_type, created_at) "
                 "VALUES (:o, 'STAGE_CHANGED', :ts)"),
            {"o": order_id, "ts": now - timedelta(days=4000)},
        )
        _insert_security_log(conn, now - timedelta(days=4000))

    with pg_engine.connect() as conn:
        result = pal.run(conn, apply=True, now=now)

    assert {t.table for t in result.tables} == set(_AUDIT_TABLES)
    with pg_engine.connect() as conn:
        assert conn.execute(
            text("SELECT count(*) FROM order_events WHERE order_id = :o"), {"o": order_id}
        ).scalar_one() == 1
        assert conn.execute(
            text("SELECT count(*) FROM orders WHERE id = :o"), {"o": order_id}
        ).scalar_one() == 1
        assert conn.execute(text("SELECT count(*) FROM security_logs")).scalar_one() == 0

    with pg_engine.begin() as conn:
        conn.execute(text("DELETE FROM order_events WHERE order_id = :o"), {"o": order_id})
        conn.execute(text("DELETE FROM orders WHERE id = :o"), {"o": order_id})


def test_retention_override_applies_per_table(pg_engine):
    """테이블별 보존기간 override 가 그 테이블에만 적용된다."""
    _clean_audit(pg_engine)
    now = now_utc_naive()
    with pg_engine.begin() as conn:
        # 둘 다 기본 보존기간 안쪽 — override 를 받은 테이블만 지워져야 한다.
        _insert_security_log(conn, _within(now, "security_logs"))
        _insert_access_log(conn, _within(now, "access_logs"))

    with pg_engine.connect() as conn:
        result = pal.run(
            conn, retention_overrides={"security_logs": 10}, apply=True, now=now
        )

    by_table = {t.table: t for t in result.tables}
    assert by_table["security_logs"].retention_days == 10
    assert by_table["security_logs"].deleted == 1
    assert (by_table["access_logs"].retention_days
            == _AUDIT_TABLES["access_logs"].default_retention_days)
    assert by_table["access_logs"].deleted == 0


def test_self_referencing_delivery_log_parent_survives_while_child_lives(pg_engine):
    """보존기간 안쪽 재전송 자식이 있는 부모는 지우지 않는다(자기참조 FK 보호)."""
    _clean_audit(pg_engine)
    now = now_utc_naive()
    with pg_engine.begin() as conn:
        parent = _insert_delivery_log(
            conn, _expired(now, "channel_delivery_logs"), key="p-1")
        _insert_delivery_log(
            conn, _within(now, "channel_delivery_logs"), key="c-1", parent_id=parent)

    with pg_engine.connect() as conn:
        result = pal.run(conn, apply=True, now=now)

    by_table = {t.table: t for t in result.tables}
    assert by_table["channel_delivery_logs"].scanned == 0
    assert by_table["channel_delivery_logs"].deleted == 0
    with pg_engine.connect() as conn:
        assert conn.execute(
            text("SELECT count(*) FROM channel_delivery_logs")
        ).scalar_one() == 2


def test_self_referencing_delivery_chain_deletes_child_before_parent(pg_engine):
    """부모·자식이 모두 만료면 자식부터 지워 FK 를 깨지 않는다(batch 1로 강제 분할)."""
    _clean_audit(pg_engine)
    now = now_utc_naive()
    with pg_engine.begin() as conn:
        parent = _insert_delivery_log(
            conn, _expired(now, "channel_delivery_logs", extra_days=100), key="p-2")
        _insert_delivery_log(
            conn, _expired(now, "channel_delivery_logs", extra_days=50), key="c-2",
            parent_id=parent)

    with pg_engine.connect() as conn:
        result = pal.run(conn, apply=True, batch_size=1, now=now)

    by_table = {t.table: t for t in result.tables}
    assert by_table["channel_delivery_logs"].deleted == 2
    assert by_table["channel_delivery_logs"].batches == 2
    with pg_engine.connect() as conn:
        assert conn.execute(
            text("SELECT count(*) FROM channel_delivery_logs")
        ).scalar_one() == 0


def test_survivor_guard_protects_grandparent_of_a_surviving_row(pg_engine):
    """2단계 체인: 손자만 보존기간 안이어도 조부까지 남는다(직속 자식만 보는 가드로는 부족)."""
    _clean_audit(pg_engine)
    now = now_utc_naive()
    with pg_engine.begin() as conn:
        grandparent = _insert_delivery_log(
            conn, _expired(now, "channel_delivery_logs", extra_days=100), key="gp")
        parent = _insert_delivery_log(
            conn, _expired(now, "channel_delivery_logs", extra_days=50), key="pp",
            parent_id=grandparent)
        _insert_delivery_log(
            conn, _within(now, "channel_delivery_logs"), key="cc", parent_id=parent)

    with pg_engine.connect() as conn:
        result = pal.run(conn, apply=True, batch_size=1, now=now)

    by_table = {t.table: t for t in result.tables}
    assert by_table["channel_delivery_logs"].scanned == 0
    assert by_table["channel_delivery_logs"].deleted == 0
    with pg_engine.connect() as conn:
        assert conn.execute(
            text("SELECT count(*) FROM channel_delivery_logs")
        ).scalar_one() == 3


def test_deep_expired_chain_is_deleted_whole_across_batches(pg_engine):
    """3단계 체인이 전부 만료면 배치가 어디서 잘려도 자손부터 지워져 전량 삭제된다."""
    _clean_audit(pg_engine)
    now = now_utc_naive()
    with pg_engine.begin() as conn:
        root = _insert_delivery_log(
            conn, _expired(now, "channel_delivery_logs", extra_days=150), key="r")
        mid = _insert_delivery_log(
            conn, _expired(now, "channel_delivery_logs", extra_days=100), key="m",
            parent_id=root)
        _insert_delivery_log(
            conn, _expired(now, "channel_delivery_logs", extra_days=50), key="l",
            parent_id=mid)

    with pg_engine.connect() as conn:
        result = pal.run(conn, apply=True, batch_size=1, now=now)

    by_table = {t.table: t for t in result.tables}
    assert by_table["channel_delivery_logs"].scanned == 3
    assert by_table["channel_delivery_logs"].deleted == 3
    with pg_engine.connect() as conn:
        assert conn.execute(
            text("SELECT count(*) FROM channel_delivery_logs")
        ).scalar_one() == 0


def test_keyset_batching_splits_deletes_and_resumes(pg_engine):
    """batch_size 단위로 나눠 지우고, 재실행이 곧 resume(남은 것 0)."""
    _clean_audit(pg_engine)
    now = now_utc_naive()
    with pg_engine.begin() as conn:
        for i in range(5):
            _insert_security_log(
                conn, _expired(now, "security_logs") - timedelta(seconds=i))

    with pg_engine.connect() as conn:
        result = pal.run(conn, apply=True, batch_size=2, now=now)

    by_table = {t.table: t for t in result.tables}
    assert by_table["security_logs"].deleted == 5
    assert by_table["security_logs"].batches == 3        # 2 + 2 + 1

    with pg_engine.connect() as conn:
        again = pal.run(conn, apply=True, batch_size=2, now=now)
    assert again.deleted == 0


def test_advisory_lock_skips_concurrent_run(pg_engine):
    """다른 purge 가 락을 쥐고 있으면 아무것도 지우지 않고 skip 한다."""
    _clean_audit(pg_engine)
    now = now_utc_naive()
    with pg_engine.begin() as conn:
        _insert_security_log(conn, _expired(now, "security_logs"))

    with pg_engine.connect() as locker:
        assert locker.execute(
            text("SELECT pg_try_advisory_lock(hashtext(:k))"),
            {"k": pal.ADVISORY_LOCK_KEY},
        ).scalar() is True
        try:
            with pg_engine.connect() as conn:
                skipped = pal.run(conn, apply=True, now=now)
            assert skipped.locked is True
            assert skipped.tables == ()
            assert _counts(pg_engine)["security_logs"] == 1
        finally:
            locker.execute(
                text("SELECT pg_advisory_unlock(hashtext(:k))"),
                {"k": pal.ADVISORY_LOCK_KEY},
            )

    # 락 해제 후에는 정상 삭제(락이 진짜 차단 원인이었음을 증명).
    with pg_engine.connect() as conn:
        result = pal.run(conn, apply=True, now=now)
    assert result.locked is False
    assert result.deleted == 1
