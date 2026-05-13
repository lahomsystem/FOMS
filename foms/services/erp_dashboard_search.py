"""ERP 주문·출고 대시보드 공통 전역 검색용 SQLAlchemy 조건."""

from sqlalchemy import String, and_, cast, or_

from models import Order


def erp_order_dashboard_search_predicate(
    search_term: str,
    *,
    include_structured_data_blob: bool = False,
):
    """
    ERP 화면에 노출되는 주요 컬럼 및 structured_data 가시 경로에 대한 ilike OR 조건.

    주문 작업 큐(`/erp/dashboard`)는 ``include_structured_data_blob=False``로 두어
    항목 메모 등 비노출 JSON 깊은 구간이 검색에 걸리지 않게 한다.

    출고 대시보드는 시공자 등 깊은 필드를 찾기 위해 ``True``로 JSON 전체 문자열
    ilike를 추가한다.

    Args:
        search_term: ``%{q}%`` 형태 ILIKE 패턴.
        include_structured_data_blob: True이면 ``cast(structured_data, String).ilike`` 추가.

    Returns:
        SQLAlchemy ``or_(...)`` 술어.
    """
    structured_visible_fields = [
        Order.structured_data["parties"]["customer"]["name"].as_string(),
        Order.structured_data["parties"]["customer"]["phone"].as_string(),
        Order.structured_data["parties"]["manager"]["name"].as_string(),
        Order.structured_data["parties"]["orderer"]["name"].as_string(),
        Order.structured_data["site"]["address_full"].as_string(),
        Order.structured_data["site"]["address_main"].as_string(),
        Order.structured_data["items"][0]["product_name"].as_string(),
        Order.structured_data["items"][0]["name"].as_string(),
        Order.structured_data["schedule"]["measurement"]["date"].as_string(),
        Order.structured_data["schedule"]["measurement"]["time"].as_string(),
        Order.structured_data["schedule"]["construction"]["date"].as_string(),
    ]

    clauses = [
        Order.id.cast(String).ilike(search_term),
        Order.customer_name.ilike(search_term),
        Order.phone.ilike(search_term),
        Order.address.ilike(search_term),
        Order.product.ilike(search_term),
        Order.manager_name.ilike(search_term),
        *[
            and_(Order.is_erp_order == True, field.ilike(search_term))
            for field in structured_visible_fields
        ],
    ]
    if include_structured_data_blob:
        clauses.append(
            and_(
                Order.is_erp_order == True,
                cast(Order.structured_data, String).ilike(search_term),
            )
        )
    return or_(*clauses)


# 출고 검색 포커스 날짜: OrderScheduleDate 후보 범위 (오늘 기준 ±일수)
SHIPMENT_SEARCH_FOCUS_SCHEDULE_HALF_RANGE_DAYS = 730
