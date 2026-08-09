"""FAILOPEN-01: AST scanner + classifier for broad/silent exception handlers.

Single source of truth for the fail-open inventory. Walks ``foms/`` plus the
root runtime modules, finds every *broad* catch, and assigns a disposition
from the handler body:

- ``LOG_AND_CONTINUE`` -- the handler wires a real logger (a logger call or
  :func:`foms.services.error_logging.log_handled_exception`) and continues, so
  the failure is observable to an operator.
- ``SWALLOW_BY_CONTROL_FLOW`` -- the handler continues **with no logger wired**
  (``has_logging=False``): it swallows via explicit control flow
  (``return``/``continue``/fallback value), or only surfaces the failure through
  ``print``/``flash``, which are not operator log sinks. AUDIT-LOG T11 split
  these out of ``LOG_AND_CONTINUE``: folded together, a logger-less swallow
  passed the release gate wearing the label of a logged one. They are now
  pinned at a **no-growth baseline** (see
  :mod:`tests.domains.test_failopen_inventory`) -- shrinking is always allowed,
  growing is red.
- ``FAIL_CLOSED`` -- the handler re-raises or ``abort()``s (fails closed).
- ``INTENTIONAL`` -- silent by design, justified with an inline
  ``# failopen: intentional: <reason>`` marker.
- ``UNCLASSIFIED`` -- a silent ``except ...: pass`` with no logging and no
  justification marker. This is the P1-29 danger and the release-gate RED
  condition (see :mod:`tests.domains.test_failopen_inventory`).

A "broad" catch is ``except:`` (bare), ``except Exception`` /
``except BaseException``, or a tuple that includes either. ``except ValueError``
and other specific handlers are ignored.

Overlap with API-ERROR-01: that packet migrated raw ``print_exc``/``str(e)``
leaks to the protected logger (exposure). This packet classifies *swallowing*
(silent catches). A site that logs via ``log_handled_exception`` is
``LOG_AND_CONTINUE`` here and is owned by API-ERROR-01 for the logging wiring.

Run ``python tools/harness/failopen_scan.py`` to (re)generate
``docs/harness/foms_failopen_inventory.json``.
"""

from __future__ import annotations

import argparse
import ast
import json
from collections import Counter
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
FOMS_DIR = REPO_ROOT / "foms"
ROOT_RUNTIME = (
    "app.py",
    "db.py",
    "models.py",
    "run.py",
    "wdcalculator_db.py",
    "wdcalculator_models.py",
)
INVENTORY_PATH = REPO_ROOT / "docs" / "harness" / "foms_failopen_inventory.json"

_LOG_METHODS = {"error", "warning", "warn", "exception", "critical", "info", "debug"}
_LOG_FUNCS = {"log_handled_exception", "capture_exception"}
_MARKER_INTENTIONAL = "failopen: intentional"
_MARKER_FAIL_CLOSED = "failopen: fail-closed"

DISPOSITIONS = (
    "LOG_AND_CONTINUE",
    "SWALLOW_BY_CONTROL_FLOW",
    "FAIL_CLOSED",
    "INTENTIONAL",
    "UNCLASSIFIED",
)


def _type_names(node: ast.expr | None) -> set[str]:
    """Collect the exception type names referenced by an ``except`` clause."""
    if node is None:
        return set()
    if isinstance(node, ast.Name):
        return {node.id}
    if isinstance(node, ast.Attribute):
        return {node.attr}
    if isinstance(node, ast.Tuple):
        names: set[str] = set()
        for elt in node.elts:
            names |= _type_names(elt)
        return names
    return set()


def _handler_type(handler: ast.ExceptHandler) -> str | None:
    """Return the broad-catch kind, or ``None`` if the handler is specific."""
    if handler.type is None:
        return "bare_except"
    names = _type_names(handler.type)
    if "BaseException" in names:
        return "base_exception"
    if "Exception" in names:
        return "broad_exception"
    return None


def _body_facts(handler: ast.ExceptHandler) -> dict[str, bool]:
    """Derive observability facts from a handler body via AST walk."""
    logs = reraises = has_print = aborts = flashes = False
    only_pass = len(handler.body) == 1 and isinstance(handler.body[0], ast.Pass)
    module = ast.Module(body=list(handler.body), type_ignores=[])
    for node in ast.walk(module):
        if isinstance(node, ast.Raise):
            reraises = True
        elif isinstance(node, ast.Call):
            func = node.func
            name = (
                func.attr
                if isinstance(func, ast.Attribute)
                else func.id
                if isinstance(func, ast.Name)
                else ""
            )
            if isinstance(func, ast.Attribute) and func.attr in _LOG_METHODS:
                logs = True
            if name in _LOG_FUNCS:
                logs = True
            if name == "print":
                has_print = True
            if name == "abort":
                aborts = True
            if name == "flash":
                flashes = True
    return {
        "logs": logs,
        "reraises": reraises,
        "has_print": has_print,
        "aborts": aborts,
        "flashes": flashes,
        "only_pass": only_pass,
    }


def _own_lines(
    source_lines: list[str],
    handler: ast.ExceptHandler,
    nested: list[ast.ExceptHandler],
) -> list[str]:
    """Source lines belonging directly to ``handler``, excluding nested handlers.

    A marker on a *nested* handler's line must not leak up to the enclosing
    handler (an outer ``except`` that re-raises would otherwise be mis-read as
    intentional). We attribute a marker only to its innermost enclosing handler.
    """
    excluded: set[int] = set()
    h_start, h_end = handler.lineno, handler.end_lineno or handler.lineno
    for child in nested:
        if child is handler:
            continue
        c_start, c_end = child.lineno, child.end_lineno or child.lineno
        if h_start <= c_start and c_end <= h_end:
            excluded.update(range(c_start, c_end + 1))
    return [
        source_lines[ln - 1]
        for ln in range(h_start, h_end + 1)
        if ln not in excluded
    ]


def _marker(own_lines: list[str]) -> str | None:
    """Find an inline ``# failopen:`` justification marker in the handler's own lines."""
    span = "\n".join(own_lines)
    if _MARKER_INTENTIONAL in span:
        return "intentional"
    if _MARKER_FAIL_CLOSED in span:
        return "fail-closed"
    return None


def _marker_reason(own_lines: list[str], token: str) -> str:
    """Extract the human reason after a ``# failopen: <token>:`` marker."""
    needle = f"failopen: {token}"
    for line in own_lines:
        idx = line.find(needle)
        if idx != -1:
            rest = line[idx + len(needle):].lstrip(":-— ").strip()
            return rest
    return ""


def _owner(rel_path: str) -> str:
    """Map a source path to a fail-domain owner (sensitivity ordering matters)."""
    p = rel_path.lower()
    if "auth" in p:
        return "auth"
    if "storage" in p or "/r2" in p or "upload" in p or "backup" in p:
        return "storage"
    if "audit" in p or "security" in p:
        return "audit"
    if "cache" in p or "redis" in p:
        return "cache"
    if any(k in p for k in ("notification", "push", "telemetry", "metric", "analytics", "rum")):
        return "telemetry"
    if p.startswith("foms/api/channel"):
        return "channel"
    if p.startswith("foms/api"):
        return "api"
    if p.startswith("foms/services"):
        return "services"
    if p.startswith("foms/web"):
        return "web"
    if p.startswith("foms/persistence"):
        return "persistence"
    if p.startswith("foms/platform"):
        return "platform"
    return "runtime"


def _disposition(facts: dict[str, bool], marker: str | None) -> str:
    """Assign a disposition from body facts and any inline marker.

    ``LOG_AND_CONTINUE`` is reserved for handlers that actually wire a logger
    (``facts["logs"]``). Everything else that keeps running is
    ``SWALLOW_BY_CONTROL_FLOW`` -- including ``print``/``flash``-only handlers,
    which notify stdout or the end user but leave no operator log line.

    :param facts: body facts from :func:`_body_facts`.
    :param marker: inline ``# failopen:`` marker token, or ``None``.
    :return: one of :data:`DISPOSITIONS`.
    """
    if marker == "intentional":
        return "INTENTIONAL"
    if marker == "fail-closed":
        return "FAIL_CLOSED"
    if facts["reraises"] or facts["aborts"]:
        return "FAIL_CLOSED"
    if facts["logs"]:
        return "LOG_AND_CONTINUE"
    # Truly silent: no observability, no explicit close, no marker.
    if facts["only_pass"]:
        return "UNCLASSIFIED"
    # Continues without a logger: control-flow swallow (return/continue/fallback)
    # or print/flash-only. Pinned at a no-growth baseline by the release gate.
    return "SWALLOW_BY_CONTROL_FLOW"


def _justification(facts: dict[str, bool], marker: str | None, reason: str) -> str:
    """Short, deterministic rationale string for the inventory entry."""
    if marker in ("intentional", "fail-closed"):
        return reason or f"marker:{marker}"
    if facts["reraises"]:
        return "re-raises"
    if facts["aborts"]:
        return "abort()"
    if facts["logs"]:
        return "logs via logger/log_handled_exception"
    if facts["has_print"]:
        return "print only, no logger (API-ERROR-01 owns stdout->logger migration)"
    if facts["flashes"]:
        return "flash() user notice only, no operator log line"
    if facts["only_pass"]:
        return "silent pass -- no logging, no marker (RESOLVE)"
    return "swallow-and-continue via control flow; no logger wired"


def _iter_files() -> list[Path]:
    files = [
        p
        for p in FOMS_DIR.rglob("*.py")
        if "__pycache__" not in p.parts
    ]
    files += [REPO_ROOT / name for name in ROOT_RUNTIME]
    return sorted(files)


def scan() -> list[dict[str, Any]]:
    """Return every broad catch under ``foms/`` + root runtime, classified.

    Returns:
        A list of inventory records sorted by ``(path, lineno)``. Each record
        carries ``path``, ``lineno``, ``handler_type``, ``disposition``,
        ``owner``, ``has_logging`` and ``justification``.
    """
    records: list[dict[str, Any]] = []
    for path in _iter_files():
        if not path.exists():
            continue
        source = path.read_text(encoding="utf-8")
        try:
            tree = ast.parse(source)
        except SyntaxError:
            continue
        source_lines = source.splitlines()
        rel = str(path.relative_to(REPO_ROOT)).replace("\\", "/")
        all_handlers = [
            n for n in ast.walk(tree) if isinstance(n, ast.ExceptHandler)
        ]
        for node in all_handlers:
            kind = _handler_type(node)
            if kind is None:
                continue
            facts = _body_facts(node)
            own_lines = _own_lines(source_lines, node, all_handlers)
            marker = _marker(own_lines)
            reason = _marker_reason(own_lines, marker) if marker else ""
            disposition = _disposition(facts, marker)
            has_logging = bool(facts["logs"])
            records.append(
                {
                    "path": rel,
                    "lineno": node.lineno,
                    "handler_type": kind,
                    "disposition": disposition,
                    "owner": _owner(rel),
                    "has_logging": has_logging,
                    "justification": _justification(facts, marker, reason),
                }
            )
    records.sort(key=lambda r: (r["path"], r["lineno"]))
    return records


def build_inventory() -> dict[str, Any]:
    """Assemble the full inventory document (summary + counts + entries)."""
    records = scan()
    disposition_counts = Counter(r["disposition"] for r in records)
    owner_counts = Counter(r["owner"] for r in records)
    silent_pass = [
        f"{r['path']}:{r['lineno']}"
        for r in records
        if r["disposition"] == "UNCLASSIFIED"
    ]
    fail_closed = [
        f"{r['path']}:{r['lineno']}"
        for r in records
        if r["disposition"] == "FAIL_CLOSED"
    ]
    swallow = [r for r in records if r["disposition"] == "SWALLOW_BY_CONTROL_FLOW"]
    return {
        "packet": "FAILOPEN-01",
        "summary": (
            "P1-29 broad/silent exception-handler inventory for foms/ + root "
            "runtime. Every broad catch (except Exception/BaseException/bare) is "
            "classified LOG_AND_CONTINUE / SWALLOW_BY_CONTROL_FLOW / FAIL_CLOSED "
            "/ INTENTIONAL. UNCLASSIFIED (silent `pass`, no logging, no marker) "
            "must be 0; SWALLOW_BY_CONTROL_FLOW (continues with no logger wired) "
            "is pinned at a no-growth baseline (AUDIT-LOG T11)."
        ),
        "scope": "foms/**.py + root runtime (" + ", ".join(ROOT_RUNTIME) + ")",
        "overlap_api_error_01": (
            "API-ERROR-01 owns response/stdout exposure (print_exc/str(e) -> "
            "log_handled_exception). This packet owns swallow classification. "
            "Sites that log via log_handled_exception are LOG_AND_CONTINUE here."
        ),
        "marker_convention": (
            "Silent-by-design catches carry an inline "
            "`# failopen: intentional: <reason>` (or `fail-closed`) marker; the "
            "scanner reads it as the justification. No bare allowlist, no lint-disable."
        ),
        "baselines": {
            "broad_total": len(records),
            "unclassified": disposition_counts.get("UNCLASSIFIED", 0),
            "swallow_by_control_flow": len(swallow),
        },
        "disposition_counts": dict(sorted(disposition_counts.items())),
        "owner_counts": dict(sorted(owner_counts.items())),
        "swallow_by_control_flow_owner_counts": dict(
            sorted(Counter(r["owner"] for r in swallow).items())
        ),
        "fail_closed_sites": fail_closed,
        "unclassified_sites": silent_pass,
        "catches": records,
    }


def write_inventory(path: Path = INVENTORY_PATH) -> dict[str, Any]:
    """Generate the inventory and write it to ``path`` as pretty JSON."""
    inventory = build_inventory()
    path.write_text(
        json.dumps(inventory, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return inventory


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="Print counts without writing the inventory file.",
    )
    args = parser.parse_args()
    if args.check:
        inv = build_inventory()
        print(json.dumps({
            "broad_total": inv["baselines"]["broad_total"],
            "dispositions": inv["disposition_counts"],
            "unclassified": inv["baselines"]["unclassified"],
        }, ensure_ascii=False, indent=2))
        return 0
    inv = write_inventory()
    print(
        f"wrote {INVENTORY_PATH.relative_to(REPO_ROOT)}: "
        f"{inv['baselines']['broad_total']} broad catches, "
        f"{inv['baselines']['unclassified']} unclassified"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
