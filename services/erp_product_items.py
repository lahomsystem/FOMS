"""ERP 제품 항목 + 실측 첨부 구성. 도면 작업실·실측 대시보드 공통."""
from models import OrderAttachment
from services.erp_display import _ensure_dict


def build_product_items_for_order(db, order):
    """
    order.structured_data에서 items 추출 후, OrderAttachment(measurement 등)로
    항목별 measurement_images를 매핑한 리스트 반환.
    도면 작업실 상세·실측 대시보드에서 동일한 구조로 사용.
    """
    if not order:
        return []
    s_data = _ensure_dict(order.structured_data)
    raw = s_data.get('items') or s_data.get('products') or s_data.get('product_items') or []
    if isinstance(raw, dict):
        raw = [raw]
    product_items = []
    for it in list(raw):
        if not isinstance(it, dict):
            continue
        item = dict(it)
        item['width'] = item.get('width') or item.get('spec_width') or ''
        item['depth'] = item.get('depth') or item.get('spec_depth') or ''
        item['height'] = item.get('height') or item.get('spec_height') or ''
        item['measurement_images'] = []
        product_items.append(item)

    order_id = getattr(order, 'id', None)
    if not order_id:
        return product_items

    for att in db.query(OrderAttachment).filter(
        OrderAttachment.order_id == order_id,
        OrderAttachment.category.in_(['measurement', 'measure_photo', 'photo'])
    ).order_by(OrderAttachment.created_at.desc()).all():
        item_index_raw = getattr(att, 'item_index', None)
        try:
            item_index = int(item_index_raw) if item_index_raw is not None else None
            if item_index is not None and item_index < 0:
                item_index = None
        except (TypeError, ValueError):
            item_index = None
        photo = {
            'filename': att.filename,
            'view_url': f'/api/files/view/{att.storage_key}',
            'download_url': f'/api/files/download/{att.storage_key}',
            'key': att.storage_key,
            'item_index': item_index,
        }
        if item_index is not None and 0 <= item_index < len(product_items):
            product_items[item_index].setdefault('measurement_images', []).append(photo)
        # 공통 실측(common_measure_photos)은 도면 상세에서만 사용하므로 여기선 항목에만 매핑

    return product_items
