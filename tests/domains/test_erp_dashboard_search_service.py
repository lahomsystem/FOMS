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


def test_erp_order_dashboard_search_predicate_customer_contact_only_omits_manager() -> None:
    full = erp_order_dashboard_search_predicate('%x%')
    narrow = erp_order_dashboard_search_predicate('%x%', customer_contact_only=True)
    assert len(narrow.clauses) < len(full.clauses)
    narrow_sql = str(narrow.compile(compile_kwargs={"literal_binds": True}))
    assert "manager_name" not in narrow_sql
    assert "customer_name" in narrow_sql
