import os
from typing import Any
from flask import g
from sqlalchemy import create_engine
from sqlalchemy.orm import scoped_session, sessionmaker, declarative_base

from foms.services.db_url_resolver import (
    postgres_dbapi_connect,
    postgresql_connect_kwargs_from_url,
    prepare_database_url_env,
    sqlalchemy_url,
)


def _resolve_database_target():
    """Resolve DB URL via shared Railway/PG env rules (percent-encoding for PG* passwords)."""
    prepare_database_url_env()
    return sqlalchemy_url(
        os.getenv('DATABASE_URL') or 'postgresql://postgres:lahom@localhost/furniture_orders'
    )


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
    _pg_connect_kw = postgresql_connect_kwargs_from_url(_db_url_str)

    def _postgresql_creator():
        return postgres_dbapi_connect(_pg_connect_kw)

    engine = create_engine(sqlalchemy_url('postgresql://'), creator=_postgresql_creator, **engine_args)
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


def mark_request_db_state(sender=None, **_extra):
    """요청 시작에 ``db_session`` 트랜잭션이 이미 열려 있었는지 적어 둔다(``request_started`` 신호)."""
    g._db_tx_open_at_start = db_session.registry.has() and db_session().in_transaction()


def release_request_db_session(e=None):
    """요청이 끝나면 그 요청이 연 DB 연결을 돌려놓는다 — ``get_db()`` 를 안 부른 요청도.

    ``close_db`` 는 ``g.db`` 가 있을 때만 닫는다. 로그인 없는 공유 링크(``foms/api/share.py``)처럼
    ``db_session`` 을 바로 쓰는 요청은 마지막에 꺼낸 연결이 요청 뒤에도 남아, greenlet 이 끝난 뒤
    GC 가 치운다(운영 [DB-LEAK] 11-08 판독: 6일 121건 중 116건). 세션이 없으면 새로 만들지 않는다.

    ``close()`` 가 아니라 ``rollback()`` 이다 — 끝나지 않은 트랜잭션만 끝내 연결을 풀에 돌려놓고,
    객체는 세션에 붙여 둔 채 만료만 시킨다. 요청 시작 전부터 열려 있던 트랜잭션(시험이 같은
    스레드에서 flush 해 둔 데이터 등)은 그 요청 것이 아니므로 건드리지 않는다 — 시작 상태를 모르면
    (``request_started`` 가 안 온 시험용 요청 문맥) 역시 건드리지 않는다.
    """
    if 'db' in g:
        return  # get_db() 를 부른 요청은 바로 뒤 close_db 가 닫는다 — 먼저 만료시키면 객체가 빈 채 떨어진다
    if g.get('_db_tx_open_at_start', True):
        return
    if db_session.registry.has():
        db_session.rollback()
