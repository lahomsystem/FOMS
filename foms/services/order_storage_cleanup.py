"""Storage cleanup helpers for permanently deleted orders."""

from __future__ import annotations

from typing import Any

from models import OrderAttachment
from foms.services.storage import get_storage
from foms.services.error_logging import log_handled_exception

__all__ = ["delete_storage_files_for_order"]

VIEW_URL_PREFIX = "/api/files/view/"


def delete_storage_files_for_order(db: Any, order: Any) -> None:
    """Delete storage files linked to an order before the DB row is removed."""
    if not order:
        return

    order_id = order.id
    storage = get_storage()

    attachments = db.query(OrderAttachment).filter(OrderAttachment.order_id == order_id).all()  # perf-ok: single-order attachments
    for attachment in attachments:
        try:
            if attachment.storage_key:
                storage.delete_file(attachment.storage_key)
        except Exception:
            log_handled_exception("storage cleanup delete_file")
        try:
            if attachment.thumbnail_key:
                storage.delete_file(attachment.thumbnail_key)
        except Exception:
            log_handled_exception("storage cleanup delete thumbnail")

    blueprint_url = (order.blueprint_image_url or "").strip()
    if blueprint_url.startswith(VIEW_URL_PREFIX):
        key = blueprint_url[len(VIEW_URL_PREFIX) :].lstrip("/")
        if key and ".." not in key:
            try:
                storage.delete_file(key)
            except Exception:
                log_handled_exception("storage cleanup delete blueprint")

    structured_data = order.structured_data or {}
    drawing_files = structured_data.get("drawing_current_files") or []
    for item in drawing_files:
        if not isinstance(item, dict):
            continue
        key = (item.get("key") or "").strip()
        if key and ".." not in key and f"orders/{order_id}/" in key:
            try:
                storage.delete_file(key)
            except Exception:
                log_handled_exception("storage cleanup delete structured key")
