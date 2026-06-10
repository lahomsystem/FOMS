"""Tests for visual baseline staleness policy (win32 vs sources, linux vs win32)."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
_POLICY_PATH = ROOT / "scripts/ops/visual_baseline_stale.py"
_spec = importlib.util.spec_from_file_location("visual_baseline_stale", _POLICY_PATH)
assert _spec and _spec.loader
policy = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(policy)


def test_path_is_visual_affecting_static_and_templates() -> None:
    assert policy.path_is_visual_affecting("static/css/foundation/erp-pro.css")
    assert policy.path_is_visual_affecting("static/js/erp/runtime-shell.js")
    assert policy.path_is_visual_affecting("templates/erp/dashboard.html")
    assert not policy.path_is_visual_affecting("services/erp_policy.py")
    assert not policy.path_is_visual_affecting("tests/visual/conftest.py")


def test_win32_stale_when_source_epoch_newer(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(policy, "newest_visual_source_epoch", lambda: 200)
    monkeypatch.setattr(policy, "git_commit_epoch", lambda _path: 100)
    monkeypatch.setattr(
        policy,
        "win32_baseline_has_worktree_refresh",
        lambda _name: False,
    )
    monkeypatch.setattr(
        policy,
        "win32_refresh_marker_has_worktree_refresh",
        lambda: False,
    )
    monkeypatch.setattr(
        policy,
        "VISUAL_BASELINE_NAMES",
        ("erp_v2_1280_light.png",),
    )

    def _exists(self: Path) -> bool:
        return self.name == "erp_v2_1280_light.png"

    monkeypatch.setattr(Path, "is_file", _exists, raising=False)
    assert policy.win32_baselines_stale_vs_sources() == ["erp_v2_1280_light.png"]


def test_win32_fresh_when_baseline_epoch_matches_sources(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(policy, "newest_visual_source_epoch", lambda: 200)
    monkeypatch.setattr(policy, "git_commit_epoch", lambda _path: 200)
    monkeypatch.setattr(
        policy,
        "win32_baseline_has_worktree_refresh",
        lambda _name: False,
    )
    monkeypatch.setattr(
        policy,
        "win32_refresh_marker_has_worktree_refresh",
        lambda: False,
    )
    monkeypatch.setattr(
        policy,
        "VISUAL_BASELINE_NAMES",
        ("erp_v2_1280_light.png",),
    )

    def _exists(self: Path) -> bool:
        return self.name == "erp_v2_1280_light.png"

    monkeypatch.setattr(Path, "is_file", _exists, raising=False)
    assert policy.win32_baselines_stale_vs_sources() == []


def test_win32_fresh_when_refresh_marker_newer_than_sources(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(policy, "newest_visual_source_epoch", lambda: 200)

    def _epoch(path: Path) -> int:
        posix = path.as_posix()
        if posix.endswith("baseline/win32/.refresh_epoch"):
            return 250
        if "win32" in posix:
            return 100
        return 0

    monkeypatch.setattr(policy, "git_commit_epoch", _epoch)
    monkeypatch.setattr(
        policy,
        "VISUAL_BASELINE_NAMES",
        ("erp_v2_1280_light.png",),
    )
    monkeypatch.setattr(
        policy,
        "win32_baseline_has_worktree_refresh",
        lambda _name: False,
    )
    monkeypatch.setattr(
        policy,
        "win32_refresh_marker_has_worktree_refresh",
        lambda: False,
    )

    def _exists(self: Path) -> bool:
        return self.name in {".refresh_epoch", "erp_v2_1280_light.png"}

    monkeypatch.setattr(Path, "is_file", _exists, raising=False)
    assert policy.win32_baselines_stale_vs_sources() == []


def test_win32_not_stale_when_worktree_refresh_pending(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(policy, "newest_visual_source_epoch", lambda: 200)
    monkeypatch.setattr(policy, "git_commit_epoch", lambda _path: 100)
    monkeypatch.setattr(
        policy,
        "VISUAL_BASELINE_NAMES",
        ("erp_v2_1280_light.png",),
    )
    monkeypatch.setattr(
        policy,
        "win32_baseline_has_worktree_refresh",
        lambda _name: True,
    )
    monkeypatch.setattr(
        policy,
        "win32_refresh_marker_has_worktree_refresh",
        lambda: False,
    )

    def _exists(self: Path) -> bool:
        return self.name == "erp_v2_1280_light.png"

    monkeypatch.setattr(Path, "is_file", _exists, raising=False)
    assert policy.win32_baselines_stale_vs_sources() == []


def test_erp_linux_stale_when_linux_older(monkeypatch: pytest.MonkeyPatch) -> None:
    epochs = {
        "win32": 200,
        "linux": 100,
    }

    def _epoch(path: Path) -> int:
        if "win32" in path.as_posix():
            return epochs["win32"]
        if "linux" in path.as_posix():
            return epochs["linux"]
        return 0

    monkeypatch.setattr(policy, "git_commit_epoch", _epoch)

    def _exists(self: Path) -> bool:
        return self.name == "erp_v2_390_light.png"

    monkeypatch.setattr(Path, "is_file", _exists, raising=False)
    assert policy.erp_linux_baselines_stale() == ["erp_v2_390_light.png"]


def test_all_linux_stale_includes_order_and_erp_baselines(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    epochs = {
        "win32": 200,
        "linux": 100,
    }

    def _epoch(path: Path) -> int:
        if "win32" in path.as_posix():
            return epochs["win32"]
        if "linux" in path.as_posix():
            return epochs["linux"]
        return 0

    monkeypatch.setattr(policy, "git_commit_epoch", _epoch)
    monkeypatch.setattr(
        policy,
        "VISUAL_BASELINE_NAMES",
        ("orders_320_light.png", "erp_v2_1280_light.png"),
    )

    def _exists(self: Path) -> bool:
        return self.name in {"orders_320_light.png", "erp_v2_1280_light.png"}

    monkeypatch.setattr(Path, "is_file", _exists, raising=False)
    assert policy.linux_baselines_stale() == [
        "orders_320_light.png",
        "erp_v2_1280_light.png",
    ]


def test_all_linux_fresh_when_refresh_marker_newer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _epoch(path: Path) -> int:
        posix = path.as_posix()
        if posix.endswith("baseline/linux/.refresh_epoch"):
            return 250
        if posix.endswith("baseline/win32/.refresh_epoch"):
            return 0
        if "win32" in posix:
            return 200
        if "linux" in posix:
            return 100
        return 0

    monkeypatch.setattr(policy, "git_commit_epoch", _epoch)
    monkeypatch.setattr(
        policy,
        "VISUAL_BASELINE_NAMES",
        ("orders_320_light.png", "erp_v2_1280_light.png"),
    )

    def _exists(self: Path) -> bool:
        return self.name in {
            ".refresh_epoch",
            "orders_320_light.png",
            "erp_v2_1280_light.png",
        }

    monkeypatch.setattr(Path, "is_file", _exists, raising=False)
    assert policy.linux_baselines_stale() == []


def test_all_linux_stale_when_win32_refresh_marker_newer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _epoch(path: Path) -> int:
        posix = path.as_posix()
        if posix.endswith("baseline/win32/.refresh_epoch"):
            return 250
        if posix.endswith("baseline/linux/.refresh_epoch"):
            return 0
        if "win32" in posix:
            return 100
        if "linux" in posix:
            return 200
        return 0

    monkeypatch.setattr(policy, "git_commit_epoch", _epoch)
    monkeypatch.setattr(
        policy,
        "VISUAL_BASELINE_NAMES",
        ("orders_320_light.png",),
    )

    def _exists(self: Path) -> bool:
        return self.name in {".refresh_epoch", "orders_320_light.png"}

    monkeypatch.setattr(Path, "is_file", _exists, raising=False)
    assert policy.linux_baselines_stale() == ["orders_320_light.png"]


def test_linux_marker_same_epoch_as_win32_does_not_hide_stale_png(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _epoch(path: Path) -> int:
        posix = path.as_posix()
        if posix.endswith(".refresh_epoch"):
            return 200
        if "win32" in posix:
            return 200
        if "linux" in posix:
            return 100
        return 0

    monkeypatch.setattr(policy, "git_commit_epoch", _epoch)
    monkeypatch.setattr(
        policy,
        "VISUAL_BASELINE_NAMES",
        ("erp_v2_390_light.png",),
    )

    def _exists(self: Path) -> bool:
        return self.name in {".refresh_epoch", "erp_v2_390_light.png"}

    monkeypatch.setattr(Path, "is_file", _exists, raising=False)
    assert policy.linux_baselines_stale() == ["erp_v2_390_light.png"]
