from pathlib import Path


def test_manager_sort_order_state_is_declared_before_initial_apply():
    content = Path("static/js/erp/measurement.js").read_text(encoding="utf-8")

    declaration_index = content.index("let _managerSortOrderMap = {};")
    initial_apply_index = content.index("applyMeasurementManagerSortAndColors();")

    assert declaration_index < initial_apply_index


def test_manager_sort_order_state_is_declared_only_once():
    content = Path("static/js/erp/measurement.js").read_text(encoding="utf-8")

    assert content.count("let _managerSortOrderMap = {};") == 1


def test_manager_editor_has_explicit_clear_action():
    content = Path("static/js/erp/measurement.js").read_text(encoding="utf-8")

    assert "data-manager-action', 'clear'" in content
    assert "commitExplicitValue('')" in content
    assert "function bindEditorActionButton(button, handler)" in content
    assert "button.addEventListener('click'" in content


def test_manager_editor_supports_keyboard_commit_and_cancel():
    content = Path("static/js/erp/measurement.js").read_text(encoding="utf-8")

    assert "input.addEventListener('keydown'" in content
    assert "evt.key === 'Enter'" in content
    assert "evt.key === 'Escape'" in content


def test_manager_dropdown_cleanup_is_centralized():
    content = Path("static/js/erp/measurement.js").read_text(encoding="utf-8")

    assert "function closeManagerDropdown(options)" in content
    assert "let _activeManagerDropdown = null;" in content
    assert "closeManagerDropdown();" in content
