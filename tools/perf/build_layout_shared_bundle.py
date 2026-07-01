#!/usr/bin/env python3
"""Concat layout runtime modules into a single deferred bundle (1 HTTP round-trip).

Sources (edit these, then re-run this script):
  layout-head-init.js, blueprint-viewer-global.js,
  layout-scripts-core.js, layout-scripts-chat.js
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RUNTIME = ROOT / "static" / "js" / "runtime"
OUT = RUNTIME / "layout-shared.bundle.js"

PARTS: tuple[str, ...] = (
    "layout-head-init.js",
    "blueprint-viewer-global.js",
    "layout-scripts-core.js",
    "layout-scripts-chat.js",
)


def main() -> None:
    chunks: list[str] = [
        "/* FOMS layout-shared.bundle.js — generated; do not edit. */",
        "/* Run: python tools/perf/build_layout_shared_bundle.py */",
        "",
    ]
    for name in PARTS:
        src = RUNTIME / name
        text = src.read_text(encoding="utf-8")
        chunks.append(f"/* --- begin {name} --- */")
        chunks.append(text.rstrip())
        chunks.append(f"/* --- end {name} --- */")
        chunks.append("")
    OUT.write_text("\n".join(chunks) + "\n", encoding="utf-8")
    print(f"wrote {OUT.relative_to(ROOT)} ({OUT.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
