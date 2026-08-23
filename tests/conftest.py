"""Pytest fixtures for FOMS (NEXT-003)."""
import os
import pytest
from werkzeug.security import generate_password_hash

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
