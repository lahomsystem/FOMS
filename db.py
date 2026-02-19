import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, scoped_session
from sqlalchemy.ext.declarative import declarative_base
from flask import g

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

# 데이터베이스 연결 정보 (환경변수 우선)
# psycopg2 드라이버를 명시적으로 지정
DB_URL = _normalize_postgres_url(
    os.getenv("DATABASE_URL") or "postgresql+psycopg2://postgres:lahom@localhost/furniture_orders"
)

# SQLAlchemy 엔진 생성
engine_args = {
    "pool_pre_ping": True,
    "echo": False  # SQL 로그 비활성화
}

# SQLite는 pool 설정을 지원하지 않음 (SingletonThreadPool 사용)
if "sqlite" not in DB_URL:
    engine_args.update({
        "pool_size": 20,       # Quest 14: Increase pool for 100 concurrent users
        "max_overflow": 20,    # Allow bursts
        "pool_recycle": 1800,  # Recycle connections every 30 mins
    })

engine = create_engine(DB_URL, **engine_args)

db_session = scoped_session(sessionmaker(autocommit=False, autoflush=False, bind=engine))

Base = declarative_base()
Base.query = db_session.query_property()

def init_db():
    """데이터베이스 초기화 및 테이블 생성"""
    try:
        # models are imported inside function to prevent circular reference
        from models import (
            Order, User, AccessLog, SecurityLog,
            ChatRoom, ChatRoomMember, ChatMessage, ChatAttachment,
            OrderAttachment, OrderEvent, OrderTask
        )
        Base.metadata.create_all(bind=engine)
        print("Database tables initialization completed")
    except Exception as e:
        print(f"Error during database initialization: {str(e)}")
        raise

def get_db():
    """Flask 앱 컨텍스트에서 데이터베이스 세션 가져오기"""
    if 'db' not in g:
        g.db = db_session
    return g.db

def close_db(e=None):
    """앱 컨텍스트가 종료될 때 데이터베이스 세션 닫기"""
    db = g.pop('db', None)
    if db is not None:
        db.close() 