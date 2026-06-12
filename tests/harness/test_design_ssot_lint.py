from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "tools" / "design" / "ssot_lint.py"


def run_lint(path: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), str(path)],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
    )


def with_repo_temp_dir():
    return tempfile.TemporaryDirectory(prefix=".ssot-lint-", dir=REPO_ROOT)


def test_design_ssot_lint_passes_current_terms() -> None:
    with with_repo_temp_dir() as raw_path:
        temp_dir = Path(raw_path)
        doc = temp_dir / "ok.md"
        doc.write_text("P0 8개 PR 58h\nC01~C14\n14종 컴포넌트\n", encoding="utf-8")
        result = run_lint(temp_dir)

    assert result.returncode == 0, result.stdout + result.stderr
    assert "SSOT lint passed" in result.stdout


def test_design_ssot_lint_blocks_old_p0_count() -> None:
    with with_repo_temp_dir() as raw_path:
        temp_dir = Path(raw_path)
        doc = temp_dir / "bad.md"
        doc.write_text("P0 7개 PR\n", encoding="utf-8")
        result = run_lint(temp_dir)

    assert result.returncode == 1
    assert "old_p0_pr_count" in result.stdout


def test_design_ssot_lint_blocks_old_component_heading() -> None:
    with with_repo_temp_dir() as raw_path:
        temp_dir = Path(raw_path)
        doc = temp_dir / "bad.md"
        doc.write_text("## 5. 컴포넌트 핵심 13종\n", encoding="utf-8")
        result = run_lint(temp_dir)

    assert result.returncode == 1
    assert "old_component_count" in result.stdout


def test_design_ssot_lint_allows_revision_audit_trail() -> None:
    with with_repo_temp_dir() as raw_path:
        temp_dir = Path(raw_path)
        doc = temp_dir / "REVISION_v1.1.md"
        doc.write_text("P0 7 PR\nC01~C13\n", encoding="utf-8")
        result = run_lint(temp_dir)

    assert result.returncode == 0, result.stdout + result.stderr
