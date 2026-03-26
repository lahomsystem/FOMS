"""Smoke tests for ChannelTalk Integration (Phase 0)."""

from apps.api import channel_integration
from services.jobs import queue as queue_module


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


def test_channel_health_uses_runtime_worker_status(client, monkeypatch):
    monkeypatch.setenv("FOMS_BASE_URL", "https://example.com")
    monkeypatch.setenv("CHANNEL_PUSH_ENABLED", "true")
    monkeypatch.setattr(
        channel_integration,
        "get_rq_runtime_status",
        lambda: {"state": "reachable", "worker_count": 2},
    )

    r = client.get("/api/channel/health")

    assert r.status_code == 200
    data = r.get_json()
    assert data["readiness"] == "ready"
    assert data["queue"]["state"] == "reachable"
    assert data["queue"]["worker_count"] == 2


def test_channel_health_returns_json_when_runtime_probe_fails(client, monkeypatch):
    monkeypatch.setenv("FOMS_BASE_URL", "https://example.com")

    def _raise_probe():
        raise RuntimeError("worker probe failed")

    monkeypatch.setattr(channel_integration, "get_rq_runtime_status", _raise_probe)

    r = client.get("/api/channel/health")

    assert r.status_code == 503
    assert r.is_json
    data = r.get_json()
    assert data["readiness"] == "fail"
    assert "CHANNEL_HEALTH_CHECK_FAILED" in data["flag_violations"]
    assert data["error"] == "worker probe failed"


def test_rq_runtime_status_uses_live_worker_count(monkeypatch):
    class DummyConnection:
        def ping(self):
            return True

    class DummyQueue:
        connection = DummyConnection()

    monkeypatch.setenv("REDIS_URL", "redis://example:6379/0")
    monkeypatch.setattr(queue_module, "get_rq_queue", lambda: DummyQueue())

    from rq import Worker

    def _fake_count(cls, connection=None, queue=None):
        assert connection is DummyQueue.connection
        assert queue.__class__ is DummyQueue
        return 3

    monkeypatch.setattr(Worker, "count", classmethod(_fake_count))

    status = queue_module.get_rq_runtime_status()

    assert status == {"state": "reachable", "worker_count": 3}


def test_rq_runtime_status_falls_back_to_worker_all(monkeypatch):
    class DummyConnection:
        def ping(self):
            return True

    class DummyQueue:
        connection = DummyConnection()

    monkeypatch.setenv("REDIS_URL", "redis://example:6379/0")
    monkeypatch.setattr(queue_module, "get_rq_queue", lambda: DummyQueue())

    from rq import Worker

    def _fake_count(cls, connection=None, queue=None):
        raise TypeError("count not supported")

    def _fake_all(cls, connection=None, job_class=None, queue_class=None, queue=None, serializer=None):
        return [object(), object()]

    monkeypatch.setattr(Worker, "count", classmethod(_fake_count))
    monkeypatch.setattr(Worker, "all", classmethod(_fake_all))

    status = queue_module.get_rq_runtime_status()

    assert status == {"state": "reachable", "worker_count": 2}
