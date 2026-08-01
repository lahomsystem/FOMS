"""WAM-TELEMETRY-01: bounded scoped telemetry ingest.

Covers:
- Scope (session) token pre-check BEFORE body parse (missing/invalid → 401,
  never 204/422).
- 2 KiB body cap (REQUEST-LIMIT-01 telemetry cap → 413) enforced pre-handler,
  before schema validation.
- Exact canonical keys + existing 7-event enum + per-field bounds
  (strings ≤ 64, counts 0..1000, latency int 0..120000) → 422; valid → 204.
- Rate limit 120/min per token+order and per canonical client (PROXY-01);
  an untrusted left-most X-Forwarded-For entry cannot reset the IP bucket → 429.
- A telemetry recording failure is fail-open (204, never 500) and never logs
  the raw / nested / PII payload.
"""

import logging
import os

import pytest

import foms.api.channel.channel_wam as channel_wam
from foms.services.channel_security import generate_wam_session_token
from foms.services.channel_wam_telemetry import ALLOWED_EVENTS

TELEMETRY_URL = "/channel/wam/api/telemetry"
_RATE_LIMIT = 120
_ORDER_ID = 4242


def _mint_token(app, order_id=_ORDER_ID, manager_id="wam_viewer"):
    """Mint a fresh page-scoped WAM session token (distinct nonce each call)."""
    with app.app_context():
        return generate_wam_session_token(manager_id, order_id)


def _reset_limiter(app):
    """Clear every limiter bucket so rate tests do not leak across the session."""
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


def _valid_body(**overrides):
    body = {
        "event_name": "wam_page_opened",
        "view_key": "order-detail",
        "page_state": "DRAWING",
        "section_count": 5,
        "attachment_count": 3,
        "latency_ms": 120,
        "key": "customer",
    }
    body.update(overrides)
    return body


@pytest.fixture(autouse=True)
def _isolate_limiter(app):
    """Reset limiter state around every test (memory storage is a singleton)."""
    _reset_limiter(app)
    yield
    _reset_limiter(app)


@pytest.fixture
def wam_client(app, monkeypatch):
    """Client carrying a valid page-scoped wam_session cookie (telemetry on)."""
    monkeypatch.setenv("CHANNEL_WAM_TELEMETRY_ENABLED", "true")
    token = _mint_token(app)
    client = app.test_client()
    client.set_cookie("wam_session", token, path="/channel/wam")
    return client


# --------------------------------------------------------------------------- #
# Valid ingest → 204
# --------------------------------------------------------------------------- #

def test_valid_payload_returns_204(wam_client):
    resp = wam_client.post(TELEMETRY_URL, json=_valid_body())
    assert resp.status_code == 204
    assert resp.get_data() == b""


def test_minimal_valid_payload_returns_204(wam_client):
    # event_name is the only required key; the rest are optional canonical keys.
    resp = wam_client.post(TELEMETRY_URL, json={"event_name": "wam_section_opened"})
    assert resp.status_code == 204


@pytest.mark.parametrize("event_name", sorted(ALLOWED_EVENTS))
def test_all_enum_events_accepted(wam_client, event_name):
    resp = wam_client.post(TELEMETRY_URL, json={"event_name": event_name})
    assert resp.status_code == 204


# --------------------------------------------------------------------------- #
# Scope token pre-check (before body parse)
# --------------------------------------------------------------------------- #

def test_missing_scope_token_rejected(app, monkeypatch):
    monkeypatch.setenv("CHANNEL_WAM_TELEMETRY_ENABLED", "true")
    client = app.test_client()  # no wam_session cookie at all
    resp = client.post(TELEMETRY_URL, json=_valid_body())
    assert resp.status_code == 401


def test_invalid_scope_token_rejected(app, monkeypatch):
    monkeypatch.setenv("CHANNEL_WAM_TELEMETRY_ENABLED", "true")
    client = app.test_client()
    client.set_cookie("wam_session", "tampered.invalid.token", path="/channel/wam")
    resp = client.post(TELEMETRY_URL, json=_valid_body())
    assert resp.status_code == 401


# --------------------------------------------------------------------------- #
# Body size cap (REQUEST-LIMIT-01 telemetry 2 KiB → 413), pre-schema
# --------------------------------------------------------------------------- #

def test_oversized_body_returns_413(wam_client):
    # Over the 2 KiB telemetry cap → 413 pre-handler (before validation/rate).
    big = '{"event_name": "wam_page_opened", "key": "' + "a" * 3000 + '"}'
    assert len(big) > 2048
    resp = wam_client.post(TELEMETRY_URL, data=big, content_type="application/json")
    assert resp.status_code == 413


# --------------------------------------------------------------------------- #
# Schema / bounds → 422
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize(
    "body",
    [
        _valid_body(event_name="wam_unknown"),               # not in enum
        _valid_body(event_name="WAM_PAGE_OPENED"),           # wrong case
        _valid_body(event_name=123),                         # non-string event
        {**_valid_body(), "eventName": "wam_page_opened"},   # camelCase alias key
        {**_valid_body(), "pageState": "x"},                 # camelCase alias key
        {**_valid_body(), "section_key": "x"},               # legacy alias key
        {**_valid_body(), "extra": 1},                       # unknown key
        _valid_body(view_key="x" * 65),                      # string > 64
        _valid_body(page_state="x" * 65),                    # string > 64
        _valid_body(key="x" * 65),                           # string > 64
        _valid_body(view_key=5),                             # non-string
        _valid_body(section_count=1001),                     # count > 1000
        _valid_body(section_count=-1),                       # count < 0
        _valid_body(section_count=True),                     # bool is not a count
        _valid_body(section_count="5"),                      # string is not a count
        _valid_body(attachment_count=1001),                  # count > 1000
        _valid_body(latency_ms=120001),                      # latency > 120000
        _valid_body(latency_ms=-1),                          # latency < 0
        _valid_body(latency_ms=1.5),                         # non-int latency
        _valid_body(key={"nested": 1}),                      # nested object not string
    ],
)
def test_invalid_payload_returns_422(wam_client, body):
    resp = wam_client.post(TELEMETRY_URL, json=body)
    assert resp.status_code == 422, f"expected 422 for {body!r}, got {resp.status_code}"


def test_non_object_payload_returns_422(wam_client):
    resp = wam_client.post(TELEMETRY_URL, data="[1,2,3]", content_type="application/json")
    assert resp.status_code == 422


def test_unparseable_body_returns_422(wam_client):
    resp = wam_client.post(TELEMETRY_URL, data="not-json", content_type="application/json")
    assert resp.status_code == 422


# --------------------------------------------------------------------------- #
# Rate limits: token+order and canonical IP (untrusted XFF cannot bypass)
# --------------------------------------------------------------------------- #

def test_rate_limit_token_order_429(wam_client):
    hit_429 = False
    for _ in range(_RATE_LIMIT + 5):
        resp = wam_client.post(TELEMETRY_URL, json=_valid_body())
        if resp.status_code == 429:
            hit_429 = True
            break
        assert resp.status_code == 204
    assert hit_429, "expected 429 after exceeding the per-token-per-minute limit"


def test_untrusted_xff_cannot_bypass_ip_rate_limit(app, monkeypatch):
    monkeypatch.setenv("CHANNEL_WAM_TELEMETRY_ENABLED", "true")
    client = app.test_client()

    # Distinct token per request → the token+order bucket never fills; only the
    # canonical-client (127.0.0.1) IP bucket accumulates.
    for _ in range(_RATE_LIMIT):
        client.set_cookie("wam_session", _mint_token(app), path="/channel/wam")
        resp = client.post(TELEMETRY_URL, json=_valid_body())
        assert resp.status_code == 204

    # A spoofed left-most (untrusted) XFF entry must NOT mint a fresh IP bucket:
    # ProxyFix keeps remote_addr = the trusted hop (127.0.0.1). Pad the trusted
    # client for each configured hop so this holds regardless of hop count.
    hops = _trusted_hops()
    xff = ", ".join(["203.0.113.9"] + ["127.0.0.1"] * hops)
    client.set_cookie("wam_session", _mint_token(app), path="/channel/wam")
    resp = client.post(TELEMETRY_URL, json=_valid_body(), headers={"X-Forwarded-For": xff})
    assert resp.status_code == 429


# --------------------------------------------------------------------------- #
# Fail-open: recording failure never breaks the flow, never logs raw payload
# --------------------------------------------------------------------------- #

def test_recording_failure_is_failopen_no_raw_payload(wam_client, monkeypatch, caplog):
    def _boom(context, record):
        raise RuntimeError("telemetry sink down")

    monkeypatch.setattr(channel_wam, "record_wam_telemetry", _boom)
    body = _valid_body(key="secret-section-xyz", page_state="SECRET_STATE")

    with caplog.at_level(logging.WARNING):
        resp = wam_client.post(TELEMETRY_URL, json=body)

    # Aggregation/log failure must NOT surface as a 500 (fail-open).
    assert resp.status_code == 204

    for record in caplog.records:
        message = record.getMessage()
        assert "secret-section-xyz" not in message
        assert "SECRET_STATE" not in message


def test_success_logs_only_bounded_projection(wam_client, caplog):
    with caplog.at_level(logging.INFO, logger="foms.services.channel_wam_telemetry"):
        resp = wam_client.post(TELEMETRY_URL, json=_valid_body())
    assert resp.status_code == 204
    logs = " ".join(r.getMessage() for r in caplog.records)
    assert "wam_telemetry" in logs
    assert "wam_page_opened" in logs
