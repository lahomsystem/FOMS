import os
from flask import g
from sqlalchemy import create_engine
from sqlalchemy.engine import URL
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import scoped_session, sessionmaker


def _normalize_postgres_url(url: str):
    if not url:
        return url
    if url.startswith('postgres://'):
        return 'postgresql://' + url[len('postgres://'):]
    return url


def _should_prefer_public_url(host: str | None) -> bool:
    return bool(
        os.name == 'nt'
        and host
        and host.endswith('.railway.internal')
    )


def _resolve_database_target():
    host = os.getenv('PGHOST')
    port = os.getenv('PGPORT')
    user = os.getenv('PGUSER')
    password = os.getenv('PGPASSWORD')
    database = os.getenv('PGDATABASE')

    if _should_prefer_public_url(host):
        for key in ('DATABASE_PUBLIC_URL', 'RAILWAY_PUBLIC_DATABASE_URL'):
            candidate = os.getenv(key)
            if candidate:
                return _normalize_postgres_url(candidate)

    if all([host, port, user, password, database]):
        return URL.create(
            drivername='postgresql+psycopg2',
            username=user,
            password=password,
            host=host,
            port=int(port) if str(port).isdigit() else port,
            database=database,
        )

    return _normalize_postgres_url(
        os.getenv('DATABASE_URL') or 'postgresql+psycopg2://postgres:lahom@localhost/furniture_orders'
    )


DB_URL = _resolve_database_target()

engine_args = {
    'pool_pre_ping': True,
    'echo': False,
}

if 'sqlite' not in str(DB_URL):
    engine_args.update({
        'pool_size': 20,
        'max_overflow': 20,
        'pool_recycle': 1800,
    })

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
