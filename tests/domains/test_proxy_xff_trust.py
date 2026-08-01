"""PROXY-01: trusted-proxy X-Forwarded-For boundary + canonical rate-limit key.

The rate-limit key-func (foms.services.rate_limit.init_limiter) must derive the
client IP from request.remote_addr — which ProxyFix normalizes by trusting only
FOMS_TRUSTED_PROXY_HOPS hops — never from the raw, attacker-controlled left-most
X-Forwarded-For entry. These tests exercise the real production key-func via the
live limiter and drive requests through the full WSGI stack so ProxyFix actually
runs.
"""

from __future__ import annotations

from typing import Any

from flask import Flask, request
from werkzeug.middleware.proxy_fix import ProxyFix

from foms.services.rate_limit import init_limiter


def _probe(*, hops: int, headers: dict[str, str]) -> dict[str, Any]:
    """Build a minimal ProxyFix-wrapped app and capture the production key-func
    result and canonical remote_addr for one request carrying ``headers``.

    Args:
        hops: Number of X-Forwarded-For hops ProxyFix should trust (x_for).
        headers: Request headers to inject (e.g. a spoofed X-Forwarded-For).

    Returns:
        Dict with ``key`` (rate-limit bucket key) and ``remote_addr``.
    """
    app = Flask(__name__)
    app.config["TESTING"] = True
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=hops, x_proto=1, x_host=1, x_prefix=1)
    limiter = init_limiter(app)
    captured: dict[str, Any] = {}

    @app.route("/probe")
    def probe() -> str:
        # limiter._key_func is the exact callable Flask-Limiter uses to bucket
        # requests; call it here so we assert on the real production key-func.
        captured["key"] = limiter._key_func()
        captured["remote_addr"] = request.remote_addr
        return "ok"

    app.test_client().get("/probe", headers=headers)
    return captured


def test_spoofed_xff_beyond_trusted_hop_ignored() -> None:
    """A client-forged left-most XFF entry must not reach the key/canonical IP.

    With one trusted hop the edge proxy appends the real client IP on the right;
    the left-most "6.6.6.6" is the client's spoof and must be dropped.
    """
    captured = _probe(hops=1, headers={"X-Forwarded-For": "6.6.6.6, 203.0.113.7"})

    assert captured["remote_addr"] == "203.0.113.7"
    assert captured["key"] == "203.0.113.7"
    assert "6.6.6.6" not in captured["key"]


def test_spoofed_x_real_ip_ignored() -> None:
    """X-Real-IP is equally attacker-controlled and must not become the key.

    Sent without X-Forwarded-For so nothing but the canonical peer address can
    legitimately win; the old key-func consulted X-Real-IP directly and would
    return the forged "6.6.6.6".
    """
    captured = _probe(hops=1, headers={"X-Real-IP": "6.6.6.6"})

    assert captured["key"] != "6.6.6.6"
    assert captured["key"] == captured["remote_addr"]


def test_normal_trusted_hop_resolves_canonical_ip() -> None:
    """A legitimate single-proxy request resolves to the canonical client IP."""
    captured = _probe(hops=1, headers={"X-Forwarded-For": "203.0.113.7"})

    assert captured["remote_addr"] == "203.0.113.7"
    assert captured["key"] == "203.0.113.7"


def test_proxy_fix_respects_trusted_hop_env(monkeypatch: Any) -> None:
    """apply_proxy_fix honors FOMS_TRUSTED_PROXY_HOPS (parameterized x_for)."""
    from foms.platform.app_factory import apply_proxy_fix

    monkeypatch.setenv("FOMS_TRUSTED_PROXY_HOPS", "2")
    app = Flask(__name__)
    apply_proxy_fix(app)
    captured: dict[str, Any] = {}

    @app.route("/probe")
    def probe() -> str:
        captured["remote_addr"] = request.remote_addr
        return "ok"

    # Two trusted hops -> the -2 entry is our edge's view of the client; the
    # left-most "6.6.6.6" remains outside the trusted window.
    app.test_client().get(
        "/probe",
        headers={"X-Forwarded-For": "6.6.6.6, 198.51.100.9, 203.0.113.7"},
    )

    assert captured["remote_addr"] == "198.51.100.9"
    assert captured["remote_addr"] != "6.6.6.6"


def test_trusted_hop_defaults_to_one(monkeypatch: Any) -> None:
    """With no env override, exactly one XFF hop is trusted (prior behavior)."""
    from foms.platform.app_factory import apply_proxy_fix

    monkeypatch.delenv("FOMS_TRUSTED_PROXY_HOPS", raising=False)
    app = Flask(__name__)
    apply_proxy_fix(app)
    captured: dict[str, Any] = {}

    @app.route("/probe")
    def probe() -> str:
        captured["remote_addr"] = request.remote_addr
        return "ok"

    app.test_client().get("/probe", headers={"X-Forwarded-For": "6.6.6.6, 203.0.113.7"})

    assert captured["remote_addr"] == "203.0.113.7"
