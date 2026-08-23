"""ERP 주문·출고 대시보드 공통 전역 검색용 SQLAlchemy 조건."""

from __future__ import annotations

from typing import Any, Iterable

from sqlalchemy import String, and_, cast, func, or_
from sqlalchemy.orm import Query

from foms.services.phone_search import extract_phone_digit_query
from models import Order

# Legacy SLG measurement dashboards (지방·수도권·자가실측) 렌더 상한.
# 이 보드들은 캡으로 뽑은 뒤 **파이썬에서 상태·날짜로 섹션을 나눈다**. 캡이 모집단보다
# 작으면 특정 섹션이 통째로 빈다(2026-08-23 도면 작업실 사고와 같은 구조). 운영 실측
# 모집단은 수도권 alert 후보가 최대 949건이라 500 은 이미 부족했다 — 폭주 가드로만
# 남도록 상향하고, 캡 발동은 _fetch_legacy_dashboard_orders 가 로그로 남긴다.
LEGACY_DASHBOARD_ORDER_LIMIT = 2000


def _strip_ilike_pattern(pattern: str) -> str:
    """``%{q}%`` ILIKE 패턴에서 원문 검색어 추출."""
    text = pattern or ""
    if text.startswith("%") and text.endswith("%") and len(text) >= 2:
        return text[1:-1]
    return text


def _phone_search_clause(raw: str, search_term: str) -> Any:
    """
    전화번호 검색 — digit-heavy 입력은 ``erp_phone_digits`` btree 인덱스 사용.

    Args:
        raw: 사용자 원문 검색어.
        search_term: ``%{raw}%`` ILIKE 패턴.

    Returns:
        SQLAlchemy 술어.
    """
    digits = extract_phone_digit_query(raw)
    if digits:
        return or_(
            and_(
                Order.erp_phone_digits.isnot(None),
                Order.erp_phone_digits.contains(digits),  # perf-ok: ix_orders_erp_phone_digits
            ),
            Order.phone.ilike(search_term),  # perf-ok: ix_orders_phone_trgm
        )
    return Order.phone.ilike(search_term)  # perf-ok: ix_orders_phone_trgm


def _order_id_match_clause(raw: str, search_term: str) -> Any:
    """주문 ID 정확 일치 또는 cast id ILIKE."""
    try:
        order_id = int(raw)
        if order_id > 0:
            return Order.id == order_id
    except ValueError:
        pass
    return Order.id.cast(String).ilike(search_term)  # perf-ok: bounded id search admin/cold path


def erp_measurement_main_search_predicate(search_term: str) -> Any:
    """
    Hot path ``/erp/measurement`` — 고객·담당·주소 + SD blob (전화 제외).

    Args:
        search_term: ``%{q}%`` ILIKE 패턴.

    Returns:
        SQLAlchemy ``or_(...)`` 술어.
    """
    return or_(
        Order.customer_name.ilike(search_term),  # perf-ok: ix_orders_customer_name_trgm
        Order.manager_name.ilike(search_term),  # perf-ok: ix_orders_manager_name_trgm
        Order.address.ilike(search_term),  # perf-ok: ix_orders_address_trgm
        and_(
            Order.is_erp_order == True,
            cast(Order.structured_data, String).ilike(search_term),  # perf-ok: ix_orders_structured_data_text_trgm
        ),
    )


def apply_legacy_dashboard_search_filter(
    query: Query,
    raw_q: str,
    *,
    extra_columns: Iterable[Any] = (),
    include_phone: bool = True,
    include_manager: bool = False,
    include_order_id: bool = True,
) -> Query:
    """
    Legacy measurement dashboards (regional/metro/self) 공통 검색 OR 필터.

    Args:
        query: SQLAlchemy query.
        raw_q: 사용자 검색어.
        extra_columns: route별 추가 ILIKE 컬럼 (product, notes, regional_memo 등).
        include_phone: True면 phone digit 인덱스 또는 ilike.
        include_manager: True면 manager_name (trgm).
        include_order_id: True면 id 정확/부분 일치.

    Returns:
        필터 적용된 query.
    """
    raw = (raw_q or "").strip()
    if not raw:
        return query
    search_term = f"%{raw}%"
    clauses: list[Any] = [
        Order.customer_name.ilike(search_term),  # perf-ok: ix_orders_customer_name_trgm
        Order.address.ilike(search_term),  # perf-ok: ix_orders_address_trgm
    ]
    if include_order_id:
        clauses.append(_order_id_match_clause(raw, search_term))
    if include_manager:
        clauses.append(Order.manager_name.ilike(search_term))  # perf-ok: ix_orders_manager_name_trgm
    if include_phone:
        clauses.append(_phone_search_clause(raw, search_term))
    for col in extra_columns:
        clauses.append(col.ilike(search_term))  # perf-ok: ix_orders_product_trgm
    return query.filter(or_(*clauses))


def erp_order_dashboard_search_predicate(
    search_term: str,
    *,
    include_structured_data_blob: bool = False,
    customer_contact_only: bool = False,
    raw_query: str | None = None,
):
    """
    ERP 화면에 노출되는 주요 컬럼 및 structured_data 가시 경로에 대한 ilike OR 조건.

    주문 작업 큐(`/erp/dashboard`)는 ``customer_contact_only=True``로 고객명·전화·주소만
    검색한다(담당자·발주자 이름 혼동 방지). ``include_structured_data_blob=False``로
    항목 메모 등 비노출 JSON 깊은 구간이 검색에 걸리지 않게 한다.

    출고 대시보드는 시공자 등 깊은 필드를 찾기 위해 ``include_structured_data_blob=True``로
    JSON 전체 문자열 ilike를 추가한다.

    Args:
        search_term: ``%{q}%`` 형태 ILIKE 패턴.
        include_structured_data_blob: True이면 ``cast(structured_data, String).ilike`` 추가.
        customer_contact_only: True이면 고객명·전화·주소(컬럼+SD parties.customer·site)만.
        raw_query: phone digit 인덱스 분기용 원문(미지정 시 search_term에서 추출).

    Returns:
        SQLAlchemy ``or_(...)`` 술어.
    """
    raw = (raw_query or _strip_ilike_pattern(search_term)).strip()
    if customer_contact_only:
        structured_visible_fields = [
            Order.structured_data["parties"]["customer"]["name"].as_string(),
            Order.structured_data["parties"]["customer"]["phone"].as_string(),
            Order.structured_data["site"]["address_full"].as_string(),
            Order.structured_data["site"]["address_main"].as_string(),
        ]
        clauses = [
            Order.customer_name.ilike(search_term),  # perf-ok: ix_orders_customer_name_trgm
            _phone_search_clause(raw, search_term),
            Order.address.ilike(search_term),  # perf-ok: ix_orders_address_trgm
            *[
                and_(Order.is_erp_order == True, field.ilike(search_term))  # perf-ok: ix_orders_sd_customer_name_trgm
                for field in structured_visible_fields
            ],
        ]
    else:
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
            Order.id.cast(String).ilike(search_term),  # perf-ok: bounded id search admin/cold path
            Order.customer_name.ilike(search_term),  # perf-ok: ix_orders_customer_name_trgm
            _phone_search_clause(raw, search_term),
            Order.address.ilike(search_term),  # perf-ok: ix_orders_address_trgm
            Order.product.ilike(search_term),  # perf-ok: ix_orders_product_trgm
            Order.manager_name.ilike(search_term),  # perf-ok: ix_orders_manager_name_trgm
            *[
                and_(Order.is_erp_order == True, field.ilike(search_term))  # perf-ok: ix_orders_sd_customer_name_trgm
                for field in structured_visible_fields
            ],
        ]
    if include_structured_data_blob:
        clauses.append(
            and_(
                Order.is_erp_order == True,
                cast(Order.structured_data, String).ilike(search_term),  # perf-ok: ix_orders_structured_data_text_trgm
            )
        )
    return or_(*clauses)


# 출고 검색 포커스 날짜: OrderScheduleDate 후보 범위 (오늘 기준 ±일수)
SHIPMENT_SEARCH_FOCUS_SCHEDULE_HALF_RANGE_DAYS = 730
