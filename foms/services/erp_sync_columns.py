"""ERP flat column synchronization helpers."""

from foms.services.erp_display import (
    _normalize_date_to_yyyymmdd,
    clean_dict_like_name,
    erp_deposit_amount_from_structured,
    manager_display_name,
)
from foms.services.datetime_kst import to_utc_naive
from foms.services.erp_order_flags import is_erp_order_record
from foms.services.phone_search import normalize_phone_digits

__all__ = [
    "is_placeholder_phone",
    "sync_as_axis_column",
    "sync_erp_flat_columns",
    "sync_identity_phone_column",
]


def is_placeholder_phone(phone: str) -> bool:
    """실제 연락처가 아닌 자리표시자 전화인가.

    ``000-0000-0000`` 한 값만 막던 시절의 구멍: 운영 주문 #4648 의 정본에
    ``000000000`` 이 들어가 있다(사람이 편집 중 남긴 값). 문자열 비교 한 줄로는 그 변형을
    못 걸러서, 정본을 따라가는 flat 동기가 **진짜 번호를 자리표시자로 덮는다.**

    판정은 숫자만 남긴 뒤에 한다 — 하이픈 유무·자릿수 변형이 전부 같은 값으로 접힌다.

    Args:
        phone: 정본에 들어 있는 전화 문자열.

    Returns:
        자리표시자(전부 0이거나 숫자가 모자람)면 True.

    >>> is_placeholder_phone('000-0000-0000')
    True
    >>> is_placeholder_phone('000000000')
    True
    >>> is_placeholder_phone('010-3468-7933')
    False
    """
    digits = normalize_phone_digits(phone or '') or ''
    if not digits:
        return True
    if set(digits) == {'0'}:
        return True
    # 시내번호(02-xxx-xxxx)까지 살리려면 9자리가 하한이다.
    return len(digits) < 9


def sync_identity_phone_column(order, structured_data: dict) -> None:
    """flat ``phone`` 을 정본 고객 전화에 맞춘다(저장 경로·flat 백필 공용 규칙).

    정본이 비었거나 자리표시자면 기존 값을 덮지 않는다. 저장 경로는
    ``foms.api.erp_orders_structured._sync_identity_flat_columns`` 가, 과거 잔여 drift 는
    ``foms.services.orders.erp_flat_backfill`` 이 이 함수를 부른다 — 규칙이 한 벌이다.

    Args:
        order: 대상 주문(ORM 또는 shim).
        structured_data: 정본 structured_data.

    Returns:
        None.
    """
    parties = structured_data.get('parties') if isinstance(structured_data, dict) else None
    customer = (parties or {}).get('customer') if isinstance(parties, dict) else None
    if not isinstance(customer, dict):
        return
    cust_phone = str(customer.get('phone') or '').strip()
    if cust_phone and not is_placeholder_phone(cust_phone):
        order.phone = cust_phone


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
    manager_name = clean_dict_like_name(manager_display_name(parties))
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
