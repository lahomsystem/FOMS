"""
주문 영구 삭제 시 스토리지(R2/로컬) 파일 정리.
OrderAttachment, blueprint, drawing_gateway(drawing_current_files) 파일 삭제.
"""

from models import Order, OrderAttachment
from services.storage import get_storage

VIEW_URL_PREFIX = "/api/files/view/"


def delete_storage_files_for_order(db, order):
    """
    주문에 연관된 스토리지 파일을 삭제합니다.
    DB 삭제 전에 호출해야 합니다 (OrderAttachment 등 조회를 위해).
    """
    if not order:
        return
    order_id = order.id
    storage = get_storage()

    # 1. OrderAttachment: storage_key, thumbnail_key
    attachments = db.query(OrderAttachment).filter(OrderAttachment.order_id == order_id).all()
    for att in attachments:
        try:
            if att.storage_key:
                storage.delete_file(att.storage_key)
        except Exception:
            pass
        try:
            if att.thumbnail_key:
                storage.delete_file(att.thumbnail_key)
        except Exception:
            pass

    # 2. Blueprint: order.blueprint_image_url -> storage key
    url = (order.blueprint_image_url or "").strip()
    if url.startswith(VIEW_URL_PREFIX):
        key = url[len(VIEW_URL_PREFIX) :].lstrip("/")
        if key and ".." not in key:
            try:
                storage.delete_file(key)
            except Exception:
                pass

    # 3. Drawing gateway: structured_data.drawing_current_files[].key
    sd = order.structured_data or {}
    drawing_files = sd.get("drawing_current_files") or []
    for item in drawing_files:
        if not isinstance(item, dict):
            continue
        key = (item.get("key") or "").strip()
        if key and ".." not in key and f"orders/{order_id}/" in key:
            try:
                storage.delete_file(key)
            except Exception:
                pass
