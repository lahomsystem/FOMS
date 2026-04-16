"""Behavioral tests for Wave 3 level routing in `run_codex.ps1`."""

from __future__ import annotations

import locale
import os
import shutil
import stat
import subprocess
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "tools" / "harness" / "run_codex.ps1"
QA_SCRIPT_PATH = REPO_ROOT / "tools" / "harness" / "run_gstack_qa.ps1"


def _powershell_executable() -> str:
    for candidate in ("powershell", "pwsh"):
        resolved = shutil.which(candidate)
        if resolved:
            return resolved
    if os.environ.get("CI") or os.environ.get("GITHUB_ACTIONS"):
        pytest.fail("No PowerShell executable available for wrapper tests in CI.")
    pytest.skip("No PowerShell executable available for wrapper tests.")


def _run_powershell_file(
    script_path: Path,
    *args: str,
    expect_success: bool = True,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(
        [_powershell_executable(), "-NoProfile", "-File", str(script_path), *args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=False,
        timeout=60,
        env=env or os.environ.copy(),
    )
    decoded = subprocess.CompletedProcess(
        args=completed.args,
        returncode=completed.returncode,
        stdout=_decode_powershell_output(completed.stdout),
        stderr=_decode_powershell_output(completed.stderr),
    )
    if expect_success:
        assert decoded.returncode == 0, decoded.stderr or decoded.stdout
    return decoded


def _decode_powershell_output(payload: bytes | None) -> str:
    if not payload:
        return ""

    encodings = ["utf-8"]
    preferred = locale.getpreferredencoding(False)
    if preferred and preferred.lower() not in {"utf-8", "utf8"}:
        encodings.append(preferred)

    for encoding in encodings:
        try:
            return payload.decode(encoding)
        except UnicodeDecodeError:
            continue

    return payload.decode(encodings[-1], errors="replace")


def _run_codex_wrapper(*args: str, expect_success: bool = True) -> subprocess.CompletedProcess[str]:
    return _run_powershell_file(SCRIPT_PATH, *args, expect_success=expect_success)


def _make_fake_codex(tmp_path: Path, exit_code: int) -> Path:
    if os.name == "nt":
        fake_codex = tmp_path / "codex.cmd"
        fake_codex.write_text(f"@echo off\r\nexit /b {exit_code}\r\n", encoding="utf-8")
        return fake_codex

    fake_codex = tmp_path / "codex"
    fake_codex.write_text(f"#!/bin/sh\nexit {exit_code}\n", encoding="utf-8")
    fake_codex.chmod(fake_codex.stat().st_mode | stat.S_IEXEC)
    return fake_codex


def test_daily_doc_review_stays_daily_and_low() -> None:
    completed = _run_codex_wrapper(
        "-Profile",
        "review",
        "-Target",
        "docs/AI_STATUS.md",
        "-DryRun",
    )
    assert "Context   : daily" in completed.stdout
    assert "Level     : low (" in completed.stdout
    assert "AutoLevel : low (" in completed.stdout


def test_harness_file_review_promotes_to_high_and_harness() -> None:
    completed = _run_codex_wrapper(
        "-Profile",
        "review",
        "-Target",
        "tools/harness/build_context_bundle.py",
        "-DryRun",
    )
    assert "Context   : harness" in completed.stdout
    assert "Level     : high (" in completed.stdout
    assert "harness core path" in completed.stdout


def test_db_core_file_review_promotes_to_high_and_harness() -> None:
    completed = _run_codex_wrapper(
        "-Profile",
        "review",
        "-Target",
        "db.py",
        "-DryRun",
    )
    assert "Context   : harness" in completed.stdout
    assert "Level     : high (" in completed.stdout
    assert "db/api/auth core path" in completed.stdout


def test_fixed_tag_override_promotes_to_top() -> None:
    completed = _run_codex_wrapper(
        "-Profile",
        "review",
        "-Target",
        "docs/AI_STATUS.md",
        "-AdditionalPrompt",
        "[\ub808\ubca8=\ucd5c\uc0c1]",
        "-DryRun",
    )
    assert "Context   : harness" in completed.stdout
    assert "Level     : top (" in completed.stdout
    assert "Override  : top via fixed tag" in completed.stdout


def test_natural_language_override_is_parsed() -> None:
    completed = _run_codex_wrapper(
        "-Profile",
        "review",
        "-Target",
        "docs/AI_STATUS.md",
        "-AdditionalPrompt",
        "\uc774\ubc88 \uac74 \ucd5c\uc0c1\uc73c\ub85c \uc9c4\ud589",
        "-DryRun",
    )
    assert "Level     : top (" in completed.stdout
    assert "Override  : top via natural language" in completed.stdout


def test_harness_plan_implement_promotes_to_top() -> None:
    completed = _run_codex_wrapper(
        "-Profile",
        "implement",
        "-Plan",
        "docs/specs/2026-04-05-harness-wave3-auto-level-routing_SPEC.md",
        "-DryRun",
    )
    assert "Context   : harness" in completed.stdout
    assert "Level     : top (" in completed.stdout


def test_risky_downgrade_requires_explicit_noninteractive_ack() -> None:
    completed = _run_codex_wrapper(
        "-Profile",
        "review",
        "-Target",
        "tools/harness/build_context_bundle.py",
        "-AdditionalPrompt",
        "[level=low]",
        "-NonInteractive",
        expect_success=False,
    )
    assert completed.returncode != 0
    combined = f"{completed.stdout}\n{completed.stderr}"
    assert "AllowRiskyLevelOverride" in combined


def test_risky_downgrade_can_be_forced_in_noninteractive_mode() -> None:
    completed = _run_codex_wrapper(
        "-Profile",
        "review",
        "-Target",
        "tools/harness/build_context_bundle.py",
        "-AdditionalPrompt",
        "[level=low]",
        "-NonInteractive",
        "-AllowRiskyLevelOverride",
        "-DryRun",
    )
    assert "Context   : daily" in completed.stdout
    assert "Level     : low (" in completed.stdout


def test_run_gstack_qa_default_dry_run_does_not_force_bundle_override() -> None:
    completed = _run_powershell_file(
        QA_SCRIPT_PATH,
        "-Url",
        "https://example.com",
        "-Scenario",
        "erp-smoke",
        "-DryRun",
    )
    assert "level policy : daily bundle by default" in completed.stdout
    assert "-Profile qa -Url https://example.com -Scenario erp-smoke" in completed.stdout
    assert "-BundlePath" not in completed.stdout


def test_run_codex_wrapper_propagates_native_exit_code(tmp_path: Path) -> None:
    _make_fake_codex(tmp_path, exit_code=7)
    env = os.environ.copy()
    env["PATH"] = f"{tmp_path}{os.pathsep}{env['PATH']}"

    completed = _run_powershell_file(
        SCRIPT_PATH,
        "-Profile",
        "review",
        "-Target",
        "docs/AI_STATUS.md",
        expect_success=False,
        env=env,
    )
    assert completed.returncode == 7


def test_run_gstack_qa_wrapper_propagates_child_exit_code(tmp_path: Path) -> None:
    _make_fake_codex(tmp_path, exit_code=9)
    env = os.environ.copy()
    env["PATH"] = f"{tmp_path}{os.pathsep}{env['PATH']}"

    completed = _run_powershell_file(
        QA_SCRIPT_PATH,
        "-Url",
        "https://example.com",
        "-Scenario",
        "erp-smoke",
        expect_success=False,
        env=env,
    )
    assert completed.returncode == 9
