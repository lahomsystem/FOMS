"""OPS-ROUTE-01 / P0-18: public ops·debug 표면 봉쇄 계약.

무인증 public 응답에서 DB schema/table/count, env·secret 존재 여부, feature flag,
worker/backlog/delivery metric, raw exception/traceback 노출이 0 임을 고정한다.

- ``/debug-db`` : deployed registration 0 → 404.
- ``/api/channel/health`` : 무인증=coarse readiness 만, ADMIN 세션=운영 detail(no-store).
- ``/healthz`` : status + commit 만.
- ``/internal/ops/*`` : public 앱에 미등록 → 404.
"""

from __future__ import annotations


# 무인증 공개 응답에 절대 나타나면 안 되는 민감 substring/키.
_SENSITIVE_SUBSTRINGS = (
    "CHANNEL_APP_SECRET",
    "CHANNEL_SIGNING_KEY",
    "CHANNEL_ID",
    "worker_count",
    "backlog_count",
    "delivery_success_rate",
    "flag_violations",
    "traceback",
    "Traceback",
    "environment",
    "metrics",
    "security",
)


def test_debug_db_removed_returns_404_anonymous(client) -> None:
    """무인증 ``/debug-db`` 는 404(deployed registration 0)."""
    resp = client.get("/debug-db")
    assert resp.status_code == 404


def test_debug_db_removed_even_for_admin(auth_client) -> None:
    """ADMIN 세션에서도 ``/debug-db`` 라우트는 존재하지 않는다(404)."""
    resp = auth_client.get("/debug-db")
    assert resp.status_code == 404


def test_channel_health_public_exposes_only_coarse_readiness(client) -> None:
    """무인증 ``/api/channel/health`` 는 coarse readiness 키 하나만 반환한다."""
    resp = client.get("/api/channel/health")
    assert resp.status_code in (200, 503)
    data = resp.get_json()
    assert set(data.keys()) == {"readiness"}
    assert data["readiness"] in ("ready", "degraded", "fail")


def test_channel_health_public_leaks_no_sensitive_strings(client) -> None:
    """무인증 응답 raw body 에 secret/metric/exception substring 이 0 이다."""
    resp = client.get("/api/channel/health")
    body = resp.get_data(as_text=True)
    for needle in _SENSITIVE_SUBSTRINGS:
        assert needle not in body, f"민감 substring 노출: {needle}"


def test_channel_health_public_metric_differential_zero(client, monkeypatch) -> None:
    """채널이 설정/운영 중이어도 무인증 응답은 metric 을 노출하지 않는다(차등 0)."""
    monkeypatch.setenv("FOMS_BASE_URL", "https://example.com")
    monkeypatch.setenv("CHANNEL_PUSH_ENABLED", "true")
    monkeypatch.setenv("CHANNEL_APP_SECRET", "s" * 40)
    import foms.api.channel.channel_integration as ci

    monkeypatch.setattr(
        ci, "get_rq_runtime_status", lambda: {"state": "reachable", "worker_count": 7}
    )
    resp = client.get("/api/channel/health")
    data = resp.get_json()
    assert set(data.keys()) == {"readiness"}
    assert "7" not in resp.get_data(as_text=True)


def test_channel_health_public_has_no_store_and_no_validators(client) -> None:
    """무인증 응답은 no-store 이고 ETag/Last-Modified 검증자가 없다."""
    resp = client.get("/api/channel/health")
    assert "no-store" in resp.headers.get("Cache-Control", "")
    assert "ETag" not in resp.headers
    assert "Last-Modified" not in resp.headers


def test_channel_health_detail_for_admin_and_no_store(auth_client) -> None:
    """ADMIN 세션은 운영 detail 을 받고, private/no-store + Vary Cookie 를 쓴다."""
    resp = auth_client.get("/api/channel/health")
    assert resp.status_code in (200, 503)
    data = resp.get_json()
    # detail 키들이 존재해야 admin 대시보드가 동작한다.
    assert "queue" in data
    assert "metrics" in data
    assert "environment" in data
    cc = resp.headers.get("Cache-Control", "")
    assert "no-store" in cc
    assert "private" in cc
    assert "Cookie" in resp.headers.get("Vary", "")
    assert "ETag" not in resp.headers
    assert "Last-Modified" not in resp.headers


def test_healthz_returns_only_status_and_commit(client) -> None:
    """``/healthz`` 는 status + commit 만 반환(DB/schema/secret 키 부재)."""
    resp = client.get("/healthz")
    assert resp.status_code == 200
    data = resp.get_json()
    assert set(data.keys()) == {"status", "commit"}
    assert data["status"] == "ok"
    body = resp.get_data(as_text=True)
    for needle in ("schema", "table", "secret", "traceback", "DATABASE_URL"):
        assert needle.lower() not in body.lower()


def test_internal_ops_surface_not_registered_on_public_app(client) -> None:
    """public 앱에는 ``/internal/ops/*`` 가 등록되지 않는다(404)."""
    for path in (
        "/internal/ops/channel-readiness",
        "/internal/ops/",
    ):
        assert client.get(path).status_code == 404
