"""Fail when stale mobile redesign SSOT phrases re-enter design docs.

The exact patterns live here instead of in docs/design so the documentation can
describe the guard without reintroducing the banned phrases it is meant to catch.
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path


TEXT_SUFFIXES = {".md", ".txt", ".html"}


@dataclass(frozen=True)
class StalePattern:
    label: str
    regex: re.Pattern[str]


SSOT_STALE_PATTERNS: tuple[StalePattern, ...] = (
    StalePattern("old_defect_count", re.compile(r"사용\s*불가급\s*결함\s*5건")),
    StalePattern("env_only_enablement", re.compile(r"환경변수만\s*켜면")),
    StalePattern("old_p0_pr_count", re.compile(r"P0\s*7\s*(?:개\s*)?PR")),
    StalePattern("old_total_pr_count", re.compile(r"P0/P1/P2\s*22\s*(?:개\s*)?PR")),
    StalePattern("old_component_range", re.compile(r"C01~C13")),
    StalePattern(
        "old_component_count",
        re.compile(r"(?:13\s*(?:개|종)\s*컴포넌트|컴포넌트\s*핵심\s*13종|컴포넌트\s*13종)"),
    ),
    StalePattern("old_artifact_count", re.compile(r"11\s*개\s*산출물")),
    StalePattern("old_shell_flag_default", re.compile(r"FOMS_V3_SHELL_ENABLED.*기본\s*ON")),
    StalePattern("old_p0_duration", re.compile(r"P0\s*5\s*[~\-]\s*6\s*작업일")),
)


def is_revision_audit_trail(path: Path) -> bool:
    """REVISION_v1.1 is retained as audit history; lint current SSOT docs only."""
    return path.name == "REVISION_v1.1.md"


def iter_text_files(paths: list[Path]) -> list[Path]:
    files: list[Path] = []
    for path in paths:
        if path.is_file() and path.suffix.lower() in TEXT_SUFFIXES:
            files.append(path)
            continue
        if path.is_dir():
            for child in path.rglob("*"):
                if child.is_file() and child.suffix.lower() in TEXT_SUFFIXES:
                    files.append(child)
    return sorted(files)


def scan_file(path: Path) -> list[str]:
    if is_revision_audit_trail(path):
        return []

    findings: list[str] = []
    text = path.read_text(encoding="utf-8", errors="replace")
    for line_no, line in enumerate(text.splitlines(), start=1):
        for pattern in SSOT_STALE_PATTERNS:
            if pattern.regex.search(line):
                findings.append(f"{path}:{line_no}: {pattern.label}: {line.strip()}")
    return findings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="*", type=Path, default=[Path("docs/design")])
    args = parser.parse_args(argv)

    files = iter_text_files(args.paths)
    findings: list[str] = []
    for file_path in files:
        findings.extend(scan_file(file_path))

    if findings:
        print("SSOT lint failed:")
        for finding in findings:
            print(finding)
        return 1

    print(f"SSOT lint passed: {len(files)} files scanned")
    return 0


if __name__ == "__main__":
    sys.exit(main())
