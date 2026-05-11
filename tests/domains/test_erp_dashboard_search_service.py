"""스모크: ERP 주문·출고 대시보드 공통 검색 서비스 정책 분리."""

from foms.services.erp_dashboard_search import (
    SHIPMENT_SEARCH_FOCUS_SCHEDULE_HALF_RANGE_DAYS,
    erp_order_dashboard_search_predicate,
)


def test_shipment_search_focus_half_range_is_stable_window() -> None:
    assert SHIPMENT_SEARCH_FOCUS_SCHEDULE_HALF_RANGE_DAYS == 730


def test_erp_order_dashboard_search_predicate_appends_blob_clause_when_enabled() -> None:
    narrow = erp_order_dashboard_search_predicate('%x%', include_structured_data_blob=False)
    wide = erp_order_dashboard_search_predicate('%x%', include_structured_data_blob=True)
    assert len(wide.clauses) == len(narrow.clauses) + 1
