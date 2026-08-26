"""Pytest fixtures for FOMS (NEXT-003)."""
import os
import pytest
import werkzeug.security as _werkzeug_security
from werkzeug.security import generate_password_hash

# --- CI-KDF-01: 테스트 레인 전용 PBKDF2 반복수 완화 -------------------------------
# werkzeug 2.3 기본값은 pbkdf2:sha256:600000 이고, 해시 1회에 약 250ms 가 든다.
# tests/ 는 User 행을 채우려고 generate_password_hash 를 404 곳에서 부르는데,
# 그렇게 만든 해시 1,695 개 중 실제 대조(check_password_hash)에 쓰이는 것은 254 개뿐이다.
# 나머지는 아무도 검증하지 않을 비밀번호를 60만 번 돌리는 순수 낭비이고, 이것이
# FOMS CI `Run tests` 839초의 약 73%(실측 676초)를 차지한다.
#
# 반복수만 낮춘다. 호출부 404 곳은 그대로 두고, 코드 경로도 그대로다 — 같은 경로가
# 싸질 뿐이라 검출력 손실이 없다(전체 4,469건 A/B 에서 실패/성공 집합 완전 동일).
# 반복수는 해시 문자열에 박히므로 check_password_hash 는 정상 동작한다.
#
# generate_password_hash 는 이 상수를 **호출 시점에** 읽는다. 그래서 위 4행처럼
# 이름을 미리 바인딩(early-bound)한 모듈이 있어도 이 패치가 먹는다. 반대로
# generate_password_hash 함수 자체를 교체하는 방식은 그런 모듈에 적용되지 않는다.
#
# 이 파일은 tests/ 전용이며 운영 코드는 import 하지 않는다. 운영 해싱 강도는
# foms/services/security/password_policy.py 가 method= 없이 호출해 werkzeug 기본값을
# 그대로 쓰므로 영향받지 않는다. 이 완화가 조용히 무효화되거나(werkzeug 상수명 변경)
# 운영으로 새는 것은 tests/domains/test_password_kdf_contract.py 가 봉인한다.
FOMS_TEST_PBKDF2_ITERATIONS = 10
PRODUCTION_PBKDF2_ITERATIONS = _werkzeug_security.DEFAULT_PBKDF2_ITERATIONS
_werkzeug_security.DEFAULT_PBKDF2_ITERATIONS = FOMS_TEST_PBKDF2_ITERATIONS

from tests.postgres_guard import assert_not_postgresql, assert_safe_for_schema_reset

# 1. Set environment variable for test database BEFORE importing app/db
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
_db_url = os.environ.get("DATABASE_URL", "").strip()
assert_not_postgresql(_db_url, context="pytest session (tests/conftest.py)")
os.environ["SECRET_KEY"] = "test-secret-key"
os.environ["DESIGNER_AI_FAKE"] = "1"

from app import app as flask_app
from db import init_db, db_session, Base, engine
from models import User

# Ensure designer models are registered in Base
import foms.persistence.designer.models  # noqa: F401


@pytest.fixture
def app():
    """Flask app with TESTING config and in-memory DB."""
    flask_app.config["TESTING"] = True
    
    # Create tables
    # 엔진 기준 가드가 **먼저** 온다. env 문자열만 보면, conftest 보다 먼저 db 를 import 한
    # 파일 하나가 엔진을 로컬 Postgres 에 묶어 놓아도 "sqlite 니까 안전"으로 통과한다
    # (2026-08-23 그렇게 로컬 dev DB 테이블 86개가 드롭됐다).
    assert_safe_for_schema_reset(
        os.environ.get("DATABASE_URL", ""),
        context="tests/conftest.py app fixture setup",
        engine=engine,
    )
    Base.metadata.create_all(bind=engine)

    yield flask_app

    # Cleanup
    db_session.remove()
    assert_safe_for_schema_reset(
        os.environ.get("DATABASE_URL", ""),
        context="tests/conftest.py app fixture teardown",
        engine=engine,
    )
    Base.metadata.drop_all(bind=engine)

@pytest.fixture
def client(app):
    """Test client."""
    return app.test_client()

@pytest.fixture
def login(client):
    """Login helper. Creates admin user and logs in."""
    # Create admin user
    user = User(
        username="admin", 
        password=generate_password_hash("admin"), 
        role="admin",
        name="Admin User"
    )
    db_session.add(user)
    db_session.commit()

    # Login
    client.post("/login", data={
        "username": "admin",
        "password": "admin"
    }, follow_redirects=True)
    
    return client


@pytest.fixture
def auth_client(app):
    """Test client with an authenticated admin session."""
    # Ensure table exists
    Base.metadata.create_all(bind=engine)

    # Create admin user if not exists
    existing = db_session.query(User).filter_by(username="testadmin").first()
    if not existing:
        user = User(
            username="testadmin",
            password=generate_password_hash("testpass"),
            role="ADMIN",
            name="Test Admin",
        )
        db_session.add(user)
        db_session.commit()

    client = app.test_client()
    client.post("/login", data={"username": "testadmin", "password": "testpass"}, follow_redirects=True)
    return client
