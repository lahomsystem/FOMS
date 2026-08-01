"""Validation of the FOMS bug-audit packet manifest (PACKET-HARNESS-00 core).

Verifies docs/harness/foms_bugfix_packet_tests.json against the report §5 / §5.2
SSOT: exact 124-packet set, explicit-edge reference integrity, acyclicity of the
effective graph (explicit union dependency_classes), the exact 18-member
backfill_artifact set, the packet_harness rule, REV-99's exact 111 dependencies,
created_tests shape, and the deploy-checks registry. Negative cases prove the
validators actually turn unknown deps / cycles / bad paths / bad owners red.
"""
from __future__ import annotations

import json
from collections import deque
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
MANIFEST_PATH = REPO_ROOT / "docs" / "harness" / "foms_bugfix_packet_tests.json"
DEPLOY_CHECKS_PATH = REPO_ROOT / "docs" / "harness" / "foms_deploy_checks.json"

ENTRY_KEYS = {
    "depends_on", "dependency_classes", "commands", "existing_regressions",
    "created_tests", "browser_scenarios", "deploy_check_ids", "deployment_evidence_mode",
}
CLASS_KEYS = {"packet_harness", "backfill_artifact", "write_guard", "postgres"}
EVIDENCE_MODES = {"PROVIDER_BOOTSTRAP", "HEARTBEAT"}
PACKET_HARNESS_FALSE = {"BASE-00", "PACKET-HARNESS-00"}

# --- §5.2 exact 124-packet set (independent transcription) --------------------
EXPECTED_PACKETS = frozenset({
    "BASE-00", "PACKET-HARNESS-00", "OPS-ROUTE-01", "API-ERROR-01", "FAILOPEN-01",
    "REQUEST-LIMIT-01", "PGTEST-00", "OPS-APPROVAL-00", "BACKFILL-ARTIFACT-00", "CUTOVER-MODE-01",
    "REV-00", "REV-CLEANUP-01", "SIDEFX-00", "SIDEFX-WORKER-01", "SIDEFX-RETENTION-01",
    "REV-99", "RELEASE-GATE-00", "ASSIGNMENT-00", "CREW-00", "SHIPMENT-REFERENCE-01",
    "ITEM-ID-00", "MIG-WEB-RETIRE-01", "SECRET-01", "SECRET-02", "SESSION-SIGNING-STATE-00",
    "SESSION-SIGNING-SECRET-01", "FE-SYNTAX", "FE-XSS", "STORED-XSS-01", "SURFACE-GATE-01",
    "DESIGNER-RETIRE-01", "PUSH-01", "PACK-01", "ERR-UX-01", "AUTH-01",
    "WRITE-GUARD-01", "AUTH-ACCOUNT-01", "PASSWORD-POLICY-01", "AUTH-FINANCE-01", "AUTH-QUEST-READ-01",
    "AUTH-QUEST-01", "CHANNEL-AUTH-01", "CHANNEL-FUNCTION-CONTRACT-01", "CHANNEL-WEBHOOK-AUTH-01", "CHANNEL-WRITER-01",
    "DELETE-CORE-00", "DELETE-BULK-01", "DELETE-TRASH-01", "DELETE-RETENTION-01", "AUTH-IMPERSONATION-01",
    "ACTOR-STATE-01", "CHAT-ROOM-01", "CHAT-MESSAGE-01", "CHAT-SOCKET-AUTH-01", "URGENT-CALL-01",
    "TASK-BACKFILL-00", "TASK-01", "WDC-XSS-01", "WDC-AUTH-01", "WDC-LINK-FENCE-00",
    "WDC-LINK-BACKFILL-00", "WDC-LINK-01", "WDC-LINK-CLEANUP-01", "ERP-ESTIMATE-01", "CALL-LOG-01",
    "EVENT-REVERT-01", "STATE-MODEL-00", "STATE-AXES-REPAIR-00", "PRODUCTION-BACKFILL-00", "QUEST-BACKFILL-00",
    "AS-BACKFILL-00", "STATE-CORE-00", "STATE-PROD-01", "STATE-PROD-ACTIONS-01", "CONSTRUCTION-BACKFILL-00",
    "STATE-CONST-CS-01", "STATE-DRAWING-01", "DRAWING-REVISION-BACKFILL-00", "STATE-AS-01", "STATE-QUEST-01",
    "DATA-01", "DATA-MEASUREMENT-01", "SHIPMENT-WRITER-01", "ORDER-CREATE-01", "ORDER-COPY-01",
    "ORDER-IMPORT-01", "CHANNEL-INBOUND-ORDER-01", "STATE-FORM-01", "STATE-OVERLAY-01", "DRAFT-LIFECYCLE-01",
    "STORAGE-WRITER-01", "STATE-LEGACY-01", "STATE-CONTROLS-01", "STATE-GUARD-01", "WIZ-01",
    "WIZ-PRESET-01", "WIZ-TRANSFER-01", "WIZ-DELETE-01", "UPLOAD-01", "FILE-LEGACY-AUDIT-00",
    "FILE-LEGACY-BACKFILL-01", "FILE-01", "UPLOAD-INTENT-01", "UPLOAD-02", "BLUEPRINT-01",
    "UPLOAD-CHAT-01", "CHAT-FILE-01", "SHELL-01", "HISTORY-01", "ROUTE-01",
    "SW-01", "OFFLINE-01", "STARTUP-SCHEMA-01", "STARTUP-BACKFILL-01", "STARTUP-ADMIN-01",
    "STARTUP-PURE-01", "SCALE-AS-01", "SCALE-CHANNEL-01", "SCALE-SKETCHUP-01", "BACKUP-01",
    "PROXY-01", "RUM-INGEST-01", "WAM-TELEMETRY-01", "INDEX-OPS-01",
})

# --- §5 last paragraph: exact 18-member backfill_artifact set -----------------
BACKFILL_ARTIFACT_18 = frozenset({
    "ASSIGNMENT-00", "CREW-00", "ITEM-ID-00", "TASK-BACKFILL-00", "WDC-LINK-BACKFILL-00",
    "WDC-LINK-CLEANUP-01", "STATE-MODEL-00", "STATE-AXES-REPAIR-00", "PRODUCTION-BACKFILL-00",
    "QUEST-BACKFILL-00", "AS-BACKFILL-00", "CONSTRUCTION-BACKFILL-00", "DRAWING-REVISION-BACKFILL-00",
    "FILE-LEGACY-AUDIT-00", "FILE-LEGACY-BACKFILL-01", "BLUEPRINT-01", "CHAT-FILE-01", "STARTUP-BACKFILL-01",
})

# --- §5 REV-99 depends_on exact 111 list --------------------------------------
REV99_DEPENDS_ON = frozenset({
    "OPS-ROUTE-01", "API-ERROR-01", "FAILOPEN-01", "REQUEST-LIMIT-01", "PGTEST-00", "OPS-APPROVAL-00",
    "CUTOVER-MODE-01", "BACKFILL-ARTIFACT-00", "REV-00", "REV-CLEANUP-01", "SIDEFX-00", "SIDEFX-WORKER-01",
    "SIDEFX-RETENTION-01", "ASSIGNMENT-00", "CREW-00", "SHIPMENT-REFERENCE-01", "ITEM-ID-00", "MIG-WEB-RETIRE-01",
    "SECRET-01", "SECRET-02", "SESSION-SIGNING-STATE-00", "SESSION-SIGNING-SECRET-01", "FE-SYNTAX", "FE-XSS",
    "STORED-XSS-01", "SURFACE-GATE-01", "DESIGNER-RETIRE-01", "PUSH-01", "PACK-01", "ERR-UX-01", "AUTH-01",
    "WRITE-GUARD-01", "AUTH-ACCOUNT-01", "PASSWORD-POLICY-01", "AUTH-FINANCE-01", "AUTH-QUEST-READ-01",
    "AUTH-QUEST-01", "CHANNEL-AUTH-01", "CHANNEL-FUNCTION-CONTRACT-01", "CHANNEL-WEBHOOK-AUTH-01",
    "CHANNEL-WRITER-01", "DELETE-CORE-00", "DELETE-BULK-01", "DELETE-TRASH-01", "DELETE-RETENTION-01",
    "AUTH-IMPERSONATION-01", "ACTOR-STATE-01", "CHAT-ROOM-01", "CHAT-MESSAGE-01", "CHAT-SOCKET-AUTH-01",
    "URGENT-CALL-01", "TASK-BACKFILL-00", "TASK-01", "WDC-XSS-01", "WDC-AUTH-01", "WDC-LINK-FENCE-00",
    "WDC-LINK-BACKFILL-00", "WDC-LINK-01", "WDC-LINK-CLEANUP-01", "ERP-ESTIMATE-01", "CALL-LOG-01",
    "EVENT-REVERT-01", "STATE-MODEL-00", "STATE-AXES-REPAIR-00", "PRODUCTION-BACKFILL-00", "QUEST-BACKFILL-00",
    "AS-BACKFILL-00", "STATE-CORE-00", "STATE-PROD-01", "STATE-PROD-ACTIONS-01", "CONSTRUCTION-BACKFILL-00",
    "STATE-CONST-CS-01", "STATE-DRAWING-01", "DRAWING-REVISION-BACKFILL-00", "STATE-AS-01", "STATE-QUEST-01",
    "DATA-01", "DATA-MEASUREMENT-01", "SHIPMENT-WRITER-01", "ORDER-CREATE-01", "ORDER-COPY-01", "ORDER-IMPORT-01",
    "CHANNEL-INBOUND-ORDER-01", "STATE-FORM-01", "STATE-OVERLAY-01", "DRAFT-LIFECYCLE-01", "STORAGE-WRITER-01",
    "STATE-LEGACY-01", "STATE-CONTROLS-01", "STATE-GUARD-01", "WIZ-01", "WIZ-PRESET-01", "WIZ-TRANSFER-01",
    "WIZ-DELETE-01", "UPLOAD-01", "FILE-LEGACY-AUDIT-00", "FILE-LEGACY-BACKFILL-01", "FILE-01", "UPLOAD-INTENT-01",
    "UPLOAD-02", "BLUEPRINT-01", "UPLOAD-CHAT-01", "CHAT-FILE-01", "SHELL-01", "HISTORY-01", "ROUTE-01",
    "SW-01", "OFFLINE-01", "PROXY-01", "RUM-INGEST-01", "WAM-TELEMETRY-01",
})


# --- reusable validators (exercised by both positive and negative cases) ------
def effective_deps(entry: dict) -> set[str]:
    """explicit depends_on union the class-implied edges (report §5 formula)."""
    deps = set(entry["depends_on"])
    dc = entry["dependency_classes"]
    if dc.get("packet_harness"):
        deps.add("PACKET-HARNESS-00")
    if dc.get("backfill_artifact"):
        deps.add("BACKFILL-ARTIFACT-00")
    return deps


def unknown_dep_refs(manifest: dict) -> set[str]:
    """Explicit deps that are not themselves packet keys."""
    ids = set(manifest)
    bad = set()
    for entry in manifest.values():
        for dep in entry["depends_on"]:
            if dep not in ids:
                bad.add(dep)
    return bad


def toposort(manifest: dict) -> list[str]:
    """Kahn topological sort over the effective graph. Raises on a cycle."""
    ids = set(manifest)
    indeg = {p: 0 for p in ids}
    radj: dict[str, list[str]] = {p: [] for p in ids}
    for p, entry in manifest.items():
        for d in effective_deps(entry):
            if d not in ids:
                continue
            radj[d].append(p)
            indeg[p] += 1
    q = deque(p for p in ids if indeg[p] == 0)
    order: list[str] = []
    while q:
        n = q.popleft()
        order.append(n)
        for m in radj[n]:
            indeg[m] -= 1
            if indeg[m] == 0:
                q.append(m)
    if len(order) != len(ids):
        raise ValueError(f"cycle: sorted {len(order)} of {len(ids)}")
    return order


def transitive_closure(manifest: dict, pid: str) -> set[str]:
    seen: set[str] = set()
    q = deque(effective_deps(manifest[pid]))
    while q:
        d = q.popleft()
        if d in seen or d not in manifest:
            continue
        seen.add(d)
        q.extend(effective_deps(manifest[d]))
    return seen


def bad_created_tests(manifest: dict) -> list[tuple[str, object]]:
    """created_tests entries that violate the {path, owner_packet} contract."""
    ids = set(manifest)
    problems: list[tuple[str, object]] = []
    for pid, entry in manifest.items():
        for item in entry["created_tests"]:
            if not isinstance(item, dict) or set(item) != {"path", "owner_packet"}:
                problems.append((pid, item))
                continue
            path = item["path"]
            owner = item["owner_packet"]
            if not isinstance(path, str) or not path.endswith(".py") or "\\" in path or not path.strip():
                problems.append((pid, item))
            elif owner not in ids:
                problems.append((pid, item))
    return problems


# --- fixtures -----------------------------------------------------------------
@pytest.fixture(scope="module")
def manifest() -> dict:
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def deploy_checks() -> dict:
    return json.loads(DEPLOY_CHECKS_PATH.read_text(encoding="utf-8"))


# --- positive tests -----------------------------------------------------------
def test_packet_set_exact(manifest):
    keys = set(manifest)
    assert keys == EXPECTED_PACKETS, {
        "missing": EXPECTED_PACKETS - keys,
        "extra": keys - EXPECTED_PACKETS,
    }
    assert len(manifest) == 124


def test_entry_schema(manifest):
    for pid, entry in manifest.items():
        assert set(entry) == ENTRY_KEYS, (pid, set(entry) ^ ENTRY_KEYS)
        dc = entry["dependency_classes"]
        assert set(dc) == CLASS_KEYS, (pid, set(dc))
        assert all(isinstance(v, bool) for v in dc.values()), pid
        for key in ("depends_on", "commands", "existing_regressions",
                    "created_tests", "browser_scenarios", "deploy_check_ids"):
            assert isinstance(entry[key], list), (pid, key)
        assert entry["deployment_evidence_mode"] in EVIDENCE_MODES, pid


def test_no_cross_packet_preseed(manifest):
    # §8.1: packets append ONLY their own entry; no future/foreign preseed.
    # created_tests owner_packet must be the packet itself; commands must be
    # plain strings (no arbitrary eval objects). Empty seed is allowed but not
    # required -- packets legitimately fill their own lists as they land.
    for pid, entry in manifest.items():
        for item in entry["created_tests"]:
            assert isinstance(item, dict) and item.get("owner_packet") == pid, (
                pid, "created_tests owner must be self (anti-preseed)", item,
            )
        for cmd in entry["commands"]:
            assert isinstance(cmd, str) and cmd.strip(), (pid, "command", cmd)


def test_explicit_deps_reference_existing_packets(manifest):
    assert unknown_dep_refs(manifest) == set()


def test_graph_is_acyclic(manifest):
    order = toposort(manifest)
    assert len(order) == 124


def test_backfill_artifact_set_exact(manifest):
    got = {p for p, e in manifest.items() if e["dependency_classes"]["backfill_artifact"]}
    assert got == BACKFILL_ARTIFACT_18, {
        "missing": BACKFILL_ARTIFACT_18 - got,
        "extra": got - BACKFILL_ARTIFACT_18,
    }
    assert len(got) == 18


def test_packet_harness_rule(manifest):
    false_ids = {p for p, e in manifest.items() if not e["dependency_classes"]["packet_harness"]}
    assert false_ids == PACKET_HARNESS_FALSE, false_ids
    # PACKET-HARNESS-00 depends only on BASE-00; BASE-00 depends on nothing.
    assert manifest["PACKET-HARNESS-00"]["depends_on"] == ["BASE-00"]
    assert manifest["BASE-00"]["depends_on"] == []


def test_rev99_depends_on_exact(manifest):
    got = manifest["REV-99"]["depends_on"]
    assert len(got) == len(set(got)) == 111
    assert set(got) == REV99_DEPENDS_ON, {
        "missing": REV99_DEPENDS_ON - set(got),
        "extra": set(got) - REV99_DEPENDS_ON,
    }


def test_transitive_completion_computable(manifest):
    # bootstrap roots
    assert transitive_closure(manifest, "BASE-00") == set()
    assert transitive_closure(manifest, "PACKET-HARNESS-00") == {"BASE-00"}
    # every non-bootstrap packet ultimately reaches the harness + base
    deep = transitive_closure(manifest, "STATE-GUARD-01")
    assert {"PACKET-HARNESS-00", "BASE-00"} <= deep
    # a backfill packet reaches BACKFILL-ARTIFACT-00 via the class edge
    assert "BACKFILL-ARTIFACT-00" in transitive_closure(manifest, "ASSIGNMENT-00")


def test_deployment_evidence_mode_consistent_with_cutover(manifest):
    # HEARTBEAT iff the packet is CUTOVER-MODE-01 or transitively depends on it.
    for pid, entry in manifest.items():
        depends_on_cutover = pid == "CUTOVER-MODE-01" or "CUTOVER-MODE-01" in transitive_closure(manifest, pid)
        expected = "HEARTBEAT" if depends_on_cutover else "PROVIDER_BOOTSTRAP"
        assert entry["deployment_evidence_mode"] == expected, (pid, entry["deployment_evidence_mode"])


def test_created_tests_shape(manifest):
    assert bad_created_tests(manifest) == []


def test_deploy_checks_registry(deploy_checks, manifest):
    assert deploy_checks["schema_version"] == 1
    checks = deploy_checks["checks"]
    assert checks, "at least the §8.2.1 effect-source checks must be seeded"
    expected_ids = {
        "CUTOVER_SIDEFX_COMPAT", "CUTOVER_STORAGE_DRAIN",
        "CUTOVER_NOTIFICATION_DRAIN", "CUTOVER_NONE_QUIET",
    }
    assert expected_ids <= set(checks)
    for cid, spec in checks.items():
        assert set(spec) == {"owner_packet", "command_template"}, cid
        assert spec["owner_packet"] in manifest, (cid, spec["owner_packet"])
        assert isinstance(spec["command_template"], str) and spec["command_template"].strip(), cid


# --- negative cases: the validators must turn each defect red -----------------
def _entry(depends_on=None, **classes):
    dc = {"packet_harness": False, "backfill_artifact": False,
          "write_guard": False, "postgres": False}
    dc.update(classes)
    return {
        "depends_on": list(depends_on or []),
        "dependency_classes": dc,
        "commands": [], "existing_regressions": [], "created_tests": [],
        "browser_scenarios": [], "deploy_check_ids": [],
        "deployment_evidence_mode": "PROVIDER_BOOTSTRAP",
    }


def test_negative_unknown_dependency():
    m = {"A-00": _entry(["GHOST-00"]), "B-00": _entry()}
    assert unknown_dep_refs(m) == {"GHOST-00"}


def test_negative_cycle_detected():
    m = {"A-00": _entry(["B-00"]), "B-00": _entry(["A-00"])}
    with pytest.raises(ValueError):
        toposort(m)


def test_negative_bad_created_test_path():
    m = {"A-00": _entry()}
    m["A-00"]["created_tests"] = [{"path": "", "owner_packet": "A-00"}]
    assert bad_created_tests(m)
    m["A-00"]["created_tests"] = [{"path": "tests\\win\\x.py", "owner_packet": "A-00"}]
    assert bad_created_tests(m)


def test_negative_bad_created_test_owner():
    m = {"A-00": _entry()}
    m["A-00"]["created_tests"] = [{"path": "tests/harness/x.py", "owner_packet": "NOPE-00"}]
    assert bad_created_tests(m)


def test_negative_good_created_test_passes():
    m = {"A-00": _entry()}
    m["A-00"]["created_tests"] = [{"path": "tests/harness/x.py", "owner_packet": "A-00"}]
    assert bad_created_tests(m) == []
