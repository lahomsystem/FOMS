"""STATE-GUARD-01 — main-stage / overlay direct-writer inventory + release gate.

Seals order state mutation behind the canonical engine. The scanner
(:mod:`tools.harness.state_writer_scan`) finds every *direct* assignment to the
order main axis (``order.status`` / ``workflow.stage`` / ``erp_stage_code``
mirror) or its overlays (``shipment.logistics_status`` / ``workflow.hold``) and
classifies each against the canonical allowlist. This suite enforces:

- the scanner detects each main/overlay write shape and ignores look-alikes
  (another model's ``.status``, the ``production["hold"]`` sub-overlay);
- every writer is classified CANONICAL / CONSTRUCTOR / AUDITED_BACKFILL /
  EXTERNAL — no writer is un-classified;
- the committed inventory equals a fresh scan, so a *new or moved* direct writer
  turns this suite red (drift guard);
- no EXTERNAL writer appears outside the reviewed, owner-tagged baseline — a
  residual writer that a STATE packet has not migrated to the canonical engine
  fails the release gate;
- canonical/constructor/backfill files carry no EXTERNAL writer.

Release target (SSOT report ~line 1073): ``EXTERNAL == 0`` — every state write
routes through the canonical engine. The current pinned baseline is the residual
set reported to owner packets; the drift guard keeps it from growing.
"""

import ast
import importlib.util
import json
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SCANNER_PATH = _REPO_ROOT / "tools" / "harness" / "state_writer_scan.py"
_INVENTORY_PATH = _REPO_ROOT / "docs" / "harness" / "foms_state_writer_inventory.json"
_ALLOWLIST_PATH = _REPO_ROOT / "docs" / "harness" / "foms_state_writer_allowlist.json"


def _load_scanner():
    """Import the standalone scanner module (``tools/`` is not a package)."""
    spec = importlib.util.spec_from_file_location("state_writer_scan", _SCANNER_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


scan_mod = _load_scanner()


@pytest.fixture(scope="module")
def fresh_scan():
    return scan_mod.scan()


@pytest.fixture(scope="module")
def inventory():
    return json.loads(_INVENTORY_PATH.read_text(encoding="utf-8"))


# --------------------------------------------------------------------------- #
# Scanner correctness (synthetic).
# --------------------------------------------------------------------------- #

def _classify_src(source: str) -> list:
    """Classify every assignment target in a source snippet."""
    tree = ast.parse(source)
    out = []
    for node in ast.walk(tree):
        for target in scan_mod._assignment_targets(node):
            out.append(scan_mod._classify_target(target))
    return out


def test_scanner_detects_main_axis_writes():
    """order.status / erp_stage_code mirror / workflow.stage subscript are main."""
    assert _classify_src("order.status = 'X'") == [("attr_status", "MAIN")]
    assert _classify_src("order.original_status = 'X'") == [("attr_status", "MAIN")]
    assert _classify_src("order.erp_stage_code = v") == [("attr_stage_mirror", "MAIN")]
    assert _classify_src("order.erp_stage_updated_at = v") == [("attr_stage_mirror", "MAIN")]
    assert _classify_src("wf['stage'] = v") == [("subscript_stage", "MAIN")]
    assert _classify_src("workflow['stage_updated_at'] = v") == [("subscript_stage", "MAIN")]
    assert _classify_src("structured_data['workflow']['stage'] = v") == [("subscript_stage", "MAIN")]


def test_scanner_detects_overlay_writes():
    """logistics_status and workflow.hold subscripts are the two overlays."""
    assert _classify_src("shipment['logistics_status'] = v") == [("subscript_logistics", "LOGISTICS")]
    assert _classify_src("workflow['hold'] = {}") == [("subscript_hold", "HOLD")]
    assert _classify_src("wf['hold'] = {}") == [("subscript_hold", "HOLD")]


def test_scanner_ignores_lookalikes():
    """Other models' .status and the production['hold'] sub-overlay are not order state."""
    assert _classify_src("run.status = 'COMPLETED'") == [None]
    assert _classify_src("attempt.status = 'READY'") == [None]
    assert _classify_src("log.status = 'accepted'") == [None]
    assert _classify_src("production['hold'] = {}") == [None]  # production sub-overlay, not workflow.hold
    assert _classify_src("cfg['stage_name'] = v") == [None]  # different key
    assert _classify_src("row['logistics'] = v") == [None]  # partial key, not logistics_status


def test_classify_site_allowlist_vs_external():
    """A canonical path inherits its classification; any other path is EXTERNAL."""
    allow = scan_mod.load_allowlist()
    canon, owner, _ = scan_mod._classify_site(
        "foms/services/orders/order_transition_service.py", allow
    )
    assert canon == "CANONICAL" and owner
    ext, ext_owner, _ = scan_mod._classify_site(
        "foms/api/some/new_endpoint.py", allow
    )
    assert ext == "EXTERNAL" and ext_owner  # synthetic external is caught + owner-tagged


# --------------------------------------------------------------------------- #
# Inventory drift + classification completeness.
# --------------------------------------------------------------------------- #

def test_inventory_matches_fresh_scan(fresh_scan, inventory):
    """Committed inventory == fresh scan. A new/moved direct writer turns this red."""
    assert inventory["writers"] == fresh_scan, (
        "inventory is stale; regenerate with "
        "`python tools/harness/state_writer_scan.py`"
    )


def test_every_writer_is_classified(fresh_scan):
    """No writer may be un-classified (every site carries a valid classification)."""
    valid = set(scan_mod.CLASSIFICATIONS)
    for r in fresh_scan:
        assert r["classification"] in valid, f"bad classification: {r}"
        assert r["axis"] in (scan_mod.AXIS_MAIN, scan_mod.AXIS_LOGISTICS, scan_mod.AXIS_HOLD)


def test_canonical_files_have_no_external(fresh_scan):
    """Every writer in an allowlisted file is canonical/constructor/backfill, never EXTERNAL."""
    allow_paths = {e["path"] for e in scan_mod.load_allowlist()}
    for r in fresh_scan:
        if r["path"] in allow_paths:
            assert r["classification"] != "EXTERNAL", (
                f"allowlisted file yielded EXTERNAL: {r['path']}:{r['lineno']}"
            )


def test_allowlisted_sites_are_canonical(fresh_scan):
    """The canonical engine's own writes are classified CANONICAL (allowlist wired)."""
    engine = [
        r for r in fresh_scan
        if r["path"] == "foms/services/orders/order_transition_service.py"
    ]
    assert engine, "expected the canonical engine to contain state writes"
    assert all(r["classification"] == "CANONICAL" for r in engine)
    create = [r for r in fresh_scan if r["path"] == "foms/services/orders/order_create.py"]
    assert create and all(r["classification"] == "CONSTRUCTOR" for r in create)


# --------------------------------------------------------------------------- #
# Release gate.
# --------------------------------------------------------------------------- #

def test_no_new_external_writers(fresh_scan, inventory):
    """No EXTERNAL writer outside the reviewed baseline (release gate / drift).

    A residual direct writer that a STATE packet has not migrated to the
    canonical engine — and that is not already in the reviewed, owner-tagged
    baseline — turns this suite red.
    """
    fresh_ext = sorted(
        (r["path"], r["lineno"], r["kind"])
        for r in fresh_scan if r["classification"] == "EXTERNAL"
    )
    pinned_ext = sorted(
        (s["path"], s["lineno"], s["kind"]) for s in inventory["external_sites"]
    )
    assert fresh_ext == pinned_ext, (
        "new/moved EXTERNAL state-writer detected outside the reviewed baseline; "
        "migrate it to the canonical engine (transition_order / stage_override / "
        "as_cycle_service), or — only if it is genuinely canonical-equivalent — "
        "allowlist its file with a justified reason and regenerate the inventory"
    )


def test_every_external_site_has_owner(inventory):
    """Each residual EXTERNAL writer names the STATE packet responsible for it."""
    for s in inventory["external_sites"]:
        assert s["owner"], f"EXTERNAL without owner: {s['path']}:{s['lineno']}"


def test_baselines_present(inventory):
    """Inventory records scan size + classification distribution for auditing."""
    assert inventory["packet"] == "STATE-GUARD-01"
    assert inventory["baselines"]["total"] == len(inventory["writers"])
    assert inventory["baselines"]["external"] == len(inventory["external_sites"])
    assert sum(inventory["classification_counts"].values()) == len(inventory["writers"])
