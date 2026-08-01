"""품목별 시공일 필터 단위 테스트 (DB 불필요).

행(주문)은 order-level + item-level 시공일 합집합으로 뜨지만, 제품/규격 셀과 자수는
선택 날짜에 실제 출고되는 품목만 반영해야 한다(visible_items_for_dates SSOT).
"""

from types import SimpleNamespace

from foms.services.shipment_dashboard_helpers import (
    order_spec_units,
    visible_items_for_dates,
    visible_spec_units,
)


def _order(items, order_date="2026-07-30"):
    """구조화 items를 가진 ERP 주문 스텁."""
    return SimpleNamespace(
        id=4318,
        is_erp_order=True,
        scheduled_date=None,
        structured_data={
            "schedule": {"construction": {"date": order_date}},
            "items": items,
        },
    )


def _item(name, construction_date="", width=""):
    return {"product_name": name, "construction_date": construction_date, "spec_width": width}


def test_item_without_own_date_inherits_order_date():
    """항목 시공일이 없으면 주문 대표 시공일을 상속한다."""
    order = _order([_item("붙박이장")], order_date="2026-07-30")

    assert visible_items_for_dates(order, target_date="2026-07-30") == order.structured_data["items"]
    # 07-31에는 미표시 → 0건이므로 폴백(전 품목)이 아니라, 다른 품목이 있을 때만 걸러진다.
    other = _order([_item("붙박이장"), _item("슬라이딩", "2026-07-31")], order_date="2026-07-30")
    names = [it["product_name"] for it in visible_items_for_dates(other, target_date="2026-07-31")]
    assert names == ["슬라이딩"]


def test_item_level_date_splits_order_across_two_days():
    """사용자 재현 시나리오: 8품목 중 1개만 07-31 → 07-30은 7개, 07-31은 1개."""
    items = [_item(f"제품{i}") for i in range(7)] + [_item("슬라이딩", "2026-07-31")]
    order = _order(items, order_date="2026-07-30")

    day30 = visible_items_for_dates(order, target_date="2026-07-30")
    day31 = visible_items_for_dates(order, target_date="2026-07-31")

    assert len(day30) == 7
    assert "슬라이딩" not in [it["product_name"] for it in day30]
    assert [it["product_name"] for it in day31] == ["슬라이딩"]


def test_comma_multi_date_item_shows_on_both_days():
    """콤마 다중 날짜 품목은 양쪽 날짜 모두에 표시된다."""
    order = _order(
        [_item("양일제품", "2026-07-30,2026-07-31"), _item("단일제품", "2026-07-30")],
        order_date="2026-07-30",
    )

    assert len(visible_items_for_dates(order, target_date="2026-07-30")) == 2
    assert [it["product_name"] for it in visible_items_for_dates(order, target_date="2026-07-31")] == [
        "양일제품"
    ]


def test_range_mode_includes_items_within_window():
    """범위 모드는 품목 날짜 중 하나라도 창 안이면 표시한다."""
    order = _order([_item("A", "2026-07-29"), _item("B", "2026-07-31")], order_date="2026-07-30")

    both = visible_items_for_dates(order, date_from="2026-07-29", date_to="2026-07-31")
    narrow = visible_items_for_dates(order, date_from="2026-07-31", date_to="2026-07-31")

    assert [it["product_name"] for it in both] == ["A", "B"]
    assert [it["product_name"] for it in narrow] == ["B"]


def test_zero_match_falls_back_to_all_items():
    """전 품목이 07-31인데 07-30 조회 → 빈 셀 대신 전 품목을 반환한다."""
    order = _order([_item("A", "2026-07-31"), _item("B", "2026-07-31")], order_date="2026-07-31")

    assert len(visible_items_for_dates(order, target_date="2026-07-30")) == 2


def test_order_spec_units_differs_per_date():
    """자수 합도 날짜별 가시 품목만 반영한다(전체 합 = 날짜 미지정)."""
    order = _order(
        [_item("A", "", "300"), _item("B", "2026-07-31", "600")],
        order_date="2026-07-30",
    )

    assert order_spec_units(order) == 3.0
    assert order_spec_units(order, target_date="2026-07-30") == 1.0
    assert order_spec_units(order, target_date="2026-07-31") == 2.0


def test_visible_spec_units_uses_attached_items():
    """KPI/팀 합계는 라우트가 부착한 가시 품목을 그대로 합산한다."""
    order = _order([_item("A", "", "300"), _item("B", "2026-07-31", "600")])

    assert visible_spec_units(order) == 3.0  # 미부착 → 전 품목
    order.shipment_visible_items = visible_items_for_dates(order, target_date="2026-07-30")
    assert visible_spec_units(order) == 1.0
