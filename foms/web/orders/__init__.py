"""Canonical orders web surface."""

from foms.web.order_edit import order_edit_bp
from foms.web.order_pages import order_pages_bp
from foms.web.orders.trash import order_trash_bp

__all__ = [
    "order_pages_bp",
    "order_edit_bp",
    "order_trash_bp",
]
