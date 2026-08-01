"""REV-99 — order mutation architecture enforcement gate (release gate).

Seals the REV-00 mutation concurrency contract across the whole app. Composes
four architecture invariants that must all hold before the enforcement flag can
flip global If-Match on:

1. **Writer inventory + drift** (:mod:`tools.harness.order_mutation_writer_scan`):
   every persisted order mutation — ``flag_modified(order, 'structured_data')``
   or a direct ``mutation_version`` bump — is classified CANONICAL /
   VERSIONED_DIRECT / AUDITED_RECOVERY (all carry the version/If-Match contract)
   or EXTERNAL (a residual direct writer with no contract). The committed
   inventory equals a fresh scan, so a *new or moved* direct writer turns this
   suite red. EXTERNAL sites are the pinned, owner-tagged report set (release
   target EXTERNAL == 0; STATE-GUARD-homologous baseline + drift).

2. **Consumer error envelope** (reuses API-ERROR-01): every JSON error response
   is neutralised at the single ``foms/platform/http.py`` after_request choke
   point to the ``INTERNAL_ERROR`` envelope (no ``str(e)`` leak). Proven live via
   a boundary probe + the pinned API-ERROR-01 leak inventory (drift guard).

3. **Offline queued writer 0**: the offline surface is a read-only snapshot; the
   only apply path is OPS-APPROVAL-gated recovery, never an autonomous queued
   writer. No ``/api/foms/offline`` route accepts a mutation method.

4. **Enforcement flag**: :func:`if_match_enforced` gates global 428 with a
   **safe default (OFF)** — flag ON makes a missing-If-Match mutation raise
   ``PreconditionRequiredError`` (428); default OFF never forces 428 (no live
   breakage). Route cutover to the flag is downstream packets' work.

Investigation note (report, no fix): REV-99 does not migrate EXTERNAL writers —
each is owned by a downstream packet and pinned here for owner review.
"""

import importlib.util
import json
from pathlib import Path

import pytest
from flask import jsonify

from db import db_session
from models import Order
from foms.services.orders.revision import (
    IF_MATCH_ENFORCED_CONFIG,
    PreconditionRequiredError,
    execute_order_mutation,
    if_match_enforced,
)

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SCANNER_PATH = _REPO_ROOT / "tools" / "harness" / "order_mutation_writer_scan.py"
_INVENTORY_PATH = _REPO_ROOT / "docs" / "harness" / "foms_order_mutation_writer_inventory.json"
_ALLOWLIST_PATH = _REPO_ROOT / "docs" / "harness" / "foms_order_mutation_writer_allowlist.json"
_API_ERROR_INVENTORY = _REPO_ROOT / "docs" / "harness" / "foms_api_error_leak_inventory.json"

_H = "a" * 64  # sha256-hex placeholder for scope/request hashes


def _load_scanner():
    """Import the standalone scanner module (``tools/`` is not a package)."""
    spec = importlib.util.spec_from_file_location("order_mutation_writer_scan", _SCANNER_PATH)
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


def _create_order() -> int:
    """Persist a minimal ERP order and return its id."""
    order = Order(
        received_date="2026-04-07",
        customer_name="REV99",
        phone="010-0000-0000",
        address="Seoul",
        product="Wardrobe",
        status="RECEIVED",
        manager_name="Alice",
        is_erp_order=True,
        structured_data={"workflow": {"stage": "RECEIVED"}},
    )
    db_session.add(order)
    db_session.commit()
    return order.id


# --------------------------------------------------------------------------- #
# 1a. Scanner correctness (synthetic).
# --------------------------------------------------------------------------- #

def _kinds(source: str) -> list:
    """Return the write-signal kind of every node in a source snippet."""
    import ast
    return [scan_mod._site_kind(n) for n in ast.walk(ast.parse(source))]


def test_scanner_detects_structured_flag_modified():
    """flag_modified(order, 'structured_data') is the JSONB mutation signal."""
    assert scan_mod.KIND_JSONB in _kinds("flag_modified(order, 'structured_data')")
    assert scan_mod.KIND_JSONB in _kinds("flag_modified(o, 'structured_data')")


def test_scanner_detects_mutation_version_bump():
    """A direct .mutation_version assignment is the version-bump signal."""
    assert scan_mod.KIND_VERSION in _kinds("order.mutation_version = 5")
    assert scan_mod.KIND_VERSION in _kinds("order.mutation_version = (order.mutation_version or 0) + 1")
    assert scan_mod.KIND_VERSION in _kinds("o.mutation_version += 1")


def test_scanner_ignores_lookalikes():
    """Other JSONB keys / other version columns are not order-mutation signals."""
    assert scan_mod.KIND_JSONB not in _kinds("flag_modified(row, 'other_json')")
    assert scan_mod.KIND_VERSION not in _kinds("draft.row_version = 2")
    assert scan_mod.KIND_VERSION not in _kinds("ticket.row_version = (ticket.row_version or 0) + 1")
    # bare module-level column definition (Name target, not Attribute) is ignored
    assert all(k is None for k in _kinds("mutation_version = Column(Integer)"))


def test_classify_site_allowlist_vs_external():
    """A canonical path inherits its classification; any other path is EXTERNAL+owner."""
    allow = scan_mod.load_allowlist()
    canon, owner, _ = scan_mod._classify_site("foms/services/orders/revision.py", allow)
    assert canon == "CANONICAL" and owner
    ext, ext_owner, _ = scan_mod._classify_site("foms/api/some/brand_new_writer.py", allow)
    assert ext == "EXTERNAL" and ext_owner  # synthetic external is caught + owner-tagged


# --------------------------------------------------------------------------- #
# 1b. Inventory drift + classification completeness (writer gate).
# --------------------------------------------------------------------------- #

def test_inventory_matches_fresh_scan(fresh_scan, inventory):
    """Committed inventory == fresh scan. A new/moved direct writer turns this red."""
    assert inventory["writers"] == fresh_scan, (
        "inventory is stale; regenerate with "
        "`python tools/harness/order_mutation_writer_scan.py`"
    )


def test_every_writer_is_classified(fresh_scan):
    """No writer may be un-classified (every site carries a valid classification)."""
    valid = set(scan_mod.CLASSIFICATIONS)
    kinds = {scan_mod.KIND_JSONB, scan_mod.KIND_VERSION}
    for r in fresh_scan:
        assert r["classification"] in valid, f"bad classification: {r}"
        assert r["kind"] in kinds, f"bad kind: {r}"


def test_canonical_files_have_no_external(fresh_scan):
    """Every writer in an allowlisted file is canonical/versioned/recovery, never EXTERNAL."""
    allow_paths = {e["path"] for e in scan_mod.load_allowlist()}
    for r in fresh_scan:
        if r["path"] in allow_paths:
            assert r["classification"] != "EXTERNAL", (
                f"allowlisted file yielded EXTERNAL: {r['path']}:{r['lineno']}"
            )


def test_revision_engine_is_canonical(fresh_scan):
    """The REV-00 engine's own version bump is classified CANONICAL (allowlist wired)."""
    engine = [r for r in fresh_scan if r["path"] == "foms/services/orders/revision.py"]
    assert engine, "expected the REV-00 engine to bump mutation_version"
    assert all(r["classification"] == "CANONICAL" for r in engine)


# --------------------------------------------------------------------------- #
# 1c. Release gate: missing (EXTERNAL) writers pinned + owned + drift-guarded.
# --------------------------------------------------------------------------- #

def test_no_new_external_writers(fresh_scan, inventory):
    """No EXTERNAL (contract-less) writer outside the reviewed baseline (release gate / drift).

    A residual order-mutation writer that a downstream packet has not migrated to
    the canonical engine — and that is not already in the reviewed, owner-tagged
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
        "new/moved EXTERNAL order-mutation writer detected outside the reviewed "
        "baseline; route it through REV-00 execute_order_mutation (version bump + "
        "If-Match + idempotency), or — only if it genuinely carries the contract "
        "(direct FOR UPDATE version bump / audited recovery) — allowlist its file "
        "with a justified reason and regenerate the inventory"
    )


def test_every_external_site_has_owner(inventory):
    """Each residual EXTERNAL writer names the packet responsible for migrating it."""
    for s in inventory["external_sites"]:
        assert s["owner"], f"EXTERNAL without owner: {s['path']}:{s['lineno']}"


def test_baselines_present(inventory):
    """Inventory records scan size + classification distribution for auditing."""
    assert inventory["packet"] == "REV-99"
    assert inventory["baselines"]["total"] == len(inventory["writers"])
    assert inventory["baselines"]["external"] == len(inventory["external_sites"])
    assert sum(inventory["classification_counts"].values()) == len(inventory["writers"])


# --------------------------------------------------------------------------- #
# 2. Consumer error envelope (str(e) leak 0) — reuses API-ERROR-01.
# --------------------------------------------------------------------------- #

def test_error_boundary_is_registered(app):
    """The single after_request containment choke point is wired into the app."""
    funcs = [f for fs in app.after_request_funcs.values() for f in fs]
    names = {getattr(f, "__name__", "") for f in funcs}
    assert "_contain_error_responses" in names, (
        "API-ERROR-01 response boundary missing; consumers could leak str(e)"
    )


def test_consumer_500_str_e_is_scrubbed_at_boundary(app):
    """A mutation consumer that returns str(e) in a 500 JSON body is neutralised."""
    leak = "SELECT token='SUPERSECRET' at /var/secret/path.py"
    with app.test_request_context("/api/__rev99_consumer_probe"):
        resp = jsonify({"success": False, "message": leak})
        resp.status_code = 500
        out = app.process_response(resp)
        body = out.get_data(as_text=True)
    assert leak not in body and "SUPERSECRET" not in body
    data = json.loads(body)
    assert data["error"]["code"] == "INTERNAL_ERROR"
    assert data["error"]["request_id"]


def test_api_error_leak_inventory_pinned():
    """Every recorded str(e)-in-500 site is contained at the boundary (drift guard)."""
    inv = json.loads(_API_ERROR_INVENTORY.read_text(encoding="utf-8"))
    contained = inv["sites"]["response_str_e_500_contained_at_boundary"]
    assert inv["baselines"]["response_str_e_500"] == len(contained), (
        "API-ERROR-01 str(e)-500 baseline drifted from its contained-site list"
    )


# --------------------------------------------------------------------------- #
# 3. Offline queued writer 0.
# --------------------------------------------------------------------------- #

def test_no_offline_mutation_writer_route(app):
    """The offline surface is read-only; no /api/foms/offline route is a mutation."""
    mutation_methods = {"POST", "PUT", "PATCH", "DELETE"}
    offending = [
        rule.endpoint
        for rule in app.url_map.iter_rules()
        if (rule.rule or "").startswith("/api/foms/offline")
        and (set(rule.methods or ()) & mutation_methods)
    ]
    assert not offending, f"offline queued writer route(s) found: {offending}"


def test_offline_recovery_is_ops_approval_gated():
    """The only offline apply path consumes an OPS-APPROVAL token (not an autonomous writer)."""
    src = (_REPO_ROOT / "foms" / "services" / "orders" / "offline_recovery.py").read_text(
        encoding="utf-8"
    )
    assert "consume_same_db" in src, "offline recovery apply must be OPS-APPROVAL gated"


# --------------------------------------------------------------------------- #
# 4. Enforcement flag (428 ON, safe default OFF).
# --------------------------------------------------------------------------- #

def test_if_match_enforced_default_off(app):
    """Safe default: with no config (and under TESTING), If-Match is NOT enforced."""
    with app.app_context():
        app.config.pop(IF_MATCH_ENFORCED_CONFIG, None)
        assert if_match_enforced() is False


def test_if_match_enforced_reads_flag(app):
    """The flag is a plain config opt-in (REV_IF_MATCH_ENFORCED)."""
    with app.app_context():
        app.config[IF_MATCH_ENFORCED_CONFIG] = True
        try:
            assert if_match_enforced() is True
        finally:
            app.config.pop(IF_MATCH_ENFORCED_CONFIG, None)


def test_enforcement_on_blocks_missing_if_match_with_428(app):
    """Flag ON -> a mutation with no expected_version raises PreconditionRequiredError (428)."""
    oid = _create_order()

    def _mutate(_session, _orders):  # must NOT be reached (428 raises first)
        raise AssertionError("mutation ran despite missing If-Match")

    with pytest.raises(PreconditionRequiredError) as exc:
        execute_order_mutation(
            db_session,
            actor_user_id=1,
            policy_id="REV99_ENFORCE_TEST",
            order_ids=[oid],
            scope_hash=_H,
            request_hash=_H,
            mutation=_mutate,
            expected_versions={},          # no If-Match supplied
            require_if_match=True,         # flag ON delegates this
        )
    assert exc.value.status_code == 428


def test_default_off_does_not_force_428(app):
    """Safe default: require_if_match=if_match_enforced() (OFF) reaches the mutation, no 428."""
    oid = _create_order()

    class _Reached(Exception):
        pass

    def _mutate(_session, _orders):
        raise _Reached()  # reaching here proves the precondition passed (no 428)

    with app.app_context():
        app.config.pop(IF_MATCH_ENFORCED_CONFIG, None)
        assert if_match_enforced() is False
        with pytest.raises(_Reached):
            execute_order_mutation(
                db_session,
                actor_user_id=1,
                policy_id="REV99_SAFE_DEFAULT",
                order_ids=[oid],
                scope_hash=_H,
                request_hash=_H,
                mutation=_mutate,
                expected_versions=None,               # client sent no If-Match
                require_if_match=if_match_enforced(),  # OFF -> False -> no 428
            )
