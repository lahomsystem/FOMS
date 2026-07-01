"""Display helpers for ERP drawing workbench dashboard rows."""

from __future__ import annotations

from typing import Any

from foms.api.files import build_file_view_url
from foms.services.feature_flags import env_bool_or_mobile_v2
from models import OrderAttachment

__all__ = [
    "drawing_thumb_enabled",
    "resolve_row_thumbnail_url",
]

_IMAGE_SUFFIXES = (".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp")


def drawing_thumb_enabled(*, mobile_v2_active: bool = False) -> bool:
    """Return whether mobile drawing card thumbnails are enabled.

    Args:
        mobile_v2_active: ERP mobile v2 cohort active for current user.

    Returns:
        True when explicit env is truthy, or env unset and ``mobile_v2_active``.
    """
    return env_bool_or_mobile_v2(
        "FOMS_V3_DRAWING_THUMB_ENABLED",
        mobile_v2_active=mobile_v2_active,
    )


def _is_image_file(file_entry: dict[str, Any]) -> bool:
    """Return True when a drawing file entry looks like an image."""
    name = (
        (file_entry.get("filename") or file_entry.get("name") or file_entry.get("key") or "")
        .strip()
        .lower()
    )
    if not name:
        return False
    return name.endswith(_IMAGE_SUFFIXES)


def resolve_row_thumbnail_url(
    order_id: int,
    drawing_files: list[Any],
    db: Any,
    *,
    mobile_v2_active: bool = False,
) -> str | None:
    """Resolve a view URL for the first image drawing file on a workbench row.

    Args:
        order_id: Order primary key.
        drawing_files: ``drawing_current_files`` entries from structured_data.
        db: SQLAlchemy session for optional ``OrderAttachment.thumbnail_key`` lookup.

    Returns:
        View URL string, or None when thumbnails are disabled or no image exists.
    """
    if not drawing_thumb_enabled(mobile_v2_active=mobile_v2_active):
        return None

    image_keys_ordered: list[str] = []
    view_url_by_key: dict[str, str] = {}
    for entry in drawing_files:
        if not isinstance(entry, dict):
            continue
        key = (entry.get("key") or "").strip()
        if not key or not _is_image_file(entry):
            continue
        view_url = (entry.get("view_url") or "").strip()
        if view_url:
            view_url_by_key[key] = view_url
        image_keys_ordered.append(key)

    attachments_by_key: dict[str, OrderAttachment] = {}
    if image_keys_ordered and any(key not in view_url_by_key for key in image_keys_ordered):
        attachments_by_key = {
            attachment.storage_key: attachment
            for attachment in db.query(OrderAttachment)
            .filter(
                OrderAttachment.order_id == order_id,
                OrderAttachment.storage_key.in_(image_keys_ordered),
            )
            .all()
        }

    for key in image_keys_ordered:
        view_url = view_url_by_key.get(key)
        if view_url:
            return view_url
        attachment = attachments_by_key.get(key)
        thumb_key = (
            (attachment.thumbnail_key or "").strip() if attachment is not None else ""
        )
        if thumb_key:
            return build_file_view_url(thumb_key)
        return build_file_view_url(key)
    return None
