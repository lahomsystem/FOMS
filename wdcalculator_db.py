import os
import json
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, scoped_session
from sqlalchemy.ext.declarative import declarative_base
from flask import g

# 독립 데이터베이스 연결 정보 (FOMS와 완전 분리)
# 견적 계산기 전용 데이터베이스
WD_CALCULATOR_DB_URL = "postgresql+psycopg2://postgres:lahom@localhost/wdcalculator_estimates"

# SQLAlchemy 엔진 생성 (독립 DB)
# JSONB 사용을 위해 json_serializer 설정 (선택사항이지만 명시적으로 지정)
wd_calculator_engine = create_engine(
    WD_CALCULATOR_DB_URL,
    pool_pre_ping=True,
    echo=False,
    json_serializer=lambda obj: json.dumps(obj, ensure_ascii=False)
)

wd_calculator_session = scoped_session(sessionmaker(autocommit=False, autoflush=False, bind=wd_calculator_engine))

WDCalculatorBase = declarative_base()
WDCalculatorBase.query = wd_calculator_session.query_property()

def init_wdcalculator_db():
    """견적 계산기 데이터베이스 초기화 및 테이블 생성"""
    try:
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

