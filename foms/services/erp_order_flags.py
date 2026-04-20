"""Canonical ERP order flag helpers."""

from __future__ import annotations

from typing import Any

__all__ = ["is_erp_order_record"]


def is_erp_order_record(order: Any) -> bool:
    """Return the canonical ERP-order flag only."""
    return bool(getattr(order, "is_erp_order", False))
