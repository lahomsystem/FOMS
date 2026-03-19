"""ERP 작업 큐 상세 preload payload helpers."""

from collections import defaultdict

from apps.api.files import build_file_download_url, build_file_view_url
from models import OrderAttachment
from services.erp_display import _ensure_dict


def _extract_row_id_and_structured_data(row):
    if isinstance(row, dict):
        return row.get("id"), _ensure_dict(row.get("structured_data"))
    return getattr(row, "id", None), _ensure_dict(getattr(row, "structured_data", None))


def build_order_detail_payload_map(db, rows):
    """Visible rows for work queues -> preloaded detail payload map."""
    structured_map = {}
    order_ids = []

    for row in rows or []:
        order_id, structured_data = _extract_row_id_and_structured_data(row)
        if not order_id:
            continue
        structured_map[order_id] = structured_data
        order_ids.append(order_id)

    if not order_ids:
        return {}

    attachments_map = defaultdict(list)
    attachments = (
        db.query(OrderAttachment)
        .filter(OrderAttachment.order_id.in_(order_ids))
        .order_by(OrderAttachment.order_id.asc(), OrderAttachment.created_at.desc())
        .all()
    )

    for attachment in attachments:
        storage_key = str(attachment.storage_key or "")
        thumbnail_key = str(attachment.thumbnail_key or "") if attachment.thumbnail_key else ""
        attachments_map[attachment.order_id].append(
            {
                "id": attachment.id,
                "order_id": attachment.order_id,
                "filename": attachment.filename,
                "file_type": attachment.file_type,
                "category": attachment.category or "measurement",
                "item_index": attachment.item_index,
                "file_size": attachment.file_size,
                "storage_key": storage_key,
                "key": storage_key,
                "thumbnail_key": thumbnail_key or None,
                "view_url": build_file_view_url(storage_key) if storage_key else "",
                "download_url": build_file_download_url(storage_key) if storage_key else "",
                "thumbnail_view_url": build_file_view_url(thumbnail_key) if thumbnail_key else None,
                "created_at": attachment.created_at.strftime("%Y-%m-%d %H:%M:%S") if attachment.created_at else None,
                "user_id": attachment.user_id,
            }
        )

    return {
        order_id: {
            "success": True,
            "structured_data": structured_map.get(order_id, {}),
            "attachments": attachments_map.get(order_id, []),
        }
        for order_id in order_ids
    }


def attach_order_detail_payloads(db, rows):
    """Attach detail payloads to visible rows/dicts for server preload."""
    payload_map = build_order_detail_payload_map(db, rows)
    for row in rows or []:
        order_id, structured_data = _extract_row_id_and_structured_data(row)
        payload = payload_map.get(
            order_id,
            {
                "success": True,
                "structured_data": structured_data,
                "attachments": [],
            },
        )
        if isinstance(row, dict):
            row["detail_payload"] = payload
        else:
            setattr(row, "detail_payload", payload)
