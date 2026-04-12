"""Compatibility shim for the canonical `foms.services.db_indexes` module."""

from foms.services.db_indexes import apply_phase2_indexes, ensure_erp_date_columns

__all__ = [
    "apply_phase2_indexes",
    "ensure_erp_date_columns",
]
