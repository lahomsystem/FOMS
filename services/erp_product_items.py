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

def build_product_items_for_orders(db, orders):
    """
    여러 주문에 대해 build_product_items_for_order를 수행하되 N+1 쿼리를 방지합니다.
    OrderAttachment를 한 번에 가져와 메모리에서 매핑합니다.
    """
    if not orders:
        return
    
    order_ids = [o.id for o in orders if hasattr(o, 'id') and o.id]
    if not order_ids:
        for o in orders:
            o.product_items = []
        return

    # 1. 모든 주문의 항목 구조 기본 파싱
    for order in orders:
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
            
        order.product_items = product_items

    # 2. 모든 주문의 첨부파일 한 번에 로드 (가장 최근 순으로 정렬)
    from models import OrderAttachment
    attachments = db.query(OrderAttachment).filter(
        OrderAttachment.order_id.in_(order_ids),
        OrderAttachment.category.in_(['measurement', 'measure_photo', 'photo'])
    ).order_by(OrderAttachment.order_id, OrderAttachment.created_at.desc()).all()

    # 3. 첨부파일들을 주문 ID별로 그룹화
    from collections import defaultdict
    order_attachments = defaultdict(list)
    for att in attachments:
        order_attachments[att.order_id].append(att)

    # 4. 메모리에서 항목에 사진 매핑
    for order in orders:
        if not hasattr(order, 'id') or order.id not in order_attachments:
            continue
            
        product_items = order.product_items
        for att in order_attachments[order.id]:
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
