"""Compatibility shim for the canonical `foms.services.erp_product_items` module."""

from foms.services.erp_product_items import (
    build_product_items_for_order,
    build_product_items_for_orders,
)

__all__ = [
    "build_product_items_for_order",
    "build_product_items_for_orders",
]
