"""Import a pinned upstream gstack source slice into the repo-local vendor zone.

This script intentionally imports only the minimum upstream files needed to pin
the Windows setup entrypoint and host configuration contract during Phase 2.
It does not attempt to vendor the full runtime tree.
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Iterable
from urllib.error import HTTPError, URLError
from urllib.request import urlopen


PINNED_COMMIT = "04b709d91a3f10efa1c816c6ddb4c8cafa735da8"
UPSTREAM_RAW_BASE = (
    "https://raw.githubusercontent.com/garrytan/gstack/{commit}/{path}"
)

SOURCE_SLICE_FILES = (
    "setup",
    "package.json",
    "VERSION",
    "hosts/index.ts",
    "hosts/claude.ts",
    "hosts/codex.ts",
    "hosts/cursor.ts",
    "hosts/factory.ts",
    "hosts/kiro.ts",
    "hosts/opencode.ts",
    "hosts/openclaw.ts",
    "hosts/slate.ts",
    "scripts/host-config.ts",
    "scripts/host-config-export.ts",
)


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments for the import script."""

    parser = argparse.ArgumentParser(
        description="Import a pinned gstack upstream source slice."
    )
    parser.add_argument(
        "--vendor-root",
        default=".agents/skills/gstack",
        help="Vendor root relative to the repository root.",
    )
    parser.add_argument(
        "--commit",
        default=PINNED_COMMIT,
        help="Pinned upstream commit to import from.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print planned writes without modifying files.",
    )
    return parser.parse_args()


def repo_root() -> Path:
    """Return the repository root from this script location."""

    return Path(__file__).resolve().parents[2]


def fetch_text(commit: str, relative_path: str) -> str:
    """Fetch one upstream text file from GitHub raw content."""

    url = UPSTREAM_RAW_BASE.format(commit=commit, path=relative_path)
    try:
        with urlopen(url) as response:
            return response.read().decode("utf-8")
    except HTTPError as exc:
        raise RuntimeError(
            f"HTTP error while fetching {relative_path}: {exc.code}"
        ) from exc
    except URLError as exc:
        raise RuntimeError(f"Network error while fetching {relative_path}: {exc}") from exc


def write_if_changed(target_path: Path, content: str, dry_run: bool) -> bool:
    """Write content only when the target file differs."""

    if target_path.exists():
        existing = target_path.read_text(encoding="utf-8")
        if existing == content:
            return False

    if dry_run:
        return True

    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_text(content, encoding="utf-8", newline="\n")
    return True


def import_files(
    *,
    commit: str,
    vendor_root: Path,
    file_paths: Iterable[str],
    dry_run: bool,
) -> tuple[int, int]:
    """Import the configured file paths into the vendor root."""

    written = 0
    unchanged = 0

    for relative_path in file_paths:
        content = fetch_text(commit=commit, relative_path=relative_path)
        target_path = vendor_root / relative_path
        changed = write_if_changed(target_path=target_path, content=content, dry_run=dry_run)
        status = "WRITE" if changed else "SKIP "
        print(f"[{status}] {relative_path}")
        if changed:
            written += 1
        else:
            unchanged += 1

    return written, unchanged


def main() -> int:
    """Run the importer and return a process exit code."""

    args = parse_args()
    target_vendor_root = repo_root() / args.vendor_root
    target_vendor_root.mkdir(parents=True, exist_ok=True)

    print("== gstack source slice import ==")
    print(f"Repo root  : {repo_root()}")
    print(f"Vendor root: {target_vendor_root}")
    print(f"Commit     : {args.commit}")
    print(f"Dry run    : {args.dry_run}")

    written, unchanged = import_files(
        commit=args.commit,
        vendor_root=target_vendor_root,
        file_paths=SOURCE_SLICE_FILES,
        dry_run=args.dry_run,
    )

    print("")
    print(f"[OK] Files updated : {written}")
    print(f"[OK] Files unchanged: {unchanged}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
