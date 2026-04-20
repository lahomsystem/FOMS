import os
from typing import Any
from flask import g
from sqlalchemy import create_engine
from sqlalchemy.orm import scoped_session, sessionmaker, declarative_base

from foms.services.db_url_resolver import (
    postgresql_psycopg2_connect_kwargs_from_url,
    prepare_database_url_env,
)


def _normalize_postgres_url(url: str) -> str:
    if not url:
        return url
    if url.startswith('postgres://'):
        return 'postgresql://' + url[len('postgres://'):]
    return url


def _ensure_psycopg2_driver(url: str) -> str:
    """Use explicit psycopg2 driver; leave non-Postgres URLs (e.g. sqlite) unchanged."""
    if not url or not url.startswith('postgresql'):
        return url
    if url.startswith('postgresql+psycopg2://'):
        return url
    if url.startswith('postgresql://'):
        return 'postgresql+psycopg2://' + url[len('postgresql://'):]
    return url


def _resolve_database_target():
    """Resolve DB URL via shared Railway/PG env rules (percent-encoding for PG* passwords)."""
    prepare_database_url_env()
    db_url = os.getenv('DATABASE_URL')
    if db_url:
        return _ensure_psycopg2_driver(_normalize_postgres_url(db_url))
    return 'postgresql+psycopg2://postgres:lahom@localhost/furniture_orders'


DB_URL = _resolve_database_target()

engine_args: dict[str, Any] = {
    'pool_pre_ping': True,
    'echo': False,
}

_db_url_str = str(DB_URL)

if 'sqlite' not in _db_url_str:
    engine_args.update({
        'pool_size': 5,       # Gunicorn 2 worker 기준 (20 → 5, 최대 커넥션 40 → 10)
        'max_overflow': 5,    # 최대 총 커넥션: 10 (Railway 소규모 플랜 적정)
        'pool_recycle': 1800,
        'pool_timeout': 10,   # gevent 환경: 30s 기본 대기 대신 10s 빠른 실패
    })

if 'sqlite' in _db_url_str:
    engine = create_engine(DB_URL, **engine_args)
elif _db_url_str.startswith('postgresql'):
    import psycopg2

    _pg_connect_kw = postgresql_psycopg2_connect_kwargs_from_url(_db_url_str)

    def _postgresql_creator():
        return psycopg2.connect(**_pg_connect_kw)

    engine = create_engine('postgresql+psycopg2://', creator=_postgresql_creator, **engine_args)
else:
    engine = create_engine(DB_URL, **engine_args)

db_session = scoped_session(sessionmaker(autocommit=False, autoflush=False, bind=engine))

Base = declarative_base()
Base.query = db_session.query_property()


def init_db():
    try:
        from models import (
            Order, User, AccessLog, SecurityLog,
            ChatRoom, ChatRoomMember, ChatMessage, ChatAttachment,
            OrderAttachment, OrderEvent, OrderTask,
            SystemSetting
        )
        Base.metadata.create_all(bind=engine)
        print('Database tables initialization completed')
    except Exception as e:
        print(f'Error during database initialization: {str(e)}')
        raise


def get_db():
    if 'db' not in g:
        g.db = db_session
    return g.db


def close_db(e=None):
    db = g.pop('db', None)
    if db is not None:
        db.close()
