"""Tests for tools.harness.verify_result."""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
HARNESS_DIR = REPO_ROOT / "tools" / "harness"
if str(HARNESS_DIR) not in sys.path:
    sys.path.insert(0, str(HARNESS_DIR))

SPEC = importlib.util.spec_from_file_location("verify_result_module", HARNESS_DIR / "verify_result.py")
assert SPEC is not None and SPEC.loader is not None
VERIFY_RESULT_MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(VERIFY_RESULT_MODULE)

extract_verification_items = VERIFY_RESULT_MODULE.extract_verification_items
find_latest_spec = VERIFY_RESULT_MODULE.find_latest_spec
main = VERIFY_RESULT_MODULE.main


def _write_repo_fixture(root: Path) -> None:
    """Create a minimal repo fixture with an importable app module."""
    (root / "docs" / "specs").mkdir(parents=True, exist_ok=True)
    (root / "app.py").write_text("app = object()\n", encoding="utf-8")


def test_extract_verification_items_from_section() -> None:
    """The script should read checklist items only from the verification section."""
    text = """
# Example Spec

## 3. 구현
- not this

## 4. 검증 기준
- [ ] 첫 번째 검증
1. 두 번째 검증

## 5. 후속 작업
- not this either
"""
    assert extract_verification_items(text) == [
        "- [ ] 첫 번째 검증",
        "1. 두 번째 검증",
    ]


def test_find_latest_spec_returns_none_when_missing(tmp_path: Path) -> None:
    """No matching *_SPEC.md file should return None."""
    _write_repo_fixture(tmp_path)
    assert find_latest_spec(tmp_path) is None


def test_find_latest_spec_is_deterministic_without_mtime_ordering(tmp_path: Path) -> None:
    """Latest spec selection should stay deterministic even with equal mtimes."""
    _write_repo_fixture(tmp_path)
    root_spec = tmp_path / "docs" / "specs" / "2026-04-01_ROOT_SPEC.md"
    nested_spec = tmp_path / "docs" / "specs" / "nested" / "2026-04-02_NESTED_SPEC.md"
    nested_spec.parent.mkdir(parents=True, exist_ok=True)
    root_spec.write_text("# Root spec\n", encoding="utf-8")
    nested_spec.write_text("# Nested spec\n", encoding="utf-8")

    same_time = 1_700_000_000
    os.utime(root_spec, (same_time, same_time))
    os.utime(nested_spec, (same_time, same_time))

    assert find_latest_spec(tmp_path) == nested_spec


def test_main_json_reports_success_without_spec(tmp_path: Path, capsys) -> None:
    """Default run should pass APP_OK baseline even when no spec exists."""
    _write_repo_fixture(tmp_path)

    assert main(["--repo-root", str(tmp_path), "--json"]) == 0
    report = json.loads(capsys.readouterr().out)

    assert report["success"] is True
    assert report["app_import"]["ok"] is True
    assert report["spec"]["found"] is False
    assert report["spec"]["verification_items"] == []


def test_main_json_uses_explicit_spec_and_collects_items(tmp_path: Path, capsys) -> None:
    """Explicit spec path should surface parsed verification items."""
    _write_repo_fixture(tmp_path)
    spec_path = tmp_path / "docs" / "specs" / "2026-04-05_TEST_SPEC.md"
    spec_path.write_text(
        "\n".join(
            [
                "# Spec",
                "",
                "## 4. 검증 기준",
                "- [ ] APP_OK 성공",
                "- [ ] smoke 통과",
            ]
        ),
        encoding="utf-8",
    )

    assert main(["--repo-root", str(tmp_path), "--spec", str(spec_path), "--json"]) == 0
    report = json.loads(capsys.readouterr().out)

    assert report["spec"]["found"] is True
    assert report["spec"]["path"].endswith("2026-04-05_TEST_SPEC.md")
    assert report["spec"]["verification_items"] == [
        "- [ ] APP_OK 성공",
        "- [ ] smoke 통과",
    ]


def test_cli_fails_when_spec_is_required_but_missing(tmp_path: Path) -> None:
    """The CLI should fail clearly when require-spec is set but no spec is available."""
    _write_repo_fixture(tmp_path)
    completed = subprocess.run(
        [
            sys.executable,
            str(HARNESS_DIR / "verify_result.py"),
            "--repo-root",
            str(tmp_path),
            "--require-spec",
            "--json",
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert completed.returncode == 1
    report = json.loads(completed.stdout)
    assert report["success"] is False
    assert report["spec"]["required"] is True
    assert report["spec"]["found"] is False


def test_cli_reports_invalid_spec_as_structured_json(tmp_path: Path) -> None:
    """An invalid explicit spec path should fail without emitting a traceback."""
    _write_repo_fixture(tmp_path)
    missing_spec = tmp_path / "docs" / "specs" / "DOES_NOT_EXIST_SPEC.md"
    completed = subprocess.run(
        [
            sys.executable,
            str(HARNESS_DIR / "verify_result.py"),
            "--repo-root",
            str(tmp_path),
            "--spec",
            str(missing_spec),
            "--json",
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert completed.returncode == 1
    assert "Traceback" not in completed.stderr
    report = json.loads(completed.stdout)
    assert report["success"] is False
    assert report["spec"]["found"] is False
    assert report["spec"]["path"].endswith("docs/specs/DOES_NOT_EXIST_SPEC.md")
    assert report["error"]["kind"] == "FileNotFoundError"
    assert "Spec file not found" in report["error"]["message"]
