"""스모크: ERP 주문·출고 대시보드 공통 검색 서비스 정책 분리."""

from foms.services.erp_dashboard_search import (
    SHIPMENT_SEARCH_FOCUS_SCHEDULE_HALF_RANGE_DAYS,
    apply_legacy_dashboard_search_filter,
    erp_measurement_main_search_predicate,
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


def test_erp_order_dashboard_search_predicate_uses_phone_digits_index_for_digit_query() -> None:
    pred = erp_order_dashboard_search_predicate(
        '%0101234%',
        customer_contact_only=True,
        raw_query='0101234',
    )
    sql = str(pred.compile(compile_kwargs={"literal_binds": True}))
    assert "erp_phone_digits" in sql


def test_erp_measurement_main_search_predicate_includes_manager_not_phone() -> None:
    pred = erp_measurement_main_search_predicate('%test%')
    sql = str(pred.compile(compile_kwargs={"literal_binds": True}))
    assert "manager_name" in sql
    assert "erp_phone_digits" not in sql
    assert "phone" not in sql.replace("manager_name", "")


def test_apply_legacy_dashboard_search_filter_adds_extra_columns() -> None:
    from models import Order

    class _Q:
        def __init__(self):
            self.filters = []

        def filter(self, *args):
            self.filters.append(args)
            return self

    q = _Q()
    apply_legacy_dashboard_search_filter(
        q,
        'abc',
        extra_columns=(Order.product,),
        include_phone=False,
        include_manager=True,
    )
    assert q.filters
    sql = str(q.filters[0][0].compile(compile_kwargs={"literal_binds": True}))
    assert "product" in sql
    assert "manager_name" in sql


def test_erp_order_dashboard_search_predicate_covers_buyer_axis() -> None:
    """ORDERER-AXIS-01: 주문한 사람(parties.buyer)도 검색 후보다.

    발주사 자리에서 갈라져 나온 값이라 여기 없으면 수집 주문을 주문자 이름·번호로 찾던
    동작이 조용히 사라진다.
    """
    sql = str(erp_order_dashboard_search_predicate('%x%').compile(
        compile_kwargs={"literal_binds": True}))
    assert "'buyer'" in sql and "'name'" in sql
    assert sql.count("'buyer'") >= 2  # name · phone
