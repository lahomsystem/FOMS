"""Designer API write guards.

The wdplanner-v2 React app runs in a same-origin iframe.  Mutating designer
endpoints require a custom same-origin header so a cross-site form POST cannot
reuse the user's session cookies silently.
"""

from __future__ import annotations

from functools import wraps
from typing import Callable, TypeVar, cast
from urllib.parse import urlparse

from flask import jsonify, request

F = TypeVar("F", bound=Callable[..., object])

_WRITE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})
_WRITE_HEADER = "X-FOMS-Designer-Write"


def require_designer_write(f: F) -> F:
    """Require same-origin write proof for mutating designer API calls."""

    @wraps(f)
    def wrapper(*args: object, **kwargs: object) -> object:
        if request.method in _WRITE_METHODS:
            if request.headers.get(_WRITE_HEADER) != "1":
                return jsonify({
                    "success": False,
                    "data": None,
                    "error": "designer write header is required",
                }), 403

            origin = request.headers.get("Origin")
            referer = request.headers.get("Referer")
            if origin and not _same_origin(origin):
                return jsonify({
                    "success": False,
                    "data": None,
                    "error": "invalid request origin",
                }), 403
            if referer and not _same_origin(referer):
                return jsonify({
                    "success": False,
                    "data": None,
                    "error": "invalid request referer",
                }), 403

        return f(*args, **kwargs)

    return cast(F, wrapper)


def _same_origin(value: str) -> bool:
    parsed = urlparse(value)
    if not parsed.scheme or not parsed.netloc:
        return False
    request_origin = f"{request.scheme}://{request.host}"
    return f"{parsed.scheme}://{parsed.netloc}" == request_origin

