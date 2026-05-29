"""Pytest fixtures for FOMS (NEXT-003)."""
import os
import pytest
from werkzeug.security import generate_password_hash

# 1. Set environment variable for test database BEFORE importing app/db
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
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
    Base.metadata.create_all(bind=engine)
    
    yield flask_app
    
    # Cleanup
    db_session.remove()
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
