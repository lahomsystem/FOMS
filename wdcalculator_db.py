import os
import json
from sqlalchemy import create_engine, text
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

# WDCalculator 스키마 (단일 DB 통합 모드에서 사용)
WD_CALCULATOR_SCHEMA = os.getenv("WD_CALCULATOR_SCHEMA") or "wdcalculator"

# 레거시(별도 DB) 모드 호환: 이 값이 설정되면 기존처럼 WDCalculator가 독립 DB를 사용
_WD_CALCULATOR_SEPARATE_DB_URL = os.getenv("WD_CALCULATOR_DATABASE_URL")
WD_CALCULATOR_IS_SEPARATE_DB = bool(_WD_CALCULATOR_SEPARATE_DB_URL)

# DB URL 결정 (환경변수 우선)
if WD_CALCULATOR_IS_SEPARATE_DB:
    # 기존 구조 유지: 별도 DB
    WD_CALCULATOR_DB_URL = _normalize_postgres_url(_WD_CALCULATOR_SEPARATE_DB_URL)
    _wd_connect_args = {}
else:
    # 추천 구조: 메인 DB(DATABASE_URL) 하나 + wdcalculator 스키마로 분리
    WD_CALCULATOR_DB_URL = _normalize_postgres_url(
        os.getenv("DATABASE_URL") or "postgresql+psycopg2://postgres:lahom@localhost/furniture_orders"
    )
    # 연결마다 search_path를 고정해 wdcalculator 스키마로 테이블/쿼리가 향하도록 함
    _wd_connect_args = {"options": f"-c search_path={WD_CALCULATOR_SCHEMA},public"}

# SQLAlchemy 엔진 생성
# JSONB 사용을 위해 json_serializer 설정 (선택사항이지만 명시적으로 지정)
wd_calculator_engine = create_engine(
    WD_CALCULATOR_DB_URL,
    pool_pre_ping=True,
    echo=False,
    connect_args=_wd_connect_args,
    json_serializer=lambda obj: json.dumps(obj, ensure_ascii=False),
)

wd_calculator_session = scoped_session(sessionmaker(autocommit=False, autoflush=False, bind=wd_calculator_engine))

WDCalculatorBase = declarative_base()
WDCalculatorBase.query = wd_calculator_session.query_property()

def ensure_wdcalculator_schema():
    """
    단일 DB 통합 모드에서 wdcalculator 스키마 존재를 보장.
    (별도 DB 모드에서는 필요 없음)
    """
    if WD_CALCULATOR_IS_SEPARATE_DB:
        return
    schema = WD_CALCULATOR_SCHEMA
    with wd_calculator_engine.begin() as conn:
        conn.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{schema}"'))

def init_wdcalculator_db():
    """견적 계산기 데이터베이스 초기화 및 테이블 생성"""
    try:
        # 단일 DB 통합 모드: 스키마 보장
        ensure_wdcalculator_schema()
        # 순환 참조 방지를 위해 함수 내부에서 임포트
        from wdcalculator_models import Estimate, EstimateOrderMatch, EstimateHistory
        WDCalculatorBase.metadata.create_all(bind=wd_calculator_engine)
        print("견적 계산기 데이터베이스 테이블 초기화 완료")
    except Exception as e:
        print(f"견적 계산기 데이터베이스 초기화 중 오류 발생: {str(e)}")
        raise

def get_wdcalculator_db():
    """Flask 앱 컨텍스트에서 견적 계산기 데이터베이스 세션 가져오기"""
    if 'wdcalculator_db' not in g:
        g.wdcalculator_db = wd_calculator_session
    return g.wdcalculator_db

def close_wdcalculator_db(e=None):
    """앱 컨텍스트가 종료될 때 견적 계산기 데이터베이스 세션 닫기"""
    db = g.pop('wdcalculator_db', None)
    if db is not None:
        db.close()

