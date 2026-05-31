"""P0-01 KPI RUM baseline ingest API."""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_rum_baseline_script_exists() -> None:
    js = (ROOT / "static/js/foms/rum-baseline.js").read_text(encoding="utf-8")
    assert "/api/foms/rum" in js
    assert "sendBeacon" in js
    assert "LCP" in js


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
