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


def test_measurement_mobile_quick_edit_removed():
    """실측 모바일 카드: 주소/연락처/담당 '빠른 수정' UI는 제거된다.

    데스크톱 인라인 편집(dashboard_main)과 공유 큐카드의 전화/지도 어포던스는 무영향이어야 한다.
    """
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

    # 빠른수정 트리거/시트/보조 스팬/핸들러는 모바일 카드·JS에서 완전히 제거된다.
    assert "data-measurement-mobile-edit-trigger" not in mobile_list
    assert "data-measurement-mobile-edit-trigger" not in mobile_js
    assert "erp-measurement-mobile-edit-sheet" not in mobile_list
    assert "data-measurement-mobile-manager-select-sheet" not in mobile_list
    assert "data-measurement-mobile-manager-status" not in mobile_list
    assert "data-measurement-mobile-field" not in mobile_list
    for field in ('data-field="address"', 'data-field="phone"', 'data-field="manager"'):
        assert field not in mobile_list

    # 공유 큐카드의 전화/지도 어포던스는 빠른수정과 무관 — 그대로 유지.
    assert 'data-queue-card-field="address"' in shared_card
    assert 'data-queue-card-field="phone"' in shared_card
    assert 'data-queue-card-field="manager"' in shared_card
    assert 'has_manager_phone' in shared_card
    assert 'tel:{{ safe_manager_phone }}' in shared_card

    # 데스크톱 인라인 편집은 무영향 — 여전히 3필드 편집 가능.
    for field in ('data-field="address"', 'data-field="phone"', 'data-field="manager"'):
        assert field in pc_dashboard

    # 카드 렌더는 여전히 실측 대시보드 복귀 컨텍스트를 전달한다.
    assert "edit_return_to='erp_measurement_dashboard'" in mobile_list
