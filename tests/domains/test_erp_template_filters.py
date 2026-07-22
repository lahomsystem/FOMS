"""Tests for ERP template filters."""

from flask import Blueprint, Flask

from foms.services.erp_template_filters import (
    coerce_deposit_amount,
    eval_spec_width_mm,
    format_phone_filter,
    item_spec_w300_display,
    item_spec_w300_value,
    lahom_deposit_gold,
    payment_confirmed_bool,
    queue_card_schedule_filter,
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


def test_lahom_deposit_gold_matches_front_standard_amounts() -> None:
    """라홈 + 표준 제외 금액만 황금 힌트. 하우드/0/표준은 False."""
    assert coerce_deposit_amount("150,000원") == 150000
    assert coerce_deposit_amount({"amount": 250000}) == 250000
    assert lahom_deposit_gold("라홈", 150000) is True
    assert lahom_deposit_gold("라홈", 50000) is False
    assert lahom_deposit_gold("라홈", 100000) is False
    assert lahom_deposit_gold("라홈", 200000) is False
    assert lahom_deposit_gold("라홈", 300000) is False
    assert lahom_deposit_gold("라홈", 400000) is False
    assert lahom_deposit_gold("라홈", 0) is False
    assert lahom_deposit_gold("하우드", 150000) is False
    assert lahom_deposit_gold("라홈시스템", 150000) is False


def test_deposit_coin_badge_partial_wires_dashboard_surfaces() -> None:
    """대시보드 동전 표면은 공용 deposit_coin_badge partial을 쓴다."""
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    grid = (root / "templates/orders/partials/dashboard_grid.html").read_text(encoding="utf-8")
    meas = (root / "templates/measurement/partials/dashboard_main.html").read_text(
        encoding="utf-8"
    )
    badge = (root / "templates/orders/partials/deposit_coin_badge.html").read_text(
        encoding="utf-8"
    )
    assert "orders/partials/deposit_coin_badge.html" in grid
    assert "orders/partials/deposit_coin_badge.html" in meas
    assert "lahom_deposit_gold" in badge
    assert "coerce_deposit_amount" in badge
    assert "erp-custom-payment-lahom-hint" in badge
    assert "pay-coin-gray.png" in badge


def test_erp_dashboard_grid_shows_lahom_system_badge_from_factory2() -> None:
    """ERP 주문 그리드 고객 셀은 실측과 동일 flags.factory2 → 라홈시스템 뱃지."""
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    grid = (root / "templates/orders/partials/dashboard_grid.html").read_text(
        encoding="utf-8"
    )
    meas = (root / "templates/measurement/partials/dashboard_main.html").read_text(
        encoding="utf-8"
    )
    assert "flags') or {}).get('factory2')" in meas
    assert "flags') or {}).get('factory2')" in grid
    assert 'fa-industry"></i> 라홈시스템' in meas
    assert 'fa-industry"></i> 라홈시스템' in grid
    customer_cell = grid.index('data-col-key="customer" data-label="고객"')
    factory_idx = grid.index("is_factory2", customer_cell)
    regional_idx = grid.index("o.is_regional", factory_idx)
    assert factory_idx < regional_idx
    assert factory_idx < grid.index("</td>", customer_cell)
    assert 'class="badge bg-success text-white align-self-start mt-1" title="지방주문"' in grid
    assert 'class="badge bg-warning text-dark align-self-start mt-1" title="라홈시스템"' in grid


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
        "coerce_deposit_amount",
        "lahom_deposit_gold",
        "queue_card_schedule",
    ]:
        assert filter_name in app.jinja_env.filters

    assert app.jinja_env.filters["payment_confirmed_bool"]("true") is True
    assert app.jinja_env.filters["lahom_deposit_gold"]("라홈", 150000) is True
    assert app.jinja_env.filters["coerce_deposit_amount"]("150,000원") == 150000
    assert app.jinja_env.filters["spec_w300"]("3600") == 12.0
    assert app.jinja_env.filters["item_spec_w300"]({"spec_width": "900"}) == 3.0
    assert app.jinja_env.filters["queue_card_schedule"](
        {
            "stage": "시공대기",
            "measurement_date": "2026-06-16",
            "construction_date": "2026-06-20",
        }
    ) == {"label": "시공", "value": "2026-06-20"}
