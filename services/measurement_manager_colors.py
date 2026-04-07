"""
실측 담당자 색상 계산 공통 헬퍼.

실측 대시보드와 실측 지도에서 동일한 담당자 팔레트 규칙을 재사용한다.
"""
from typing import Any, Iterable, Mapping

MEASUREMENT_MANAGER_PALETTE = (
    '#FADADD',
    '#DCEBFF',
    '#FFF1BF',
    '#DDF4E4',
    '#E8DDF8',
    '#D9F3F0',
    '#FFE6CC',
    '#F9D9EC',
    '#E5F5D2',
    '#FDE2E4',
)

DEFAULT_MEASUREMENT_MANAGER_BG_COLOR = '#CCCCCC'
DEFAULT_MEASUREMENT_MANAGER_TEXT_COLOR = '#000000'


def normalize_measurement_manager_key(name: Any) -> str:
    """담당자 색상 매핑용 정규화 키를 반환한다."""
    cleaned = str(name or '').strip()
    if not cleaned or cleaned == '-':
        return ''
    return cleaned.lower()


def build_measurement_manager_sort_order_map(
    measurement_manager_options: Iterable[Any],
) -> dict[str, int]:
    """설정의 실측 담당자 정렬 순서를 조회용 dict로 변환한다."""
    sort_map: dict[str, int] = {}
    for item in measurement_manager_options or []:
        if isinstance(item, Mapping):
            name = str(item.get('name') or '').strip()
            sort_order_raw = item.get('sort_order', 999)
        else:
            name = str(item or '').strip()
            sort_order_raw = 999

        key = normalize_measurement_manager_key(name)
        if not key or key in sort_map:
            continue

        try:
            sort_map[key] = int(sort_order_raw)
        except (TypeError, ValueError):
            sort_map[key] = 999
    return sort_map


def _coerce_manager_entry(entry: Any, fallback_order_id: int) -> tuple[str, int]:
    """manager color map 계산용 입력을 표준화한다."""
    if isinstance(entry, Mapping):
        manager_name = str(
            entry.get('manager_name') or entry.get('name') or ''
        ).strip()
        order_id_raw = entry.get('order_id', fallback_order_id)
    else:
        manager_name = str(entry or '').strip()
        order_id_raw = fallback_order_id

    try:
        order_id = int(order_id_raw)
    except (TypeError, ValueError):
        order_id = fallback_order_id

    return manager_name, order_id


def build_measurement_manager_color_map(
    manager_entries: Iterable[Any],
    measurement_manager_options: Iterable[Any],
) -> dict[str, dict[str, str]]:
    """실측 대시보드 규칙과 동일한 담당자 색상 맵을 만든다."""
    sort_map = build_measurement_manager_sort_order_map(measurement_manager_options)
    sortable_entries: list[tuple[int, str, int, str]] = []

    for index, entry in enumerate(manager_entries or []):
        manager_name, order_id = _coerce_manager_entry(entry, index)
        key = normalize_measurement_manager_key(manager_name)
        if not key:
            continue
        sortable_entries.append(
            (
                sort_map.get(key, 999),
                manager_name,
                order_id,
                key,
            )
        )

    sortable_entries.sort(
        key=lambda item: (
            item[0],
            item[1] or 'ZZZ',
            item[2],
        )
    )

    color_map: dict[str, dict[str, str]] = {}
    next_palette_index = 0
    for _, _, _, key in sortable_entries:
        if key in color_map:
            continue
        color_map[key] = {
            'background': MEASUREMENT_MANAGER_PALETTE[
                next_palette_index % len(MEASUREMENT_MANAGER_PALETTE)
            ],
            'text': DEFAULT_MEASUREMENT_MANAGER_TEXT_COLOR,
        }
        next_palette_index += 1

    return color_map


def resolve_measurement_manager_color(
    manager_name: Any,
    manager_color_map: Mapping[str, Mapping[str, str]] | None,
) -> dict[str, str]:
    """담당자 이름에 대응하는 실측 색상 테마를 반환한다."""
    key = normalize_measurement_manager_key(manager_name)
    if key and manager_color_map and key in manager_color_map:
        color_set = manager_color_map[key]
        return {
            'background': str(
                color_set.get('background') or DEFAULT_MEASUREMENT_MANAGER_BG_COLOR
            ),
            'text': str(
                color_set.get('text') or DEFAULT_MEASUREMENT_MANAGER_TEXT_COLOR
            ),
            'source': 'palette',
        }

    return {
        'background': DEFAULT_MEASUREMENT_MANAGER_BG_COLOR,
        'text': DEFAULT_MEASUREMENT_MANAGER_TEXT_COLOR,
        'source': 'fallback',
    }
