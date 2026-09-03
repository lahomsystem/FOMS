"""ERP flat column synchronization helpers."""

from foms.services.erp_display import (
    _normalize_date_to_yyyymmdd,
    clean_dict_like_name,
    erp_deposit_amount_from_structured,
)
from foms.services.datetime_kst import to_utc_naive
from foms.services.erp_order_flags import is_erp_order_record
from foms.services.phone_search import normalize_phone_digits

__all__ = ["sync_as_axis_column", "sync_erp_flat_columns"]


def _parse_stage_updated_at(value):
    return to_utc_naive(value)


def sync_as_axis_column(order, structured_data: dict) -> None:
    """AS 축 플랫 투영(``orders.as_axis_status``)을 동기화한다 (AS-AXIS-01).

    **ERP 여부와 직교한 축이라 ERP 게이트 밖에 있다.** 게이트 안에 있던 동안, AS 완료
    커맨드가 ``order.status`` 는 무조건 쓰고 이 컬럼만 못 써서 비ERP AS 주문이 완료 후에도
    미완료 탭에 남았다(2026-09-03 운영 실측 3건 — #1315·#1119·#1706, 전부
    ``is_erp_order=False``). 탭 술어는 이 컬럼을, 뱃지는 status 를 보므로 초록 'AS완료'
    뱃지를 단 채 미완료 목록에 갇힌다.

    **값이 나오면 갱신하고, 안 나오면 기존 값을 지우지 않는다.** as_lifecycle 이 없는
    레거시 AS 주문(운영 566건 중 506건)은 유도 근거가 status 뿐이라, status 를 COMPLETED 로
    덮는 write 가 이 동기화를 지나면 투영까지 지워져 2026-08-14 사고가 그대로 재현된다
    (2026-08-18 스테이징 실측으로 확인). AS 이력은 한번 생기면 사라지지 않는 축이므로
    (종료도 COMPLETED 라는 값이다) 암묵적 삭제는 규약 위반이다.

    Args:
        order: 대상 주문(ORM).
        structured_data: 커밋 전 최신 structured_data.

    Returns:
        None. ``order.as_axis_status`` 를 제자리에서 갱신한다.
    """
    from foms.services.orders.state_axes import derive_as_axis_status

    derived_as_axis = derive_as_axis_status(order, structured_data)
    if derived_as_axis is not None:
        order.as_axis_status = derived_as_axis


def sync_erp_flat_columns(order, structured_data: dict) -> None:
    """Synchronize ERP Order flat columns from structured order data before commit."""
    # AS 축은 ERP 여부와 직교한다 — 게이트보다 먼저 동기화한다(AS-AXIS-01).
    sync_as_axis_column(order, structured_data)

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
