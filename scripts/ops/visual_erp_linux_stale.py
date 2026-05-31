"""Exit 1 when linux erp_v2 baselines are older than win32 (git commit time).

Used by CI visual job to refresh Linux SSOT after win32-only baseline updates.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LINUX = ROOT / "tests/visual/baseline/linux"
WIN32 = ROOT / "tests/visual/baseline/win32"
ERP_BASELINES: tuple[str, ...] = (
    "erp_v2_390_light.png",
    "erp_v2_390_dark.png",
    "erp_v2_768_light.png",
    "erp_v2_768_dark.png",
    "erp_v2_1280_light.png",
    "erp_v2_1280_dark.png",
)


def _git_commit_epoch(path: Path) -> int:
    """Return last commit Unix time for path, or 0 if untracked."""
    result = subprocess.run(
        ["git", "log", "-1", "--format=%ct", "--", str(path)],
        capture_output=True,
        text=True,
        cwd=ROOT,
        check=False,
    )
    if result.returncode != 0 or not result.stdout.strip():
        return 0
    return int(result.stdout.strip())


def erp_linux_baselines_stale() -> list[str]:
    """
    Return erp_v2 baseline filenames that need a Linux refresh.

    Stale when linux file is missing or last committed before win32 counterpart.
    """
    stale: list[str] = []
    for name in ERP_BASELINES:
        win32_path = WIN32 / name
        linux_path = LINUX / name
        if not win32_path.is_file():
            continue
        if not linux_path.is_file():
            stale.append(name)
            continue
        if _git_commit_epoch(linux_path) < _git_commit_epoch(win32_path):
            stale.append(name)
    return stale


def main() -> int:
    stale = erp_linux_baselines_stale()
    for name in stale:
        print(f"stale: {name}", file=sys.stderr)
    return 1 if stale else 0


if __name__ == "__main__":
    raise SystemExit(main())
