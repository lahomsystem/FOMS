"""Protected exception logging + log redaction for FOMS (API-ERROR-01).

Centralizes how handled/unhandled exceptions reach the server log so that:

- the stack is recorded exactly once, through a logger that carries a
  redaction filter (secrets/credentials/object-keys/connection-strings are
  masked in the log *message*), and
- request handlers never write a raw exception traceback to stdout again
  (that path leaked file paths and SQL into captured logs).

The traceback itself is intentionally *kept* in the server log (a protected
server-side stack is required); only secret-shaped values in the rendered
message are masked. The client never receives any of this — response
containment lives in :mod:`foms.platform.http`.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from flask import has_request_context, request

# Dedicated protected logger for handled exceptions. Carries the redaction
# filter (installed by ``install_protected_logging``) so callers get masking
# for free.
_logger = logging.getLogger("foms.error")

_FILTER_NAME = "foms_redaction"

# (name, pattern, replacement) — mask secret-shaped substrings in a log
# message. Order matters: URI credentials before the generic key/value rule.
_REDACTIONS: tuple[tuple[str, "re.Pattern[str]", str], ...] = (
    # scheme://user:password@host  ->  scheme://***:***@host
    ("uri_credentials", re.compile(r"://[^/\s:@]+:[^/\s@]+@"), "://***:***@"),
    # password=..., "token": "...", authorization: Bearer ...
    (
        "credential_kv",
        re.compile(
            r"(?i)(password|passwd|pwd|secret|secret[_-]?key|token|api[_-]?key|"
            r"authorization|bearer|access[_-]?key|aws[_-]?secret)"
            r"([\"'\s:=]+)([^\s,'\"}]+)"
        ),
        r"\1\2***",
    ),
    # AWS access key id
    ("aws_key", re.compile(r"\bAKIA[0-9A-Z]{16}\b"), "***"),
    # Long opaque tokens (>=40 chars of base64/hex-ish). uuid hex (32) is safe.
    ("long_token", re.compile(r"\b[A-Za-z0-9_\-]{40,}\b"), "***"),
)


class RedactionFilter(logging.Filter):
    """Mask secret-shaped substrings in a log record's rendered message.

    A ``logging.Filter`` runs inside ``Logger.handle`` *before* handlers, so
    mutating ``record.msg`` here scrubs the message for every downstream
    handler. The exception stack (``record.exc_info``) is not touched — it is
    added by the formatter and is allowed in the protected server log.
    """

    def __init__(self) -> None:
        super().__init__()
        self.name = _FILTER_NAME

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            message = record.getMessage()
        except (TypeError, ValueError, KeyError, IndexError):
            # Bad %-formatting: never let redaction break logging itself.
            return True
        redacted = message
        for _name, pattern, replacement in _REDACTIONS:
            redacted = pattern.sub(replacement, redacted)
        if redacted != message:
            record.msg = redacted
            record.args = ()
        return True


def install_protected_logging(app: Any) -> None:
    """Attach the redaction filter to the app, root, and error loggers.

    Idempotent: safe to call on every app build / handler re-registration.

    Args:
        app: The Flask application whose ``logger`` should be protected.
    """

    def _ensure(logger: logging.Logger) -> None:
        if not any(getattr(f, "name", "") == _FILTER_NAME for f in logger.filters):
            logger.addFilter(RedactionFilter())

    _ensure(app.logger)
    _ensure(logging.getLogger())  # root: covers third-party + module loggers
    _ensure(_logger)


def log_handled_exception(context: str = "") -> None:
    """Log the currently-handled exception once, with stack, via the protected logger.

    Drop-in replacement for raw traceback prints inside request handlers.
    Must be called from within an ``except`` block so the active
    exception's stack is captured. The stack goes to the server log only —
    never to the client or to stdout.

    Args:
        context: Optional short label for where the exception was handled.
    """
    endpoint = request.path if has_request_context() else ""
    _logger.error("handled exception endpoint=%s %s", endpoint, context, exc_info=True)
