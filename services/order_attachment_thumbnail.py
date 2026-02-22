"""Background thumbnail jobs for ERP order attachments."""
import os
from concurrent.futures import ThreadPoolExecutor

from db import db_session
from models import OrderAttachment
from services.storage import get_storage

_thumb_workers_raw = os.environ.get('ORDER_ATTACHMENT_THUMBNAIL_WORKERS', '2')
try:
    _thumb_workers = int(_thumb_workers_raw or 2)
except (TypeError, ValueError):
    _thumb_workers = 2
_thumb_workers = max(1, min(_thumb_workers, 4))
_thumbnail_executor = ThreadPoolExecutor(max_workers=_thumb_workers)


def _generate_order_attachment_thumbnail_background(attachment_id, storage_key):
    if not attachment_id or not storage_key:
        return
    try:
        storage = get_storage()
        result = storage.generate_thumbnail_from_storage_key(storage_key)
        if not result.get('success'):
            return
        thumbnail_key = result.get('thumbnail_key')
        if not thumbnail_key:
            return

        attachment_db = db_session()
        try:
            attachment = attachment_db.query(OrderAttachment).filter(
                OrderAttachment.id == attachment_id
            ).first()
            if attachment and not attachment.thumbnail_key:
                attachment.thumbnail_key = thumbnail_key
                attachment_db.commit()
        finally:
            attachment_db.close()
            db_session.remove()
    except Exception as e:
        print(f"[OrderAttachmentThumbnail] background generation error: {e}")


def schedule_order_attachment_thumbnail_generation(attachment_id, storage_key):
    if not attachment_id or not storage_key:
        return
    try:
        _thumbnail_executor.submit(
            _generate_order_attachment_thumbnail_background,
            int(attachment_id),
            storage_key,
        )
    except Exception as e:
        print(f"[OrderAttachmentThumbnail] schedule error: {e}")
