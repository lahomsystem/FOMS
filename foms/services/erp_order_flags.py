"""Canonical ERP order flag helpers."""

from __future__ import annotations

from typing import Any

__all__ = [
    "is_erp_order_record",
    "is_erp_draft_structured_data",
    "is_erp_order_draft",
]


def is_erp_order_record(order: Any) -> bool:
    """Return the canonical ERP-order flag only."""
    return bool(getattr(order, "is_erp_order", False))


def is_erp_draft_structured_data(structured_data: Any) -> bool:
    """Return whether structured_data carries the canonical ERP draft marker."""
    if not isinstance(structured_data, dict):
        return False
    meta = structured_data.get("meta")
    return isinstance(meta, dict) and meta.get("draft") is True


def is_erp_order_draft(order: Any) -> bool:
    """Return whether an order is still an unfinalized ERP draft."""
    if not is_erp_order_record(order):
        return False
    if str(getattr(order, "status", "") or "").upper() == "DRAFT":
        return True
    return is_erp_draft_structured_data(getattr(order, "structured_data", None))
