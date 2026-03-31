from datetime import datetime
from services.erp_display import _normalize_date_to_yyyymmdd, clean_dict_like_name

def sync_erp_flat_columns(order, structured_data: dict) -> None:
    """Phase B & D: ERP Beta 주문의 정규화 플랫 컬럼을 structured_data와 동기화.

    호출 시점: 단계 변경, 일정 수정 API 완료 후 db.commit() 전.

    Args:
        order: Order 모델 인스턴스
        structured_data: order.structured_data dict (이미 수정 완료된 상태)
    """
    if not getattr(order, 'is_erp_beta', False):
        return

    parties = (structured_data.get('parties') or {})
    manager_name = clean_dict_like_name(((parties.get('manager') or {}).get('name')) or '')
    order.manager_name = manager_name or ''
    
    # Phase B: Dates
    schedule = (structured_data.get('schedule') or {})
    meas_raw = (schedule.get('measurement') or {}).get('date')
    cons_raw = (schedule.get('construction') or {}).get('date')
    
    order.erp_measurement_date = _normalize_date_to_yyyymmdd(meas_raw)
    order.erp_construction_date = _normalize_date_to_yyyymmdd(cons_raw)

    # Phase D: Flat Columns
    workflow = (structured_data.get('workflow') or {})
    stage = workflow.get('stage')
    order.erp_stage_code = stage if isinstance(stage, str) else None

    flags = (structured_data.get('flags') or {})
    order.erp_urgent = str(flags.get('urgent')).lower() == 'true' or flags.get('urgent') is True

    stage_updated_at = workflow.get('stage_updated_at')
    parsed_date = None
    if stage_updated_at:
        try:
            parsed_date = datetime.fromisoformat(str(stage_updated_at).replace('Z', '+00:00'))
        except (ValueError, TypeError):
            pass
    order.erp_drawing_updated_at = parsed_date

    assignments = (structured_data.get('assignments') or {})
    owner_team = assignments.get('owner_team')
    order.erp_owner_team_code = owner_team if isinstance(owner_team, str) else None
