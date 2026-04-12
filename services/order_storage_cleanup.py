"""Compatibility shim for the canonical `foms.services.order_storage_cleanup` module."""

from foms.services.order_storage_cleanup import VIEW_URL_PREFIX, delete_storage_files_for_order

__all__ = ["delete_storage_files_for_order"]
