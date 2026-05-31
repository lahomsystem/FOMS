"""Report --foms-* vs --erp-* token coverage (P1-06)."""

from __future__ import annotations

import argparse
import re
from pathlib import Path

_FOMS = re.compile(r"var\(\s*(--foms-[a-z0-9-]+)")
_ERP = re.compile(r"var\(\s*(--erp-[a-z0-9-]+)")


def _scan(root: Path, pattern: re.Pattern[str]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for file in root.rglob("*"):
        if file.suffix not in {".css", ".html", ".js"}:
            continue
        try:
            text = file.read_text(encoding="utf-8")
        except OSError:
            continue
        for match in pattern.findall(text):
            counts[match] = counts.get(match, 0) + 1
    return counts


def main() -> int:
    """Print foms/erp token usage counts."""
    parser = argparse.ArgumentParser(description="Token coverage report for FOMS redesign.")
    parser.add_argument("--root", default="static", help="Scan root (default: static)")
    args = parser.parse_args()
    root = Path(args.root)
    foms = _scan(root, _FOMS)
    erp = _scan(root, _ERP)
    print("FOMS_TOKEN_COUNT", sum(foms.values()))
    print("ERP_TOKEN_COUNT", sum(erp.values()))
    print("FOMS_UNIQUE", len(foms))
    print("ERP_UNIQUE", len(erp))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
