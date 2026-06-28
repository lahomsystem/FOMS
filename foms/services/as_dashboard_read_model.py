"""ERP AS 대시보드 read-model (Batch 5 AS 구조-추출, 동작 보존).

`erp_as_dashboard()`의 탭 카운트/미완료 요약 count context를 분리한다.
목록 query, pagination, row DTO 조립은 라우트에 그대로 둔다(한 슬라이스 한 경계).
flat 모듈(subpackage __init__ 순환 회피).
"""
from __future__ import annotations

from sqlalchemy import and_

from foms.services.as_dashboard_helpers import (
    _count_cases,
    _erp_as_completed_condition,
)


def build_as_tab_count_context(
    filtered_base_query,
    *,
    tab,
    bucket,
    incomplete_non_sales_condition,
    sales_delivery_condition,
    as_pending_true,
    as_visit_date_present,
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
    incomplete_buckets = {
        'visit_confirmed': and_(incomplete_non_sales_condition, ~as_pending_true, as_visit_date_present),
        'pending': and_(incomplete_non_sales_condition, as_pending_true),
        'unassigned': and_(incomplete_non_sales_condition, ~as_pending_true, ~as_visit_date_present),
    }
    as_bucket = (bucket or '').strip()
    if tab != 'incomplete' or as_bucket not in incomplete_buckets:
        as_bucket = ''  # 'total'·빈값·타 탭 → 버킷 필터 없음(전체 미완료)

    as_tab_counts = _count_cases(
        filtered_base_query,
        ('sales_delivery', sales_delivery_condition),
        ('incomplete', incomplete_non_sales_condition),
        ('completed', _erp_as_completed_condition()),
    )
    as_incomplete_summary = _count_cases(
        filtered_base_query,
        ('total', incomplete_non_sales_condition),
        ('visit_confirmed', incomplete_buckets['visit_confirmed']),
        ('pending', incomplete_buckets['pending']),
        ('unassigned', incomplete_buckets['unassigned']),
    )
    return {
        "incomplete_buckets": incomplete_buckets,
        "as_bucket": as_bucket,
        "as_tab_counts": as_tab_counts,
        "as_incomplete_summary": as_incomplete_summary,
    }
