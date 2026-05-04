from foms.services.measurement_manager_colors import (
    DEFAULT_MEASUREMENT_MANAGER_BG_COLOR,
    MEASUREMENT_MANAGER_PALETTE,
    build_measurement_manager_color_map,
    resolve_measurement_manager_color,
)


def _rgb(hex_color: str) -> tuple[int, int, int]:
    return tuple(int(hex_color[index:index + 2], 16) for index in (1, 3, 5))


def _rgb_distance(color_a: str, color_b: str) -> float:
    a = _rgb(color_a)
    b = _rgb(color_b)
    return sum((a[channel] - b[channel]) ** 2 for channel in range(3)) ** 0.5


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


def test_measurement_manager_palette_keeps_pastel_tone_with_distinct_neighbors():
    for color in MEASUREMENT_MANAGER_PALETTE:
        red, green, blue = _rgb(color)
        assert min(red, green, blue) >= 0xB6
        assert max(red, green, blue) <= 0xF7

    for index, color in enumerate(MEASUREMENT_MANAGER_PALETTE):
        next_color = MEASUREMENT_MANAGER_PALETTE[(index + 1) % len(MEASUREMENT_MANAGER_PALETTE)]
        assert _rgb_distance(color, next_color) >= 90


def test_resolve_measurement_manager_color_returns_fallback_for_blank():
    color = resolve_measurement_manager_color('', {})

    assert color['background'] == DEFAULT_MEASUREMENT_MANAGER_BG_COLOR
    assert color['source'] == 'fallback'
