"""Temporary attachment storage for OrderDraft wizard (P2)."""

from __future__ import annotations

import os
import re
from typing import Any

from sqlalchemy.orm import Session

from foms.api.files.common import allowed_erp_attachment_file, get_erp_media_max_size
from foms.services.storage import get_storage
from models import OrderAttachment

_DRAFT_KEY_SAFE = re.compile(r"[^a-zA-Z0-9._-]+")


def sanitize_draft_key_for_storage(draft_key: str) -> str:
    """Return storage-safe draft key segment."""
    cleaned = _DRAFT_KEY_SAFE.sub("_", (draft_key or "").strip())
    return cleaned[:64] or "draft"


def draft_attachment_folder(user_id: int, draft_key: str) -> str:
    """Build storage folder path for wizard draft attachments."""
    safe = sanitize_draft_key_for_storage(draft_key)
    return f"order-drafts/{user_id}/{safe}"


def validate_draft_attachment_upload(filename: str, file_size: int) -> str | None:
    """Return error message when upload is invalid, else None."""
    if not filename:
        return "파일명이 없습니다."
    if not allowed_erp_attachment_file(filename, "measurement"):
        return "허용되지 않은 파일 형식입니다."
    max_size = get_erp_media_max_size(filename)
    if file_size > max_size:
        size_mb = max_size / (1024 * 1024)
        return f"파일 크기가 너무 큽니다. 최대 {size_mb:.0f}MB까지 업로드 가능합니다."
    return None


def promote_draft_attachments(
    db: Session,
    *,
    order_id: int,
    items: list[dict[str, Any]],
    user_id: int | None,
) -> None:
    """Create OrderAttachment rows from wizard draft tmp_key references."""
    storage = get_storage()
    for item_index, item in enumerate(items):
        if not isinstance(item, dict):
            continue
        attachments = item.get("attachments")
        if not isinstance(attachments, list):
            continue
        for raw in attachments:
            if not isinstance(raw, dict):
                continue
            tmp_key = str(raw.get("tmp_key") or "").strip()
            filename = str(raw.get("filename") or "").strip()
            if not tmp_key or not filename:
                continue
            if not storage.object_exists(tmp_key):
                continue
            file_type = storage.get_file_type(filename)
            if file_type not in ("image", "video"):
                continue
            file_size = 0
            if storage.storage_type == "local":
                upload_folder = getattr(storage, "upload_folder", None)
                if upload_folder:
                    local_path = os.path.join(upload_folder, tmp_key)
                    if os.path.exists(local_path):
                        file_size = os.path.getsize(local_path)
            db.add(
                OrderAttachment(
                    order_id=order_id,
                    filename=filename,
                    file_type=file_type,
                    category="measurement",
                    item_index=item_index,
                    file_size=file_size,
                    storage_key=tmp_key,
                    thumbnail_key=None,
                    user_id=user_id,
                )
            )
