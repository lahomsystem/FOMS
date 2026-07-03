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
    # Empty list is valid after perf debt paydown; guard only blocks net-new findings.
    assert all(isinstance(fid, str) and fid for fid in data["finding_ids"])


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


# --- 2026-07-03 초정밀 감사 이식 규칙 4종 -----------------------------------


def _rules(findings) -> set[str]:
    return {f.rule for f in findings}


# ① fragment-multi-script -----------------------------------------------------


def test_fragment_multi_script_flags_two_or_more_srcs():
    mod = _load_module()
    findings = []
    text = (
        '<script src="{{ url_for(\'static\', filename=\'a.js\') }}" defer></script>\n'
        '<script src="{{ url_for(\'static\', filename=\'b.js\') }}" defer></script>\n'
    )
    mod._scan_fragment_multi_script(
        "templates/shipment/partials/dashboard_scripts.html", text, findings, guard_mode=False
    )
    assert "fragment-multi-script" in _rules(findings)
    assert findings[0].severity == "high"
    assert findings[0].dimension == "interaction-debt"


def test_fragment_multi_script_ignores_single_src():
    mod = _load_module()
    findings = []
    text = '<script src="a.js" defer></script>\n<div>markup</div>\n'
    mod._scan_fragment_multi_script(
        "templates/orders/partials/dashboard_scripts.html", text, findings, guard_mode=False
    )
    assert findings == []


def test_fragment_multi_script_excludes_layout_delivery_file():
    mod = _load_module()
    findings = []
    text = '<script src="a.js" defer></script>\n<script src="b.js" defer></script>\n'
    mod._scan_fragment_multi_script(
        "templates/partials/shared/layout_scripts.html", text, findings, guard_mode=False
    )
    assert findings == []


def test_is_fragment_scripts_partial_matcher():
    mod = _load_module()
    assert mod._is_fragment_scripts_partial("templates/shipment/partials/dashboard_scripts.html")
    assert not mod._is_fragment_scripts_partial("templates/shipment/partials/dashboard.html")
    assert not mod._is_fragment_scripts_partial("static/js/foo_scripts.html")


# ② broad-cache-invalidation --------------------------------------------------


def test_broad_cache_invalidation_flags_non_allowlisted_file():
    mod = _load_module()
    findings = []
    lines = [(10, "        invalidate_all_dashboard_slice_caches()")]
    mod._scan_broad_cache_invalidation("foms/api/some_new_mutation.py", lines, findings, guard_mode=False)
    assert "broad-cache-invalidation" in _rules(findings)
    assert findings[0].dimension == "hot-compute"


def test_broad_cache_invalidation_skips_allowlist_and_perf_ok():
    mod = _load_module()
    findings = []
    lines = [(10, "        invalidate_all_dashboard_slice_caches()")]
    # allowlisted Tier A intent file
    mod._scan_broad_cache_invalidation("foms/api/quest.py", lines, findings, guard_mode=False)
    # definition file
    mod._scan_broad_cache_invalidation(
        "foms/services/common/dashboard_cache.py", lines, findings, guard_mode=False
    )
    # tests
    mod._scan_broad_cache_invalidation("tests/perf/x.py", lines, findings, guard_mode=False)
    # perf-ok escape on a non-allowlisted file
    mod._scan_broad_cache_invalidation(
        "foms/api/other.py",
        [(1, "    invalidate_all_dashboard_slice_caches()  # perf-ok")],
        findings,
        guard_mode=False,
    )
    assert findings == []


def test_broad_cache_invalidation_is_hot_high_in_guard():
    mod = _load_module()
    # guard severity promotion: broad-cache-invalidation on hot path -> high
    assert mod._guard_severity("broad-cache-invalidation", "medium", "foms/api/new.py") == "high"


# ③ jsonb-path-filter ---------------------------------------------------------


def test_jsonb_path_filter_flags_cast_filter():
    mod = _load_module()
    findings = []
    lines = [(5, '    stage_col = cast(Order.structured_data["workflow"]["stage"], String)')]
    mod._scan_jsonb_path_filter("foms/web/construction/dashboard.py", lines, findings, guard_mode=False)
    assert "jsonb-path-filter" in _rules(findings)
    assert findings[0].dimension == "query-scale"


def test_jsonb_path_filter_skips_ilike_perf_ok_and_docstring():
    mod = _load_module()
    findings = []
    # ilike is owned by jsonb-text-ilike rule
    mod._scan_jsonb_path_filter(
        "foms/x.py",
        [(1, '    q.filter(Order.structured_data["a"].astext.ilike("%x%"))')],
        findings,
        guard_mode=False,
    )
    # perf-ok escape
    mod._scan_jsonb_path_filter(
        "foms/x.py",
        [(2, '    q.filter(cast(Order.structured_data["a"], String))  # perf-ok')],
        findings,
        guard_mode=False,
    )
    # backtick docstring reference (not executable code)
    mod._scan_jsonb_path_filter(
        "foms/x.py",
        [(3, "    JSONB path cast(``structured_data['workflow']['stage']``, 인덱스 없음)를 제거")],
        findings,
        guard_mode=False,
    )
    # access without a query call on the same line
    mod._scan_jsonb_path_filter(
        "foms/x.py", [(4, '    val = order.structured_data["workflow"]')], findings, guard_mode=False
    )
    assert findings == []


# ④ mobile-queue-row-no-batch -------------------------------------------------


def test_mobile_queue_row_no_batch_flags_call_without_batch_ctx():
    mod = _load_module()
    findings = []
    lines = [(56, "        row = build_mobile_queue_order_row(db, order, user)")]
    mod._scan_mobile_queue_row_no_batch("foms/api/fragment.py", lines, findings, guard_mode=False)
    assert "mobile-queue-row-no-batch" in _rules(findings)
    assert findings[0].dimension == "query-scale"


def test_mobile_queue_row_no_batch_skips_batch_ctx_def_and_perf_ok():
    mod = _load_module()
    findings = []
    # call passes batch_ctx
    mod._scan_mobile_queue_row_no_batch(
        "foms/x.py",
        [(1, "        row = build_mobile_queue_order_row(db, order, user, batch_ctx=ctx)")],
        findings,
        guard_mode=False,
    )
    # the definition itself
    mod._scan_mobile_queue_row_no_batch(
        "foms/x.py",
        [(2, "def build_mobile_queue_order_row(db, order, current_user=None, *, batch_ctx=None):")],
        findings,
        guard_mode=False,
    )
    # perf-ok escape
    mod._scan_mobile_queue_row_no_batch(
        "foms/x.py",
        [(3, "        build_mobile_queue_order_row(db, o, u)  # perf-ok")],
        findings,
        guard_mode=False,
    )
    assert findings == []


def test_baseline_debt_contains_seeded_new_rule_debt():
    baseline = ROOT / "tools" / "perf" / "baseline_debt.json"
    data = json.loads(baseline.read_text(encoding="utf-8"))
    fids = data["finding_ids"]
    new_rules = {"fragment-multi-script", "broad-cache-invalidation", "jsonb-path-filter", "mobile-queue-row-no-batch"}
    seeded_rules = {fid.split("|", 1)[0] for fid in fids}
    # at least one new-rule finding got baselined so guard vetoes only net-new debt
    assert seeded_rules & new_rules
