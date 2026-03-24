"""
주소 변경 시 지오코딩 초기화 공통 Helper (2026-03-15).
commit/queue는 caller가 성공 경계에서 처리.
"""
from sqlalchemy.orm.attributes import flag_modified


def reset_order_geocode_on_address_change(order, new_address):
    """
    주소 수정 시 lat/lng 초기화 및 geocode_status=pending 설정.
    db.commit(), enqueue_geocode_order_address()는 호출하지 않음.

    Args:
        order: Order 인스턴스
        new_address: 새 주소 문자열

    Returns:
        정규화된 주소 문자열 (저장된 값)
    """
    addr = (new_address or '').strip()
    if not addr:
        return ''

    if order.is_erp_beta and order.structured_data is not None:
        import copy
        sd = copy.deepcopy(order.structured_data or {})
        if 'site' not in sd:
            sd['site'] = {}
        sd['site']['address_full'] = addr
        sd['site']['address_main'] = addr
        order.structured_data = sd
        flag_modified(order, 'structured_data')

    order.address = addr  # ERP Beta / 비 Beta 공통으로 DB 컬럼 동기화

    order.lat = None
    order.lng = None
    order.geocode_status = 'pending'

    return addr
