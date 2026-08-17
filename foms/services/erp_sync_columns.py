"""ERP flat column synchronization helpers."""

from foms.services.erp_display import (
    _normalize_date_to_yyyymmdd,
    clean_dict_like_name,
    erp_deposit_amount_from_structured,
)
from foms.services.datetime_kst import to_utc_naive
from foms.services.erp_order_flags import is_erp_order_record
from foms.services.phone_search import normalize_phone_digits

__all__ = ["sync_erp_flat_columns"]


def _parse_stage_updated_at(value):
    return to_utc_naive(value)


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
    order.measurement_date = order.erp_measurement_date or ""
    order.scheduled_date = order.erp_construction_date or ""

    workflow = (structured_data.get('workflow') or {})
    stage = workflow.get('stage')
    order.erp_stage_code = stage if isinstance(stage, str) else None

    # AS-AXIS-01: AS 축을 SQL 로 물을 수 있게 플랫 투영한다. status 컬럼은 overlay
    # projection 이라 외부 write 에 덮이면 AS 목록이 통째로 사라졌다(2026-08-14 사고).
    from foms.services.orders.state_axes import derive_as_axis_status
    order.as_axis_status = derive_as_axis_status(order, structured_data)

    flags = (structured_data.get('flags') or {})
    order.erp_urgent = str(flags.get('urgent')).lower() == 'true' or flags.get('urgent') is True

    stage_updated_at = workflow.get('stage_updated_at')
    parsed_date = _parse_stage_updated_at(stage_updated_at)
    order.erp_drawing_updated_at = parsed_date
    order.erp_stage_updated_at = parsed_date

    assignments = (structured_data.get('assignments') or {})
    owner_team = assignments.get('owner_team')
    order.erp_owner_team_code = owner_team if isinstance(owner_team, str) else None

    customer = (parties.get('customer') or {}) if isinstance(parties.get('customer'), dict) else {}
    phone_raw = customer.get('phone') or getattr(order, 'phone', None)
    order.erp_phone_digits = normalize_phone_digits(phone_raw)

    pa = erp_deposit_amount_from_structured(structured_data)
    if pa is not None:
        order.payment_amount = pa
