"""STATE-GUARD-01 — static main-stage / overlay direct-writer scan gate.

Single source of truth for the order state-write inventory. Walks ``foms/`` and
flags every *direct* assignment to the order main axis (``order.status`` /
``workflow.stage`` mirror ``erp_stage_code``) or its two overlays (logistics /
hold), then classifies each site against the canonical allowlist:

- ``CANONICAL`` — the write lives inside a canonical mutator module
  (:mod:`order_transition_service`, :mod:`stage_override`, :mod:`as_cycle_service`,
  :mod:`erp_sync_columns` mirror-sync). These *are* the single write path.
- ``CONSTRUCTOR`` — the write seeds the initial stage of a *new* order
  (:func:`order_create.create_order`).
- ``AUDITED_BACKFILL`` — an audited repair/backfill re-projection
  (:mod:`repair_order_state_axes`).
- ``EXTERNAL`` — a direct writer *outside* every allowlisted path. Per the
  SSOT (report line ~1073) the release target is ``EXTERNAL == 0``; any
  ``EXTERNAL`` site is a residual writer a STATE packet must migrate to the
  canonical engine. These are pinned + owner-tagged in the inventory and
  reported, never silently reclassified as canonical.

What counts as a main/overlay write (mirrors the canonical engine's own
``_apply_main`` / ``_apply_logistics`` / ``_apply_hold`` write targets):

- attribute ``.erp_stage_code`` / ``.erp_stage_updated_at`` (Order-only mirror);
- attribute ``.status`` / ``.original_status`` on an Order-shaped receiver;
- subscript key ``"stage"`` / ``"stage_updated_at"`` (``workflow.stage``);
- subscript key ``"logistics_status"`` (``shipment`` logistics overlay);
- subscript key ``"hold"`` under a ``workflow`` container (hold overlay).

Out of scope by design (owned by downstream sub-state-machines, exactly as the
canonical engine delegates AS/construction/delete/production): other models'
``.status`` (``run``/``attempt``/``log``…), and ``production["hold"]`` (the
production sub-overlay, distinct from ``workflow["hold"]``).

Run ``python tools/harness/state_writer_scan.py`` to (re)generate
``docs/harness/foms_state_writer_inventory.json``.

ponytail: ``.status``/``.original_status`` detection uses a receiver-name
heuristic (``order``/``o``/…); an Order stored under an unlisted variable name
would be missed. Upgrade path: type inference / a per-site marker if a false
negative appears. Attribute ``erp_stage_code`` and every subscript key are
Order-unambiguous and need no heuristic.
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
ALLOWLIST_PATH = REPO_ROOT / "docs" / "harness" / "foms_state_writer_allowlist.json"
INVENTORY_PATH = REPO_ROOT / "docs" / "harness" / "foms_state_writer_inventory.json"

# Order-only flat mirror columns (unambiguous — no other model carries these).
_MAIN_MIRROR_ATTRS = {"erp_stage_code", "erp_stage_updated_at"}
# Shared attribute names that are the main axis *only* on an Order receiver.
_MAIN_STATUS_ATTRS = {"status", "original_status"}
# Receiver names that denote an Order (heuristic; see module ceiling note).
_ORDER_NAMES = {
    "order", "o", "existing_order", "new_order", "db_order", "target_order",
    "order_obj", "ord", "restored_order", "src_order", "dst_order",
}
# Subscript keys and their axis. "hold" is scoped to a workflow container below.
_MAIN_KEYS = {"stage", "stage_updated_at"}
_LOGISTICS_KEYS = {"logistics_status"}
_HOLD_KEY = "hold"
_WORKFLOW_NAMES = {"workflow", "wf"}

AXIS_MAIN = "MAIN"
AXIS_LOGISTICS = "LOGISTICS"
AXIS_HOLD = "HOLD"

CLASSIFICATIONS = ("CANONICAL", "CONSTRUCTOR", "AUDITED_BACKFILL", "EXTERNAL")


def _const_str(node: ast.expr | None) -> str | None:
    """Return a subscript slice's string key, or ``None`` if it is not a str literal."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _receiver_leaf_name(node: ast.expr) -> str | None:
    """Best-effort leaf name of an attribute/subscript/name receiver chain."""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    if isinstance(node, ast.Subscript):
        return _const_str(node.slice)
    return None


def _is_order_receiver(node: ast.expr) -> bool:
    """Whether an attribute-write receiver denotes an Order (name heuristic)."""
    name = _receiver_leaf_name(node)
    return name in _ORDER_NAMES


def _is_workflow_container(node: ast.expr) -> bool:
    """Whether a subscript container is the ``workflow`` dict (scopes ``hold``)."""
    return _receiver_leaf_name(node) in _WORKFLOW_NAMES


def _classify_attr_target(target: ast.Attribute) -> tuple[str, str] | None:
    """Classify an attribute-assignment target as ``(kind, axis)`` or ``None``."""
    if target.attr in _MAIN_MIRROR_ATTRS:
        return ("attr_stage_mirror", AXIS_MAIN)
    if target.attr in _MAIN_STATUS_ATTRS and _is_order_receiver(target.value):
        return ("attr_status", AXIS_MAIN)
    return None


def _classify_subscript_target(target: ast.Subscript) -> tuple[str, str] | None:
    """Classify a subscript-assignment target as ``(kind, axis)`` or ``None``."""
    key = _const_str(target.slice)
    if key is None:
        return None
    if key in _MAIN_KEYS:
        return ("subscript_stage", AXIS_MAIN)
    if key in _LOGISTICS_KEYS:
        return ("subscript_logistics", AXIS_LOGISTICS)
    if key == _HOLD_KEY and _is_workflow_container(target.value):
        return ("subscript_hold", AXIS_HOLD)
    return None


def _classify_target(target: ast.expr) -> tuple[str, str] | None:
    """Dispatch a single assignment target to attr/subscript classifiers."""
    if isinstance(target, ast.Attribute):
        return _classify_attr_target(target)
    if isinstance(target, ast.Subscript):
        return _classify_subscript_target(target)
    return None


def _assignment_targets(node: ast.AST) -> list[ast.expr]:
    """Return the write targets of an assignment node (Assign/AnnAssign/AugAssign)."""
    if isinstance(node, ast.Assign):
        return list(node.targets)
    if isinstance(node, ast.AnnAssign) and node.value is not None:
        return [node.target]
    if isinstance(node, ast.AugAssign):
        return [node.target]
    return []


def load_allowlist(path: Path | None = None) -> list[dict[str, str]]:
    """Load the canonical/constructor/backfill allowlist (path + classification + reason).

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


def _classify_site(rel_path: str, allowlist: list[dict[str, str]]) -> tuple[str, str, str]:
    """Return ``(classification, owner, reason)`` for a write site via the allowlist.

    A finding whose path suffix-matches an allowlist entry inherits that entry's
    classification; otherwise it is ``EXTERNAL`` with a path-derived owner.
    """
    norm = rel_path.replace("\\", "/")
    for entry in allowlist:
        if norm.endswith(entry["path"].replace("\\", "/")):
            return (entry["classification"], entry.get("owner", ""), entry.get("reason", ""))
    return ("EXTERNAL", _external_owner(norm), "")


def _external_owner(rel_path: str) -> str:
    """Map an un-allowlisted writer path to the STATE packet that should migrate it."""
    p = rel_path
    if "/construction/" in p:
        return "STATE-CONST-CS"
    if "/drawing/" in p:
        return "STATE-DRAWING"
    if "/production/" in p:
        return "STATE-PROD"
    if p.endswith("web/orders/trash.py"):
        return "DELETE-TRASH"
    if p.endswith("web/orders/listing.py"):
        return "ORDER-CREATE"
    if p.endswith("api/orders/status.py") or p.endswith("api/orders/field_update.py"):
        return "STATE-LEGACY"
    if p.endswith("api/erp_orders_structured.py"):
        return "STATE-FORM"
    return "UNASSIGNED"


def _iter_files() -> list[Path]:
    """Every ``.py`` under ``foms/`` (excluding bytecode caches), sorted."""
    return sorted(p for p in FOMS_DIR.rglob("*.py") if "__pycache__" not in p.parts)


def scan(allowlist: list[dict[str, str]] | None = None) -> list[dict[str, Any]]:
    """Return every main/overlay direct writer under ``foms/``, classified.

    Args:
        allowlist: Allowlist entries; loaded from disk when omitted.

    Returns:
        Inventory records sorted by ``(path, lineno)``; each carries ``path``,
        ``lineno``, ``kind``, ``axis``, ``classification`` and ``owner``.
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
            for target in _assignment_targets(node):
                hit = _classify_target(target)
                if hit is None:
                    continue
                kind, axis = hit
                classification, owner, _reason = _classify_site(rel, allow)
                records.append({
                    "path": rel,
                    "lineno": getattr(node, "lineno", 0),
                    "kind": kind,
                    "axis": axis,
                    "classification": classification,
                    "owner": owner,
                })
    records.sort(key=lambda r: (r["path"], r["lineno"], r["kind"]))
    return records


def build_inventory() -> dict[str, Any]:
    """Assemble the full state-writer inventory document (summary + counts + sites)."""
    records = scan()
    class_counts = Counter(r["classification"] for r in records)
    axis_counts = Counter(r["axis"] for r in records)
    external = [
        {"path": r["path"], "lineno": r["lineno"], "axis": r["axis"],
         "kind": r["kind"], "owner": r["owner"]}
        for r in records if r["classification"] == "EXTERNAL"
    ]
    return {
        "packet": "STATE-GUARD-01",
        "summary": (
            "Order main-stage / overlay direct-writer inventory for foms/. Every "
            "direct assignment to order.status / workflow.stage(+erp_stage_code "
            "mirror) / shipment.logistics_status / workflow.hold is classified "
            "CANONICAL / CONSTRUCTOR / AUDITED_BACKFILL / EXTERNAL. Release target: "
            "EXTERNAL == 0 (every write routes through the canonical engine). "
            "EXTERNAL sites below are pinned residual writers reported to their "
            "owner STATE packet — the drift gate keeps the set from growing."
        ),
        "scope": "foms/**.py",
        "baselines": {
            "total": len(records),
            "external": class_counts.get("EXTERNAL", 0),
        },
        "classification_counts": dict(sorted(class_counts.items())),
        "axis_counts": dict(sorted(axis_counts.items())),
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
    parser = argparse.ArgumentParser(description="STATE-GUARD-01 state-writer scan gate")
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
        f"{inv['baselines']['total']} state writers, "
        f"{inv['baselines']['external']} external"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
