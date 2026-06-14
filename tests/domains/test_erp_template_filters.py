"""Tests for ERP template filters."""

from flask import Blueprint, Flask

from foms.services.erp_template_filters import (
    eval_spec_width_mm,
    format_phone_filter,
    item_spec_w300_display,
    item_spec_w300_value,
    payment_confirmed_bool,
    register_erp_template_filters,
    schedule_datetime_display,
    spec_w300_filter,
    spec_w300_value,
    split_count_filter,
    split_list_filter,
    strip_product_w_filter,
)


def test_string_filters_cover_common_dashboard_cases() -> None:
    assert split_count_filter("A, ,B") == 2
    assert split_list_filter("A, ,B") == ["A", "B"]
    assert strip_product_w_filter("제품명 120W, 몰딩여닫이 3600 3600") == "제품명, 몰딩여닫이 3600"


def test_spec_and_schedule_filters_render_expected_values() -> None:
    assert spec_w300_filter("3600x600") == 12.0
    assert schedule_datetime_display("2026-04-09", "09:30") == "2026-04-09 09:30"
    assert schedule_datetime_display("", "09:30") == "-"


def test_phone_and_payment_filters_normalize_values() -> None:
    assert format_phone_filter("01012345678") == "010-1234-5678"
    assert payment_confirmed_bool("true") is True
    assert payment_confirmed_bool("false") is False
    assert payment_confirmed_bool(1) is True
    assert payment_confirmed_bool(2) is False


def test_item_spec_w300_value_sums_spec_rows() -> None:
    item = {
        "spec_rows": [
            {"spec_width": "600"},
            {"w": "300"},
        ]
    }

    assert item_spec_w300_display(item) == 3.0
    assert item_spec_w300_value(item) == 3.0


def test_eval_spec_width_mm_handles_composite_specs() -> None:
    """복합 규격 W를 출고/시공비 기준 총 폭(mm)으로 정확히 평가한다."""
    # 명시 총합(괄호 앞) 우선, 괄호 안 세부치수 무시
    assert eval_spec_width_mm("5700(2402+1864+1638)") == 5700.0
    # 명시 총합이 없으면 최상위 가산항 합산('+' 및 ',' 모두 인식)
    assert eval_spec_width_mm("2352+2100+2860") == 7312.0
    assert eval_spec_width_mm("5700,4512,2300") == 12512.0
    assert eval_spec_width_mm("2352+2100,2860") == 7312.0
    # 단일 값
    assert eval_spec_width_mm("9000") == 9000.0
    # 깊이류 괄호 무시 + 차원 표기 흡수
    assert eval_spec_width_mm("1000(700,750)") == 1000.0
    assert eval_spec_width_mm("3600x600") == 3600.0
    # 빈 값/상담 텍스트
    assert eval_spec_width_mm("") == 0.0
    assert eval_spec_width_mm("상담") == 0.0
    assert eval_spec_width_mm(None) == 0.0


def test_spec_w300_uses_composite_total_for_shipment_units() -> None:
    """출고 단위(W/300)가 복합 규격의 총 폭을 반영한다(첫 숫자만이 아니라)."""
    # 명시 총합: 5700/300
    assert spec_w300_value("5700(2402+1864+1638)") == 19.0
    # 합산: (2352+2100+2860)/300 = 7312/300
    assert spec_w300_value("2352+2100+2860") == round(7312 / 300, 1)
    assert spec_w300_filter("2352+2100+2860") == round(7312 / 300, 1)
    # 다중 행: 각 행 총 폭 합산 후 /300
    item = {
        "spec_rows": [
            {"spec_width": "5700(2402+1864+1638)"},
            {"spec_width": "2352+2100+2860"},
        ]
    }
    assert item_spec_w300_value(item) == round((5700 + 7312) / 300, 1)


def test_register_erp_template_filters_registers_expected_jinja_filters() -> None:
    app = Flask(__name__)
    blueprint = Blueprint("erp_template_filters_test", __name__)

    register_erp_template_filters(blueprint)
    app.register_blueprint(blueprint)

    for filter_name in [
        "split_count",
        "split_list",
        "strip_product_w",
        "spec_w300",
        "format_phone",
        "item_spec_w300",
        "schedule_datetime_display",
        "payment_confirmed_bool",
    ]:
        assert filter_name in app.jinja_env.filters

    assert app.jinja_env.filters["payment_confirmed_bool"]("true") is True
    assert app.jinja_env.filters["spec_w300"]("3600") == 12.0
    assert app.jinja_env.filters["item_spec_w300"]({"spec_width": "900"}) == 3.0
