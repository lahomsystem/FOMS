"""Unit tests for tools/perf/perf_scan.py (ERP slowdown radar engine)."""
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PERF_SCAN = ROOT / "tools" / "perf" / "perf_scan.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("foms_perf_scan_test", PERF_SCAN)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def test_finding_has_dimension_and_fid():
    mod = _load_module()
    f = mod.Finding("high", "jsonb-text-ilike", "query-scale", "services/x.py", 10, "snip", "fix")
    assert f.dimension == "query-scale"
    assert f.fid == "jsonb-text-ilike|services/x.py|10"


def test_guard_severity_hot_path_promotes_b_layer():
    mod = _load_module()
    assert mod._guard_severity("general-ilike", "medium", "services/dashboard/foo.py") == "high"
    assert mod._guard_severity("general-ilike", "medium", "tests/foo.py") == "medium"
    assert mod._guard_severity("render-blocking-script", "high", "templates/x.html") == "high"


def test_radar_json_has_all_dimensions():
    mod = _load_module()
    findings = [
        mod.Finding("high", "jsonb-text-ilike", "query-scale", "a.py", 1, "", ""),
        mod.Finding("medium", "general-ilike", "query-scale", "b.py", 2, "", ""),
    ]
    radar = mod.build_radar(findings)
    for dim in mod.DIMENSIONS:
        assert dim in radar.dimensions


def test_audit_finds_fragment_replayed_js_in_graph():
    mod = _load_module()
    replayed = mod._collect_fragment_replayed_js_paths()
    assert "js/foms/erp-attachment-preview-open.js" in replayed


def test_baseline_debt_file_exists_and_valid_json():
    baseline = ROOT / "tools" / "perf" / "baseline_debt.json"
    assert baseline.exists()
    data = json.loads(baseline.read_text(encoding="utf-8"))
    assert data.get("version") == 1
    assert isinstance(data.get("finding_ids"), list)
    assert len(data["finding_ids"]) > 0


def test_cli_radar_json_exit_zero():
    proc = subprocess.run(
        [sys.executable, str(ROOT / "tools" / "perf" / "perf_scan.py"), "--radar", "--json"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=180,
    )
    assert proc.returncode == 0
    payload = json.loads(proc.stdout)
    assert "dimensions" in payload
    assert "deploy_risk_summary" in payload
    for dim in (
        "amplifier",
        "render-block",
        "interaction-debt",
        "sw-cache",
        "query-scale",
        "payload",
        "hot-compute",
        "io-bound",
    ):
        assert dim in payload["dimensions"]


def test_cli_guard_exit_zero_on_clean_tree():
    proc = subprocess.run(
        [sys.executable, str(ROOT / "tools" / "perf" / "perf_scan.py"), "--guard"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=30,
    )
    assert proc.returncode == 0
