"""RELEASE-GATE-00: release-gate verifier contract tests.

Proves the read-only readiness verifier's exit-code contract (0 ready · 1 data ·
2 service · 3 artifact/config), the multi-domain precedence, that a defect in
each domain turns the gate RED, that a healthy tree is GREEN, that output is
value-free (booleans/counts/fixed tokens only), and that the verifier performs
no application mutation (no DB write calls in its source; worker path is
SELECT-only via already-tested collectors).
"""

from __future__ import annotations

import importlib.util
import json
import re
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]


def _load_gate():
    """Import the CLI module by path (tools/ops has no package __init__)."""
    ops = str(REPO_ROOT / "tools" / "ops")
    if ops not in sys.path:
        sys.path.insert(0, ops)
    path = REPO_ROOT / "tools" / "ops" / "check_foms_remediation_readiness.py"
    spec = importlib.util.spec_from_file_location("check_foms_remediation_readiness_ut", path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


gate = _load_gate()


def _healthy_worker_probe():
    return [gate.WorkerReadiness("sidefx", True, 0), gate.WorkerReadiness("channel", True, 0)]


# --- exit-code contract + precedence -----------------------------------------
def _ok(domain):
    return gate.CheckResult("x", domain, True, 0)


def _bad(domain):
    return gate.CheckResult("x", domain, False, 1)


def test_exit_ready_when_all_ok():
    assert gate.exit_code_for([_ok(gate.DOMAIN_CONFIG), _ok(gate.DOMAIN_DATA), _ok(gate.DOMAIN_SERVICE)]) == 0


def test_exit_data_fault():
    assert gate.exit_code_for([_ok(gate.DOMAIN_CONFIG), _bad(gate.DOMAIN_DATA)]) == 1


def test_exit_service_fault():
    assert gate.exit_code_for([_ok(gate.DOMAIN_DATA), _bad(gate.DOMAIN_SERVICE)]) == 2


def test_exit_config_fault():
    assert gate.exit_code_for([_bad(gate.DOMAIN_CONFIG), _ok(gate.DOMAIN_DATA)]) == 3


def test_exit_precedence_config_over_service_over_data():
    # config(3) wins over everything.
    assert gate.exit_code_for([_bad(gate.DOMAIN_DATA), _bad(gate.DOMAIN_SERVICE), _bad(gate.DOMAIN_CONFIG)]) == 3
    # service(2) wins over data(1).
    assert gate.exit_code_for([_bad(gate.DOMAIN_DATA), _bad(gate.DOMAIN_SERVICE)]) == 2


# --- packet coverage (artifact/config) ---------------------------------------
def test_packet_coverage_real_tree_ok():
    result = gate.check_packet_coverage(REPO_ROOT)
    assert result.ok and result.domain == gate.DOMAIN_CONFIG and result.count == 0


def test_packet_coverage_missing_created_test_is_red(tmp_path):
    manifest = {"A-00": {"created_tests": [{"path": "tests/does_not_exist.py", "owner_packet": "A-00"}]}}
    (tmp_path / "docs" / "harness").mkdir(parents=True)
    (tmp_path / "docs" / "harness" / "foms_bugfix_packet_tests.json").write_text(
        json.dumps(manifest), encoding="utf-8"
    )
    result = gate.check_packet_coverage(tmp_path, expected=1)
    assert not result.ok and result.domain == gate.DOMAIN_CONFIG and result.count >= 1


def test_packet_coverage_wrong_count_is_red(tmp_path):
    (tmp_path / "docs" / "harness").mkdir(parents=True)
    (tmp_path / "docs" / "harness" / "foms_bugfix_packet_tests.json").write_text("{}", encoding="utf-8")
    result = gate.check_packet_coverage(tmp_path, expected=124)
    assert not result.ok and result.count == 124


# --- CI + persona (artifact/config) ------------------------------------------
def test_ci_coverage_real_tree_ok():
    assert gate.check_ci_coverage(REPO_ROOT).ok


def test_ci_coverage_missing_is_red(tmp_path):
    result = gate.check_ci_coverage(tmp_path)
    assert not result.ok and result.domain == gate.DOMAIN_CONFIG and result.count == len(gate.REQUIRED_WORKFLOWS)


def test_persona_real_tree_ok():
    assert gate.check_persona_artifacts(REPO_ROOT).ok


def test_persona_missing_is_red(tmp_path):
    result = gate.check_persona_artifacts(tmp_path)
    assert not result.ok and result.domain == gate.DOMAIN_CONFIG and result.count == len(gate.REQUIRED_PERSONAS)


# --- enforcement flags (artifact/config) -------------------------------------
def test_flags_default_is_safe():
    result = gate.check_enforcement_flags({})
    assert result.ok and "REV_IF_MATCH_ENFORCED:default" in result.note


def test_flags_boolean_values_ok():
    result = gate.check_enforcement_flags({"REV_IF_MATCH_ENFORCED": "0", "WRITE_GUARD_ENABLED": "1"})
    assert result.ok and "REV_IF_MATCH_ENFORCED:off" in result.note and "WRITE_GUARD_ENABLED:on" in result.note


def test_flags_malformed_is_red_and_does_not_echo_value():
    secret = "s3cr3t-not-a-bool"
    result = gate.check_enforcement_flags({"REV_IF_MATCH_ENFORCED": secret})
    assert not result.ok and result.domain == gate.DOMAIN_CONFIG and result.count == 1
    assert secret not in result.note and "malformed" in result.note  # value never echoed


# --- API leak + broad catch (artifact/config) --------------------------------
def _tmp_repo_with_leak(tmp_path, *, leak_lines, baseline):
    foms = tmp_path / "foms"
    foms.mkdir()
    body = "\n".join(f'    return jsonify({{"m": str(e)}}), 500  # {i}' for i in range(leak_lines))
    (foms / "leaky.py").write_text(f"def h(e):\n{body}\n" if leak_lines else "x = 1\n", encoding="utf-8")
    inv_dir = tmp_path / "docs" / "harness"
    inv_dir.mkdir(parents=True)
    (inv_dir / "foms_api_error_leak_inventory.json").write_text(
        json.dumps({"baselines": {"response_str_e_500": baseline}}), encoding="utf-8"
    )
    return tmp_path


def test_api_leak_real_tree_ok():
    assert gate.check_api_leak(REPO_ROOT).ok


def test_api_leak_growth_is_red(tmp_path):
    repo = _tmp_repo_with_leak(tmp_path, leak_lines=3, baseline=1)
    result = gate.check_api_leak(repo)
    assert not result.ok and result.domain == gate.DOMAIN_CONFIG and result.count == 2  # 3 - baseline 1


def test_api_leak_within_baseline_ok(tmp_path):
    repo = _tmp_repo_with_leak(tmp_path, leak_lines=2, baseline=2)
    assert gate.check_api_leak(repo).ok


def test_broad_catch_real_tree_ok():
    assert gate.check_broad_catch(REPO_ROOT, live_unclassified=0).ok


def test_broad_catch_unclassified_is_red():
    result = gate.check_broad_catch(REPO_ROOT, live_unclassified=3)
    assert not result.ok and result.domain == gate.DOMAIN_CONFIG and result.count == 3


# --- data coverage (data) ----------------------------------------------------
def test_data_coverage_real_tree_ok():
    result = gate.check_data_coverage(REPO_ROOT)
    assert result.ok and result.domain == gate.DOMAIN_DATA


def test_data_coverage_missing_is_red(tmp_path):
    result = gate.check_data_coverage(tmp_path)
    assert not result.ok and result.domain == gate.DOMAIN_DATA and result.count == len(gate.REQUIRED_DATA_FILES)


def test_data_coverage_malformed_json_is_red(tmp_path):
    for rel in gate.REQUIRED_DATA_FILES:
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("{ not json", encoding="utf-8")
    result = gate.check_data_coverage(tmp_path)
    assert not result.ok and result.count == len(gate.REQUIRED_DATA_FILES)


# --- workers (service) -------------------------------------------------------
def test_workers_ready_ok():
    assert gate.check_workers(_healthy_worker_probe).ok


def test_workers_not_ready_is_red():
    def probe():
        return [gate.WorkerReadiness("sidefx", True, 0), gate.WorkerReadiness("channel", False, 2)]

    result = gate.check_workers(probe)
    assert not result.ok and result.domain == gate.DOMAIN_SERVICE and result.count == 1


def test_workers_db_error_is_fail_closed():
    def probe():
        raise RuntimeError("DATABASE_URL is not set")

    result = gate.check_workers(probe)
    assert not result.ok and result.domain == gate.DOMAIN_SERVICE and result.note == "probe_unavailable"


def test_workers_no_evidence_is_fail_closed():
    result = gate.check_workers(lambda: [])
    assert not result.ok and result.domain == gate.DOMAIN_SERVICE and result.note == "no_worker_evidence"


# --- holistic red -> green ---------------------------------------------------
def test_healthy_tree_is_green():
    results = gate.collect_results(
        REPO_ROOT,
        env={},
        worker_probe=_healthy_worker_probe,
        live_unclassified=0,
    )
    assert gate.exit_code_for(results) == 0, [(r.name, r.count) for r in results if not r.ok]


def test_injected_fault_turns_gate_red():
    def bad_probe():
        return [gate.WorkerReadiness("sidefx", False, 1)]

    results = gate.collect_results(
        REPO_ROOT, env={}, worker_probe=bad_probe, live_unclassified=0
    )
    assert gate.exit_code_for(results) == 2  # service fault


def test_skip_service_excludes_worker_check():
    results = gate.collect_results(
        REPO_ROOT,
        env={},
        worker_probe=_healthy_worker_probe,
        live_unclassified=0,
        include_service=False,
    )
    assert not any(r.name == "workers" for r in results)


# --- value exposure 0 + mutation 0 -------------------------------------------
def test_output_is_value_free():
    """Rendered/JSON output must carry only names, domains, bools, ints, fixed tokens."""
    results = gate.collect_results(
        REPO_ROOT, env={"REV_IF_MATCH_ENFORCED": "topsecretpassword"},
        worker_probe=_healthy_worker_probe, live_unclassified=0,
    )
    payload = gate.report_payload(results, gate.exit_code_for(results))
    blob = json.dumps(payload, ensure_ascii=False) + "\n" + gate.render_text(payload)
    # No raw env value / secret / traceback markers leak into output.
    for forbidden in ("topsecretpassword", "Traceback", "/var/", "SELECT", "password="):
        assert forbidden not in blob, forbidden
    for check in payload["checks"]:
        assert isinstance(check["count"], int) and isinstance(check["ok"], bool)
        assert set(check.keys()) == {"name", "domain", "ok", "count", "note"}


# SQLAlchemy write methods (lowercase, dotted) + uppercase SQL DML/DDL. Case-sensitive
# so list ops like ``sys.path.insert`` (lowercase, no dot-add) are not false positives.
_MUTATION_PATTERNS = re.compile(
    r"\.commit\(|\.add\(|\.add_all\(|\.delete\(|\.flush\(|\.merge\(|\.bulk_save"
    r"|\b(?:INSERT|UPDATE|DELETE|TRUNCATE)\s"
)


def test_verifier_source_has_no_db_mutation_calls():
    """Static proof of application-mutation-0: no write/DDL/DML calls in the verifier source."""
    src = (REPO_ROOT / "tools" / "ops" / "check_foms_remediation_readiness.py").read_text(encoding="utf-8")
    # strip comments/docstrings noise is unnecessary; the tokens simply must not appear as calls.
    hits = [m.group(0) for m in _MUTATION_PATTERNS.finditer(src)]
    assert hits == [], f"unexpected mutation-like calls in verifier: {hits}"


def test_collect_results_without_service_touches_no_db(monkeypatch):
    """File-only run must never import/hit the DB worker path."""
    def explode():
        raise AssertionError("worker probe must not be called when service is skipped")

    results = gate.collect_results(
        REPO_ROOT, env={}, worker_probe=explode, live_unclassified=0, include_service=False
    )
    assert results  # ran the file checks, never called the probe
