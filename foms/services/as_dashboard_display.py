"""Display helpers for ERP AS dashboard mobile cards."""

from __future__ import annotations

from typing import Any

from foms.api.files import build_file_view_url
from foms.services.feature_flags import env_bool
from models import OrderAttachment

__all__ = [
    "as_stage_badge_modifier",
    "as_thumb_enabled",
    "batch_resolve_as_thumbnail_urls",
]

_IMAGE_SUFFIXES = (".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp")


def as_thumb_enabled() -> bool:
    """Return whether mobile AS card thumbnails are enabled.

    Returns:
        True when ``FOMS_V3_AS_THUMB_ENABLED`` is truthy.
    """
    return env_bool("FOMS_V3_AS_THUMB_ENABLED", default=False)


def as_stage_badge_modifier(*, status: str, as_pending: bool) -> str:
    """Return v1.1 stage badge CSS modifier for an AS row.

    Args:
        status: Order status code (e.g. ``AS_RECEIVED``, ``AS_COMPLETED``).
        as_pending: Whether the row is marked pending on visit date.

    Returns:
        Modifier suffix such as ``--cs`` or ``--completed``.
    """
    if status == "AS_COMPLETED":
        return "--completed"
    return "--cs"


def _is_image_filename(filename: str | None) -> bool:
    name = (filename or "").strip().lower()
    if not name:
        return False
    return name.endswith(_IMAGE_SUFFIXES)


def _attachment_image_url(attachment: OrderAttachment) -> str | None:
    thumb_key = (attachment.thumbnail_key or "").strip()
    if thumb_key:
        return build_file_view_url(thumb_key)
    storage_key = (attachment.storage_key or "").strip()
    if not storage_key:
        return None
    if (attachment.file_type or "").strip().lower() == "image" or _is_image_filename(
        attachment.filename
    ):
        return build_file_view_url(storage_key)
    return None


def batch_resolve_as_thumbnail_urls(order_ids: list[int], db: Any) -> dict[int, str | None]:
    """Resolve first AS image thumbnail URL per order id.

    Args:
        order_ids: Order primary keys on the current page.
        db: SQLAlchemy session.

    Returns:
        Mapping of order id to view URL (missing keys mean no thumbnail).
    """
    if not as_thumb_enabled() or not order_ids:
        return {}

    attachments = (
        db.query(OrderAttachment)
        .filter(
            OrderAttachment.order_id.in_(order_ids),
            OrderAttachment.category == "as",
        )
        .order_by(OrderAttachment.order_id.asc(), OrderAttachment.created_at.asc())
        .all()
    )

    urls: dict[int, str | None] = {}
    for attachment in attachments:
        oid = int(attachment.order_id)
        if oid in urls:
            continue
        url = _attachment_image_url(attachment)
        if url:
            urls[oid] = url
    return urls
