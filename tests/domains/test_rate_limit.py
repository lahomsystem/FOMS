import hashlib

from flask import Flask, session

import foms.services.rate_limit as rate_limit


class _LimiterSpy:
    def __init__(
        self,
        key_func,
        *,
        app,
        storage_uri,
        default_limits,
        swallow_errors=None,
        in_memory_fallback_enabled=None,
        storage_options=None,
    ):
        self.key_func = key_func
        self.app = app
        self.storage_uri = storage_uri
        self.default_limits = default_limits
        self.swallow_errors = swallow_errors
        self.in_memory_fallback_enabled = in_memory_fallback_enabled
        self.storage_options = storage_options


def test_init_limiter_passes_expected_storage_uri_and_parsed_limits(monkeypatch):
    monkeypatch.setenv("REDIS_URL", "redis://example")
    monkeypatch.setenv("FLASK_DEFAULT_RATE_LIMITS", "10 per minute, 2 per second ")
    monkeypatch.setattr(rate_limit, "Limiter", _LimiterSpy)

    app = Flask(__name__)

    limiter = rate_limit.init_limiter(app)

    assert limiter.app is app
    assert limiter.storage_uri == "redis://example"
    assert limiter.default_limits == ["10 per minute", "2 per second"]
    assert limiter.swallow_errors is True
    assert limiter.in_memory_fallback_enabled is True
    assert limiter.storage_options.get("socket_connect_timeout") == 2
    assert limiter.storage_options.get("socket_timeout") == 2


def test_init_limiter_falls_back_to_memory_and_default_limits_when_env_blank(monkeypatch):
    monkeypatch.delenv("REDIS_URL", raising=False)
    monkeypatch.setenv("FLASK_DEFAULT_RATE_LIMITS", "   ")
    monkeypatch.setattr(rate_limit, "Limiter", _LimiterSpy)

    app = Flask(__name__)

    limiter = rate_limit.init_limiter(app)

    assert limiter.storage_uri == "memory://"
    assert limiter.default_limits == ["5000 per day", "1200 per hour"]
    assert limiter.storage_options == {}


def test_init_limiter_rate_limit_key_precedence(monkeypatch):
    monkeypatch.delenv("REDIS_URL", raising=False)
    monkeypatch.delenv("FLASK_DEFAULT_RATE_LIMITS", raising=False)
    monkeypatch.setattr(rate_limit, "Limiter", _LimiterSpy)
    monkeypatch.setattr(rate_limit, "get_remote_address", lambda: "9.9.9.9")

    app = Flask(__name__)
    app.secret_key = "test-secret"
    app.config["SESSION_COOKIE_NAME"] = "session_staging"

    limiter = rate_limit.init_limiter(app)

    with app.test_request_context("/", headers={"X-Forwarded-For": "1.1.1.1, 2.2.2.2"}):
        session["user_id"] = 7
        assert limiter.key_func() == "user:7"

    raw_cookie = "cookie-value"
    expected_cookie_hash = hashlib.sha1(raw_cookie.encode("utf-8")).hexdigest()[:16]
    with app.test_request_context(
        "/",
        headers={
            "Cookie": f"session_staging={raw_cookie}",
            "X-Forwarded-For": "1.1.1.1, 2.2.2.2",
        },
    ):
        assert limiter.key_func() == f"sess:{expected_cookie_hash}"

    # PROXY-01: raw X-Forwarded-For / X-Real-IP are attacker-controlled and are
    # NOT consulted; the key falls back to the canonical client IP
    # (get_remote_address == request.remote_addr, normalized by ProxyFix).
    with app.test_request_context(
        "/",
        headers={
            "X-Forwarded-For": "1.1.1.1, 2.2.2.2",
            "X-Real-IP": "3.3.3.3",
        },
    ):
        assert limiter.key_func() == "9.9.9.9"

    with app.test_request_context("/", headers={"X-Real-IP": "3.3.3.3"}):
        assert limiter.key_func() == "9.9.9.9"

    with app.test_request_context("/"):
        assert limiter.key_func() == "9.9.9.9"


def test_dead_redis_does_not_500_and_falls_back(monkeypatch):
    """A dead Redis must NOT cause 500s — limiter fails open to in-memory (regression: prod outage 2026-07-21)."""
    # Point REDIS_URL at a port with nothing listening -> storage errors at request time.
    monkeypatch.setenv("REDIS_URL", "redis://127.0.0.1:6390")
    monkeypatch.setenv("FLASK_DEFAULT_RATE_LIMITS", "100 per minute")

    app = Flask(__name__)

    @app.route("/ping")
    def ping():
        return "ok"

    rate_limit.init_limiter(app)  # real Limiter with fail-open config

    resp = app.test_client().get("/ping")
    assert resp.status_code != 500  # fail-open: never 500 on Redis outage
    assert resp.status_code == 200
