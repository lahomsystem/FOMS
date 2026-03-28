from __future__ import annotations

from collections import defaultdict
from urllib.parse import quote

from flask import has_request_context, url_for

from db import get_db
from models import OrderAttachment
from services.channel_wam_view_models import (
    AttachmentGroupVM,
    AttachmentItemVM,
    WamRequestContext,
)
from services.storage import get_storage


CATEGORY_LABELS = {
    "measurement": "Measurement",
    "measure_photo": "Measurement",
    "photo": "Site Photo",
    "drawing": "Drawing",
    "construction": "Construction",
    "as": "AS",
}

CATEGORY_PRIORITY = {
    "measurement": 10,
    "measure_photo": 10,
    "photo": 20,
    "drawing": 30,
    "construction": 40,
    "as": 50,
}


def _normalize_category(category: str | None) -> str:
    if not category:
        return "measurement"
    return str(category)


def _category_label(category: str) -> str:
    return CATEGORY_LABELS.get(category, category.replace("_", " ").title())


def _group_key(category: str, item_index: int | None) -> str:
    item_token = "common" if item_index is None else f"item-{item_index}"
    return f"{category}:{item_token}"


def _group_title(category: str, item_index: int | None) -> str:
    base = _category_label(category)
    if item_index is None:
        return base
    return f"{base} / Item {item_index + 1}"


def _size_label(file_size: int | None) -> str | None:
    if not file_size:
        return None
    size = float(file_size)
    units = ["B", "KB", "MB", "GB"]
    index = 0
    while size >= 1024 and index < len(units) - 1:
        size /= 1024
        index += 1
    if index == 0:
        return f"{int(size)} {units[index]}"
    return f"{size:.1f} {units[index]}"


def _attachment_action_url(context: WamRequestContext, attachment_id: int, action: str) -> str:
    if not has_request_context():
        return ""
    endpoint = (
        "channel_wam_api.wam_attachment_open"
        if action == "open"
        else "channel_wam_api.wam_attachment_download"
    )
    return url_for(endpoint, attachment_id=attachment_id)


def _build_item_vm(att: OrderAttachment, context: WamRequestContext) -> AttachmentItemVM:
    category = _normalize_category(att.category)
    open_url = _attachment_action_url(context, att.id, "open")
    download_url = _attachment_action_url(context, att.id, "download")
    return AttachmentItemVM(
        id=att.id,
        name=att.filename,
        file_type=att.file_type,
        category=category,
        category_label=_category_label(category),
        item_index=att.item_index,
        created_at_label=att.created_at.strftime("%Y-%m-%d %H:%M") if att.created_at else None,
        size_label=_size_label(att.file_size),
        open_url=open_url,
        download_url=download_url,
        thumbnail_url=open_url if att.file_type == "image" else None,
    )


def _group_sort_key(group: AttachmentGroupVM) -> tuple[int, int, str]:
    category = group.key.split(":", 1)[0]
    item_index = group.items[0].item_index if group.items else None
    return (
        CATEGORY_PRIORITY.get(category, 999),
        -1 if item_index is None else item_index,
        group.title,
    )


def list_attachment_groups(
    context: WamRequestContext,
    *,
    preview_limit: int = 3,
) -> list[AttachmentGroupVM]:
    if not context.allows("attachments") or not context.allows_attachment_order(context.order_id):
        return []

    db = get_db()
    attachments = (
        db.query(OrderAttachment)
        .filter(OrderAttachment.order_id == context.order_id)
        .order_by(OrderAttachment.created_at.desc(), OrderAttachment.id.desc())
        .all()
    )

    grouped_rows: dict[tuple[str, int | None], list[OrderAttachment]] = defaultdict(list)
    for att in attachments:
        grouped_rows[(_normalize_category(att.category), att.item_index)].append(att)

    groups: list[AttachmentGroupVM] = []
    for (category, item_index), rows in grouped_rows.items():
        items = [_build_item_vm(att, context) for att in rows]
        groups.append(
            AttachmentGroupVM(
                key=_group_key(category, item_index),
                title=_group_title(category, item_index),
                count=len(items),
                preview_items=items[:preview_limit],
                items=items,
            )
        )

    return sorted(groups, key=_group_sort_key)


def get_scoped_attachment(context: WamRequestContext, attachment_id: int) -> OrderAttachment | None:
    if not context.allows("attachments") or not context.allows_attachment_order(context.order_id):
        return None

    db = get_db()
    return (
        db.query(OrderAttachment)
        .filter(
            OrderAttachment.id == int(attachment_id),
            OrderAttachment.order_id == context.order_id,
        )
        .first()
    )


def resolve_attachment_redirect_url(
    context: WamRequestContext,
    attachment_id: int,
    action: str,
) -> str | None:
    attachment = get_scoped_attachment(context, attachment_id)
    if not attachment or not attachment.storage_key:
        return None

    disposition = None
    if action == "download":
        ascii_name = attachment.filename.encode("ascii", "ignore").decode("ascii") or "download"
        utf8_name = quote(attachment.filename)
        disposition = f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{utf8_name}"

    storage = get_storage()
    return storage.get_download_url(
        attachment.storage_key,
        expires_in=300,
        response_content_disposition=disposition,
    )
