import re
from pathlib import Path


def test_map_manager_edit_allows_blank_save():
    content = Path("templates/measurement/map_view.html").read_text(encoding="utf-8")

    assert "saveMapManager(orderId, nextValue);" in content
    assert "if (val) saveMapManager(orderId, val);" not in content


def test_map_manager_edit_has_compact_action_buttons():
    content = Path("templates/measurement/map_view.html").read_text(encoding="utf-8")

    assert ".map-manager-edit__button" in content
    assert ".map-manager-edit__input" in content
    assert "data-map-manager-action', 'clear'" in content
    assert "data-map-manager-action', 'list'" in content
    assert "data-map-manager-action', 'save'" in content


def test_map_manager_save_renders_dash_for_blank_value():
    content = Path("templates/measurement/map_view.html").read_text(encoding="utf-8")

    assert "function applyMapManagerValue(orderId, managerName)" in content
    assert "const displayValue = normalized || '-';" in content


def test_map_manager_dropdown_cleanup_is_centralized():
    content = Path("templates/measurement/map_view.html").read_text(encoding="utf-8")

    assert "function closeMapManagerDropdown()" in content
    assert "closeMapManagerDropdown();" in content


def test_map_manager_save_reloads_map_for_marker_color_sync():
    content = Path("templates/measurement/map_view.html").read_text(encoding="utf-8")

    # res.ok 동반 검사는 2026-08-31 CSRF 403 대응으로 추가됨(실패 사유 표시). 성공 분기의
    # 계약(applyMapManagerValue → loadMap)만 고정하고 조건식 형태는 느슨하게 둔다.
    assert re.search(
        r"if \([^)]*data\.success\) \{\s*applyMapManagerValue\(orderId, cleanName\);\s*loadMap\(\);",
        content,
    )
