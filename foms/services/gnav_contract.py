"""Global-nav G1-A fragment request contract (dual-mode full HTML vs main swap fragment)."""

from __future__ import annotations

from flask import request

__all__ = [
    "gnav_orders_layout_parent",
    "wants_gnav_fragment",
]

_GNAV_SWAP_SHELL = "orders/gnav_swap_shell.html"
_ORDERS_LAYOUT = "orders/layout.html"


def wants_gnav_fragment() -> bool:
    """Return True when the client requests the nav fragment (not a full document)."""
    if (request.headers.get("X-FOMS-GNAV") or "").strip() == "1":
        return True
    return (request.args.get("view") or "").strip() == "nav-fragment"


def gnav_orders_layout_parent() -> str:
    """Parent template for orders index/trash: full layout or fragment shell only."""
    return _GNAV_SWAP_SHELL if wants_gnav_fragment() else _ORDERS_LAYOUT
