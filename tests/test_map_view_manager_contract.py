import re
from pathlib import Path


def test_map_manager_edit_allows_blank_save():
    content = Path("templates/map_view.html").read_text(encoding="utf-8")

    assert "saveMapManager(orderId, nextValue);" in content
    assert "if (val) saveMapManager(orderId, val);" not in content


def test_map_manager_edit_has_compact_action_buttons():
    content = Path("templates/map_view.html").read_text(encoding="utf-8")

    assert ".map-manager-edit__button" in content
    assert ".map-manager-edit__input" in content
    assert "data-map-manager-action', 'clear'" in content
    assert "data-map-manager-action', 'list'" in content
    assert "data-map-manager-action', 'save'" in content


def test_map_manager_save_renders_dash_for_blank_value():
    content = Path("templates/map_view.html").read_text(encoding="utf-8")

    assert "function applyMapManagerValue(orderId, managerName)" in content
    assert "const displayValue = normalized || '-';" in content


def test_map_manager_dropdown_cleanup_is_centralized():
    content = Path("templates/map_view.html").read_text(encoding="utf-8")

    assert "function closeMapManagerDropdown()" in content
    assert "closeMapManagerDropdown();" in content


def test_map_manager_save_reloads_map_for_marker_color_sync():
    content = Path("templates/map_view.html").read_text(encoding="utf-8")

    assert re.search(
        r"if \(data\.success\) \{\s*applyMapManagerValue\(orderId, cleanName\);\s*loadMap\(\);",
        content,
    )
