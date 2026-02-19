import pytest

def test_quick_search_missing_q_returns_400(login):
    """GET /api/orders/quick-search without q returns 400 Bad Request."""
    client = login
    r = client.get("/api/orders/quick-search")
    assert r.status_code == 400
    assert r.is_json
    data = r.get_json()
    assert data['success'] is False
    assert '검색어' in data['message']

def test_quick_search_with_query(login):
    """GET /api/orders/quick-search?q=test returns 200 OK."""
    client = login
    r = client.get("/api/orders/quick-search?q=test")
    assert r.status_code == 200
    assert r.is_json
    data = r.get_json()
    # It returns list of orders directly or wrapped
    assert isinstance(data, (list, dict))
