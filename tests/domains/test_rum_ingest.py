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


def _spy_limiter_charges(app, monkeypatch):
    """limiter 저장소에 보내는 hit/test 호출을 (한도 문자열, 범위) 로 모은다."""
    charges: list[tuple[str, str]] = []
    for lim in app.extensions.get("limiter", set()):
        inner = lim.limiter
        for name in ("hit", "test"):
            original = getattr(inner, name)

            def _spy(item, *identifiers, _orig=original, **kwargs):
                charges.append((str(item), identifiers[-1] if identifiers else ""))
                return _orig(item, *identifiers, **kwargs)

            monkeypatch.setattr(inner, name, _spy)
    return charges


def test_rum_charges_only_its_own_limit_not_default_limits(app, rum_client, monkeypatch):
    """P3-3: RUM 은 전용 한도 버킷 하나만 깎는다(요청당 저장소 1회) — 기본 한도와 섞이지 않는다.

    대조군: 기본 한도가 걸리는 다른 라우트(GET /login)는 기본 한도 두 개를 깎는다 — 스파이가
    기본 한도를 실제로 잡는다는 증거다. 이 대조가 없으면 "RUM 이 기본 한도를 안 깎는다"는
    스파이가 아무것도 못 잡아서 통과하는 것과 구별되지 않는다.
    """
    charges = _spy_limiter_charges(app, monkeypatch)
    default_limits = {
        value.strip()
        for value in os.environ.get("FLASK_DEFAULT_RATE_LIMITS", "5000 per day,1200 per hour").split(",")
        if value.strip()
    }

    assert rum_client.post(RUM_URL, json=_valid_payload()).status_code == 200
    assert charges == [(f"{_RUM_RATE_LIMIT} per 1 minute", "foms_rum.ingest_rum_event")]

    charges.clear()
    assert rum_client.get("/login").status_code == 200
    charged = {limit for limit, _scope in charges}
    assert len(charges) == len(default_limits) >= 1
    assert f"{_RUM_RATE_LIMIT} per 1 minute" not in charged


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


# --------------------------------------------------------------------------- #
# 느린 LOAD 분해(nav·slow) — docs/specs/2026-10-21-rum-slow-load-breakdown_SPEC.md
# --------------------------------------------------------------------------- #

def _nav(**overrides):
    nav = {"dns": 0, "conn": 120, "ttfb": 310, "resp": 40, "dcl": 900, "redir": 0}
    nav.update(overrides)
    return nav


def _slow_item(**overrides):
    item = {"h": "cdn.jsdelivr.net", "p": ".css", "d": 4800, "s": 120, "c": 0, "k": "link"}
    item.update(overrides)
    return item


def _slow_load(**overrides):
    body = _valid_payload(metric="LOAD", value=5200, nav=_nav(),
                          slow=[_slow_item(), _slow_item(h="lahom-production.up.railway.app",
                                                         p="/static/js/foms/erp-shell.js", c=1, k="script")])
    body.update(overrides)
    return body


def test_slow_load_breakdown_accepted_and_logged(rum_client, caplog):
    with caplog.at_level(logging.INFO, logger="foms.rum"):
        resp = rum_client.post(RUM_URL, json=_slow_load())
    assert resp.status_code == 200
    lines = [r.getMessage() for r in caplog.records if r.name == "foms.rum"]
    assert lines and '"nav": {"conn": 120' in lines[-1]
    assert '"slow": [{"h": "cdn.jsdelivr.net"' in lines[-1]
    assert "/static/js/foms/erp-shell.js" in lines[-1]


def test_plain_payload_still_accepted_without_breakdown(rum_client, caplog):
    """음성 대조군: 지금 5키 페이로드는 그대로 통과하고 로그에 분해가 없다."""
    with caplog.at_level(logging.INFO, logger="foms.rum"):
        resp = rum_client.post(RUM_URL, json=_valid_payload(metric="LOAD", value=900))
    assert resp.status_code == 200
    lines = [r.getMessage() for r in caplog.records if r.name == "foms.rum"]
    assert lines and '"nav"' not in lines[-1] and '"slow"' not in lines[-1]


@pytest.mark.parametrize(
    "payload",
    [
        _slow_load(metric="LCP"),                                     # 분해는 LOAD 만
        _slow_load(nav=_nav(extra=1)),                                # nav 키 초과
        _slow_load(nav={"dns": 1}),                                   # nav 키 부족
        _slow_load(nav=_nav(ttfb=-1)),                                # 음수
        _slow_load(nav=_nav(ttfb=120001)),                            # 범위 밖
        _slow_load(nav=_nav(ttfb=1.5)),                               # 정수만
        _slow_load(nav=_nav(ttfb=True)),                              # bool 거부
        _slow_load(slow=[_slow_item()] * 4),                          # 4개
        _slow_load(slow={"h": "x"}),                                  # 리스트 아님
        _slow_load(slow=[_slow_item(h="evil.com/x")]),                # 호스트에 경로
        _slow_load(slow=[_slow_item(h="")]),                          # 빈 호스트
        _slow_load(slow=[_slow_item(p="/static/a.js?v=1")]),          # 쿼리
        _slow_load(slow=[_slow_item(p="/api/files/5728/photo.jpg")]),  # /static/ 밖 경로(사진 주소)
        _slow_load(slow=[_slow_item(p=".toolongext1")]),              # 확장자 9자
        _slow_load(slow=[_slow_item(c=2)]),                           # 캐시 표시 0/1
        _slow_load(slow=[_slow_item(c=True)]),                        # bool 거부
        _slow_load(slow=[_slow_item(k="Script")]),                    # 대문자
        _slow_load(slow=[{**_slow_item(), "url": "x"}]),              # 항목 키 초과
    ],
)
def test_slow_load_breakdown_rejected(rum_client, payload):
    resp = rum_client.post(RUM_URL, json=payload)
    assert resp.status_code == 400, f"expected 400 for {payload!r}, got {resp.status_code}"


def test_slow_load_max_payload_fits_2kib_cap(rum_client):
    """가장 긴 정상 분해(3개 · /static/ 200자 · 긴 호스트)도 2 KiB 한도 안이다."""
    import json as _json
    long_path = "/static/" + "a" * 189 + ".js"
    item = _slow_item(h="a" * 60 + ".example.com", p=long_path, d=120000, s=120000, k="xmlhttpr")
    body = _slow_load(path="/" + "p" * 120, viewport="10000x10000", slow=[item] * 3,
                      nav=_nav(**{k: 120000 for k in ("dns", "conn", "ttfb", "resp", "dcl", "redir")}))
    assert len(_json.dumps(body)) < 2048
    assert rum_client.post(RUM_URL, json=body).status_code == 200
