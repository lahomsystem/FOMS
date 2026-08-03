"""FAILOPEN-01: broad/silent exception-handler inventory + release gate.

P1-29: broad ``except Exception`` blocks with a silent ``pass`` hide auth /
storage / audit / cache / telemetry failures. This suite pins the classified
inventory produced by :mod:`tools.harness.failopen_scan` and enforces the
release gate:

- the scanner detects every broad catch and ignores specific handlers;
- every broad catch is classified (owner + disposition), so
  ``UNCLASSIFIED`` is 0;
- the committed inventory matches a fresh scan, so a *new* or moved broad
  catch that has not been reviewed turns this suite red;
- every silent ``except ...: pass`` is resolved (logging added or an inline
  ``# failopen: intentional`` justification) -- release-mode silent broad
  ``pass`` is 0;
- ``FAIL_CLOSED`` entries genuinely re-raise / ``abort()`` (sample check);
- ``INTENTIONAL`` entries carry a justification (no bare allowlist).

Overlap with API-ERROR-01: that packet owns response/stdout *exposure*
(``print_exc``/``str(e)`` -> ``log_handled_exception``). This packet owns
*swallow* classification; a site that logs via ``log_handled_exception`` is
``LOG_AND_CONTINUE`` here.
"""

import ast
import importlib.util
import json
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SCANNER_PATH = _REPO_ROOT / "tools" / "harness" / "failopen_scan.py"
_INVENTORY_PATH = _REPO_ROOT / "docs" / "harness" / "foms_failopen_inventory.json"


def _load_scanner():
    """Import the standalone scanner module (``tools/`` is not a package)."""
    spec = importlib.util.spec_from_file_location("failopen_scan", _SCANNER_PATH)
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


# --------------------------------------------------------------------------
# Scanner correctness
# --------------------------------------------------------------------------

def _only_handler(source: str) -> ast.ExceptHandler:
    tree = ast.parse(source)
    return next(n for n in ast.walk(tree) if isinstance(n, ast.ExceptHandler))


def test_scanner_detects_broad_and_ignores_specific():
    """Broad forms are flagged; a specific ``except ValueError`` is not."""
    assert scan_mod._handler_type(_only_handler("try:\n a\nexcept Exception:\n pass")) == "broad_exception"
    assert scan_mod._handler_type(_only_handler("try:\n a\nexcept:\n pass")) == "bare_except"
    assert scan_mod._handler_type(_only_handler("try:\n a\nexcept BaseException:\n pass")) == "base_exception"
    assert scan_mod._handler_type(_only_handler("try:\n a\nexcept (ValueError, Exception):\n pass")) == "broad_exception"
    assert scan_mod._handler_type(_only_handler("try:\n a\nexcept ValueError:\n pass")) is None
    assert scan_mod._handler_type(_only_handler("try:\n a\nexcept (KeyError, TypeError):\n pass")) is None


def test_disposition_logic():
    """Body facts + marker map to the expected disposition."""
    disp = scan_mod._disposition
    assert disp({"logs": True, "has_print": False, "flashes": False, "reraises": False, "aborts": False, "only_pass": False}, None) == "LOG_AND_CONTINUE"
    assert disp({"logs": False, "has_print": False, "flashes": False, "reraises": True, "aborts": False, "only_pass": False}, None) == "FAIL_CLOSED"
    assert disp({"logs": False, "has_print": False, "flashes": False, "reraises": False, "aborts": True, "only_pass": False}, None) == "FAIL_CLOSED"
    # silent bare pass with no marker -> the P1-29 danger
    assert disp({"logs": False, "has_print": False, "flashes": False, "reraises": False, "aborts": False, "only_pass": True}, None) == "UNCLASSIFIED"
    # marker overrides
    assert disp({"logs": False, "has_print": False, "flashes": False, "reraises": False, "aborts": False, "only_pass": True}, "intentional") == "INTENTIONAL"


def test_nested_marker_does_not_leak_to_outer():
    """A marker on a nested inner handler must not reclassify the outer one."""
    src = (
        "try:\n"
        "    work()\n"
        "except Exception as exc:\n"          # outer: re-raises -> FAIL_CLOSED
        "    try:\n"
        "        cleanup()\n"
        "    except Exception:\n"
        "        pass  # failopen: intentional: cleanup best-effort\n"
        "    raise exc\n"
    )
    tree = ast.parse(src)
    handlers = [n for n in ast.walk(tree) if isinstance(n, ast.ExceptHandler)]
    lines = src.splitlines()
    outer = min(handlers, key=lambda h: h.lineno)
    inner = max(handlers, key=lambda h: h.lineno)
    assert scan_mod._marker(scan_mod._own_lines(lines, outer, handlers)) is None
    assert scan_mod._marker(scan_mod._own_lines(lines, inner, handlers)) == "intentional"


# --------------------------------------------------------------------------
# Release gate
# --------------------------------------------------------------------------

def _lineno_free(records):
    """Drop ``lineno`` and canonicalize ordering so pure line shifts don't gate.

    An edit anywhere above a broad catch shifts every ``lineno`` below it; the
    catch itself is unchanged. Comparing the multiset of lineno-free records
    keeps the real gate (a new/removed/reclassified catch still turns red)
    while making comment/whitespace-only shifts a non-event.
    """
    stripped = [{k: v for k, v in r.items() if k != "lineno"} for r in records]
    return sorted(stripped, key=lambda r: json.dumps(r, sort_keys=True, ensure_ascii=False))


def test_inventory_matches_fresh_scan(fresh_scan, inventory):
    """Committed inventory == fresh scan (lineno-insensitive). A new/removed/reclassified broad catch turns this red."""
    assert _lineno_free(inventory["catches"]) == _lineno_free(fresh_scan), (
        "inventory is stale; regenerate with "
        "`python tools/harness/failopen_scan.py`"
    )


def test_no_unclassified(fresh_scan, inventory):
    """No broad catch may be UNCLASSIFIED (silent pass with no logging/marker)."""
    unclassified = [c for c in fresh_scan if c["disposition"] == "UNCLASSIFIED"]
    assert unclassified == [], f"unclassified broad/silent catches: {unclassified}"
    assert inventory["baselines"]["unclassified"] == 0


def test_every_catch_has_owner_and_disposition(fresh_scan):
    """100% classification: every catch carries an owner and a valid disposition."""
    valid = {"LOG_AND_CONTINUE", "FAIL_CLOSED", "INTENTIONAL"}
    for c in fresh_scan:
        assert c["owner"], f"missing owner: {c}"
        assert c["disposition"] in valid, f"bad disposition: {c}"


def test_silent_pass_is_resolved(fresh_scan):
    """Every ``except ...: pass`` is resolved (never UNCLASSIFIED in release mode)."""
    for path in scan_mod._iter_files():
        if not path.exists():
            continue
        source = path.read_text(encoding="utf-8")
        try:
            tree = ast.parse(source)
        except SyntaxError:
            continue
        rel = str(path.relative_to(_REPO_ROOT)).replace("\\", "/")
        handlers = [n for n in ast.walk(tree) if isinstance(n, ast.ExceptHandler)]
        for h in handlers:
            if scan_mod._handler_type(h) is None:
                continue
            if not (len(h.body) == 1 and isinstance(h.body[0], ast.Pass)):
                continue
            marker = scan_mod._marker(scan_mod._own_lines(source.splitlines(), h, handlers))
            assert marker is not None, (
                f"silent broad `except: pass` with no justification marker at "
                f"{rel}:{h.lineno} -- add logging or a `# failopen: intentional` marker"
            )


# --------------------------------------------------------------------------
# Disposition integrity
# --------------------------------------------------------------------------

def _handler_at(path: str, lineno: int) -> ast.ExceptHandler:
    tree = ast.parse((_REPO_ROOT / path).read_text(encoding="utf-8"))
    for n in ast.walk(tree):
        if isinstance(n, ast.ExceptHandler) and n.lineno == lineno:
            return n
    raise AssertionError(f"no ExceptHandler at {path}:{lineno}")


def test_fail_closed_sites_actually_fail_closed(fresh_scan):
    """Every FAIL_CLOSED entry's body re-raises or calls abort() (fail closed)."""
    fail_closed = [c for c in fresh_scan if c["disposition"] == "FAIL_CLOSED"]
    assert fail_closed, "expected at least one FAIL_CLOSED entry"
    for c in fail_closed:
        # A marker-driven fail-closed is trusted via its justification.
        if c["justification"].startswith("marker:") or "failopen" in c["justification"]:
            continue
        handler = _handler_at(c["path"], c["lineno"])
        facts = scan_mod._body_facts(handler)
        assert facts["reraises"] or facts["aborts"], (
            f"FAIL_CLOSED but neither re-raises nor abort()s: {c['path']}:{c['lineno']}"
        )


def test_intentional_sites_have_justification(fresh_scan):
    """INTENTIONAL entries must carry a concrete reason (no bare allowlist)."""
    for c in fresh_scan:
        if c["disposition"] == "INTENTIONAL":
            assert c["justification"].strip(), (
                f"INTENTIONAL without justification: {c['path']}:{c['lineno']}"
            )


def test_baselines_present(inventory):
    """Inventory records the scan size + disposition distribution for auditing."""
    assert inventory["packet"] == "FAILOPEN-01"
    assert inventory["baselines"]["broad_total"] == len(inventory["catches"])
    assert sum(inventory["disposition_counts"].values()) == len(inventory["catches"])
