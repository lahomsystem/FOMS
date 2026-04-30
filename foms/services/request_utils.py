"""Request-related helpers: list filter preservation and legacy ``open`` query canonicalization."""

from __future__ import annotations

from typing import Any, Optional
from urllib.parse import urlencode

from flask import Response, redirect, request, url_for

__all__ = [
    "get_preserved_filter_args",
    "get_search_query_arg",
    "redirect_if_legacy_open_erp_beta",
]


def get_search_query_arg(*names: str) -> str:
    """Return the first non-blank search query from equivalent request parameters."""
    for name in names:
        value = request.args.get(name)
        if value and value.strip():
            return value.strip()
    return ""


def get_preserved_filter_args(request_args: Any) -> dict[str, Any]:
    """Return redirect query params that should survive list/detail actions."""
    redirect_args: dict[str, Any] = {}
    preserved_params = [
        "search",
        "status",
        "region",
        "page",
        "sort",
        "direction",
        "sort_by",
        "sort_order",
    ]
    preserved_params += [key for key in request_args.keys() if key.startswith("filter_")]
    for key in preserved_params:
        if key in request_args:
            redirect_args[key] = request_args.get(key)
    return redirect_args


def redirect_if_legacy_open_erp_beta(endpoint: str, **url_values: Any) -> Optional[Response]:
    """
    Legacy deep links used ``?open=erp-beta``. Canonical is ``open=erp-order``.

    When the client still requests ``open=erp-beta``, respond with **302** to the same
    route with ``open=erp-order`` and all other query parameters preserved.

    Args:
        endpoint: Flask endpoint name (e.g. ``order_pages.add_order``).
        url_values: Path parameters for ``url_for`` (e.g. ``order_id=`` for edit).

    Returns:
        Redirect response if legacy open was present; otherwise ``None``.
    """
    if request.args.get("open") != "erp-beta":
        return None
    # Single value per key (last wins if duplicates); typical deep links use unique keys.
    flat = request.args.to_dict(flat=True)
    flat["open"] = "erp-order"
    path = url_for(endpoint, **url_values)
    # Stable query ordering helps tests and log diffs.
    query = urlencode(sorted(flat.items()))
    return redirect(f"{path}?{query}", code=302)
