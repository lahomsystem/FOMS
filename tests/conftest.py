"""Pytest fixtures for FOMS (NEXT-003)."""
import pytest


@pytest.fixture
def app():
    """Flask app with TESTING config."""
    from app import app as flask_app
    flask_app.config["TESTING"] = True
    return flask_app


@pytest.fixture
def client(app):
    """Test client."""
    return app.test_client()
