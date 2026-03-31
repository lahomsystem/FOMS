from pathlib import Path


def test_manager_sort_order_state_is_declared_before_initial_apply():
    content = Path("static/js/erp/measurement.js").read_text(encoding="utf-8")

    declaration_index = content.index("let _managerSortOrderMap = {};")
    initial_apply_index = content.index("applyMeasurementManagerSortAndColors();")

    assert declaration_index < initial_apply_index


def test_manager_sort_order_state_is_declared_only_once():
    content = Path("static/js/erp/measurement.js").read_text(encoding="utf-8")

    assert content.count("let _managerSortOrderMap = {};") == 1
