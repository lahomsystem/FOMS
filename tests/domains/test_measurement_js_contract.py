from pathlib import Path


def test_manager_sort_order_state_is_declared_before_initial_apply():
    content = Path("static/js/measurement/dashboard.js").read_text(encoding="utf-8")

    declaration_index = content.index("let _managerSortOrderMap = {};")
    initial_apply_index = content.index("applyMeasurementManagerSortAndColors();")

    assert declaration_index < initial_apply_index


def test_manager_sort_order_state_is_declared_only_once():
    content = Path("static/js/measurement/dashboard.js").read_text(encoding="utf-8")

    assert content.count("let _managerSortOrderMap = {};") == 1


def test_manager_editor_has_explicit_clear_action():
    content = Path("static/js/measurement/dashboard.js").read_text(encoding="utf-8")

    assert "data-manager-action', 'clear'" in content
    assert "commitExplicitValue('')" in content
    assert "function bindEditorActionButton(button, handler)" in content
    assert "button.addEventListener('click'" in content


def test_manager_editor_supports_keyboard_commit_and_cancel():
    content = Path("static/js/measurement/dashboard.js").read_text(encoding="utf-8")

    assert "input.addEventListener('keydown'" in content
    assert "evt.key === 'Enter'" in content
    assert "evt.key === 'Escape'" in content


def test_manager_dropdown_cleanup_is_centralized():
    content = Path("static/js/measurement/dashboard.js").read_text(encoding="utf-8")

    assert "function closeManagerDropdown(options)" in content
    assert "let _activeManagerDropdown = null;" in content
    assert "closeManagerDropdown();" in content


def test_measurement_mobile_edit_contract_is_wired_to_v2_cards():
    mobile_js = Path("static/js/measurement/mobile.js").read_text(encoding="utf-8")
    mobile_list = Path("templates/measurement/partials/mobile_list.html").read_text(
        encoding="utf-8"
    )
    shared_card = Path("templates/partials/shared/erp_mobile_queue_card_v2.html").read_text(
        encoding="utf-8"
    )
    pc_dashboard = Path("templates/measurement/partials/dashboard_main.html").read_text(
        encoding="utf-8"
    )

    assert "data-measurement-mobile-edit-trigger" in mobile_js
    assert "erp-measurement-mobile-edit-sheet" in mobile_list
    assert "data-measurement-mobile-edit-trigger" in mobile_list
    assert "data-measurement-mobile-manager-select-sheet" in mobile_list
    assert 'data-queue-card-field="address"' in shared_card
    assert 'data-queue-card-field="phone"' in shared_card
    assert 'data-queue-card-field="manager"' in shared_card
    assert 'has_manager_phone' in shared_card
    assert 'tel:{{ safe_manager_phone }}' in shared_card
    assert "data-queue-card-call-link" in mobile_js
    assert "data-queue-card-map-link" in mobile_js
    for field in ('data-field="address"', 'data-field="phone"', 'data-field="manager"'):
        assert field in pc_dashboard
    for field in ('data-field="address"', 'data-field="phone"', 'data-field="manager"'):
        assert field in mobile_list
    assert "edit_return_to='erp_measurement_dashboard'" in mobile_list
