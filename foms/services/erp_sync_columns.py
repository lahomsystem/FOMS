"""ERP flat column synchronization helpers."""

from datetime import datetime

from foms.services.erp_display import (
    _normalize_date_to_yyyymmdd,
    clean_dict_like_name,
    erp_payment_amount_from_structured,
)
from foms.services.erp_order_flags import is_erp_order_record

__all__ = ["sync_erp_flat_columns"]


def _parse_stage_updated_at(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace('Z', '+00:00'))
    except (ValueError, TypeError):
        return None


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
    parsed_date = _parse_stage_updated_at(stage_updated_at)
    order.erp_drawing_updated_at = parsed_date
    order.erp_stage_updated_at = parsed_date

    assignments = (structured_data.get('assignments') or {})
    owner_team = assignments.get('owner_team')
    order.erp_owner_team_code = owner_team if isinstance(owner_team, str) else None

    pa = erp_payment_amount_from_structured(structured_data)
    if pa is not None:
        order.payment_amount = pa
