import os
import sys
from logging.config import fileConfig

from dotenv import load_dotenv
load_dotenv()

from pathlib import Path as _Path

from sqlalchemy import engine_from_config
from sqlalchemy import pool
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError


def _targets_throwaway_test_db(url: str) -> bool:
    """DSN이 테스트 레인의 일회용 ``foms_test_*`` DB를 가리키는지 판정한다.

    Args:
        url: 검사할 DSN 문자열 (비어 있을 수 있다).

    Returns:
        DB 이름이 ``foms_test_`` 로 시작하면 True. 파싱 불가/미지정이면 False
        (fail-closed — 공유 DB로 간주해 차단한다).
    """
    if not url:
        return False
    try:
        return (make_url(url).database or "").startswith("foms_test_")
    except ArgumentError:
        return False


# 세션 worktree(c:/tmp/foms-s-*)에서 alembic 실행 시 공유 DB 스키마가
# 해당 브랜치 기준으로 바뀌므로 코드 수준에서 차단한다 (Phase1 규칙).
# 예외: pytest PG 레인이 세션마다 만들고 지우는 일회용 ``foms_test_*`` DB는
# 공유 자원이 아니므로 차단 대상이 아니다(마이그레이션 체인 왕복 테스트가
# worktree 에서도 돌아야 한다).
_repo_root = _Path(__file__).resolve().parents[1]
if _repo_root.name.lower().startswith("foms-s-") and not _targets_throwaway_test_db(
    os.getenv("DATABASE_URL", "")
):
    raise RuntimeError(
        "세션 worktree에서 alembic 실행 금지 — 공유 DB 스키마가 이 브랜치 기준으로 바뀐다. "
        "마이그레이션은 메인 트리에서 실행하라."
    )

from alembic import context

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# add your model's MetaData object here
# for 'autogenerate' support
# from myapp import mymodel
# target_metadata = mymodel.Base.metadata
sys.path.insert(0, os.path.realpath(os.path.join(os.path.dirname(__file__), '..')))
from db import Base
from models import Order, User, AccessLog, SecurityLog, OrderDraft
# Designer AX models must be imported so Alembic sees their tables
import foms.persistence.designer.models  # noqa: F401
target_metadata = Base.metadata

_POSTGRES_ALEMBIC_LOCK_ID = 782364901234567890

def _normalize_postgres_url(url: str) -> str:
    """
    Railway 등에서 DATABASE_URL이 'postgres://'로 내려오는 경우가 있어
    SQLAlchemy/psycopg2 호환을 위해 'postgresql://'로 정규화.
    """
    if not url:
        return url
    if url.startswith("postgres://"):
        return "postgresql://" + url[len("postgres://"):]
    return url

def _get_database_url() -> str:
    # env 우선, 없으면 alembic.ini 값을 사용
    env_url = os.getenv("DATABASE_URL")
    ini_url = config.get_main_option("sqlalchemy.url")
    return _normalize_postgres_url(env_url or ini_url)
# other values from the config, defined by the needs of env.py,
# can be acquired:
# my_important_option = config.get_main_option("my_important_option")
# ... etc.


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    url = _get_database_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.

    """
    # env 기반 URL을 alembic config에 주입 (Railway 대응)
    config.set_main_option("sqlalchemy.url", _get_database_url())

    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        is_postgres = connection.dialect.name == "postgresql"

        # 세션 레벨 advisory lock으로 다중 replica의 동시 `alembic upgrade head`를 직렬화.
        # 주의: 과거 pg_advisory_xact_lock(트랜잭션 레벨)은 CONCURRENTLY 마이그레이션이
        # 내부에서 COMMIT(_run_concurrently)을 실행하는 순간 즉시 해제되어, 이후 인덱스
        # 빌드가 락 없이 replica 간 레이스를 일으켜 INVALID 인덱스를 남겼다.
        # 세션 레벨(pg_advisory_lock)은 내부 COMMIT을 넘어 유지되므로 upgrade 전체를
        # 한 replica로 직렬화한다. 명시적 unlock(+연결 종료)으로 해제한다.
        if is_postgres:
            print("[ALEMBIC] Waiting for PostgreSQL migration advisory lock (session-level)...")
            connection.execute(
                text("SELECT pg_advisory_lock(:lock_id)"),
                {"lock_id": _POSTGRES_ALEMBIC_LOCK_ID},
            )
            connection.commit()  # 락 획득 구문의 암묵 트랜잭션 종료(세션 락은 유지됨)
            print("[ALEMBIC] PostgreSQL migration advisory lock acquired.")

        try:
            context.configure(
                connection=connection, target_metadata=target_metadata
            )

            with context.begin_transaction():
                context.run_migrations()
        finally:
            if is_postgres:
                connection.execute(
                    text("SELECT pg_advisory_unlock(:lock_id)"),
                    {"lock_id": _POSTGRES_ALEMBIC_LOCK_ID},
                )
                connection.commit()
                print("[ALEMBIC] PostgreSQL migration advisory lock released.")


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
