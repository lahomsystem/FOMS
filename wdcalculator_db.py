import os
import json
from typing import Any
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, scoped_session, declarative_base
from flask import g

from foms.services.db_url_resolver import (
    postgresql_psycopg2_connect_kwargs_from_url,
    prepare_database_url_env,
)


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


def _ensure_psycopg2_driver(url: str) -> str:
    """Use explicit psycopg2 driver; leave non-Postgres URLs (e.g. sqlite) unchanged."""
    if not url or not url.startswith("postgresql"):
        return url
    if url.startswith("postgresql+psycopg2://"):
        return url
    if url.startswith("postgresql://"):
        return "postgresql+psycopg2://" + url[len("postgresql://"):]
    return url


# PG* / DATABASE_URL 정렬 (db.py와 동일; 단독 import 시에도 동작)
prepare_database_url_env()

# WDCalculator 스키마 (단일 DB 통합 모드에서 사용)
WD_CALCULATOR_SCHEMA = os.getenv("WD_CALCULATOR_SCHEMA") or "wdcalculator"

# 레거시(별도 DB) 모드 호환: 이 값이 설정되면 기존처럼 WDCalculator가 독립 DB를 사용
_WD_CALCULATOR_SEPARATE_DB_URL = os.getenv("WD_CALCULATOR_DATABASE_URL")
WD_CALCULATOR_IS_SEPARATE_DB = bool(_WD_CALCULATOR_SEPARATE_DB_URL)

# DB URL 결정 (환경변수 우선)
if WD_CALCULATOR_IS_SEPARATE_DB:
    WD_CALCULATOR_DB_URL = _ensure_psycopg2_driver(
        _normalize_postgres_url(_WD_CALCULATOR_SEPARATE_DB_URL)
    )
else:
    WD_CALCULATOR_DB_URL = _ensure_psycopg2_driver(
        _normalize_postgres_url(
            os.getenv("DATABASE_URL")
            or "postgresql+psycopg2://postgres:lahom@localhost/furniture_orders"
        )
    )

_db_url_str = str(WD_CALCULATOR_DB_URL)

# SQLAlchemy 엔진 생성
engine_args: dict[str, Any] = {
    "pool_pre_ping": True,
    "echo": False,
    "json_serializer": lambda obj: json.dumps(obj, ensure_ascii=False),
}

if "sqlite" not in _db_url_str:
    engine_args.update(
        {
            # ERP 대비 계산기 트래픽 소량 — 프로세스 4개 총 커넥션 상한 완화(120→72).
            # 프로세스당 pool_size(3)+max_overflow(3)=6, ×4 프로세스 ×(main+wdc) 계열.
            "pool_size": 3,
            "max_overflow": 3,
            "pool_recycle": 1800,
            # main DB(db.py)와 동일하게 10s 빠른 실패. gevent 환경에서 기본 30s
            # 대기는 커넥션 고갈 시 그린렛을 오래 붙잡아 tail을 키운다.
            "pool_timeout": 10,
        }
    )

if "sqlite" in _db_url_str:
    engine_args["connect_args"] = {}
    wd_calculator_engine = create_engine(WD_CALCULATOR_DB_URL, **engine_args)
elif _db_url_str.startswith("postgresql"):
    import psycopg2

    _wd_pg_kw = dict(postgresql_psycopg2_connect_kwargs_from_url(WD_CALCULATOR_DB_URL))
    if not WD_CALCULATOR_IS_SEPARATE_DB:
        _wd_pg_kw["options"] = f"-c search_path={WD_CALCULATOR_SCHEMA},public"

    def _wd_pg_creator():
        return psycopg2.connect(**_wd_pg_kw)

    wd_calculator_engine = create_engine(
        "postgresql+psycopg2://",
        creator=_wd_pg_creator,
        **engine_args,
    )
else:
    engine_args["connect_args"] = {}
    wd_calculator_engine = create_engine(WD_CALCULATOR_DB_URL, **engine_args)

wd_calculator_session = scoped_session(sessionmaker(autocommit=False, autoflush=False, bind=wd_calculator_engine))

WDCalculatorBase = declarative_base()
WDCalculatorBase.query = wd_calculator_session.query_property()


def ensure_wdcalculator_schema():
    """
    Ensure 'wdcalculator' schema exists in single-DB mode.
    (Not needed in separate-DB mode)
    """
    if WD_CALCULATOR_IS_SEPARATE_DB:
        return
    if wd_calculator_engine.dialect.name != "postgresql":
        return
    schema = WD_CALCULATOR_SCHEMA
    with wd_calculator_engine.begin() as conn:
        conn.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{schema}"'))


def ensure_settings_schema_upgrades():
    """기존 wdcalculator_product_settings 테이블에 신규 컬럼을 멱등 추가한다.

    ``create_all``은 신규 테이블만 생성하고 기존 테이블에 컬럼을 추가하지 않으므로,
    ``spec_field_presets`` 같은 후행 컬럼은 부팅 시 멱등 ALTER로 보강한다.
    PostgreSQL은 ``ADD COLUMN IF NOT EXISTS``로, SQLite(로컬 QA)는 컬럼 존재 확인 후
    추가한다(2회 부팅·기존 DB 모두 안전).
    """
    table = "wdcalculator_product_settings"
    dialect = wd_calculator_engine.dialect.name
    if dialect == "postgresql":
        schema = None if WD_CALCULATOR_IS_SEPARATE_DB else WD_CALCULATOR_SCHEMA
        qualified = f'"{schema}".{table}' if schema else table
        with wd_calculator_engine.begin() as conn:
            conn.execute(
                text(
                    f"ALTER TABLE {qualified} "
                    "ADD COLUMN IF NOT EXISTS spec_field_presets JSONB NOT NULL DEFAULT '{}'::jsonb"
                )
            )
        return
    # SQLite 등: ADD COLUMN IF NOT EXISTS 미지원 → 컬럼 존재 확인 후 추가
    from sqlalchemy import inspect as sa_inspect

    insp = sa_inspect(wd_calculator_engine)
    if table not in insp.get_table_names():
        return
    existing = {col["name"] for col in insp.get_columns(table)}
    if "spec_field_presets" not in existing:
        with wd_calculator_engine.begin() as conn:
            conn.execute(
                text(
                    f"ALTER TABLE {table} "
                    "ADD COLUMN spec_field_presets JSON NOT NULL DEFAULT '{}'"
                )
            )


def init_wdcalculator_db():
    """Initialize WDCalculator database and create tables"""
    try:
        # 1. Ensure schema in single-DB mode
        ensure_wdcalculator_schema()
        # Import models inside function to prevent circular reference
        from wdcalculator_models import (
            Estimate,
            EstimateHistory,
            EstimateOrderMatch,
            WDCalculatorProductSettings,
        )
        WDCalculatorBase.metadata.create_all(bind=wd_calculator_engine)
        # 2. 기존 테이블에 신규 컬럼 멱등 보강 (create_all이 못 하는 부분)
        ensure_settings_schema_upgrades()
        print("WDCalculator tables initialization completed")
    except Exception as e:
        print(f"Error during WDCalculator initialization: {str(e)}")
        raise


def get_wdcalculator_db():
    """Flask 앱 컨텍스트에서 견적 계산기 데이터베이스 세션 가져오기"""
    if "wdcalculator_db" not in g:
        g.wdcalculator_db = wd_calculator_session
    return g.wdcalculator_db


def close_wdcalculator_db(e=None):
    """앱 컨텍스트가 종료될 때 견적 계산기 데이터베이스 세션 닫기"""
    db = g.pop("wdcalculator_db", None)
    if db is not None:
        db.close()
