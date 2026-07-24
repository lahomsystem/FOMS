"""REQUEST-LIMIT-01: pre-parse request body caps (P1-31).

The default global cap was 500 MiB with no per-route or per-form limits, so any
public control-plane endpoint (login, telemetry, JSON APIs) could force the
worker to buffer a huge body into memory or spill oversized multipart parts to
temp files *before* a single line of handler code ran. That is a memory /
tempfile denial-of-service.

This module closes that gap with three cooperating layers, all enforced *before*
the view runs and without trusting the default parser to cap file size:

1. ``FomsRequest`` — a Flask ``Request`` subclass that pins the form-parsing
   limits Werkzeug already understands (``max_form_memory_size`` = 1 MiB,
   ``max_form_parts`` = 1000) and, on any parse failure, closes/unlinks every
   partial temp file the multipart parser created so aborted uploads never leak
   spilled files on disk.

2. A 4-field route body-cap manifest (``route_pattern``, ``max_body_bytes``,
   ``max_files``, ``category``) declaring the ceiling for each public surface:
   telemetry 2 KiB, login 16 KiB, Excel import 10 MiB + 64 KiB body overhead,
   legacy multipart upload 50 MiB + 256 KiB, and a 1 MiB ``normal`` default for
   everything else. Presigned / direct-upload endpoints are excluded (their file
   bytes never transit the app — the browser PUTs straight to R2/S3).

3. A pre-handler ``before_request`` guard that rejects an oversized *declared*
   ``Content-Length`` with 413 and an unsupported ``Transfer-Encoding`` with 415,
   then wraps ``wsgi.input`` so the *streamed* byte count is the final authority:
   a chunked / mislabelled body that exceeds the cap trips 413 while it is being
   read, not after it has been fully buffered.

The global config cap (``MAX_CONTENT_LENGTH`` = 50 MiB + 256 KiB) is the
outermost ceiling; Werkzeug enforces it both preemptively against
``Content-Length`` and on the stream via its own ``LimitedStream``.

413 / 415 responses use the API-ERROR-01 JSON envelope — never an HTML error
page — so programmatic callers get a structured domain error.
"""

from __future__ import annotations

import re
import uuid
from typing import Any, Callable, NamedTuple

from flask import Flask, Request, g, jsonify, request
from werkzeug.wsgi import LimitedStream

_KIB = 1024
_MIB = 1024 * 1024

# --- Category caps -----------------------------------------------------------
# Body caps are the *whole request body* ceiling for the category (file bytes +
# multipart/field overhead), per the REQUEST-LIMIT-01 manifest.
_TELEMETRY_CAP = 2 * _KIB
_LOGIN_CAP = 16 * _KIB
_NORMAL_CAP = 1 * _MIB

# Excel import: one file, 10 MiB of file bytes + 64 KiB body/multipart overhead.
_EXCEL_CAP = 10 * _MIB + 64 * _KIB

# Legacy multipart upload: file/total <= 50 MiB + 256 KiB body overhead.
_LEGACY_CAP = 50 * _MIB + 256 * _KIB
_LEGACY_MAX_FILES = 20

# Global outermost ceiling (replaces the old 500 MiB). Also the MAX_CONTENT_LENGTH.
GLOBAL_BODY_CAP = 50 * _MIB + 256 * _KIB

# Form-parsing limits pinned on the Request class (enforced by Werkzeug).
_FORM_MEMORY_CAP = 1 * _MIB
_MAX_FORM_PARTS = 1000

_BODY_METHODS = frozenset({"POST", "PUT", "PATCH"})

_MSG_413 = "요청 본문이 허용된 크기를 초과했습니다."
_MSG_415 = "지원하지 않는 전송 인코딩입니다."
_CODE_413 = "REQUEST_BODY_TOO_LARGE"
_CODE_415 = "UNSUPPORTED_TRANSFER_ENCODING"


class BodyCap(NamedTuple):
    """One route body-cap manifest entry.

    Attributes:
        route_pattern: Anchored regex matched against ``request.path``.
        max_body_bytes: Ceiling for the whole request body in bytes.
        max_files: Advisory max number of file parts for the category (0 = none).
        category: Human label used in logs / tests.
    """

    route_pattern: str
    max_body_bytes: int
    max_files: int
    category: str


# Ordered manifest; first pattern that matches wins.
_MANIFEST: tuple[BodyCap, ...] = (
    BodyCap(r"^/api/foms/rum$", _TELEMETRY_CAP, 0, "telemetry"),
    BodyCap(r"^/channel/wam/api/telemetry$", _TELEMETRY_CAP, 0, "telemetry"),
    BodyCap(r"^/login$", _LOGIN_CAP, 0, "login"),
    BodyCap(r"^/upload$", _EXCEL_CAP, 1, "excel"),
    BodyCap(r"^/api/orders/\d+/attachments$", _LEGACY_CAP, _LEGACY_MAX_FILES, "legacy"),
    BodyCap(r"^/api/chat/upload$", _LEGACY_CAP, _LEGACY_MAX_FILES, "legacy"),
)

# Presigned / direct-upload surfaces: the file bytes go browser -> R2/S3, only a
# tiny JSON handshake transits the app, so route body caps do not apply (the
# global MAX_CONTENT_LENGTH ceiling still does).
_EXCLUDED_PATTERNS: tuple[str, ...] = (
    r"^/api/upload/session",
    r"^/api/orders/\d+/attachments/complete$",
    r"^/api/chat/upload/session$",
    r"^/api/chat/upload/complete$",
    r"^/api/files/presigned-urls/",
)

_NORMAL_CAP_ENTRY = BodyCap(r".*", _NORMAL_CAP, 0, "normal")

_COMPILED_MANIFEST = tuple((re.compile(c.route_pattern), c) for c in _MANIFEST)
_COMPILED_EXCLUDED = tuple(re.compile(p) for p in _EXCLUDED_PATTERNS)


def resolve_body_cap(path: str) -> BodyCap | None:
    """Resolve the body cap for a request path.

    Args:
        path: The request path (``request.path``).

    Returns:
        The matching :class:`BodyCap`, the ``normal`` default when nothing
        matches, or ``None`` when the path is an excluded presigned /
        direct-upload surface (no route cap applies).
    """
    for excluded in _COMPILED_EXCLUDED:
        if excluded.match(path):
            return None
    for pattern, cap in _COMPILED_MANIFEST:
        if pattern.match(path):
            return cap
    return _NORMAL_CAP_ENTRY


class FomsRequest(Request):
    """Flask request with pinned form limits and leak-free temp-file cleanup.

    ``max_form_memory_size`` bounds in-memory form fields to 1 MiB and
    ``max_form_parts`` bounds multipart parts to 1000 (both enforced by
    Werkzeug's parser). The overridden :meth:`make_form_data_parser` additionally
    guarantees that if parsing aborts partway (e.g. the part limit trips after
    some files already spilled to disk), every partial temp file is closed and
    unlinked instead of lingering.
    """

    max_form_memory_size: int | None = _FORM_MEMORY_CAP
    max_form_parts: int | None = _MAX_FORM_PARTS

    def make_form_data_parser(self) -> Any:
        """Build the standard parser, then wrap it to clean up on parse failure.

        Returns:
            A Werkzeug ``FormDataParser`` whose ``stream_factory`` records every
            file container it creates and whose ``parse`` closes/unlinks those
            containers if the parse raises.
        """
        parser = super().make_form_data_parser()
        created: list[Any] = []
        inner_factory = parser.stream_factory

        def _tracking_factory(*args: Any, **kwargs: Any) -> Any:
            container = inner_factory(*args, **kwargs)
            created.append(container)
            return container

        parser.stream_factory = _tracking_factory
        _orig_parse = parser.parse

        def _guarded_parse(*args: Any, **kwargs: Any) -> Any:
            try:
                return _orig_parse(*args, **kwargs)
            except BaseException:
                # Any partial part already spilled to a SpooledTemporaryFile /
                # TemporaryFile is closed here; .close() unlinks the on-disk file.
                for container in created:
                    try:
                        container.close()
                    except Exception:
                        pass
                raise

        parser.parse = _guarded_parse  # type: ignore[method-assign]
        return parser


def _body_limit_error(status: int, code: str, message: str) -> Any:
    """Build an API-ERROR-01-compatible JSON error response (never HTML).

    Args:
        status: HTTP status (413 or 415).
        code: Domain error code.
        message: User-facing message.

    Returns:
        A Flask JSON ``Response`` carrying the ``{success, message, error}``
        envelope with a request id.
    """
    rid = getattr(g, "request_id", None) or uuid.uuid4().hex
    response = jsonify(
        {
            "success": False,
            "message": message,
            "error": {"code": code, "message": message, "request_id": rid},
        }
    )
    response.status_code = status
    return response


def _wrap_input_stream(environ: dict[str, Any], max_body_bytes: int) -> None:
    """Cap ``wsgi.input`` so the streamed byte count is the final authority.

    ``LimitedStream(is_max=True)`` raises ``RequestEntityTooLarge`` once reads
    pass the limit, so a chunked or mislabelled body that exceeds the cap trips
    413 while it is read — after at most ``max_body_bytes`` are buffered, not the
    whole payload. The ``+ 1`` lets a body exactly at the cap through; only a
    strictly larger body trips.
    """
    stream = environ.get("wsgi.input")
    if stream is None:
        return
    environ["wsgi.input"] = LimitedStream(stream, max_body_bytes + 1, is_max=True)


def _enforce_request_body_limit() -> Any | None:
    """``before_request`` guard: reject oversized/mis-encoded bodies pre-handler.

    Returns:
        A 413 / 415 JSON response to short-circuit the request, or ``None`` to
        let it proceed (with ``wsgi.input`` capped for streamed enforcement).
    """
    if request.method not in _BODY_METHODS:
        return None
    path = request.path or ""
    if path.startswith("/static/"):
        return None

    cap = resolve_body_cap(path)
    if cap is None:
        return None  # presigned / direct-upload excluded

    # Reject an unsupported Transfer-Encoding before touching the body (415).
    transfer_encoding = (request.headers.get("Transfer-Encoding") or "").strip().lower()
    if transfer_encoding and transfer_encoding not in ("chunked", "identity"):
        return _body_limit_error(415, _CODE_415, _MSG_415)

    # Reject an oversized *declared* Content-Length before the body is read (413).
    declared = request.content_length
    if declared is not None and declared > cap.max_body_bytes:
        return _body_limit_error(413, _CODE_413, _MSG_413)

    # Streamed bytes are authoritative: cap the raw stream so a chunked / lying
    # body that exceeds the cap trips 413 during the read.
    _wrap_input_stream(request.environ, cap.max_body_bytes)
    return None


def register_request_limits(app: Flask) -> None:
    """Wire the pre-parse body-limit guard and 413/415 JSON handlers onto ``app``.

    Registers the ``before_request`` guard first (so oversized bodies are
    rejected at the earliest hook) and error handlers that convert any
    ``RequestEntityTooLarge`` / ``UnsupportedMediaType`` — including ones raised
    while the body is streamed or the global ``MAX_CONTENT_LENGTH`` is exceeded —
    into the API-ERROR-01 JSON envelope.

    Args:
        app: The Flask app to configure. The caller is responsible for setting
            ``app.request_class = FomsRequest`` and ``MAX_CONTENT_LENGTH``.
    """
    app.before_request(_enforce_request_body_limit)

    @app.errorhandler(413)
    def _handle_413(error: Any) -> Any:  # noqa: ANN401
        return _body_limit_error(413, _CODE_413, _MSG_413)

    @app.errorhandler(415)
    def _handle_415(error: Any) -> Any:  # noqa: ANN401
        return _body_limit_error(415, _CODE_415, _MSG_415)


__all__ = [
    "BodyCap",
    "FomsRequest",
    "GLOBAL_BODY_CAP",
    "register_request_limits",
    "resolve_body_cap",
]
