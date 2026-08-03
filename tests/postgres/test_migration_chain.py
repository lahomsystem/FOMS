"""MIGCHAIN-01: CI가 Alembic 체인을 정적 검사가 아니라 **실제로 실행**한다.

왜 필요한가
-----------
``tests/postgres/conftest.py`` 는 스키마를 ``Base.metadata.create_all`` 로 만든다 —
``alembic upgrade head`` 가 아니다. 그래서 지금까지 CI 는 마이그레이션이 실제로
도는지 한 번도 확인하지 않았고, 승격 때 마이그레이션이 무사히 돈 것은 사람이
스테이징에서 손으로 왕복을 돌려봤기 때문이지 CI 보장이 아니었다.

왜 "전체 체인 재생"이 아닌가 (2026-08-03 로컬 PG17 실측)
------------------------------------------------------
빈 DB 에서 ``alembic upgrade head`` 는 **첫 리비전에서 즉시 죽는다**::

    INFO  [alembic.runtime.migration] Running upgrade  -> aef164da4c43, ...
    psycopg2.errors.UndefinedTable: relation "orders" does not exist
    [SQL: ALTER TABLE orders ADD COLUMN measurement_completed BOOLEAN]

base 리비전 ``aef164da4c43`` 이 create-table 선행 없이 ``add_column`` 부터 시작하기
때문이다(과거 ``create_all`` + ``stamp`` 로 부트스트랩된 이력). 즉 전체 체인 재생은
불가능하고, 검증 가능한 최대 범위는 **신규 부트스트랩 DB(create_all + stamp head)에서
최근 마이그레이션 창을 downgrade → upgrade 왕복**하는 것이다.

무엇을 잡는가
-------------
왕복 창은 head 기준으로 정의되므로 **앞으로 추가되는 모든 마이그레이션이 자동으로
창 안에 들어온다** — 신규 마이그레이션의 ``upgrade()``/``downgrade()`` 는 머지 전에
실 PostgreSQL 에서 반드시 1회 실행된다. 표적은 2026-07-28 ``sidefx_00`` 실사고처럼
"이미 적용된 DB·SQLite 레인에서는 절대 안 잡히고 빈 DB/신규 환경/스테이징 predeploy
에서만 터지는" 결함 계열이다.

격리
----
공유 세션 DB(``pg_test_database``)를 쓰지 않고 자기 전용 throwaway DB 를 만든다.
downgrade 는 테이블을 실제로 지우므로 같은 세션의 다른 PG 테스트와 스키마를 공유하면
안 된다.
"""
from __future__ import annotations

import uuid
from pathlib import Path
from typing import Iterator

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.engine.url import URL

from tests.postgres.conftest import _raw_connect, assert_test_db_name

_REPO_ROOT = Path(__file__).resolve().parents[2]

# 왕복 하한. head 에서 여기까지 내려갔다가 다시 head 로 올라온다(2026-08-03 기준 15 리비전).
#
# 왜 더 못 내려가는가: 하한을 한 칸 더 내리려면 ``index_ops_00`` 자신의 downgrade 가
# 돌아야 하는데, 그 downgrade 는 ``designer_sketchup_parse_jobs`` 에 unique index 를
# 재생성한다. 그 테이블은 마이그레이션 계보에만 있고 models.py 에는 더 이상 없어서
# create_all 로 만든 신규 부트스트랩 DB 에는 존재하지 않는다 → UndefinedTable.
# 즉 이 하한은 create_all 계보와 마이그레이션 계보가 갈라지는 지점이지 임의값이 아니다.
# 더 내리려면 models.py ↔ 마이그레이션 드리프트를 먼저 없애야 한다.
_ROUNDTRIP_FLOOR = "index_ops_00"

# create_all(ORM) 이 자동 명명한 FK 를, 마이그레이션이 소유한 이름으로 정렬한다.
# models.py 가 이 FK 들에 이름을 주지 않아 create_all 은 ``<table>_<col>_fkey`` 를
# 만드는 반면 마이그레이션은 ``fk_dseo_*`` 를 만든다 — 실제 드리프트이며, 이 정렬이
# 없으면 신규 부트스트랩 DB 에서는 롤백(downgrade) 자체가 불가능하다.
_FK_NAME_ALIGNMENT = tuple(
    "ALTER TABLE domain_side_effect_outbox RENAME CONSTRAINT "
    f"domain_side_effect_outbox_{column} TO fk_dseo_{owned}"
    for column, owned in (
        ("wizard_pending_id_fkey", "wizard_pending"),
        ("order_import_artifact_id_fkey", "order_import_artifact"),
        ("upload_draft_id_fkey", "upload_draft"),
        ("upload_ticket_id_fkey", "upload_ticket"),
    )
)

# 이미 존재하는 models.py ↔ 마이그레이션 타입 불일치. 왕복이 이걸 발견했다(2026-08-03).
# 운영/스테이징은 마이그레이션 계보이므로 **오른쪽 타입이 실제 운영 타입**이고,
# ORM·create_all 테스트 레인만 왼쪽 타입을 본다. 여기서는 고칠 수 없어(새 마이그레이션
# 필요) 알려진 목록으로 고정한다 — 목록이 늘면 새 드리프트가 생긴 것이고, 줄면 누군가
# 고친 것이니 항목을 지워라.
#   (table, column, create_all 타입, 운영 타입)
_KNOWN_TYPE_DRIFT = frozenset({
    ("channel_inbound_worker_heartbeats", "metadata_json", "jsonb", "json"),
    ("system_setting_receipts", "read_receipt_id", "uuid", "character varying"),
    ("system_setting_receipts", "response_body", "jsonb", "json"),
})

# 같은 컬럼에 같은 UNIQUE 인덱스를 만들지만 이름만 다른 케이스(기능 동일).
# create_all: system_setting_receipts_read_receipt_id_key
# 마이그레이션: uq_system_setting_receipt_read_id
_KNOWN_INDEX_NAME_DRIFT = frozenset({"system_setting_receipts_read_receipt_id_key"})


@pytest.fixture(scope="module")
def migration_chain_url(pg_admin_url: URL) -> Iterator[URL]:
    """왕복 전용 throwaway DB 를 만들고 종료 시 DROP 한다.

    Args:
        pg_admin_url: conftest 가 검증한 로컬 admin URL.

    Yields:
        ``foms_test_migchain_*`` 데이터베이스를 가리키는 SQLAlchemy URL.
    """
    db_name = assert_test_db_name(f"foms_test_migchain_{uuid.uuid4().hex[:12]}")
    admin_dbname = pg_admin_url.database or "postgres"

    conn = _raw_connect(pg_admin_url, admin_dbname)
    conn.autocommit = True
    try:
        with conn.cursor() as cur:
            cur.execute(f'CREATE DATABASE "{db_name}"')
    finally:
        conn.close()

    try:
        yield pg_admin_url.set(drivername="postgresql+psycopg2", database=db_name)
    finally:
        assert_test_db_name(db_name)  # defense in depth before DROP
        conn = _raw_connect(pg_admin_url, admin_dbname)
        conn.autocommit = True
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                    "WHERE datname = %s AND pid <> pg_backend_pid()",
                    (db_name,),
                )
                cur.execute(f'DROP DATABASE IF EXISTS "{db_name}"')
        finally:
            conn.close()


def _column_fingerprint(engine) -> dict[tuple[str, str], tuple[str, str, str]]:
    """``{(table, column): (data_type, is_nullable, default)}`` 지문.

    Args:
        engine: 대상 DB 엔진.

    Returns:
        public 스키마 전 컬럼의 지문. ``alembic_version`` 은 왕복 중 내용만 바뀌는
        메타 테이블이라 제외한다.
    """
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT table_name, column_name, data_type, is_nullable, "
                "       COALESCE(column_default, '') "
                "FROM information_schema.columns "
                "WHERE table_schema = 'public' AND table_name <> 'alembic_version'"
            )
        ).all()
    return {(row[0], row[1]): (row[2], row[3], row[4]) for row in rows}


def _index_names(engine) -> set[str]:
    """public 스키마 인덱스 이름 집합.

    Args:
        engine: 대상 DB 엔진.

    Returns:
        인덱스 이름 집합 (``alembic_version`` 제외).
    """
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT indexname FROM pg_indexes "
                "WHERE schemaname = 'public' AND tablename <> 'alembic_version'"
            )
        ).all()
    return {row[0] for row in rows}


def _alembic_config() -> Config:
    """alembic.ini 없이 Config 를 만든다.

    alembic.ini 를 넘기면 env.py 가 ``fileConfig()`` 로 **전역 logging 을 재설정**해
    같은 pytest 세션의 다른 테스트에 영향을 준다. script_location 만 주면 동일한
    env.py / 동일한 리비전 파일을 그대로 쓰면서 그 부작용만 피할 수 있다(DB URL 은
    운영과 똑같이 ``DATABASE_URL`` 환경변수로 전달된다).

    Returns:
        migrations/ 를 script_location 으로 갖는 Alembic Config.
    """
    config = Config()
    config.set_main_option("script_location", str(_REPO_ROOT / "migrations"))
    return config


def test_recent_migration_window_roundtrips_on_a_fresh_bootstrap(
    migration_chain_url: URL, monkeypatch: pytest.MonkeyPatch
) -> None:
    """신규 부트스트랩 DB 에서 최근 마이그레이션 창을 내렸다가 다시 올린다.

    create_all + ``stamp head`` 로 신규 환경 부트스트랩을 재현한 뒤
    ``downgrade _ROUNDTRIP_FLOOR`` → ``upgrade head`` 를 실제로 실행하고,
    스키마가 왕복 전과 컬럼·인덱스 단위로 동일하게 복원되는지 확인한다.
    """
    import app  # noqa: F401  (모든 모델 모듈을 Base.metadata 에 등록)
    from db import Base

    engine = create_engine(migration_chain_url, connect_args={"client_encoding": "utf8"})
    try:
        Base.metadata.create_all(bind=engine)
        with engine.begin() as conn:
            for statement in _FK_NAME_ALIGNMENT:
                conn.execute(text(statement))

        # 운영 predeploy 와 같은 경로: env.py 가 DATABASE_URL 을 읽는다.
        monkeypatch.setenv(
            "DATABASE_URL", migration_chain_url.render_as_string(hide_password=False)
        )
        config = _alembic_config()

        command.stamp(config, "head")
        before = _column_fingerprint(engine)
        before_indexes = _index_names(engine)

        command.downgrade(config, _ROUNDTRIP_FLOOR)
        during = _column_fingerprint(engine)
        # downgrade 가 실제로 스키마를 걷어냈는지 — no-op 왕복이면 아무것도 검증 못 한다.
        assert len(during) < len(before), (
            "downgrade removed nothing; the round trip would prove nothing"
        )

        command.upgrade(config, "head")
        after = _column_fingerprint(engine)
        after_indexes = _index_names(engine)

        # 1) 왕복이 컬럼을 잃지 않는다 (마이그레이션 계보에 구멍이 없다).
        missing = sorted(set(before) - set(after))
        assert not missing, f"upgrade did not restore columns: {missing}"

        # 2) models.py ↔ 마이그레이션 타입 불일치는 알려진 목록 그대로여야 한다.
        shared = set(before) & set(after)
        type_drift = {
            (table, column, before[(table, column)][0], after[(table, column)][0])
            for table, column in shared
            if before[(table, column)][0] != after[(table, column)][0]
        }
        assert type_drift == _KNOWN_TYPE_DRIFT, (
            "models.py 와 마이그레이션의 컬럼 타입 불일치가 변했다.\n"
            f"  새로 생긴 드리프트: {sorted(type_drift - _KNOWN_TYPE_DRIFT)}\n"
            f"  해소된 드리프트(목록에서 지워라): {sorted(_KNOWN_TYPE_DRIFT - type_drift)}"
        )

        # 3) nullable/default 는 예외 없이 일치해야 한다.
        attr_drift = sorted(
            (table, column, before[(table, column)][1:], after[(table, column)][1:])
            for table, column in shared
            if before[(table, column)][1:] != after[(table, column)][1:]
        )
        assert not attr_drift, f"nullable/default drift after replay: {attr_drift}"

        # 4) 인덱스는 사라지면 안 된다. 추가는 정상(startup_schema_00 이 ORM 에 없는
        #    성능 인덱스를 소유한다 — test_startup_schema.py 의 migration_only_indexes).
        missing_indexes = before_indexes - after_indexes
        assert missing_indexes == _KNOWN_INDEX_NAME_DRIFT, (
            f"인덱스가 복원되지 않았다: {sorted(missing_indexes - _KNOWN_INDEX_NAME_DRIFT)}"
        )
    finally:
        engine.dispose()
