"""Dry-run token migration helper (P1-06 Phase 3 prep)."""

from __future__ import annotations

import argparse
import re
from pathlib import Path

_ERP_VAR = re.compile(r"var\(\s*(--erp-[a-z0-9-]+)")


def scan(paths: list[Path]) -> dict[str, int]:
    """Count --erp-* var() usages under given paths."""
    counts: dict[str, int] = {}
    for root in paths:
        for file in root.rglob("*"):
            if file.suffix not in {".css", ".html", ".js"}:
                continue
            try:
                text = file.read_text(encoding="utf-8")
            except OSError:
                continue
            for match in _ERP_VAR.findall(text):
                counts[match] = counts.get(match, 0) + 1
    return counts


def main() -> int:
    """CLI: report legacy --erp-* var() counts (dry-run only)."""
    parser = argparse.ArgumentParser(description="Scan legacy --erp-* token usage (dry-run).")
    parser.add_argument("--root", default="static/css", help="Root directory to scan")
    args = parser.parse_args()
    root = Path(args.root)
    counts = scan([root])
    for name, total in sorted(counts.items(), key=lambda item: (-item[1], item[0])):
        print(f"{name}\t{total}")
    print(f"TOTAL\t{sum(counts.values())}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
