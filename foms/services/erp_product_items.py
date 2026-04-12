"""ERP product items and measurement attachment helpers."""

from collections import defaultdict

from models import OrderAttachment

from foms.services.erp_display import _ensure_dict

__all__ = [
    "build_product_items_for_order",
    "build_product_items_for_orders",
]


def build_product_items_for_order(db, order):
    """Build normalized product items for one order and map measurement attachments."""
    if not order:
        return []
    s_data = _ensure_dict(order.structured_data)
    raw = s_data.get('items') or s_data.get('products') or s_data.get('product_items') or []
    if isinstance(raw, dict):
        raw = [raw]
    product_items = []
    for item_data in list(raw):
        if not isinstance(item_data, dict):
            continue
        item = dict(item_data)
        item['width'] = item.get('width') or item.get('spec_width') or ''
        item['depth'] = item.get('depth') or item.get('spec_depth') or ''
        item['height'] = item.get('height') or item.get('spec_height') or ''
        item['measurement_images'] = []
        product_items.append(item)

    order_id = getattr(order, 'id', None)
    if not order_id:
        return product_items

    for attachment in db.query(OrderAttachment).filter(
        OrderAttachment.order_id == order_id,
        OrderAttachment.category.in_(['measurement', 'measure_photo', 'photo'])
    ).order_by(OrderAttachment.created_at.desc()).all():
        item_index_raw = getattr(attachment, 'item_index', None)
        try:
            item_index = int(item_index_raw) if item_index_raw is not None else None
            if item_index is not None and item_index < 0:
                item_index = None
        except (TypeError, ValueError):
            item_index = None
        photo = {
            'filename': attachment.filename,
            'view_url': f'/api/files/view/{attachment.storage_key}',
            'download_url': f'/api/files/download/{attachment.storage_key}',
            'key': attachment.storage_key,
            'item_index': item_index,
        }
        if item_index is not None and 0 <= item_index < len(product_items):
            product_items[item_index].setdefault('measurement_images', []).append(photo)

    return product_items


def build_product_items_for_orders(db, orders):
    """Batch-build product items for many orders while avoiding N+1 attachment queries."""
    if not orders:
        return

    order_ids = [order.id for order in orders if hasattr(order, 'id') and order.id]
    if not order_ids:
        for order in orders:
            order.product_items = []
        return

    for order in orders:
        s_data = _ensure_dict(order.structured_data)
        raw = s_data.get('items') or s_data.get('products') or s_data.get('product_items') or []
        if isinstance(raw, dict):
            raw = [raw]

        product_items = []
        for item_data in list(raw):
            if not isinstance(item_data, dict):
                continue
            item = dict(item_data)
            item['width'] = item.get('width') or item.get('spec_width') or ''
            item['depth'] = item.get('depth') or item.get('spec_depth') or ''
            item['height'] = item.get('height') or item.get('spec_height') or ''
            item['measurement_images'] = []
            product_items.append(item)

        order.product_items = product_items

    attachments = db.query(OrderAttachment).filter(
        OrderAttachment.order_id.in_(order_ids),
        OrderAttachment.category.in_(['measurement', 'measure_photo', 'photo'])
    ).order_by(OrderAttachment.order_id, OrderAttachment.created_at.desc()).all()

    order_attachments = defaultdict(list)
    for attachment in attachments:
        order_attachments[attachment.order_id].append(attachment)

    for order in orders:
        if not hasattr(order, 'id') or order.id not in order_attachments:
            continue

        product_items = order.product_items
        for attachment in order_attachments[order.id]:
            item_index_raw = getattr(attachment, 'item_index', None)
            try:
                item_index = int(item_index_raw) if item_index_raw is not None else None
                if item_index is not None and item_index < 0:
                    item_index = None
            except (TypeError, ValueError):
                item_index = None

            photo = {
                'filename': attachment.filename,
                'view_url': f'/api/files/view/{attachment.storage_key}',
                'download_url': f'/api/files/download/{attachment.storage_key}',
                'key': attachment.storage_key,
                'item_index': item_index,
            }
            if item_index is not None and 0 <= item_index < len(product_items):
                product_items[item_index].setdefault('measurement_images', []).append(photo)
