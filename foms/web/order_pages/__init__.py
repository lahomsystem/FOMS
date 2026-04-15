"""Canonical order pages (SFC-B11B: implementation in ``foms.web.order_pages.routes``)."""

from foms.web.order_pages.routes import enqueue_geocode_order_address, order_pages_bp

__all__ = ["order_pages_bp", "enqueue_geocode_order_address"]
