from services.measurement_manager_colors import (
    DEFAULT_MEASUREMENT_MANAGER_BG_COLOR,
    MEASUREMENT_MANAGER_PALETTE,
    build_measurement_manager_color_map,
    resolve_measurement_manager_color,
)


def test_build_measurement_manager_color_map_respects_sort_order():
    color_map = build_measurement_manager_color_map(
        [
            {'manager_name': '세번째', 'order_id': 30},
            {'manager_name': '첫번째', 'order_id': 10},
            {'manager_name': '두번째', 'order_id': 20},
        ],
        [
            {'name': '첫번째', 'sort_order': 1},
            {'name': '두번째', 'sort_order': 2},
            {'name': '세번째', 'sort_order': 3},
        ],
    )

    assert color_map['첫번째'.lower()]['background'] == MEASUREMENT_MANAGER_PALETTE[0]
    assert color_map['두번째'.lower()]['background'] == MEASUREMENT_MANAGER_PALETTE[1]
    assert color_map['세번째'.lower()]['background'] == MEASUREMENT_MANAGER_PALETTE[2]


def test_resolve_measurement_manager_color_returns_fallback_for_blank():
    color = resolve_measurement_manager_color('', {})

    assert color['background'] == DEFAULT_MEASUREMENT_MANAGER_BG_COLOR
    assert color['source'] == 'fallback'
