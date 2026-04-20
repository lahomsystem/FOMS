import datetime
from types import SimpleNamespace

from foms.services.erp_display import (
    _ensure_dict,
    _normalize_date_to_yyyymmdd,
    clean_dict_like_name,
    normalize_manager_name,
    self_measurement_four_checks_done,
)


def test_normalize_manager_name_keeps_plain_text_names() -> None:
    assert normalize_manager_name("  홍길동  ") == "홍길동"
    assert clean_dict_like_name("{'name': '김영희'}") == "김영희"


def test_ensure_dict_and_normalize_date_helpers_handle_common_inputs() -> None:
    assert _ensure_dict({"name": "라홈"}) == {"name": "라홈"}
    assert _ensure_dict('{"name": "라홈"}') == {"name": "라홈"}
    assert _ensure_dict("not-json") == {}

    assert _normalize_date_to_yyyymmdd(datetime.date(2026, 4, 7)) == "2026-04-07"
    assert _normalize_date_to_yyyymmdd({"year": 2026, "month": 4, "day": 7}) == "2026-04-07"


def test_self_measurement_four_checks_done_requires_all_flags() -> None:
    complete = SimpleNamespace(
        is_self_measurement=True,
        measurement_completed=True,
        regional_sales_order_upload=True,
        regional_blueprint_sent=True,
        regional_order_upload=True,
    )
    incomplete = SimpleNamespace(
        is_self_measurement=True,
        measurement_completed=True,
        regional_sales_order_upload=False,
        regional_blueprint_sent=True,
        regional_order_upload=True,
    )

    assert self_measurement_four_checks_done(complete) is True
    assert self_measurement_four_checks_done(incomplete) is False
