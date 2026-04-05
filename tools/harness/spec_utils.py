"""Shared helpers for locating Spec documents across harness workflows."""

from __future__ import annotations

from pathlib import Path
import re


DATE_PREFIX_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})")


def _spec_sort_key(repo_root: Path, path: Path) -> tuple[int, str, int, str]:
    """Return a deterministic sort key for choosing the latest spec."""
    relative_path = path.resolve().relative_to(repo_root.resolve()).as_posix()
    match = DATE_PREFIX_RE.match(path.name)
    if match:
        return (1, match.group(1), path.stat().st_mtime_ns, relative_path)
    return (0, "", path.stat().st_mtime_ns, relative_path)


def find_latest_spec(repo_root: Path) -> Path | None:
    """Return the deterministic latest `*_SPEC.md` under `docs/specs/` recursively."""
    spec_dir = repo_root / "docs" / "specs"
    if not spec_dir.is_dir():
        return None

    candidates = [path for path in spec_dir.rglob("*_SPEC.md") if path.is_file()]
    if not candidates:
        return None
    return max(candidates, key=lambda path: _spec_sort_key(repo_root, path))
