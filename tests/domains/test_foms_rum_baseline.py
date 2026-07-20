"""P0-01 KPI RUM baseline ingest API."""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_rum_baseline_script_exists() -> None:
    js = (ROOT / "static/js/foms/rum-baseline.js").read_text(encoding="utf-8")
    assert "/api/foms/rum" in js
    assert "sendBeacon" in js
    assert "LCP" in js
    # LOAD: load 핸들러 안 loadEventEnd=0 레이스 회피(setTimeout 0 후 재측정).
    assert "metric: 'LOAD'" in js or 'metric: "LOAD"' in js
    assert "setTimeout" in js
    assert "loadEventEnd" in js


def test_layout_includes_rum_when_flag_on() -> None:
    scripts = (ROOT / "templates/partials/shared/layout_scripts.html").read_text(
        encoding="utf-8"
    )
    ctx = (ROOT / "foms/services/context_processors.py").read_text(encoding="utf-8")
    assert "rum-baseline.js" in scripts
    assert "flag_rum_baseline" in scripts
    assert "FOMS_RUM_BASELINE_ENABLED" in ctx


def test_rum_ingest_endpoint(client) -> None:
    response = client.post(
        "/api/foms/rum",
        json={"metric": "LCP", "value": 1234, "path": "/erp/dashboard"},
    )
    assert response.status_code == 200
    data = response.get_json()
    assert data["success"] is True


def test_rum_report_requires_login(client) -> None:
    """비로그인 → login_required 리다이렉트(302)."""
    resp = client.get("/api/foms/rum/report", follow_redirects=False)
    assert resp.status_code in (301, 302)


def test_rum_report_non_admin_forbidden(login) -> None:
    """로그인했으나 role != ADMIN(login 픽스처 role='admin') → 403."""
    resp = login.get("/api/foms/rum/report")
    assert resp.status_code == 403
    assert resp.get_json()["success"] is False


def test_rum_report_admin_reaches_redis_check(auth_client) -> None:
    """ADMIN 로그인 → 권한 통과 후 Redis 부재(테스트) → 503(집계 조회 불가)."""
    resp = auth_client.get("/api/foms/rum/report")
    assert resp.status_code == 503
    body = resp.get_json()
    assert body["success"] is False
    assert body["error"] == "redis_unavailable"
