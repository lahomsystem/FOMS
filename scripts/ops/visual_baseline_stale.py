"""Visual baseline freshness: win32 vs CSS sources, linux vs win32 (CI seed).

Win32 staleness compares last git commit touching visual-affecting paths
(static/css, static/js, templates) against each win32 baseline PNG commit.
Linux staleness (CI) compares linux vs win32 baseline commit times, with a
linux refresh marker for byte-identical regenerated PNGs.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WIN32 = ROOT / "tests/visual/baseline/win32"
LINUX = ROOT / "tests/visual/baseline/linux"
LINUX_REFRESH_MARKER = LINUX / ".refresh_epoch"

# Paths that can change captured PNGs (SSOT for pre-push visual gate).
VISUAL_AFFECTING_PREFIXES: tuple[str, ...] = (
    "static/css/",
    "static/js/",
    "templates/",
)

VISUAL_BASELINE_NAMES: tuple[str, ...] = (
    "orders_320_light.png",
    "orders_320_dark.png",
    "orders_390_light.png",
    "orders_390_dark.png",
    "orders_767_light.png",
    "orders_767_dark.png",
    "erp_v2_390_light.png",
    "erp_v2_390_dark.png",
    "erp_v2_768_light.png",
    "erp_v2_768_dark.png",
    "erp_v2_1280_light.png",
    "erp_v2_1280_dark.png",
)

ERP_V2_BASELINE_NAMES: tuple[str, ...] = tuple(
    name for name in VISUAL_BASELINE_NAMES if name.startswith("erp_v2_")
)


def git_commit_epoch(path: Path, *, cwd: Path = ROOT) -> int:
    """Return last commit Unix time for path, or 0 if untracked."""
    result = subprocess.run(
        ["git", "log", "-1", "--format=%ct", "--", str(path)],
        capture_output=True,
        text=True,
        cwd=cwd,
        check=False,
    )
    if result.returncode != 0 or not result.stdout.strip():
        return 0
    return int(result.stdout.strip())


def newest_visual_source_epoch(
    prefixes: tuple[str, ...] = VISUAL_AFFECTING_PREFIXES,
    *,
    cwd: Path = ROOT,
) -> int:
    """Latest commit epoch touching any visual-affecting path prefix."""
    result = subprocess.run(
        ["git", "log", "-1", "--format=%ct", "--", *prefixes],
        capture_output=True,
        text=True,
        cwd=cwd,
        check=False,
    )
    if result.returncode != 0 or not result.stdout.strip():
        return 0
    return int(result.stdout.strip())


def _git_diff_name_only(*extra_args: str, cwd: Path = ROOT) -> list[str]:
    """Return changed paths from git diff variants."""
    args = ["git", "diff", "--name-only", *extra_args]
    result = subprocess.run(
        args,
        capture_output=True,
        text=True,
        cwd=cwd,
        check=False,
    )
    if result.returncode != 0 or not result.stdout.strip():
        return []
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def path_is_visual_affecting(path: str) -> bool:
    """True when path is under a visual-affecting prefix."""
    normalized = path.replace("\\", "/")
    return any(normalized.startswith(prefix) for prefix in VISUAL_AFFECTING_PREFIXES)


def visual_affecting_changed_paths(
    *,
    include_uncommitted: bool = True,
    since_ref: str | None = None,
    cwd: Path = ROOT,
) -> list[str]:
    """
    Return visual-affecting paths changed in the working tree or since a ref.

    Args:
        include_uncommitted: Include staged + unstaged diffs vs HEAD.
        since_ref: When set, also include `git diff --name-only since_ref...HEAD`.
        cwd: Repository root.
    """
    seen: set[str] = set()
    ordered: list[str] = []

    def _add(paths: list[str]) -> None:
        for path in paths:
            if path not in seen and path_is_visual_affecting(path):
                seen.add(path)
                ordered.append(path)

    if include_uncommitted:
        _add(_git_diff_name_only("--cached", cwd=cwd))
        _add(_git_diff_name_only(cwd=cwd))
    if since_ref:
        _add(_git_diff_name_only(f"{since_ref}...HEAD", cwd=cwd))
    return ordered


def _git_paths_with_changes(*extra_args: str, cwd: Path = ROOT) -> set[str]:
    """Return repo-relative paths with staged or unstaged changes."""
    changed: set[str] = set()
    for args in (("--cached",), tuple()):
        paths = _git_diff_name_only(*args, *extra_args, cwd=cwd)
        changed.update(path.replace("\\", "/") for path in paths)
    return changed


def win32_baseline_has_worktree_refresh(name: str, *, cwd: Path = ROOT) -> bool:
    """True when win32 baseline PNG differs from HEAD (regenerated, pending commit)."""
    rel = f"tests/visual/baseline/win32/{name}".replace("\\", "/")
    return rel in _git_paths_with_changes(cwd=cwd)


def win32_baselines_stale_vs_sources(
    *,
    source_epoch: int | None = None,
) -> list[str]:
    """
    Baselines missing or last committed before newest visual source change.

    When CSS/templates change but win32 PNGs are not regenerated, every
    affected baseline should be flagged — unlike linux-vs-win32 skew alone.
    Working-tree PNG updates (--update-snapshots, not yet committed) are not stale.
    """
    newest = source_epoch if source_epoch is not None else newest_visual_source_epoch()
    if newest == 0:
        return []

    stale: list[str] = []
    for name in VISUAL_BASELINE_NAMES:
        win32_path = WIN32 / name
        if not win32_path.is_file():
            stale.append(name)
            continue
        if win32_baseline_has_worktree_refresh(name):
            continue
        if git_commit_epoch(win32_path) < newest:
            stale.append(name)
    return stale


def erp_linux_baselines_stale() -> list[str]:
    """
    ERP v2 linux baselines missing or older than win32 counterpart commits.

    Used by CI visual job to refresh Linux SSOT after win32-only updates.
    """
    return linux_baselines_stale(ERP_V2_BASELINE_NAMES)


def linux_baselines_stale(
    baseline_names: tuple[str, ...] = VISUAL_BASELINE_NAMES,
) -> list[str]:
    """
    Linux baselines missing or older than win32 counterpart commits.

    A visual-affecting change can update legacy order-list and ERP v2 PNGs in
    the same commit. CI must refresh the same baseline family that changed,
    not only ERP v2, before running strict visual comparison.
    """
    stale: list[str] = []
    refresh_epoch = (
        git_commit_epoch(LINUX_REFRESH_MARKER)
        if LINUX_REFRESH_MARKER.is_file()
        else 0
    )
    for name in baseline_names:
        win32_path = WIN32 / name
        linux_path = LINUX / name
        if not win32_path.is_file():
            continue
        if not linux_path.is_file():
            stale.append(name)
            continue
        win32_epoch = git_commit_epoch(win32_path)
        linux_epoch = git_commit_epoch(linux_path)
        # Marker can stand in for byte-identical Linux PNG refreshes only when
        # it was committed after the win32 counterpart it refreshes.
        if 0 < win32_epoch < refresh_epoch:
            linux_epoch = max(linux_epoch, refresh_epoch)
        if linux_epoch < win32_epoch:
            stale.append(name)
    return stale


def _print_stale(prefix: str, names: list[str]) -> None:
    for name in names:
        print(f"{prefix}: {name}", file=sys.stderr)


def main(argv: list[str] | None = None) -> int:
    """CLI for pre-push gate and CI linux seed checks."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check-win32-vs-sources",
        action="store_true",
        help="Exit 1 when win32 baselines are older than visual source commits.",
    )
    parser.add_argument(
        "--check-linux-vs-win32",
        action="store_true",
        help="Exit 1 when linux erp_v2 baselines are older than win32 (CI seed).",
    )
    parser.add_argument(
        "--check-all-linux-vs-win32",
        action="store_true",
        help="Exit 1 when any linux baseline is older than its win32 counterpart.",
    )
    parser.add_argument(
        "--list-visual-affecting-changes",
        action="store_true",
        help="Print visual-affecting changed paths (one per line) and exit 1 if any.",
    )
    parser.add_argument(
        "--since-ref",
        default="",
        help="Optional ref for diff (e.g. origin/deploy) with --list-visual-affecting-changes.",
    )
    args = parser.parse_args(argv)

    if args.check_win32_vs_sources:
        stale = win32_baselines_stale_vs_sources()
        _print_stale("win32_stale", stale)
        return 1 if stale else 0

    if args.check_linux_vs_win32:
        stale = erp_linux_baselines_stale()
        _print_stale("stale", stale)
        return 1 if stale else 0

    if args.check_all_linux_vs_win32:
        stale = linux_baselines_stale()
        _print_stale("stale", stale)
        return 1 if stale else 0

    if args.list_visual_affecting_changes:
        since = args.since_ref.strip() or None
        changed = visual_affecting_changed_paths(since_ref=since)
        for path in changed:
            print(path)
        return 1 if changed else 0

    parser.error("Specify --check-win32-vs-sources, --check-linux-vs-win32, --check-all-linux-vs-win32, or --list-visual-affecting-changes")


if __name__ == "__main__":
    raise SystemExit(main())
