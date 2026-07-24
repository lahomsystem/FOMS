"""FE-SYNTAX parser CI — every static/js file must parse as JavaScript.

Root-cause guard for P0-6: a Python ``#`` comment leaked into
``static/js/foms/erp-attachment-preview-open.js`` and broke the whole module
(``SyntaxError: Invalid or unexpected token``). Any non-parsing JS shipped to
the browser is a hard failure, so this test runs ``node --check`` over the
entire ``static/js`` tree and fails on the first file that does not parse.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
STATIC_JS = ROOT / "static" / "js"


def _all_js_files() -> list[Path]:
    return sorted(STATIC_JS.rglob("*.js"))


def test_static_js_tree_is_nonempty() -> None:
    """Guard against a glob that silently matches nothing."""
    assert _all_js_files(), f"no .js files found under {STATIC_JS}"


def test_every_static_js_parses() -> None:
    node = shutil.which("node")
    assert node, "node must be on PATH for the FE-SYNTAX parser CI test"

    broken: list[str] = []
    for path in _all_js_files():
        proc = subprocess.run(
            [node, "--check", str(path)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        if proc.returncode != 0:
            first_err = (proc.stderr or proc.stdout).strip().splitlines()
            detail = first_err[0] if first_err else "unknown parse error"
            broken.append(f"{path.relative_to(ROOT).as_posix()}: {detail}")

    assert not broken, "static/js files failed `node --check`:\n" + "\n".join(broken)
