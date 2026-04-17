"""HTTP helpers for ERP shell + fragment requests."""

from __future__ import annotations

from flask import Request, Response

from foms.services.common import erp_navigation_contract as enc


def get_erp_shell_view_mode(req: Request) -> str | None:
    """Return ``fragment`` / ``critical`` / ``heavy`` when shell tab body is requested.

    Requires active shell header **and** ``view`` matching a known mode. Otherwise
    ``None`` (full HTML document — direct GET, refresh, JS off).

    Full page and fragment must use the same handler and data path (single truth).
    """
    if req.headers.get(enc.ERP_SHELL_REQUEST_HEADER) != enc.ERP_SHELL_REQUEST_HEADER_ACTIVE:
        return None
    raw = (req.args.get(enc.ERP_VIEW_QUERY_PARAM) or "").strip()
    if raw == enc.VIEW_FRAGMENT:
        return enc.VIEW_FRAGMENT
    if raw == enc.VIEW_CRITICAL:
        return enc.VIEW_CRITICAL
    if raw == enc.VIEW_HEAVY:
        return enc.VIEW_HEAVY
    return None


def wants_erp_shell_tab_body(req: Request) -> bool:
    """True when the client should receive tab-body HTML (partial), not a full document."""
    return get_erp_shell_view_mode(req) is not None


def wants_erp_tab_fragment(req: Request) -> bool:
    """Backward-compatible name: any shell body mode (fragment/critical/heavy).

    Deprecated alias for :func:`wants_erp_shell_tab_body`.
    """
    return wants_erp_shell_tab_body(req)


def apply_erp_shell_fragment_headers(response: Response, req: Request) -> None:
    """Set fragment response headers when ``get_erp_shell_view_mode`` is non-None."""
    mode = get_erp_shell_view_mode(req)
    if mode is None:
        return
    response.headers[enc.ERP_FRAGMENT_RESPONSE_HEADER] = enc.ERP_FRAGMENT_RESPONSE_ACTIVE
    response.headers[enc.ERP_FRAGMENT_VIEW_TIER_HEADER] = mode
