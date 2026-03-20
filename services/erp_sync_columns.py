from services.erp_display import _normalize_date_to_yyyymmdd

def sync_erp_date_columns(order, structured_data: dict) -> None:
    """ERP Beta 주문의 정규화 날짜 컬럼을 structured_data와 동기화.

    호출 시점: 단계 변경, 일정 수정 API 완료 후 db.commit() 전.

    Args:
        order: Order 모델 인스턴스
        structured_data: order.structured_data dict (이미 수정 완료된 상태)
    """
    if not getattr(order, 'is_erp_beta', False):
        return
    
    schedule = (structured_data.get('schedule') or {})
    meas_raw = (schedule.get('measurement') or {}).get('date')
    cons_raw = (schedule.get('construction') or {}).get('date')
    
    order.erp_measurement_date = _normalize_date_to_yyyymmdd(meas_raw)
    order.erp_construction_date = _normalize_date_to_yyyymmdd(cons_raw)
