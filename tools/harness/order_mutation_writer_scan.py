"""REV-99 — order mutation writer architecture scan gate.

Single source of truth for the order *mutation* writer inventory (the REV-00
concurrency contract, distinct from STATE-GUARD-01's state-axis inventory).
Walks ``foms/`` and flags every site that *persists an order mutation* through
one of two unambiguous signals:

- a ``flag_modified(<recv>, "structured_data")`` call — the canonical JSONB
  dirty-marker every persisted ``Order.structured_data`` change must emit
  (project rule: ``copy.deepcopy`` + mutate + ``flag_modified``);
- a direct ``.mutation_version`` assignment — the REV-00 optimistic-concurrency
  version bump.

Both keys are Order-unambiguous (only :class:`models.Order` carries
``structured_data`` / ``mutation_version``), so no receiver heuristic is needed.

Each site's *file* is classified against the canonical allowlist:

- ``CANONICAL`` — the write routes through the REV-00 helper
  :func:`foms.services.orders.revision.execute_order_mutation` (version bump +
  If-Match + idempotency receipt), or is a canonical mutator the engine drives
  (:mod:`order_transition_service` / :mod:`stage_override` / :mod:`as_cycle_service`).
  These *are* the single versioned write path.
- ``VERSIONED_DIRECT`` — the write bumps ``mutation_version`` directly under a
  ``FOR UPDATE`` row lock (upload finalize / drawing transfer cancel). It honours
  the REV-00 contract with equivalent metadata rather than the helper.
- ``AUDITED_RECOVERY`` — an OPS-APPROVAL-gated, all-or-none offline recovery
  apply (:mod:`offline_recovery`); no autonomous/background replay.
- ``EXTERNAL`` — a direct writer *outside* every allowlisted path: it mutates
  order JSONB and commits **without** the version/If-Match contract. Per the SSOT
  (report line ~995) the release target is ``EXTERNAL == 0``; each ``EXTERNAL``
  site is a residual writer a downstream packet must migrate to the canonical
  engine. These are pinned + owner-tagged in the inventory and reported, never
  silently reclassified as canonical.

Run ``python tools/harness/order_mutation_writer_scan.py`` to (re)generate
``docs/harness/foms_order_mutation_writer_inventory.json``.

ponytail: classification is file-level (an allowlisted file that *also* held a
non-canonical direct writer would inherit the canonical tag). This mirrors
STATE-GUARD-01's accepted ceiling; the drift gate + owner review cover the gap,
and the write signals themselves are Order-unambiguous. Upgrade path: per-site
enclosing-call analysis if a false negative appears.
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
ALLOWLIST_PATH = REPO_ROOT / "docs" / "harness" / "foms_order_mutation_writer_allowlist.json"
INVENTORY_PATH = REPO_ROOT / "docs" / "harness" / "foms_order_mutation_writer_inventory.json"

# JSONB dirty-marker key that is the Order structured_data write signal.
_STRUCTURED_KEY = "structured_data"
# Order-only optimistic-concurrency version column (unambiguous attribute).
_VERSION_ATTR = "mutation_version"

KIND_JSONB = "flag_modified_structured_data"
KIND_VERSION = "mutation_version_bump"

CLASSIFICATIONS = ("CANONICAL", "VERSIONED_DIRECT", "AUDITED_RECOVERY", "EXTERNAL")


def _assignment_targets(node: ast.AST) -> list[ast.expr]:
    """Return the write targets of an assignment node (Assign/AnnAssign/AugAssign)."""
    if isinstance(node, ast.Assign):
        return list(node.targets)
    if isinstance(node, ast.AnnAssign) and node.value is not None:
        return [node.target]
    if isinstance(node, ast.AugAssign):
        return [node.target]
    return []


def _is_structured_flag_modified(node: ast.AST) -> bool:
    """Whether ``node`` is ``flag_modified(<recv>, "structured_data")``."""
    if not isinstance(node, ast.Call):
        return False
    fn = node.func
    name = fn.id if isinstance(fn, ast.Name) else (fn.attr if isinstance(fn, ast.Attribute) else None)
    if name != "flag_modified" or len(node.args) < 2:
        return False
    key = node.args[1]
    return isinstance(key, ast.Constant) and key.value == _STRUCTURED_KEY


def _is_version_bump_target(target: ast.expr) -> bool:
    """Whether an assignment target is ``<order>.mutation_version`` (Order-only attr)."""
    return isinstance(target, ast.Attribute) and target.attr == _VERSION_ATTR


def _site_kind(node: ast.AST) -> str | None:
    """Classify a node as an order-mutation write signal, or ``None``."""
    if _is_structured_flag_modified(node):
        return KIND_JSONB
    for target in _assignment_targets(node):
        if _is_version_bump_target(target):
            return KIND_VERSION
    return None


def load_allowlist(path: Path | None = None) -> list[dict[str, str]]:
    """Load the canonical/versioned/recovery allowlist (path + classification + reason).

    Args:
        path: Allowlist JSON path; defaults to the repo allowlist.

    Returns:
        Allowlist entries (empty when the file is absent).
    """
    p = path or ALLOWLIST_PATH
    if not p.exists():
        return []
    raw = json.loads(p.read_text(encoding="utf-8"))
    return list(raw.get("allow", []))


def _external_owner(rel_path: str) -> str:
    """Map an un-allowlisted mutation writer path to the packet that should migrate it."""
    p = rel_path
    if p.endswith("api/orders/status.py") or p.endswith("api/orders/field_update.py"):
        return "STATE-LEGACY-01"
    if p.endswith("services/orders/quest_transition_service.py") or p.endswith("api/quest.py"):
        return "STATE-QUEST-01"
    if p.endswith("services/orders/backfill_order_quests.py"):
        return "QUEST-BACKFILL-00"
    if p.endswith("services/orders/blueprint_projection.py"):
        return "BLUEPRINT-01"
    if p.endswith("api/drawing/erp_orders_revision.py"):
        return "DRAWING-REVISION-BACKFILL-00"
    if p.endswith("api/drawing/erp_orders_draftsman.py"):
        return "STATE-DRAWING-01"
    if "/drawing/" in p or p.endswith("services/notifications/drawing_order_change.py"):
        return "STATE-DRAWING-01"
    if p.endswith("api/cs/complete.py") or p.endswith("api/cs/confirm.py") or p.endswith("api/cs/dashboard.py"):
        return "STATE-CONST-CS-01"
    if p.endswith("api/events.py"):
        return "EVENT-REVERT-01"
    if p.endswith("services/order_geocode.py"):
        return "DATA-01"
    if p.endswith("api/wdcalculator/blueprint.py"):
        return "WDC-LINK-01"
    if p.endswith("web/orders/edit.py"):
        return "ORDER-CREATE-01"
    return "UNASSIGNED"


def _classify_site(rel_path: str, allowlist: list[dict[str, str]]) -> tuple[str, str, str]:
    """Return ``(classification, owner, reason)`` for a write site via the allowlist.

    A finding whose path suffix-matches an allowlist entry inherits that entry's
    classification/owner/reason; otherwise it is ``EXTERNAL`` with a path-derived
    owner.
    """
    norm = rel_path.replace("\\", "/")
    for entry in allowlist:
        if norm.endswith(entry["path"].replace("\\", "/")):
            return (entry["classification"], entry.get("owner", ""), entry.get("reason", ""))
    return ("EXTERNAL", _external_owner(norm), "")


def _iter_files() -> list[Path]:
    """Every ``.py`` under ``foms/`` (excluding bytecode caches), sorted."""
    return sorted(p for p in FOMS_DIR.rglob("*.py") if "__pycache__" not in p.parts)


def scan(allowlist: list[dict[str, str]] | None = None) -> list[dict[str, Any]]:
    """Return every order-mutation writer under ``foms/``, classified.

    Args:
        allowlist: Allowlist entries; loaded from disk when omitted.

    Returns:
        Inventory records sorted by ``(path, lineno, kind)``; each carries
        ``path``, ``lineno``, ``kind``, ``classification`` and ``owner``.
    """
    allow = allowlist if allowlist is not None else load_allowlist()
    records: list[dict[str, Any]] = []
    for path in _iter_files():
        try:
            source = path.read_text(encoding="utf-8")
            tree = ast.parse(source)
        except (OSError, UnicodeDecodeError, SyntaxError):
            continue
        rel = str(path.relative_to(REPO_ROOT)).replace("\\", "/")
        for node in ast.walk(tree):
            kind = _site_kind(node)
            if kind is None:
                continue
            classification, owner, _reason = _classify_site(rel, allow)
            records.append({
                "path": rel,
                "lineno": getattr(node, "lineno", 0),
                "kind": kind,
                "classification": classification,
                "owner": owner,
            })
    records.sort(key=lambda r: (r["path"], r["lineno"], r["kind"]))
    return records


def build_inventory() -> dict[str, Any]:
    """Assemble the full order-mutation-writer inventory document (summary + counts + sites)."""
    records = scan()
    class_counts = Counter(r["classification"] for r in records)
    kind_counts = Counter(r["kind"] for r in records)
    external = [
        {"path": r["path"], "lineno": r["lineno"], "kind": r["kind"], "owner": r["owner"]}
        for r in records if r["classification"] == "EXTERNAL"
    ]
    return {
        "packet": "REV-99",
        "summary": (
            "Order mutation writer inventory for foms/. Every persisted order "
            "mutation — flag_modified(order, 'structured_data') or a direct "
            "mutation_version bump — is classified CANONICAL (routes through "
            "REV-00 execute_order_mutation / canonical mutator) / VERSIONED_DIRECT "
            "(direct version bump under FOR UPDATE) / AUDITED_RECOVERY "
            "(OPS-APPROVAL offline apply) / EXTERNAL (direct writer with no "
            "version/If-Match contract). Release target: EXTERNAL == 0 (every "
            "order mutation carries version bump + If-Match/idempotency metadata). "
            "EXTERNAL sites below are pinned residual writers reported to their "
            "owner packet — the drift gate keeps the set from growing."
        ),
        "scope": "foms/**.py",
        "baselines": {
            "total": len(records),
            "external": class_counts.get("EXTERNAL", 0),
        },
        "classification_counts": dict(sorted(class_counts.items())),
        "kind_counts": dict(sorted(kind_counts.items())),
        "external_sites": external,
        "writers": records,
    }


def write_inventory(path: Path = INVENTORY_PATH) -> dict[str, Any]:
    """Generate the inventory and write it to ``path`` as pretty JSON."""
    inventory = build_inventory()
    path.write_text(
        json.dumps(inventory, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return inventory


def main(argv: list[str] | None = None) -> int:
    """CLI: regenerate the inventory, or ``--check`` to print counts only."""
    parser = argparse.ArgumentParser(description="REV-99 order-mutation-writer scan gate")
    parser.add_argument("--check", action="store_true",
                        help="Print counts without writing the inventory file.")
    args = parser.parse_args(argv)
    if args.check:
        inv = build_inventory()
        print(json.dumps({
            "total": inv["baselines"]["total"],
            "classifications": inv["classification_counts"],
            "external": inv["baselines"]["external"],
        }, ensure_ascii=False, indent=2))
        return 0
    inv = write_inventory()
    print(
        f"wrote {INVENTORY_PATH.relative_to(REPO_ROOT)}: "
        f"{inv['baselines']['total']} mutation writers, "
        f"{inv['baselines']['external']} external"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
