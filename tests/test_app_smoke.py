"""Smoke tests for FOMS app (NEXT-003)."""


def test_app_import():
    """App module imports and exposes Flask app."""
    from app import app as flask_app
    assert flask_app is not None


def test_index_returns_ok_or_redirect(client):
    """GET / returns 200 or 302 (redirect to login)."""
    r = client.get("/")
    assert r.status_code in (200, 302)


def test_login_page_returns_200(client):
    """GET /login returns 200."""
    r = client.get("/login")
    assert r.status_code == 200
