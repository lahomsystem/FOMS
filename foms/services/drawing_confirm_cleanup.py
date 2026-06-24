"""Finalize drawing files when sales confirms receipt in the drawing workbench."""

from __future__ import annotations

import logging
from typing import Any

from models import OrderAttachment
from foms.services.storage import get_storage

logger = logging.getLogger(__name__)

__all__ = [
    "apply_transfer_to_drawing_files",
    "collect_obsolete_drawing_keys",
    "delete_drawing_storage_keys",
    "resolve_final_drawing_files",
    "finalize_drawing_files_on_confirm",
]


def _file_key(entry: Any) -> str:
    """Return storage key from a drawing file dict."""
    if not isinstance(entry, dict):
        return ""
    return (entry.get("key") or "").strip()


def _normalize_file_entry(entry: dict[str, Any]) -> dict[str, str]:
    """Normalize a drawing file entry for structured_data storage."""
    key = _file_key(entry)
    filename = (entry.get("filename") or key.rsplit("/", 1)[-1]).strip()
    return {
        "key": key,
        "filename": filename,
        "view_url": (entry.get("view_url") or f"/api/files/view/{key}").strip(),
        "download_url": (entry.get("download_url") or f"/api/files/download/{key}").strip(),
    }


def _transfer_is_retransfer(history: list[Any], transfer_idx: int) -> bool:
    """Return True when a TRANSFER follows a revision request since the prior TRANSFER."""
    for j in range(transfer_idx - 1, -1, -1):
        item = history[j]
        if not isinstance(item, dict):
            continue
        action = (item.get("action") or "").upper()
        if action == "REQUEST_REVISION":
            return True
        if action == "TRANSFER":
            return False
    return False


def apply_transfer_to_drawing_files(
    old_files: list[dict[str, Any]],
    transfer_entry: dict[str, Any],
    *,
    is_retransfer: bool = False,
) -> list[dict[str, str]]:
    """Apply one TRANSFER history entry onto a snapshot of previous current files.

    Args:
        old_files: Files before this transfer (usually ``previous_current_files``).
        transfer_entry: A ``drawing_transfer_history`` TRANSFER record.
        is_retransfer: Whether this transfer happened after a revision request.

    Returns:
        Updated drawing file list after applying the transfer mode.
    """
    normalized_old = [_normalize_file_entry(f) for f in old_files if _file_key(f)]
    new_files = [_normalize_file_entry(f) for f in (transfer_entry.get("files") or []) if _file_key(f)]
    mode = (transfer_entry.get("mode") or "APPEND").upper()
    replace_target_keys = [
        k.strip()
        for k in (transfer_entry.get("replace_target_keys") or [])
        if isinstance(k, str) and k.strip()
    ]

    if mode == "REPLACE_ALL":
        return new_files

    if replace_target_keys or mode == "REPLACE":
        updated = list(normalized_old)
        indices: list[int] = []
        for target_key in replace_target_keys:
            for idx, file_entry in enumerate(updated):
                if _file_key(file_entry) == target_key:
                    indices.append(idx)
                    break
        if replace_target_keys and len(indices) != len(replace_target_keys):
            return normalized_old
        for idx in sorted(set(indices), reverse=True):
            updated.pop(idx)
        first_index = min(indices) if indices else len(updated)
        for offset, new_file in enumerate(new_files):
            updated.insert(first_index + offset, new_file)
        return updated

    if is_retransfer:
        if len(normalized_old) > 1 and not replace_target_keys:
            # Legacy rows may predate API guard; keep only newly transferred files.
            return new_files
        if len(normalized_old) <= 1:
            return new_files
        return list(normalized_old) + new_files

    return list(normalized_old) + new_files


def resolve_final_drawing_files(structured_data: dict[str, Any]) -> list[dict[str, str]]:
    """Rebuild the canonical final drawing list from transfer history.

    Uses the latest TRANSFER entry and its ``previous_current_files`` snapshot so
    confirm-time cleanup matches what the transfer API intended, including
    revision retransfers that previously appended instead of replacing.

    Args:
        structured_data: Order ``structured_data`` dict.

    Returns:
        Normalized drawing files that should remain after sales confirm.
    """
    history = list(structured_data.get("drawing_transfer_history") or [])
    last_transfer_idx = -1
    last_transfer: dict[str, Any] | None = None
    for idx, item in enumerate(history):
        if isinstance(item, dict) and (item.get("action") or "").upper() == "TRANSFER":
            last_transfer_idx = idx
            last_transfer = item

    if last_transfer is None:
        return [
            _normalize_file_entry(f)
            for f in (structured_data.get("drawing_current_files") or [])
            if _file_key(f)
        ]

    previous_snapshot = last_transfer.get("previous_current_files")
    if not isinstance(previous_snapshot, list):
        return [
            _normalize_file_entry(f)
            for f in (structured_data.get("drawing_current_files") or [])
            if _file_key(f)
        ]

    old_files = [f for f in previous_snapshot if isinstance(f, dict)]

    is_retransfer = _transfer_is_retransfer(history, last_transfer_idx)
    return apply_transfer_to_drawing_files(
        old_files,
        last_transfer,
        is_retransfer=is_retransfer,
    )


def collect_obsolete_drawing_keys(
    structured_data: dict[str, Any],
    keep_keys: set[str],
) -> set[str]:
    """Collect drawing storage keys that should be deleted on confirm.

    Args:
        structured_data: Order ``structured_data`` dict.
        keep_keys: Canonical keys to retain.

    Returns:
        Storage keys safe to delete from R2 and ``OrderAttachment``.
    """
    obsolete: set[str] = set()
    history = structured_data.get("drawing_transfer_history") or []

    for item in history:
        if not isinstance(item, dict):
            continue
        fields = ("files", "previous_current_files")
        for field in fields:
            for file_entry in item.get(field) or []:
                key = _file_key(file_entry)
                if key and key not in keep_keys:
                    obsolete.add(key)

    for file_entry in structured_data.get("drawing_current_files") or []:
        key = _file_key(file_entry)
        if key and key not in keep_keys:
            obsolete.add(key)

    return obsolete


def delete_drawing_storage_keys(db: Any, order_id: int, keys_to_delete: set[str]) -> int:
    """Delete drawing files from storage and attachment rows.

    Args:
        db: SQLAlchemy session.
        order_id: Order primary key.
        keys_to_delete: Storage keys to remove.

    Returns:
        Count of attachment rows deleted.
    """
    if not keys_to_delete:
        return 0

    storage = get_storage()
    deleted_count = 0
    key_list = list(keys_to_delete)

    rows = (
        db.query(OrderAttachment)
        .filter(
            OrderAttachment.order_id == order_id,
            OrderAttachment.storage_key.in_(key_list),
        )
        .all()
    )
    deleted_row_keys: set[str] = set()
    for row in rows:
        try:
            if row.storage_key:
                storage.delete_file(row.storage_key)
                deleted_row_keys.add(row.storage_key)
            if row.thumbnail_key:
                storage.delete_file(row.thumbnail_key)
        except Exception as exc:
            logger.warning(
                "drawing confirm cleanup: storage delete failed order=%s key=%s: %s",
                order_id,
                row.storage_key,
                exc,
            )
        db.delete(row)
        deleted_count += 1

    for key in key_list:
        if key in deleted_row_keys:
            continue
        try:
            storage.delete_file(key)
        except Exception as exc:
            logger.warning(
                "drawing confirm cleanup: orphan storage delete failed order=%s key=%s: %s",
                order_id,
                key,
                exc,
            )

    return deleted_count


def finalize_drawing_files_on_confirm(
    db: Any,
    order_id: int,
    structured_data: dict[str, Any],
) -> tuple[list[dict[str, str]], int]:
    """Prune structured_data to final drawings and delete superseded storage.

    Args:
        db: SQLAlchemy session.
        order_id: Order primary key.
        structured_data: Mutable order ``structured_data`` dict (updated in place).

    Returns:
        Tuple of (final drawing files, deleted attachment count).
    """
    final_files = resolve_final_drawing_files(structured_data)
    keep_keys = {_file_key(f) for f in final_files if _file_key(f)}
    obsolete_keys = collect_obsolete_drawing_keys(structured_data, keep_keys)

    drawing_attachment_rows = (
        db.query(OrderAttachment)
        .filter(
            OrderAttachment.order_id == order_id,
            OrderAttachment.category == "drawing",
        )
        .all()
    )
    for row in drawing_attachment_rows:
        key = (row.storage_key or "").strip()
        if key and key not in keep_keys:
            obsolete_keys.add(key)

    structured_data["drawing_current_files"] = final_files
    deleted_count = delete_drawing_storage_keys(db, order_id, obsolete_keys)
    return final_files, deleted_count
