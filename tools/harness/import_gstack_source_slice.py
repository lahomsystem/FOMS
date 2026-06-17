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


PINNED_COMMIT = "c7ae63201ab193a7dc7fb7e0d81238645111ffac"
UPSTREAM_RAW_BASE = (
    "https://raw.githubusercontent.com/garrytan/gstack/{commit}/{path}"
)
FETCH_TIMEOUT_SECONDS = 30

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

RUNTIME_STATIC_FILES = (
    "ETHOS.md",
    "review/SKILL.md",
    "review/checklist.md",
    "review/design-checklist.md",
    "review/greptile-triage.md",
    "review/TODOS-format.md",
    "qa/SKILL.md",
    "qa/SKILL.md.tmpl",
    "qa/references/issue-taxonomy.md",
    "qa/templates/qa-report-template.md",
    "gstack-upgrade/SKILL.md.tmpl",
    "gstack-upgrade/migrations/v0.15.2.0.sh",
    "gstack-upgrade/migrations/v1.58.0.0.sh",
)

BUILD_SOURCE_PATTERNS = (
    "bin/*",
    "browse/bin/*",
    "browse/src/*",
    "browse/scripts/*",
    "design/src/*",
    "scripts/discover-skills.ts",
    "scripts/gen-skill-docs.ts",
    "scripts/resolvers/*",
    "**/SKILL.md.tmpl",
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
    parser.add_argument(
        "--include-runtime-static",
        action="store_true",
        help="Also import the pinned static runtime asset subset for review/qa/upgrade.",
    )
    parser.add_argument(
        "--include-build-source",
        action="store_true",
        help="Also import the pinned build/generated-skill source layer from a local upstream checkout.",
    )
    parser.add_argument(
        "--source-root",
        default=".tmp/gstack-upstream-scan",
        help="Local upstream checkout root relative to the repository root.",
    )
    return parser.parse_args()


def repo_root() -> Path:
    """Return the repository root from this script location."""

    return Path(__file__).resolve().parents[2]


def fetch_text(commit: str, relative_path: str) -> str:
    """Fetch one upstream text file from GitHub raw content."""

    url = UPSTREAM_RAW_BASE.format(commit=commit, path=relative_path)
    try:
        with urlopen(url, timeout=FETCH_TIMEOUT_SECONDS) as response:
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


def import_remote_files(
    *,
    commit: str,
    vendor_root: Path,
    file_paths: Iterable[str],
    dry_run: bool,
) -> tuple[int, int]:
    """Import configured remote file paths into the vendor root."""

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


def import_local_files(
    *,
    source_root: Path,
    vendor_root: Path,
    file_paths: Iterable[str],
    dry_run: bool,
) -> tuple[int, int]:
    """Import configured local text file paths into the vendor root."""

    written = 0
    unchanged = 0

    for relative_path in file_paths:
        source_path = source_root / relative_path
        if not source_path.exists():
            raise RuntimeError(f"Local source file missing: {source_path}")

        try:
            content = source_path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            # The build-source layer intentionally excludes compiled artifacts
            # that may live alongside text scripts in upstream directories.
            print(f"[SKIPB] {relative_path}")
            unchanged += 1
            continue

        target_path = vendor_root / relative_path
        changed = write_if_changed(target_path=target_path, content=content, dry_run=dry_run)
        status = "WRITE" if changed else "SKIP "
        print(f"[{status}] {relative_path}")
        if changed:
            written += 1
        else:
            unchanged += 1

    return written, unchanged


def build_file_list(include_runtime_static: bool) -> tuple[str, ...]:
    """Build the ordered import list for the current invocation."""

    file_paths: list[str] = list(SOURCE_SLICE_FILES)
    if include_runtime_static:
        file_paths.extend(RUNTIME_STATIC_FILES)

    # Preserve order while avoiding duplicates across lists.
    seen: set[str] = set()
    ordered: list[str] = []
    for path in file_paths:
        if path in seen:
            continue
        seen.add(path)
        ordered.append(path)
    return tuple(ordered)


def expand_local_patterns(source_root: Path, patterns: Iterable[str]) -> tuple[str, ...]:
    """Expand local glob patterns from a pinned upstream checkout."""

    matches: list[str] = []
    for pattern in patterns:
        for path in sorted(source_root.glob(pattern)):
            if path.is_dir():
                continue
            relative_path = path.relative_to(source_root).as_posix()
            matches.append(relative_path)

    seen: set[str] = set()
    ordered: list[str] = []
    for path in matches:
        if path in seen:
            continue
        seen.add(path)
        ordered.append(path)
    return tuple(ordered)


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
    print(f"Static set : {args.include_runtime_static}")
    print(f"Build set  : {args.include_build_source}")

    written = 0
    unchanged = 0

    remote_written, remote_unchanged = import_remote_files(
        commit=args.commit,
        vendor_root=target_vendor_root,
        file_paths=build_file_list(include_runtime_static=args.include_runtime_static),
        dry_run=args.dry_run,
    )
    written += remote_written
    unchanged += remote_unchanged

    if args.include_build_source:
        source_root = repo_root() / args.source_root
        if not source_root.exists():
            raise RuntimeError(
                f"Local source root not found: {source_root}. Clone the pinned upstream tree first."
            )

        print(f"Source root: {source_root}")
        local_written, local_unchanged = import_local_files(
            source_root=source_root,
            vendor_root=target_vendor_root,
            file_paths=expand_local_patterns(source_root=source_root, patterns=BUILD_SOURCE_PATTERNS),
            dry_run=args.dry_run,
        )
        written += local_written
        unchanged += local_unchanged

    print("")
    print(f"[OK] Files updated : {written}")
    print(f"[OK] Files unchanged: {unchanged}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
