"""Visual baseline platform policy (P0-00D SSOT)."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.visual.conftest import (
    VISUAL_BASELINE_NAMES,
    missing_baseline_names,
    resolve_baseline_dir,
)


ROOT = Path(__file__).resolve().parents[2]


def test_visual_baseline_manifest_count() -> None:
    assert len(VISUAL_BASELINE_NAMES) == 12


def test_win32_baselines_present() -> None:
    win32 = ROOT / "tests/visual/baseline/win32"
    missing = missing_baseline_names(win32)
    assert not missing, f"win32 baselines missing: {missing}"


def test_resolve_baseline_dir_uses_platform_subdir(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("VISUAL_BASELINE_DIR", raising=False)
    monkeypatch.setattr("tests.visual.conftest.sys.platform", "win32")
    assert resolve_baseline_dir().name == "win32"
    monkeypatch.setattr("tests.visual.conftest.sys.platform", "linux")
    assert resolve_baseline_dir().name == "linux"
