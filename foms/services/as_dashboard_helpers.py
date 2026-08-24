"""ERP AS 대시보드 탭/카운트 조건 헬퍼 (Batch 5 AS 구조-추출, 동작 보존).

AS 미완료/완료 탭 SQL 조건 + 다중 케이스 집계(_count_cases)를 분리한다.
라우트와 (향후) AS read-model이 공유한다. 원본은 `foms/web/cs/as_dashboard.py`
모듈 함수였고 verbatim 이전한다. Order 컬럼/JSON expression 기반 조건이라 sqlalchemy + Order만 의존.
flat 모듈(subpackage __init__ 순환 회피).
"""
from __future__ import annotations

from sqlalchemy import or_, and_, cast, String, func, case, select, text
from sqlalchemy.sql.elements import ColumnElement

from models import Order


def _erp_as_incomplete_filter(query):
    """AS 미완료 탭 공통 필터."""
    return query.filter(_erp_as_incomplete_condition())


def _erp_as_completed_condition():
    """AS 완료 탭 공통 조건(AS-AXIS-01 — 술어는 AS 축 투영 컬럼)."""
    return and_(
        Order.as_axis_status == 'COMPLETED',
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
        # type_=String 필수: 무타입(NullType) 산물끼리 `+` 하면 SQLAlchemy가 문자열
        # 결합으로 승격하지 못해 postgres에서 `text + text`(연산자 없음) → 500.
        expr = func.regexp_replace(expr, r'<[^>]+>', '', 'g', type_=String)
    return expr


def _as_log_text_expr(*, dialect_name='', use_postgres_regex=False):
    """structured_data.shipment.as_log 항목 본문(text)을 검색용 문자열로 반환.

    두 dialect 모두 **항목 본문만** 모은다. 배열을 통째로 텍스트화하면 (a) 항목
    id(``al_<epoch_ms>_..``)·ts가 검색어에 걸려 숫자 검색이 오탐투성이가 되고,
    (b) sqlite는 비ASCII를 ``\\uXXXX``로 이스케이프해 저장하므로 한글이 아예 안 잡힌다.

    Args:
        dialect_name: 바인드 dialect 이름.
        use_postgres_regex: PostgreSQL regexp로 HTML 태그를 제거할지 여부.

    Returns:
        태그가 제거된(옵션) as_log 본문 텍스트 SQL 표현식.
    """
    if dialect_name == 'postgresql':
        expr = func.jsonb_path_query_array(
            Order.structured_data,
            text("'$.shipment.as_log[*].text'::jsonpath"),
        )
    elif dialect_name == 'sqlite':
        # wildcard jsonpath가 없어 항목을 펼쳐 text만 이어붙인다. as_log가 배열이 아니면
        # json_each는 'malformed JSON'으로 터지므로(postgres lax 모드는 조용히 무매칭)
        # json_type 가드로 두 dialect의 실패 동작을 맞춘다.
        element = func.json_each(
            Order.structured_data, '$.shipment.as_log'
        ).table_valued('value')
        joined = (
            select(func.group_concat(func.json_extract(element.c.value, '$.text'), ' '))
            .select_from(element)
            .scalar_subquery()
        )
        expr = case(
            (func.json_type(Order.structured_data, '$.shipment.as_log') == 'array', joined),
            else_='',
        )
    else:
        expr = cast(Order.structured_data, String)
    expr = func.coalesce(cast(expr, String), '')
    if dialect_name == 'postgresql' and use_postgres_regex:
        # type_=String 필수: 무타입(NullType) 산물끼리 `+` 하면 SQLAlchemy가 문자열
        # 결합으로 승격하지 못해 postgres에서 `text + text`(연산자 없음) → 500.
        expr = func.regexp_replace(expr, r'<[^>]+>', '', 'g', type_=String)
    return expr


def _combined_as_content_expr(*, dialect_name='', use_postgres_regex=False):
    """legacy AS 내용(1/2) + 타임라인 기록(as_log) 본문을 합쳐 검색용 문자열로 반환.

    as_content 쓰기가 퇴역(T12)한 뒤 새 기록은 as_log에만 쌓인다. as_log를 빼면
    AS 내용 검색이 시간이 갈수록 비어간다.

    성분 사이에 구분자를 넣지 않는다 — 유일한 소비자가 `_sql_compact`(공백 전부 제거)라
    구분자는 어차피 지워지는데, 넣으려면 각 성분을 `CASE` 판정에서 한 번 더 평가해야
    한다(행당 평가 2배).
    """
    parts = [
        _as_content_expr(
            'as_content',
            dialect_name=dialect_name,
            use_postgres_regex=use_postgres_regex,
        ),
        _as_content_expr(
            'as_content_2',
            dialect_name=dialect_name,
            use_postgres_regex=use_postgres_regex,
        ),
        _as_log_text_expr(
            dialect_name=dialect_name,
            use_postgres_regex=use_postgres_regex,
        ),
    ]
    return parts[0] + parts[1] + parts[2]


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


def _as_availability_days_expr(*, dialect_name: str = '') -> ColumnElement[str]:
    """structured_data.schedule.as_visit.availability.days 추출(미기입='' 유지, 소문자).

    미기입('')과 명시적 '무관'(any)을 구분해야 지도 필터가 "미기입 N건 제외"를
    고지할 수 있다 — 기본값 주입 금지. SSOT: services/orders/as_availability.py.
    """
    return func.lower(func.coalesce(
        cast(_json_text_expr('schedule', 'as_visit', 'availability', 'days',
                             dialect_name=dialect_name), String),
        '',
    ))


def _as_availability_time_expr(*, dialect_name: str = '') -> ColumnElement[str]:
    """structured_data.schedule.as_visit.availability.time 추출(미기입='' 유지, 소문자)."""
    return func.lower(func.coalesce(
        cast(_json_text_expr('schedule', 'as_visit', 'availability', 'time',
                             dialect_name=dialect_name), String),
        '',
    ))


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


def erp_as_scope_condition():
    """AS 대시보드 모집단 조건(AS-AXIS-01) — AS 축이 있는 주문 전체.

    구 술어 ``Order.status.in_(['AS','AS_RECEIVED','AS_COMPLETED'])`` 를 대체한다. status 는
    overlay projection 이라 외부 write 한 번에 모집단에서 통째로 빠졌다(2026-08-14 사고).

    Returns:
        SQLAlchemy 조건식(``as_axis_status IS NOT NULL``).
    """
    return Order.as_axis_status.isnot(None)


def erp_as_status_filter_condition(status_filter):
    """AS 탭의 legacy status 필터를 AS 축 값으로 옮긴다(AS-AXIS-01).

    화면 필터는 여전히 ``AS``/``AS_RECEIVED``/``AS_COMPLETED`` 문자열을 보낸다(URL 하위호환).

    Args:
        status_filter: 화면이 보낸 legacy status 문자열.

    Returns:
        SQLAlchemy 조건식. 매핑되지 않는 값이면 ``None``(필터 미적용).
    """
    mapping = {'AS_RECEIVED': 'RECEIVED', 'AS': 'IN_PROGRESS', 'AS_COMPLETED': 'COMPLETED'}
    axis_value = mapping.get(str(status_filter or '').strip())
    return Order.as_axis_status == axis_value if axis_value else None


def _erp_as_incomplete_condition():
    """AS 미완료 탭 공통 조건.

    AS-AXIS-01: 술어는 **AS 축 투영 컬럼**(``as_axis_status``)을 본다. ``status`` 는 overlay
    projection 이라 일괄 완료처리 같은 외부 write 한 번에 AS 목록이 통째로 사라졌다
    (2026-08-14 사고 55건). 투영 컬럼은 ``sync_erp_flat_columns`` 를 지나는 AS 쓰기 경로만
    갱신하므로 status 를 덮어도 목록이 흔들리지 않는다.
    """
    return or_(
        Order.as_axis_status == 'RECEIVED',
        Order.as_axis_status == 'IN_PROGRESS',
        and_(
            Order.as_axis_status == 'COMPLETED',
            or_(
                Order.as_completed_date.is_(None),
                Order.as_completed_date == ''
            )
        )
    )
