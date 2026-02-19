"""Pytest fixtures for FOMS (NEXT-003)."""
import os
import pytest
from werkzeug.security import generate_password_hash

# 1. Set environment variable for test database BEFORE importing app/db
os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["SECRET_KEY"] = "test-secret-key"

from app import app as flask_app
from db import init_db, db_session, Base, engine
from models import User

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
