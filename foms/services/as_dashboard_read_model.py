"""ERP AS 대시보드 read-model (Batch 5 AS 구조-추출, 동작 보존).

`erp_as_dashboard()`의 탭 카운트/미완료 요약 count context를 분리한다.
목록 query, pagination, row DTO 조립은 라우트에 그대로 둔다(한 슬라이스 한 경계).
flat 모듈(subpackage __init__ 순환 회피).
"""
from __future__ import annotations

from sqlalchemy import and_

from foms.services.as_dashboard_helpers import (
    _as_billing_confirmed_expr,
    _as_billing_type_expr,
    _as_pending_expr,
    _as_visit_date_expr,
    _count_cases,
    _erp_as_completed_condition,
    _erp_as_incomplete_condition,
    _has_text_value,
    _sales_delivery_expr,
    _sales_delivery_true_filter,
)


AS_INCOMPLETE_BUCKET_KEYS = ('visit_confirmed', 'pending', 'unassigned', 'paid_unconfirmed')


def build_as_incomplete_bucket_conditions(
    *,
    incomplete_non_sales_condition,
    as_pending_true,
    as_visit_date_present,
    paid_unconfirmed_condition,
):
    """미완료 하위 버킷 조건(SSOT) — 탭 카운트·목록 필터·지도 쿼리가 공유한다.

    Args:
        incomplete_non_sales_condition: 미완료(영업/택배 제외) 조건.
        as_pending_true: `shipment.as_pending` true 조건.
        as_visit_date_present: `schedule.as_visit.date` 존재 조건.
        paid_unconfirmed_condition: 유상 미확정 조건.

    Returns:
        {bucket_key: SQLAlchemy 조건} — 키는 ``AS_INCOMPLETE_BUCKET_KEYS``.
    """
    return {
        'visit_confirmed': and_(incomplete_non_sales_condition, ~as_pending_true, as_visit_date_present),
        'pending': and_(incomplete_non_sales_condition, as_pending_true),
        'unassigned': and_(incomplete_non_sales_condition, ~as_pending_true, ~as_visit_date_present),
        'paid_unconfirmed': and_(incomplete_non_sales_condition, paid_unconfirmed_condition),
    }


def build_as_tab_query_conditions(*, dialect_name=''):
    """AS 탭 필터와 카운트가 공유하는 SQL 조건 context를 만든다."""
    sales_delivery = _sales_delivery_expr(dialect_name=dialect_name)
    sales_delivery_true = _sales_delivery_true_filter(sales_delivery)
    as_pending_true = _sales_delivery_true_filter(_as_pending_expr(dialect_name=dialect_name))
    as_visit_date_present = _has_text_value(_as_visit_date_expr(dialect_name=dialect_name))
    incomplete_non_sales_condition = and_(
        _erp_as_incomplete_condition(),
        ~sales_delivery_true,
    )
    sales_delivery_condition = and_(
        _erp_as_incomplete_condition(),
        sales_delivery_true,
    )
    # 비용(무상/유상/미정) 판정: JSONB ->> 등호 비교(ILIKE 금지). confirmed는 dialect별
    # boolean 표현 차이(postgres 'true' / sqlite 1) 때문에 true 집합 필터로 판정한다.
    billing_type = _as_billing_type_expr(dialect_name=dialect_name)
    billing_confirmed_true = _sales_delivery_true_filter(
        _as_billing_confirmed_expr(dialect_name=dialect_name)
    )
    paid_unconfirmed_condition = and_(billing_type == 'paid', ~billing_confirmed_true)
    billing_filters = {
        'free': billing_type == 'free',
        'paid': billing_type == 'paid',
        'undecided': billing_type == 'undecided',
    }
    return {
        "as_pending_true": as_pending_true,
        "as_visit_date_present": as_visit_date_present,
        "incomplete_non_sales_condition": incomplete_non_sales_condition,
        "sales_delivery_condition": sales_delivery_condition,
        "paid_unconfirmed_condition": paid_unconfirmed_condition,
        "billing_filters": billing_filters,
    }


def build_as_tab_count_context(
    filtered_base_query,
    *,
    tab,
    bucket,
    incomplete_non_sales_condition,
    sales_delivery_condition,
    as_pending_true,
    as_visit_date_present,
    paid_unconfirmed_condition,
):
    """AS 탭 카운트와 미완료 summary count context를 계산한다.

    Returns:
        {
            "incomplete_buckets": {...},
            "as_bucket": str,
            "as_tab_counts": {...},
            "as_incomplete_summary": {...},
        }
    """
    # 미완료 stats 칩 → 버킷 필터(방문확정/미결/미정). 요약 집계와 필터가 같은 조건을
    # 단일 출처(SSOT)로 공유해 칩 카운트와 실제 목록 결과가 항상 일치하게 한다.
    incomplete_buckets = build_as_incomplete_bucket_conditions(
        incomplete_non_sales_condition=incomplete_non_sales_condition,
        as_pending_true=as_pending_true,
        as_visit_date_present=as_visit_date_present,
        paid_unconfirmed_condition=paid_unconfirmed_condition,
    )
    as_bucket = (bucket or '').strip()
    if tab != 'incomplete' or as_bucket not in incomplete_buckets:
        as_bucket = ''  # 'total'·빈값·타 탭 → 버킷 필터 없음(전체 미완료)

    # 탭 카운트와 미완료 summary 는 **같은 모집단(filtered_base_query)** 을 센다. 예전엔
    # _count_cases 를 두 번 불러 같은 스캔을 2회 반복했다(스테이징 실측 tab_counts 27ms).
    # SUM(CASE) 컬럼을 한 쿼리로 합치면 스캔 1회로 같은 값이 나온다. 'total' 은
    # 'incomplete' 과 조건이 동일하므로 컬럼을 늘리지 않고 결과에서 이어 붙인다.
    counts = _count_cases(
        filtered_base_query,
        ('sales_delivery', sales_delivery_condition),
        ('incomplete', incomplete_non_sales_condition),
        ('completed', _erp_as_completed_condition()),
        ('visit_confirmed', incomplete_buckets['visit_confirmed']),
        ('pending', incomplete_buckets['pending']),
        ('unassigned', incomplete_buckets['unassigned']),
        ('paid_unconfirmed', incomplete_buckets['paid_unconfirmed']),
    )
    as_tab_counts = {
        'sales_delivery': counts['sales_delivery'],
        'incomplete': counts['incomplete'],
        'completed': counts['completed'],
    }
    as_incomplete_summary = {
        'total': counts['incomplete'],
        'visit_confirmed': counts['visit_confirmed'],
        'pending': counts['pending'],
        'unassigned': counts['unassigned'],
        'paid_unconfirmed': counts['paid_unconfirmed'],
    }
    return {
        "incomplete_buckets": incomplete_buckets,
        "as_bucket": as_bucket,
        "as_tab_counts": as_tab_counts,
        "as_incomplete_summary": as_incomplete_summary,
    }
