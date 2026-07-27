"""ERP AS 대시보드 탭/카운트 조건 헬퍼 (Batch 5 AS 구조-추출, 동작 보존).

AS 미완료/완료 탭 SQL 조건 + 다중 케이스 집계(_count_cases)를 분리한다.
라우트와 (향후) AS read-model이 공유한다. 원본은 `foms/web/cs/as_dashboard.py`
모듈 함수였고 verbatim 이전한다. Order 컬럼/JSON expression 기반 조건이라 sqlalchemy + Order만 의존.
flat 모듈(subpackage __init__ 순환 회피).
"""
from __future__ import annotations

from sqlalchemy import or_, and_, cast, String, func, case
from sqlalchemy.sql.elements import ColumnElement

from models import Order


def _erp_as_incomplete_filter(query):
    """AS 미완료 탭 공통 필터."""
    return query.filter(_erp_as_incomplete_condition())


def _erp_as_completed_condition():
    """AS 완료 탭 공통 조건."""
    return and_(
        Order.status == 'AS_COMPLETED',
        Order.as_completed_date.isnot(None),
        Order.as_completed_date != ''
    )


def _count_cases(query, *definitions):
    """여러 조건의 집계를 한 번에 계산한다."""
    columns = [
        func.coalesce(func.sum(case((condition, 1), else_=0)), 0).label(name)
        for name, condition in definitions
    ]
    row = query.with_entities(*columns).one()
    return {
        name: int(getattr(row, name) or 0)
        for name, _condition in definitions
    }


def _sql_compact(expr, *, use_postgres_regex=False):
    """DB 비교용 공백 제거 식."""
    expr = func.coalesce(cast(expr, String), '')
    if use_postgres_regex:
        return func.lower(func.regexp_replace(expr, r'\s+', '', 'g'))
    return func.lower(
        func.replace(
            func.replace(
                func.replace(
                    func.replace(expr, ' ', ''),
                    '\n', ''
                ),
                '\r', ''
            ),
            '\t', ''
        )
    )


def _json_text_expr(*path_parts, dialect_name=''):
    """DB dialect에 맞춰 JSON 경로의 텍스트 값을 추출."""
    if dialect_name == 'postgresql':
        return func.jsonb_extract_path_text(Order.structured_data, *path_parts)
    if dialect_name == 'sqlite':
        return func.json_extract(Order.structured_data, '$.' + '.'.join(path_parts))
    return cast(Order.structured_data, String)


def _as_content_expr(field_name='as_content', *, dialect_name='', use_postgres_regex=False):
    """structured_data.shipment AS 내용 필드 추출 (검색/탭 판정용)."""
    expr = _json_text_expr('shipment', field_name, dialect_name=dialect_name)
    expr = func.coalesce(cast(expr, String), '')
    if dialect_name == 'postgresql' and use_postgres_regex:
        expr = func.regexp_replace(expr, r'<[^>]+>', '', 'g')
    return expr


def _combined_as_content_expr(*, dialect_name='', use_postgres_regex=False):
    """AS 내용 1/2 탭을 합쳐 검색용 문자열로 반환."""
    primary = _as_content_expr(
        'as_content',
        dialect_name=dialect_name,
        use_postgres_regex=use_postgres_regex,
    )
    secondary = _as_content_expr(
        'as_content_2',
        dialect_name=dialect_name,
        use_postgres_regex=use_postgres_regex,
    )
    return func.trim(primary + case((secondary != '', ' '), else_='') + secondary)


def _sales_delivery_expr(*, dialect_name=''):
    """structured_data.shipment.sales_delivery 추출 (탭 분류용)."""
    return func.coalesce(
        cast(_json_text_expr('shipment', 'sales_delivery', dialect_name=dialect_name), String),
        'false'
    )


def _display_customer_name_expr(*, dialect_name=''):
    return func.coalesce(
        cast(_json_text_expr('parties', 'customer', 'name', dialect_name=dialect_name), String),
        Order.customer_name,
    )


def _display_manager_name_expr(*, dialect_name=''):
    return func.coalesce(
        cast(_json_text_expr('parties', 'manager', 'name', dialect_name=dialect_name), String),
        Order.manager_name,
    )


def _display_phone_expr(*, dialect_name=''):
    return func.coalesce(
        cast(_json_text_expr('parties', 'customer', 'phone', dialect_name=dialect_name), String),
        Order.phone,
    )


def _display_address_expr(*, dialect_name=''):
    address_full = cast(_json_text_expr('site', 'address_full', dialect_name=dialect_name), String)
    address_main = func.coalesce(cast(_json_text_expr('site', 'address_main', dialect_name=dialect_name), String), '')
    address_detail = func.coalesce(cast(_json_text_expr('site', 'address_detail', dialect_name=dialect_name), String), '')
    address_joined = func.trim(
        address_main + case((address_detail != '', ' '), else_='') + address_detail
    )
    return func.coalesce(address_full, func.nullif(address_joined, ''), Order.address)


def _sales_delivery_true_filter(sales_delivery_expr):
    """영업/택배 체크된 주문 필터."""
    return func.lower(cast(sales_delivery_expr, String)).in_(['true', '1', 'yes'])


def _as_pending_expr(*, dialect_name=''):
    """structured_data.shipment.as_pending 추출 (집계용)."""
    return func.coalesce(
        cast(_json_text_expr('shipment', 'as_pending', dialect_name=dialect_name), String),
        'false'
    )


def _as_visit_date_expr(*, dialect_name=''):
    """structured_data.schedule.as_visit.date 추출 (집계용)."""
    return func.coalesce(
        cast(_json_text_expr('schedule', 'as_visit', 'date', dialect_name=dialect_name), String),
        ''
    )


def _as_billing_type_expr(*, dialect_name: str = '') -> ColumnElement[str]:
    """structured_data.shipment.as_billing.type 추출(기본 'free', 소문자).

    Args:
        dialect_name: DB dialect 이름('postgresql'/'sqlite'/기타).

    Returns:
        비용 종류 문자열 SQL 식(등호 비교용).
    """
    return func.lower(func.coalesce(
        cast(_json_text_expr('shipment', 'as_billing', 'type', dialect_name=dialect_name), String),
        'free',
    ))


def _as_billing_confirmed_expr(*, dialect_name: str = '') -> ColumnElement[str]:
    """structured_data.shipment.as_billing.confirmed 추출(기본 'false', 소문자).

    dialect마다 JSON boolean 표현이 다르므로(postgres 'true' / sqlite 1) 값 비교는
    `_sales_delivery_true_filter`(true/1/yes 집합)로 하고 여기서는 문자열만 낸다.

    Args:
        dialect_name: DB dialect 이름('postgresql'/'sqlite'/기타).

    Returns:
        확정 여부 문자열 SQL 식(진리값 판정은 호출부에서).
    """
    return func.lower(func.coalesce(
        cast(_json_text_expr('shipment', 'as_billing', 'confirmed', dialect_name=dialect_name), String),
        'false',
    ))


def _has_text_value(expr):
    """빈 문자열이 아닌 값 판정용 SQL 식."""
    return func.trim(func.coalesce(cast(expr, String), '')) != ''


def _erp_as_incomplete_condition():
    """AS 미완료 탭 공통 조건."""
    return or_(
        Order.status == 'AS',
        Order.status == 'AS_RECEIVED',
        and_(
            Order.status == 'AS_COMPLETED',
            or_(
                Order.as_completed_date.is_(None),
                Order.as_completed_date == ''
            )
        )
    )
