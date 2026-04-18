"""ERP flat column synchronization helpers."""

from datetime import datetime

from foms.services.erp_display import _normalize_date_to_yyyymmdd, clean_dict_like_name
from foms.services.erp_order_flags import is_erp_order_record

__all__ = ["sync_erp_flat_columns"]


def sync_erp_flat_columns(order, structured_data: dict) -> None:
    """Synchronize ERP Order flat columns from structured order data before commit."""
    if not is_erp_order_record(order):
        return

    parties = (structured_data.get('parties') or {})
    manager_name = clean_dict_like_name(((parties.get('manager') or {}).get('name')) or '')
    order.manager_name = manager_name or ''

    schedule = (structured_data.get('schedule') or {})
    meas_raw = (schedule.get('measurement') or {}).get('date')
    cons_raw = (schedule.get('construction') or {}).get('date')

    order.erp_measurement_date = _normalize_date_to_yyyymmdd(meas_raw)
    order.erp_construction_date = _normalize_date_to_yyyymmdd(cons_raw)

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
