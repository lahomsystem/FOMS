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


def test_erp_returns_ok_or_redirect_or_not_found(client):
    """GET /erp/ or /erp returns 200/302 (auth) or 404 (route may vary)."""
    r = client.get("/erp/")
    assert r.status_code in (200, 302, 404)


def test_api_orders_calendar_returns_ok_or_auth(client):
    """GET /api/orders (calendar) returns 200 or 401/302."""
    r = client.get("/api/orders")
    assert r.status_code in (200, 302, 401)
