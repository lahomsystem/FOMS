"""REQUEST-LIMIT-01: pre-parse request body cap enforcement (P1-31).

Covers, all through the API-ERROR-01 JSON envelope (never HTML):

* per-category declared-``Content-Length`` caps (telemetry / login / normal /
  Excel / legacy) rejected pre-handler with 413, normal traffic untouched;
* the removed 500 MiB global cap (now 50 MiB + 256 KiB) and the active
  ``FomsRequest``;
* form ``max_form_memory_size`` (1 MiB) and ``max_form_parts`` (1000) with zero
  leftover temp files when a multipart parse aborts;
* unsupported ``Transfer-Encoding`` rejected with 415;
* presigned / direct-upload surfaces excluded from route caps (global still
  applies);
* streamed byte count as the final authority for a chunked body with no
  trustworthy declared length.
"""

import io
import tempfile

import pytest
from flask import request
from werkzeug.test import EnvironBuilder

from app import app as _app
from foms.platform.request_limits import GLOBAL_BODY_CAP, FomsRequest

_KIB = 1024
_MIB = 1024 * 1024

# category, path, whole-body cap in bytes (mirrors the REQUEST-LIMIT-01 manifest)
_CATEGORIES = [
    ("telemetry", "/api/foms/rum", 2 * _KIB),
    ("telemetry", "/channel/wam/api/telemetry", 2 * _KIB),
    ("login", "/login", 16 * _KIB),
    ("legacy", "/api/orders/1/attachments", 50 * _MIB + 256 * _KIB),
]


def _register_throwaway_routes() -> None:
    """Register body-reading probe routes on the shared app singleton.

    Done at import (collection) time so it runs before any test issues a
    request; the ``_got_first_request`` reset keeps it order-robust even if the
    app has already served a request (the shared-app singleton locks route
    setup otherwise).
    """
    if "limit_read_body" in _app.view_functions:
        return

    def limit_read_body():
        request.get_data()
        return "ok"

    def limit_read_form():
        # Touch the parser (files) and the stream (form) so the caps engage.
        _ = request.files
        _ = request.form
        return "ok"

    was_locked = _app._got_first_request
    _app._got_first_request = False
    try:
        # NORMAL default cap (1 MiB).
        _app.add_url_rule(
            "/api/__limit_read", "limit_read_body", limit_read_body, methods=["POST"]
        )
        # Excluded surface (matches ^/api/upload/session): route cap bypassed,
        # but the global ceiling and form-parser limits still apply.
        _app.add_url_rule(
            "/api/upload/session-test",
            "limit_read_form",
            limit_read_form,
            methods=["POST"],
        )
    finally:
        _app._got_first_request = was_locked


_register_throwaway_routes()


def _error(resp):
    """Assert a JSON (never HTML) body-limit envelope and return the error dict."""
    assert resp.mimetype == "application/json", "413/415 must be JSON, not HTML"
    data = resp.get_json()
    assert data["success"] is False
    return data["error"]


def _spoof_cl(client, path, content_length, data=b"x"):
    """POST a tiny body but a spoofed declared ``Content-Length`` header.

    Exercises the pre-handler declared check without transmitting the bytes.
    """
    return client.post(
        path, data=data, environ_overrides={"CONTENT_LENGTH": str(content_length)}
    )


# --------------------------------------------------------------------------
# Config / activation
# --------------------------------------------------------------------------


def test_global_500mib_cap_removed_and_fomsrequest_active(app):
    """The 500 MiB cap is gone (now 50 MiB + 256 KiB) and FomsRequest is wired."""
    assert app.config["MAX_CONTENT_LENGTH"] == GLOBAL_BODY_CAP
    assert app.config["MAX_CONTENT_LENGTH"] == 50 * _MIB + 256 * _KIB
    assert app.config["MAX_CONTENT_LENGTH"] != 500 * _MIB
    assert app.request_class is FomsRequest
    assert app.request_class.max_form_memory_size == 1 * _MIB
    assert app.request_class.max_form_parts == 1000


# --------------------------------------------------------------------------
# Per-category declared caps
# --------------------------------------------------------------------------


@pytest.mark.parametrize("category,path,cap", _CATEGORIES)
def test_declared_over_cap_returns_413_json(client, category, path, cap):
    """A declared body over the category cap is rejected 413 (JSON) pre-handler."""
    resp = _spoof_cl(client, path, cap + 1)
    assert resp.status_code == 413, f"{category} over cap should be 413"
    err = _error(resp)
    assert err["code"] == "REQUEST_BODY_TOO_LARGE"
    assert err["request_id"]


@pytest.mark.parametrize("category,path,cap", _CATEGORIES)
def test_normal_small_body_not_413(client, category, path, cap):
    """Normal-sized traffic to each category is not blocked."""
    resp = client.post(path, data=b"{}", content_type="application/json")
    assert resp.status_code != 413, f"{category} normal body must not be 413"


def test_boundary_exactly_at_cap_allowed(client):
    """A body exactly at the cap passes (declared check is strictly greater)."""
    resp = client.post("/api/foms/rum", data=b"x" * (2 * _KIB))
    assert resp.status_code != 413


# --------------------------------------------------------------------------
# Transfer-Encoding
# --------------------------------------------------------------------------


def test_bad_transfer_encoding_returns_415_json(client):
    """An unsupported Transfer-Encoding is rejected 415 (JSON)."""
    resp = client.post(
        "/api/foms/rum", data=b"{}", headers={"Transfer-Encoding": "gzip"}
    )
    assert resp.status_code == 415
    err = _error(resp)
    assert err["code"] == "UNSUPPORTED_TRANSFER_ENCODING"


# --------------------------------------------------------------------------
# Global ceiling + presigned/direct-upload exclusion
# --------------------------------------------------------------------------


def test_global_cap_over_50mib_returns_413(client):
    """Even an excluded surface is bounded by the 50 MiB + 256 KiB global cap."""
    resp = _spoof_cl(client, "/api/upload/session-test", GLOBAL_BODY_CAP + 1)
    assert resp.status_code == 413
    assert resp.mimetype == "application/json"


def test_presigned_route_excluded_from_route_cap(client):
    """A presigned/direct-upload surface skips route caps (2 MiB > NORMAL 1 MiB)."""
    resp = client.post(
        "/api/upload/session-test",
        data=b"x" * (2 * _MIB),
        content_type="application/octet-stream",
    )
    assert resp.status_code != 413, "excluded route must not apply the 1 MiB route cap"


# --------------------------------------------------------------------------
# Form parser limits + temp-file leak
# --------------------------------------------------------------------------


def test_form_memory_over_1mib_rejected(client):
    """A urlencoded form field over the 1 MiB memory limit is rejected 413."""
    body = b"a=" + b"x" * (1 * _MIB + 100)
    resp = client.post(
        "/api/upload/session-test",
        data=body,
        content_type="application/x-www-form-urlencoded",
    )
    assert resp.status_code == 413
    assert _error(resp)["code"] == "REQUEST_BODY_TOO_LARGE"


def test_form_parts_over_1000_rejected_without_tempfile_leak(
    client, tmp_path, monkeypatch
):
    """>1000 multipart parts is rejected 413 and leaves zero partial temp files.

    Two parts are large enough (>512000 bytes) to spill to disk before the part
    limit trips; the FomsRequest parser must close/unlink them.
    """
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))

    boundary = "----fomslimit"
    parts = []
    for i in range(2):  # spilled-to-disk file parts
        parts.append(f"--{boundary}".encode())
        parts.append(
            f'Content-Disposition: form-data; name="f{i}"; filename="f{i}.bin"'.encode()
        )
        parts.append(b"Content-Type: application/octet-stream")
        parts.append(b"")
        parts.append(b"y" * (600 * _KIB))
    for i in range(1001):  # tiny parts to exceed max_form_parts=1000
        parts.append(f"--{boundary}".encode())
        parts.append(
            f'Content-Disposition: form-data; name="t{i}"; filename="t{i}.txt"'.encode()
        )
        parts.append(b"")
        parts.append(b"z")
    parts.append(f"--{boundary}--".encode())
    body = b"\r\n".join(parts) + b"\r\n"

    resp = client.post(
        "/api/upload/session-test",
        data=body,
        content_type=f"multipart/form-data; boundary={boundary}",
    )
    assert resp.status_code == 413
    leftover = list(tmp_path.iterdir())
    assert leftover == [], f"partial temp files leaked: {leftover}"


# --------------------------------------------------------------------------
# Streamed bytes authoritative
# --------------------------------------------------------------------------


def _drive_chunked(app, path, body):
    """Drive the raw WSGI app with a chunked (input-terminated) body.

    The Werkzeug test client strips ``wsgi.input_terminated``, so a genuine
    chunked stream (no declared length) must be driven directly.
    """
    builder = EnvironBuilder(
        method="POST", path=path, content_type="application/octet-stream"
    )
    environ = builder.get_environ()
    environ.pop("CONTENT_LENGTH", None)
    environ["wsgi.input"] = io.BytesIO(body)
    environ["wsgi.input_terminated"] = True
    environ["HTTP_TRANSFER_ENCODING"] = "chunked"

    captured = {}

    def start_response(status, headers, exc_info=None):
        captured["status"] = status

    payload = b"".join(app.wsgi_app(environ, start_response))
    return int(captured["status"].split(" ", 1)[0]), payload


def test_streamed_bytes_authoritative_over_cap(app):
    """A chunked body with no declared length is capped by its streamed bytes."""
    status, payload = _drive_chunked(app, "/api/__limit_read", b"x" * (1 * _MIB + 5000))
    assert status == 413
    assert b"REQUEST_BODY_TOO_LARGE" in payload


def test_streamed_under_cap_passes(app):
    """A chunked body under the cap streams through normally."""
    status, payload = _drive_chunked(app, "/api/__limit_read", b"x" * (500 * _KIB))
    assert status == 200
    assert payload == b"ok"
