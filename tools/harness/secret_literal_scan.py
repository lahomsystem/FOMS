"""SECRET-02 — static credential-literal scan gate.

Detects hardcoded, credential-shaped string literals committed to source under
``foms/``, ``SCheduler/`` and ``app.py``. A finding is a bare module/class-level
constant whose *name* matches a credential token (SECRET / PASSWORD / API_KEY /
TOKEN / PRIVATE_KEY / VAPID) and whose *value* is a direct string literal that
looks like an actual secret (12+ chars, not an identifier / env-name / CLI flag).

Boundary (disjoint packets):
- Env-backed reads (``os.environ.get(name, default)``) have a *call* value, not a
  bare literal, so their dev fallbacks are not flagged here. The two Flask/WAM
  signing-secret fallbacks (``app_factory`` ``app.secret_key = "..."`` attribute
  assignment; ``channel_security`` ``SECRET_KEY = os.environ.get(...)``) are owned
  by SESSION-SIGNING-SECRET-01 and are intentionally out of scope: this scanner
  only inspects *bare Name* targets, never attribute targets.

Allowlist (name + file + rationale, never the value) lives in
``docs/harness/foms_secret_literal_allowlist.json`` — currently only the public,
domain-restricted Kakao JS client key.

Values are NEVER printed or logged: findings report variable name, location and
character length only.

ponytail: heuristic entropy filter (identifier/flag/env-name shapes are treated
as non-secrets); a real secret that is pure lower-snake-with-underscores would be
missed. Upgrade path: add a Shannon-entropy threshold if false negatives appear.
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence

# Repo root = two parents up from tools/harness/this_file.py
REPO_ROOT = Path(__file__).resolve().parents[2]
ALLOWLIST_PATH = REPO_ROOT / "docs" / "harness" / "foms_secret_literal_allowlist.json"

# Variable-name tokens that mark a target as credential-shaped.
_CREDENTIAL_NAME_RE = re.compile(
    r"(SECRET|PASSWORD|API_KEY|TOKEN|PRIVATE_KEY|VAPID)", re.IGNORECASE
)

# Minimum literal length to be considered a credential (per SECRET-02 brief).
_MIN_LEN = 12

# "Not a secret" value shapes: an identifier reference, not a secret value.
_UPPER_SNAKE_RE = re.compile(r"^[A-Z][A-Z0-9]*(_[A-Z0-9]+)+$")  # env-var name, e.g. VAPID_PUBLIC_KEY
_LOWER_SNAKE_RE = re.compile(r"^[a-z][a-z0-9]*(_[a-z0-9]+)+$")  # dict key, e.g. drawing_wizard_presets


@dataclass(frozen=True)
class Finding:
    """A credential-shaped literal found in source (no value retained)."""

    path: str  # posix path, repo-relative when possible
    line: int
    name: str
    length: int


@dataclass(frozen=True)
class AllowEntry:
    """One allowlist record: variable name + optional file suffix + rationale."""

    name: str
    file: str | None
    reason: str


def _looks_like_secret_value(value: str) -> bool:
    """Return whether a string literal looks like an actual secret value.

    Excludes obvious non-secret shapes: CLI flags (``--foo``), UPPER_SNAKE
    env-var-name references, lower_snake dict-key identifiers, and values
    containing whitespace (labels/messages). Everything else that is long
    enough is treated as a possible secret.

    Args:
        value: The literal string assigned to a credential-named variable.

    Returns:
        True when ``value`` is secret-shaped and should be reported.
    """
    if len(value) < _MIN_LEN:
        return False
    if value.startswith("-"):
        return False  # CLI flag name, e.g. "--approval-token-file"
    if any(ch.isspace() for ch in value):
        return False  # header/label/message, not a secret
    if _UPPER_SNAKE_RE.match(value):
        return False  # env-var name reference, e.g. "VAPID_PUBLIC_KEY"
    if _LOWER_SNAKE_RE.match(value):
        return False  # dict-key identifier, e.g. "drawing_wizard_presets"
    return True


def load_allowlist(path: Path | None = None) -> list[AllowEntry]:
    """Load the credential-literal allowlist (name + file + rationale only).

    Args:
        path: Allowlist JSON path; defaults to the repo allowlist.

    Returns:
        Parsed allowlist entries (empty when the file is absent).
    """
    p = path or ALLOWLIST_PATH
    if not p.exists():
        return []
    raw = json.loads(p.read_text(encoding="utf-8"))
    entries: list[AllowEntry] = []
    for item in raw.get("allow", []):
        entries.append(
            AllowEntry(
                name=item["name"],
                file=item.get("file"),
                reason=item.get("reason", ""),
            )
        )
    return entries


def _is_allowlisted(finding: Finding, allowlist: Sequence[AllowEntry]) -> bool:
    """Return whether a finding matches an allowlist entry by name (+ file suffix)."""
    fpath = finding.path.replace("\\", "/")
    for entry in allowlist:
        if entry.name != finding.name:
            continue
        if entry.file is None or fpath.endswith(entry.file.replace("\\", "/")):
            return True
    return False


def _rel(path: Path) -> str:
    """Repo-relative posix path when possible, else absolute posix."""
    try:
        return path.resolve().relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return path.resolve().as_posix()


def scan_files(files: Iterable[Path]) -> list[Finding]:
    """Scan the given .py files for credential-shaped literal assignments.

    Only bare ``Name`` targets (module/class-level constants) are inspected;
    attribute targets (e.g. ``app.secret_key = ...``) are intentionally skipped
    (SESSION-SIGNING-SECRET-01 boundary). Env-backed reads have a call value and
    are naturally excluded.

    Args:
        files: Iterable of .py file paths.

    Returns:
        Raw findings before allowlist filtering.
    """
    findings: list[Finding] = []
    for file in files:
        try:
            source = Path(file).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        try:
            tree = ast.parse(source, filename=str(file))
        except SyntaxError:
            continue
        rel = _rel(Path(file))
        for node in ast.walk(tree):
            targets: list[ast.expr]
            if isinstance(node, ast.Assign):
                targets = list(node.targets)
                value = node.value
            elif isinstance(node, ast.AnnAssign) and node.value is not None:
                targets = [node.target]
                value = node.value
            else:
                continue
            if not (isinstance(value, ast.Constant) and isinstance(value.value, str)):
                continue
            literal = value.value
            for target in targets:
                if not isinstance(target, ast.Name):
                    continue  # skip attribute/tuple/subscript targets by design
                name = target.id
                if not _CREDENTIAL_NAME_RE.search(name):
                    continue
                if not _looks_like_secret_value(literal):
                    continue
                findings.append(
                    Finding(path=rel, line=node.lineno, name=name, length=len(literal))
                )
    return findings


def default_targets(root: Path | None = None) -> list[Path]:
    """Return the SECRET-02 scan surface: foms/, SCheduler/ .py files and app.py."""
    base = root or REPO_ROOT
    files: list[Path] = []
    for sub in ("foms", "SCheduler"):
        sub_dir = base / sub
        if sub_dir.is_dir():
            files.extend(sorted(sub_dir.rglob("*.py")))
    app_py = base / "app.py"
    if app_py.exists():
        files.append(app_py)
    return files


def scan(
    root: Path | None = None,
    allowlist: Sequence[AllowEntry] | None = None,
) -> list[Finding]:
    """Scan the default surface and drop allowlisted findings.

    Args:
        root: Repo root to scan (defaults to this repo).
        allowlist: Allowlist entries; loaded from disk when omitted.

    Returns:
        Findings that are NOT allowlisted (i.e. gate violations).
    """
    allow = list(allowlist) if allowlist is not None else load_allowlist()
    return [f for f in scan_files(default_targets(root)) if not _is_allowlisted(f, allow)]


def main(argv: list[str] | None = None) -> int:
    """CLI gate: exit non-zero when un-allowlisted credential literals exist.

    Prints variable name, location and length only — never the literal value.
    """
    parser = argparse.ArgumentParser(description="SECRET-02 credential-literal scan gate")
    parser.add_argument("--root", default=None, help="Repo root to scan")
    args = parser.parse_args(argv)
    root = Path(args.root) if args.root else None
    findings = scan(root=root)
    if findings:
        print("[SECRET-02] hardcoded credential-shaped literal(s) detected:")
        for f in findings:
            print(f"  {f.path}:{f.line}  {f.name}  (len={f.length})")
        print(
            "Fix: read the value from the environment, or add a justified allowlist "
            "entry (name + file + reason, never the value) to "
            "docs/harness/foms_secret_literal_allowlist.json"
        )
        return 1
    print("[SECRET-02] OK - no un-allowlisted credential literals in foms/, SCheduler/, app.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
