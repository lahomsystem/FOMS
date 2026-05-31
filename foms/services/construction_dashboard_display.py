"""Display helpers for ERP construction dashboard mobile queue cards."""

from __future__ import annotations

from typing import Any

from foms.api.files import build_file_view_url
from foms.services.feature_flags import env_bool_or_mobile_v2
from models import OrderAttachment

__all__ = [
    "construction_stage_badge_modifier",
    "construction_thumb_enabled",
    "enrich_construction_mobile_rows",
]

_IMAGE_SUFFIXES = (".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp")
_DRAWING_CATEGORIES = frozenset({"drawing"})
_MEASUREMENT_CATEGORIES = frozenset({"measurement", "measure_photo", "photo"})
_ATTACHMENT_CATEGORIES = _DRAWING_CATEGORIES | _MEASUREMENT_CATEGORIES | frozenset(
    {"construction"}
)
_MAX_PREVIEW_COUNT = 4


def construction_thumb_enabled(*, mobile_v2_active: bool = False) -> bool:
    """Return whether construction mobile card thumbnails are enabled.

    Args:
        mobile_v2_active: ERP mobile v2 cohort active for current user.

    Returns:
        True when explicit env is truthy, or env unset and ``mobile_v2_active``.
    """
    return env_bool_or_mobile_v2(
        "FOMS_V3_CONSTRUCTION_THUMB_ENABLED",
        mobile_v2_active=mobile_v2_active,
    )


def construction_stage_badge_modifier(stage: str | None) -> str:
    """Return v1.1 stage badge CSS modifier for a construction queue row.

    Args:
        stage: Human-readable stage label (e.g. ``시공중``, ``시공완료``).

    Returns:
        Modifier suffix such as ``--construction`` or ``--completed``.
    """
    label = (stage or "").strip()
    if label == "시공완료":
        return "--completed"
    return "--construction"


def _is_image_filename(filename: str | None) -> bool:
    name = (filename or "").strip().lower()
    if not name:
        return False
    return name.endswith(_IMAGE_SUFFIXES)


def _is_image_file_entry(entry: dict[str, Any]) -> bool:
    name = (
        (entry.get("filename") or entry.get("name") or entry.get("key") or "")
        .strip()
        .lower()
    )
    if not name:
        return False
    return name.endswith(_IMAGE_SUFFIXES)


def _url_from_file_entry(entry: dict[str, Any]) -> str | None:
    if not isinstance(entry, dict):
        return None
    key = (entry.get("key") or "").strip()
    if not key or not _is_image_file_entry(entry):
        return None
    view_url = (entry.get("view_url") or "").strip()
    if view_url:
        return view_url
    return build_file_view_url(key)


def _url_from_attachment(attachment: OrderAttachment) -> str | None:
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


def _collect_preview_urls(row: dict[str, Any], db: Any) -> list[str]:
    """Resolve drawing + measurement preview URLs for one construction queue row."""
    seen: set[str] = set()
    urls: list[str] = []

    def _add(url: str | None) -> None:
        if not url or url in seen:
            return
        seen.add(url)
        urls.append(url)

    sd = row.get("structured_data") if isinstance(row.get("structured_data"), dict) else {}
    order_id = row.get("id")
    for entry in sd.get("drawing_current_files") or []:
        _add(_url_from_file_entry(entry))
        if len(urls) >= _MAX_PREVIEW_COUNT:
            return urls[:_MAX_PREVIEW_COUNT]

    if not order_id:
        return urls[:_MAX_PREVIEW_COUNT]

    attachments = (
        db.query(OrderAttachment)
        .filter(
            OrderAttachment.order_id == int(order_id),
            OrderAttachment.category.in_(sorted(_ATTACHMENT_CATEGORIES)),
        )
        .order_by(OrderAttachment.created_at.asc())
        .all()
    )

    def _sort_key(att: OrderAttachment) -> tuple[int, Any]:
        cat = (att.category or "").strip().lower()
        if cat in _DRAWING_CATEGORIES:
            bucket = 0
        elif cat in _MEASUREMENT_CATEGORIES:
            bucket = 1
        else:
            bucket = 2
        return (bucket, att.created_at or "")

    for attachment in sorted(attachments, key=_sort_key):
        _add(_url_from_attachment(attachment))
        if len(urls) >= _MAX_PREVIEW_COUNT:
            break

    return urls[:_MAX_PREVIEW_COUNT]


def enrich_construction_mobile_rows(
    rows: list[dict[str, Any]],
    db: Any,
    *,
    mobile_v2_active: bool = False,
) -> None:
    """Attach v1.1 badge + thumbnail fields to construction ``paginated_orders`` dicts.

    Args:
        rows: Mutable list of row dicts built in ``construction.dashboard``.
        db: SQLAlchemy session for attachment lookup.
    """
    thumb_on = construction_thumb_enabled(mobile_v2_active=mobile_v2_active)
    for row in rows:
        stage = row.get("stage")
        row["stage_badge_modifier"] = construction_stage_badge_modifier(
            str(stage) if stage is not None else None
        )
        row["construction_thumb_active"] = thumb_on
        if not thumb_on:
            row["thumbnail_url"] = None
            row["attachment_previews"] = []
            continue
        previews = _collect_preview_urls(row, db)
        row["attachment_previews"] = previews
        row["thumbnail_url"] = previews[0] if previews else None
