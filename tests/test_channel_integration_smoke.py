"""Smoke tests for ChannelTalk Integration (Phase 0)."""

def test_channel_health_endpoint_exists(client):
    """GET /api/channel/health returns 200 or 503 depending on env vars."""
    r = client.get("/api/channel/health")
    assert r.status_code in (200, 503)
    data = r.get_json()
    assert "readiness" in data
    assert "environment" in data
    assert "flags" in data

def test_channel_admin_delivery_status_requires_auth(client):
    """GET /api/channel/admin/delivery-status requires authentication."""
    r = client.get("/api/channel/admin/delivery-status")
    # Should redirect to login or return 401
    assert r.status_code in (302, 401)
