"""Compatibility shim for the canonical `foms.services.order_attachment_thumbnail` module."""

from foms.services.order_attachment_thumbnail import schedule_order_attachment_thumbnail_generation

__all__ = ["schedule_order_attachment_thumbnail_generation"]
