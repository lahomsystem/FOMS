import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, scoped_session
from sqlalchemy.ext.declarative import declarative_base
from flask import g

# 데이터베이스 연결 정보 하드코딩
# psycopg2 드라이버를 명시적으로 지정
DB_URL = "postgresql+psycopg2://postgres:lahom@localhost/furniture_orders"

# SQLAlchemy 엔진 생성
engine = create_engine(
    DB_URL,
    connect_args={"client_encoding": "utf8"},
    echo=False  # SQL 로그 비활성화
)

db_session = scoped_session(sessionmaker(autocommit=False, autoflush=False, bind=engine))

Base = declarative_base()
Base.query = db_session.query_property()

def init_db():
    """데이터베이스 초기화 및 테이블 생성"""
    try:
        # models는 함수 내부에서 임포트하여 순환 참조 방지
        from models import (
            Order, User, AccessLog, SecurityLog,
            ChatRoom, ChatRoomMember, ChatMessage, ChatAttachment
        )
        Base.metadata.create_all(bind=engine)
        print("데이터베이스 테이블 초기화 완료")
    except Exception as e:
        print(f"데이터베이스 초기화 중 오류 발생: {str(e)}")
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