"""RUM-INGEST-01: anonymous RUM ingest strict validation + rate + admin report bounds.

Covers:
- Anonymous POST body validation (exact keys, metric/value/path/viewport/bool bounds).
- 2 KiB body cap (enforced by REQUEST-LIMIT-01 telemetry cap → 413).
- Rate limit 120/min per canonical client (remote_addr); untrusted X-Forwarded-For
  entries cannot reset the bucket.
- Redis aggregation error → warning log (no raw payload) + fail-open 200.
- Admin report: 401 unauthenticated, 403 non-admin, days bound 1..35.
"""

import logging
import os

import pytest
from werkzeug.security import generate_password_hash

import foms.services.common.dashboard_cache as dashboard_cache
from db import db_session
from models import User

RUM_URL = "/api/foms/rum"
REPORT_URL = "/api/foms/rum/report"

# Matches the FOMS_RUM_INGEST_RATE_LIMIT default binding ("120 per minute").
_RUM_RATE_LIMIT = 120


def _valid_payload(**overrides):
    body = {
        "metric": "LCP",
        "value": 1234,
        "path": "/erp/orders",
        "viewport": "1920x1080",
        "mobile_v2": False,
    }
    body.update(overrides)
    return body


def _reset_limiter(app):
    """Clear all limiter buckets so rate tests do not leak state across tests."""
    for lim in app.extensions.get("limiter", set()):
        try:
            lim.reset()
        except Exception:  # test-only cleanup; storage may not support reset
            pass


def _trusted_hops():
    raw = os.environ.get("FOMS_TRUSTED_PROXY_HOPS", "1") or "1"
    try:
        return max(1, int(raw))
    except ValueError:
        return 1


@pytest.fixture
def rum_client(app):
    """Fresh anonymous client with limiter reset before and after (isolation)."""
    _reset_limiter(app)
    client = app.test_client()
    yield client
    _reset_limiter(app)


# --------------------------------------------------------------------------- #
# Ingest input validation
# --------------------------------------------------------------------------- #

def test_valid_payload_accepted(rum_client):
    resp = rum_client.post(RUM_URL, json=_valid_payload())
    assert resp.status_code == 200
    assert resp.get_json()["success"] is True


@pytest.mark.parametrize(
    "payload",
    [
        _valid_payload(metric="XXX"),          # unknown metric
        _valid_payload(metric="lcp"),          # wrong case
        _valid_payload(metric=123),            # non-string metric
        _valid_payload(value="fast"),          # non-numeric value
        _valid_payload(value=True),            # bool is not a metric value
        _valid_payload(value=-1),              # negative
        _valid_payload(value=120001),          # over 120000
        _valid_payload(path="/x?y=1"),         # query not allowed
        _valid_payload(path="/x#frag"),        # fragment not allowed
        _valid_payload(path="http://evil/x"),  # absolute URL
        _valid_payload(path="//evil/x"),       # protocol-relative
        _valid_payload(path="relative"),       # not root-relative
        _valid_payload(path="/" + "a" * 500),  # over 500 chars
        _valid_payload(viewport="1920"),       # missing H
        _valid_payload(viewport="0x1080"),     # W < 1
        _valid_payload(viewport="10001x100"),  # W > 10000
        _valid_payload(viewport="axb"),        # non-numeric dims
        _valid_payload(mobile_v2="yes"),       # non-bool
        {**_valid_payload(), "extra": 1},      # key outside schema
    ],
)
def test_invalid_payload_rejected(rum_client, payload):
    resp = rum_client.post(RUM_URL, json=payload)
    assert resp.status_code == 400, f"expected 400 for {payload!r}, got {resp.status_code}"
    assert resp.get_json()["success"] is False


def test_value_nan_rejected(rum_client):
    # json.dumps emits bare NaN by default; the endpoint must reject non-finite.
    resp = rum_client.post(
        RUM_URL,
        data='{"metric": "LCP", "value": NaN}',
        content_type="application/json",
    )
    assert resp.status_code == 400


def test_oversized_body_rejected_by_2kib_cap(rum_client):
    # REQUEST-LIMIT-01 telemetry cap = 2 KiB → declared oversized body trips 413
    # pre-handler (before validation / rate limit).
    big = '{"metric": "LCP", "value": 1, "path": "/' + "a" * 3000 + '"}'
    assert len(big) > 2048
    resp = rum_client.post(RUM_URL, data=big, content_type="application/json")
    assert resp.status_code == 413


# --------------------------------------------------------------------------- #
# Redis aggregation error → warning (no raw payload) + fail-open
# --------------------------------------------------------------------------- #

class _FailingPipe:
    def hincrby(self, *a, **k):
        return self

    def expire(self, *a, **k):
        return self

    def execute(self):
        raise RuntimeError("redis pipeline down")


class _FailingRedis:
    def pipeline(self):
        return _FailingPipe()


def test_redis_error_failopen_no_raw_payload(rum_client, monkeypatch, caplog):
    monkeypatch.setattr(dashboard_cache, "get_dashboard_redis", lambda: _FailingRedis())
    payload = _valid_payload(path="/secret/customer/path", value=99999)
    with caplog.at_level(logging.WARNING):
        resp = rum_client.post(RUM_URL, json=payload)

    # Aggregation failure must NOT surface as a 500 (fail-open).
    assert resp.status_code == 200

    warnings = [r for r in caplog.records if r.levelno >= logging.WARNING]
    # The Redis error is logged (not silently swallowed)...
    assert any("aggregate skip" in r.getMessage() for r in warnings)
    # ...but the raw payload / PII must not appear in any warning log line.
    for r in warnings:
        msg = r.getMessage()
        assert "/secret/customer/path" not in msg
        assert "99999" not in msg


# --------------------------------------------------------------------------- #
# Rate limit: canonical client, untrusted XFF cannot bypass
# --------------------------------------------------------------------------- #

def test_rate_limit_429_after_exceeding_limit(rum_client):
    hit_429 = False
    for _ in range(_RUM_RATE_LIMIT + 5):
        resp = rum_client.post(RUM_URL, json=_valid_payload())
        if resp.status_code == 429:
            hit_429 = True
            break
        assert resp.status_code == 200
    assert hit_429, "expected 429 after exceeding the per-minute limit"


def test_untrusted_xff_cannot_bypass_rate_limit(rum_client):
    # Exhaust the bucket for the canonical client (remote_addr 127.0.0.1, no XFF).
    for _ in range(_RUM_RATE_LIMIT + 5):
        rum_client.post(RUM_URL, json=_valid_payload())

    # A spoofed *leftmost* (untrusted) XFF entry must NOT create a fresh bucket:
    # ProxyFix keeps remote_addr = the trusted hop (127.0.0.1). Pad the trusted
    # client for each configured hop so the test holds regardless of hop count.
    hops = _trusted_hops()
    xff = ", ".join(["203.0.113.9"] + ["127.0.0.1"] * hops)
    resp = rum_client.post(
        RUM_URL, json=_valid_payload(), headers={"X-Forwarded-For": xff}
    )
    assert resp.status_code == 429


# --------------------------------------------------------------------------- #
# Admin report: auth + days bound
# --------------------------------------------------------------------------- #

class _EmptyReportRedis:
    def hgetall(self, key):
        return {}


def test_report_unauthenticated_401(rum_client):
    resp = rum_client.get(REPORT_URL, query_string={"days": 7})
    assert resp.status_code == 401


def test_report_non_admin_403(app):
    existing = db_session.query(User).filter_by(username="rum_viewer").first()
    if not existing:
        db_session.add(
            User(
                username="rum_viewer",
                password=generate_password_hash("pw"),
                role="MEASURE",  # any non-ADMIN role
                name="Viewer",
            )
        )
        db_session.commit()
    client = app.test_client()
    client.post("/login", data={"username": "rum_viewer", "password": "pw"}, follow_redirects=True)

    resp = client.get(REPORT_URL, query_string={"days": 7})
    assert resp.status_code == 403


def test_report_days_over_35_rejected(auth_client):
    resp = auth_client.get(REPORT_URL, query_string={"days": 36})
    assert resp.status_code == 400


def test_report_days_below_1_rejected(auth_client):
    resp = auth_client.get(REPORT_URL, query_string={"days": 0})
    assert resp.status_code == 400


def test_report_valid_days_ok(auth_client, monkeypatch):
    monkeypatch.setattr(dashboard_cache, "get_dashboard_redis", lambda: _EmptyReportRedis())
    resp = auth_client.get(REPORT_URL, query_string={"days": 35})
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["success"] is True
    assert body["data"]["days"] >= 35
