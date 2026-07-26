"""API-ERROR-01: unexpected-exception response/log containment.

Verifies that:

1. An *unhandled* exception on an API route returns the contained
   ``INTERNAL_ERROR`` JSON (no ``str(e)`` / traceback / path / SQL) with a
   ``request_id``, and the server logs the stack exactly once (protected).
2. A *handled* 500 that echoes ``str(e)`` into the body is scrubbed at the
   response boundary (the historical P1-28 leak pattern).
3. Expected domain errors (4xx) keep their mapping and message.
4. Static guard: no raw ``print(traceback)`` / ``print_exc`` survives in
   ``foms/``, and response ``str(e)`` leaks do not grow past the inventory
   baseline.
"""

import json
import logging
import re
from pathlib import Path

import pytest
from flask import abort, jsonify

_LEAK = "SELECT * FROM users WHERE token='SUPERSECRETVALUE' at /var/secret/path.py"

# Substrings that must never reach the client on an unexpected 500.
_FORBIDDEN = [
    "SELECT",
    "SUPERSECRETVALUE",
    "/var/secret/path.py",
    "Traceback",
    "ValueError",
    'File "',
]

_REPO_ROOT = Path(__file__).resolve().parents[2]
_FOMS_DIR = _REPO_ROOT / "foms"
_INVENTORY = _REPO_ROOT / "docs" / "harness" / "foms_api_error_leak_inventory.json"


def _register_error_probe_routes(app):
    """Register throwaway routes that exercise each error path (idempotent).

    ``add_url_rule`` may only be called before the app handles its first request.
    We therefore register at module import (collection) time — before any test
    makes a request — so this file is independent of alphabetical ordering: a
    request-making domain test sorting earlier would otherwise lock the shared
    app and turn these registrations into ``add_url_rule`` errors.
    """
    if "err_unhandled" in app.view_functions:
        return

    def err_unhandled():
        raise ValueError(_LEAK)

    def err_handled_500():
        try:
            raise ValueError(_LEAK)
        except ValueError as e:  # historical P1-28 leak pattern
            return jsonify({"success": False, "message": str(e)}), 500

    def err_domain_409_json():
        return jsonify({"success": False, "message": "도메인 오류 DOMAINKEEP"}), 409

    def err_domain_400_abort():
        abort(400, description="입력이 올바르지 않습니다 DOMAINKEEP")

    app.add_url_rule("/api/__err_unhandled", "err_unhandled", err_unhandled)
    app.add_url_rule("/api/__err_handled_500", "err_handled_500", err_handled_500)
    app.add_url_rule("/api/__err_domain_409", "err_domain_409", err_domain_409_json)
    app.add_url_rule("/api/__err_domain_400", "err_domain_400", err_domain_400_abort)


# Register at import time (before the shared app handles any request), so the
# probe routes exist regardless of test-file execution order.
from app import app as _shared_app  # noqa: E402

_register_error_probe_routes(_shared_app)


@pytest.fixture(autouse=True)
def _test_error_routes(app):
    """Safety net: ensure probe routes exist (idempotent no-op after import)."""
    _register_error_probe_routes(app)
    return app


def _no_leak(body: str) -> None:
    for token in _FORBIDDEN:
        assert token not in body, f"sensitive token leaked to client: {token!r}"


def test_unhandled_exception_is_contained(app):
    """Unhandled 500 -> contained INTERNAL_ERROR JSON, request_id, no leak."""
    app.config["PROPAGATE_EXCEPTIONS"] = False  # let error handlers run
    try:
        client = app.test_client()
        resp = client.get("/api/__err_unhandled")
    finally:
        app.config.pop("PROPAGATE_EXCEPTIONS", None)

    assert resp.status_code == 500
    body = resp.get_data(as_text=True)
    _no_leak(body)
    data = resp.get_json()
    assert data["success"] is False
    assert data["error"]["code"] == "INTERNAL_ERROR"
    assert data["error"]["request_id"]
    assert resp.headers.get("X-Request-ID")


def test_handled_500_str_e_is_scrubbed(client):
    """A handler that returns str(e) in a 500 body is scrubbed at the boundary."""
    resp = client.get("/api/__err_handled_500")
    assert resp.status_code == 500
    body = resp.get_data(as_text=True)
    _no_leak(body)
    data = resp.get_json()
    assert data["error"]["code"] == "INTERNAL_ERROR"
    assert data["error"]["request_id"]


def test_domain_json_4xx_mapping_preserved(client):
    """Expected 4xx JSON errors keep their status and message (not scrubbed)."""
    resp = client.get("/api/__err_domain_409")
    assert resp.status_code == 409
    body = resp.get_data(as_text=True)
    assert "DOMAINKEEP" in body


def test_domain_abort_4xx_mapping_preserved(client):
    """abort(4xx) keeps its status (domain mapping preserved)."""
    resp = client.get("/api/__err_domain_400")
    assert resp.status_code == 400


def test_server_log_records_stack_once(app, caplog):
    """Unhandled 500 logs the stack exactly once, without leaking secrets."""
    app.config["PROPAGATE_EXCEPTIONS"] = False
    try:
        client = app.test_client()
        with caplog.at_level(logging.ERROR):
            client.get("/api/__err_unhandled")
    finally:
        app.config.pop("PROPAGATE_EXCEPTIONS", None)

    with_stack = [r for r in caplog.records if r.levelno >= logging.ERROR and r.exc_info]
    assert len(with_stack) == 1, f"expected 1 stack log, got {len(with_stack)}"
    # The message (not the allowed stack) must not carry the raw secret.
    assert "SUPERSECRETVALUE" not in with_stack[0].getMessage()


# --------------------------------------------------------------------------
# Static guard: prevent regression of raw stdout leaks / response str(e) growth
# --------------------------------------------------------------------------

_PRINT_EXC = re.compile(r"print\(\s*traceback\.format_exc|traceback\.print_exc\(")
_RESP_STR_E_500 = re.compile(r"return jsonify\(.*str\(e\).*\)\s*,\s*500")


def _scan_foms(pattern: re.Pattern) -> list[str]:
    hits = []
    for path in _FOMS_DIR.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        for i, line in enumerate(text.splitlines(), 1):
            if pattern.search(line):
                hits.append(f"{path.relative_to(_REPO_ROOT)}:{i}")
    return hits


def test_no_raw_traceback_print_in_foms():
    """No source file may write a raw traceback to stdout (use log_handled_exception)."""
    hits = _scan_foms(_PRINT_EXC)
    assert hits == [], f"raw print(traceback)/print_exc must be 0, found: {hits}"


def test_response_str_e_leaks_do_not_grow():
    """str(e)-in-500-response count must not exceed the recorded inventory baseline."""
    baseline = json.loads(_INVENTORY.read_text(encoding="utf-8"))["baselines"][
        "response_str_e_500"
    ]
    actual = len(_scan_foms(_RESP_STR_E_500))
    assert actual <= baseline, f"response str(e) 500 leaks grew: {actual} > {baseline}"
