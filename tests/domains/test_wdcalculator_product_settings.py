"""Regression tests for WDCalculator product settings persistence."""
import json
import re

import pytest

from db import db_session
from models import Order
from wdcalculator_db import wd_calculator_session
from wdcalculator_models import (
    Estimate,
    EstimateHistory,
    EstimateOrderMatch,
    WDCalculatorProductSettings,
)


def _write_json(path, payload):
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def _create_order(**overrides) -> Order:
    """Create a minimal FOMS order row for WDCalculator search/match contracts."""
    payload = {
        "received_date": "2026-04-12",
        "customer_name": "WD Order Contract",
        "phone": "010-2222-3333",
        "address": "Seoul",
        "product": "Wardrobe",
        "status": "RECEIVED",
        "structured_data": {},
    }
    payload.update(overrides)
    order = Order(**payload)
    db_session.add(order)
    db_session.commit()
    return order


def test_wdcalculator_page_renders_inline_config_contract(wdcalculator_settings_env, login):
    """`/wdcalculator` must keep the inline config and shared.js load-order contract."""
    client = login

    response = client.get("/wdcalculator")

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    categories_idx = body.index("var wdCalculatorCategories =")
    notes_idx = body.index("var wdNotesCategories =")
    shared_idx = body.index("js/wdcalculator/shared.js")
    unsaved_exit_guard_idx = body.index("js/wdcalculator/unsaved-exit-guard.js")
    layout_sync_wiring_idx = body.index("js/wdcalculator/layout-sync-wiring.js")
    composition_idx = body.index("js/wdcalculator/composition.js")
    estimate_lifecycle_idx = body.index("js/wdcalculator/estimate-lifecycle.js")
    primary_form_idx = body.index("js/wdcalculator/primary-form.js")
    pricing_core_idx = body.index("js/wdcalculator/pricing-core.js")
    dom_ready_idx = body.index("document.addEventListener('DOMContentLoaded'")
    categories_match = re.search(
        r"var wdCalculatorCategories = (.+?) \|\| \[\];",
        body,
        re.S,
    )
    notes_match = re.search(
        r"var wdNotesCategories = (.+?) \|\| \[\];",
        body,
        re.S,
    )

    assert (
        categories_idx
        < shared_idx
        < unsaved_exit_guard_idx
        < layout_sync_wiring_idx
        < composition_idx
        < estimate_lifecycle_idx
        < primary_form_idx
        < pricing_core_idx
        < dom_ready_idx
    )
    for retired_src in (
        "js/wdcalculator/sidebar-estimates.js",
        "js/wdcalculator/search-results-load.js",
        "js/wdcalculator/render-estimates-list.js",
        "js/wdcalculator/reset-input-form-keep-customer.js",
        "js/wdcalculator/load-estimate-to-input-form.js",
        "js/wdcalculator/load-saved-estimate-to-form.js",
        "js/wdcalculator/save-estimate.js",
        "js/wdcalculator/add-estimate.js",
        "js/wdcalculator/estimate-list-events.js",
        "js/wdcalculator/refresh-after-save.js",
        "js/wdcalculator/estimate-mutation-bridge.js",
        "js/wdcalculator/url-bootstrap.js",
        "js/wdcalculator/order-match-ui.js",
        "js/wdcalculator/loading-state.js",
        "js/wdcalculator/current-database-estimate-id.js",
        "js/wdcalculator/products-state.js",
        "js/wdcalculator/editing-estimate-id.js",
        "js/wdcalculator/estimates-state.js",
        "js/wdcalculator/estimate-totals.js",
        "js/wdcalculator/current-estimate-math.js",
        "js/wdcalculator/calculation-resolvers.js",
        "js/wdcalculator/current-estimate-orchestration.js",
        "js/wdcalculator/total-estimates-display.js",
        "js/wdcalculator/coupon-shipping-wiring.js",
    ):
        assert retired_src not in body
    assert notes_idx < shared_idx
    assert categories_match is not None
    assert notes_match is not None
    categories_payload = json.loads(categories_match.group(1))
    notes_payload = json.loads(notes_match.group(1))
    assert categories_payload[0]["name"] == "기본 옵션"
    assert notes_payload[0]["name"] == "기본 비고"


def test_wdcalculator_page_keeps_saved_estimate_alias_wiring_contract(
    wdcalculator_settings_env, login
):
    """Saved-estimate loader wiring must stay direct and avoid wrapper/TDZ regressions."""
    client = login

    response = client.get("/wdcalculator")

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    total_estimates_alias_idx = body.index(
        "const { calculateTotalEstimates } = WdCalculatorTotalEstimatesDisplay;"
    )
    coupon_search_render_host_bootstrap_config_idx = body.index(
        "WdCalculatorCouponSearchRenderHostBootstrap.configure({"
    )
    load_saved_alias_idx = body.index(
        "const { loadEstimateToForm: loadSavedEstimateToForm } = WdCalculatorLoadSavedEstimateToForm;"
    )
    coupon_search_render_host_bootstrap_init_idx = body.index(
        "WdCalculatorCouponSearchRenderHostBootstrap.initCouponSearchRenderHostBootstrap();"
    )
    totals_startup_terminal_host_bootstrap_config_idx = body.index(
        "WdCalculatorTotalsStartupTerminalHostBootstrap.configure({"
    )

    assert "function loadEstimateToForm(estimate)" not in body
    assert body.count("loadEstimateToForm: loadSavedEstimateToForm,") == 2
    assert total_estimates_alias_idx < coupon_search_render_host_bootstrap_config_idx
    assert (
        load_saved_alias_idx
        < coupon_search_render_host_bootstrap_config_idx
        < coupon_search_render_host_bootstrap_init_idx
        < totals_startup_terminal_host_bootstrap_config_idx
    )


def test_wdcalculator_page_keeps_totals_startup_terminal_host_bootstrap_shell_contract(
    wdcalculator_settings_env, login
):
    """Totals/startup/terminal host wrapper must preserve startup-before-notes timing."""
    client = login

    response = client.get("/wdcalculator")

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    coupon_search_render_host_bootstrap_init_idx = body.index(
        "WdCalculatorCouponSearchRenderHostBootstrap.initCouponSearchRenderHostBootstrap();"
    )
    totals_startup_terminal_host_bootstrap_config_idx = body.index(
        "WdCalculatorTotalsStartupTerminalHostBootstrap.configure({"
    )
    totals_startup_terminal_host_bootstrap_init_idx = body.index(
        "WdCalculatorTotalsStartupTerminalHostBootstrap.initTotalsStartupTerminalHostBootstrap();"
    )
    notes_ui_host_bootstrap_config_idx = body.index(
        "WdCalculatorNotesUiHostBootstrap.configure({"
    )
    notes_ui_host_bootstrap_init_idx = body.index(
        "WdCalculatorNotesUiHostBootstrap.initNotesUiHostBootstrap();"
    )
    load_initial_products_idx = body.index("loadInitialProducts();")
    estimate_mutation_bridge_config_idx = body.index("WdCalculatorEstimateMutationBridge.configure({")

    assert "WdCalculatorTotalEstimatesDisplay.configure({" not in body
    assert "WdCalculatorStartupInit.configure({" not in body
    assert "WdCalculatorTerminalInit.configure({" not in body
    assert "initStartupInteractions();" not in body
    assert "bindProductSelect();" not in body
    assert "initBaseComponentsLiveInteractions();" not in body
    assert "initAddOptionButton();" not in body
    assert "initCalculateButton();" not in body
    assert "initSearchResultsLoadBridge();" not in body
    assert "bindOrderMatchButtons();" not in body
    assert "initCouponShippingWiring();" not in body
    assert "console.warn('카테고리 데이터가 없습니다. 제품 설정에서 추가 옵션을 등록해주세요.');" not in body
    assert "loadProducts();" not in body
    assert "ensureBaseComponentsUI();" not in body
    assert "WdCalculatorTotalsStartupTerminalBootstrap.configure({" not in body
    assert "WdCalculatorTotalsStartupTerminalBootstrap.initTotalsStartupTerminalBootstrap();" not in body
    assert "WdCalculatorNotesUiBootstrap.configure({" not in body
    assert "WdCalculatorNotesUiBootstrap.initNotesUiBootstrap();" not in body
    assert (
        "WdCalculatorTotalsStartupTerminalHostBootstrap.configure({\n        totalsStartupTerminalBootstrap: WdCalculatorTotalsStartupTerminalBootstrap,\n        totalEstimatesDisplay: WdCalculatorTotalEstimatesDisplay,\n        startupInit: WdCalculatorStartupInit,\n        terminalInit: WdCalculatorTerminalInit,\n        getEstimates,\n        getEditingEstimateId,\n        getCouponValue,"
        in body
    )
    assert "initCouponShippingWiring,\n        loadProducts,\n        ensureBaseComponentsUI," in body
    assert (
        coupon_search_render_host_bootstrap_init_idx
        < totals_startup_terminal_host_bootstrap_config_idx
        < totals_startup_terminal_host_bootstrap_init_idx
        < notes_ui_host_bootstrap_config_idx
        < notes_ui_host_bootstrap_init_idx
        < load_initial_products_idx
        < estimate_mutation_bridge_config_idx
    )


def test_wdcalculator_page_keeps_notes_ui_host_bootstrap_shell_contract(
    wdcalculator_settings_env, login
):
    """Notes UI host shell must replace the direct notes init call without reordering product load."""
    client = login

    response = client.get("/wdcalculator")

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    totals_startup_terminal_host_bootstrap_init_idx = body.index(
        "WdCalculatorTotalsStartupTerminalHostBootstrap.initTotalsStartupTerminalHostBootstrap();"
    )
    notes_ui_host_bootstrap_config_idx = body.index(
        "WdCalculatorNotesUiHostBootstrap.configure({"
    )
    notes_ui_host_bootstrap_init_idx = body.index(
        "WdCalculatorNotesUiHostBootstrap.initNotesUiHostBootstrap();"
    )
    load_initial_products_idx = body.index("loadInitialProducts();")

    assert "WdCalculatorNotesUI.initNotesUi();" not in body
    assert "WdCalculatorNotesUiBootstrap.configure({" not in body
    assert "WdCalculatorNotesUiBootstrap.initNotesUiBootstrap();" not in body
    assert (
        "WdCalculatorNotesUiHostBootstrap.configure({\n        notesUiBootstrap: WdCalculatorNotesUiBootstrap,\n        notesUi: WdCalculatorNotesUI,"
        in body
    )
    assert (
        totals_startup_terminal_host_bootstrap_init_idx
        < notes_ui_host_bootstrap_config_idx
        < notes_ui_host_bootstrap_init_idx
        < load_initial_products_idx
    )


def test_wdcalculator_page_keeps_current_estimate_helper_wiring_contract(
    wdcalculator_settings_env, login
):
    """Current-estimate orchestration helper must replace inline calculate/collect bodies."""
    client = login

    response = client.get("/wdcalculator")

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    orchestration_alias_idx = body.index(
        "const {\n        calculateEstimate,\n        collectCurrentEstimate,\n    } = WdCalculatorCurrentEstimateOrchestration;"
    )
    notes_collect_alias_idx = body.index("const { collectNotes } = WdCalculatorNotesUI;")
    orchestration_config_idx = body.index("WdCalculatorCurrentEstimateOrchestration.configure({")
    catalog_buttons_host_bootstrap_config_idx = body.index(
        "WdCalculatorCatalogButtonsHostBootstrap.configure({"
    )
    estimate_mutation_bridge_config_idx = body.index("WdCalculatorEstimateMutationBridge.configure({")
    post_mutation_ui_host_bootstrap_config_idx = body.index(
        "WdCalculatorPostMutationUiHostBootstrap.configure({"
    )

    assert "function calculateEstimate()" not in body
    assert "function collectCurrentEstimate()" not in body
    assert notes_collect_alias_idx < orchestration_config_idx
    assert (
        orchestration_alias_idx
        < orchestration_config_idx
        < catalog_buttons_host_bootstrap_config_idx
    )
    assert (
        orchestration_config_idx
        < estimate_mutation_bridge_config_idx
        < post_mutation_ui_host_bootstrap_config_idx
    )
    assert "collectCurrentEstimate,\n        resetInputFormKeepCustomerName,\n        resetInputFormToNewEstimate," in body
    assert "getCurrentDatabaseEstimateId,\n        collectNotes,\n        getCouponValue," in body


def test_wdcalculator_page_keeps_estimates_early_bootstrap_shell_contract(
    wdcalculator_settings_env, login
):
    """Host head shell must preserve estimates seed + early bootstrap ordering."""
    client = login

    response = client.get("/wdcalculator")

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    estimates_alias_idx = body.index(
        "const {\n        getEstimates,\n        getEstimatesLength,\n        setEstimates,\n    } = WdCalculatorEstimatesState;"
    )
    estimates_early_host_bootstrap_config_idx = body.index(
        "WdCalculatorEstimatesEarlyHostBootstrap.configure({"
    )
    estimates_early_host_bootstrap_init_idx = body.index(
        "WdCalculatorEstimatesEarlyHostBootstrap.initEstimatesEarlyHostBootstrap();"
    )
    current_estimate_alias_idx = body.index(
        "const {\n        calculateEstimate,\n        collectCurrentEstimate,\n    } = WdCalculatorCurrentEstimateOrchestration;"
    )

    assert "WdCalculatorEstimatesState.configure({" not in body
    assert "WdCalculatorEarlyBootstrap.configure({" not in body
    assert "WdCalculatorEarlyBootstrap.initEarlyBootstrap();" not in body
    assert "WdCalculatorUnsavedExitGuard.configure({" not in body
    assert "WdCalculatorUnsavedExitGuard.initUnsavedExitGuard();" not in body
    assert "WdCalculatorLayoutSyncWiring.configure({" not in body
    assert "WdCalculatorLayoutSyncWiring.initLayoutSyncWiring();" not in body
    assert "WdCalculatorEstimatesEarlyBootstrap.configure({" not in body
    assert "WdCalculatorEstimatesEarlyBootstrap.initEstimatesEarlyBootstrap();" not in body
    assert (
        "WdCalculatorEstimatesEarlyHostBootstrap.configure({\n        estimatesEarlyBootstrap: WdCalculatorEstimatesEarlyBootstrap,\n        estimatesState: WdCalculatorEstimatesState,\n        earlyBootstrap: WdCalculatorEarlyBootstrap,\n        unsavedExitGuard: WdCalculatorUnsavedExitGuard,\n        layoutSyncWiring: WdCalculatorLayoutSyncWiring,\n        initialEstimates: [],\n        getEstimates,"
        in body
    )
    assert (
        estimates_alias_idx
        < estimates_early_host_bootstrap_config_idx
        < estimates_early_host_bootstrap_init_idx
        < current_estimate_alias_idx
    )


def test_wdcalculator_page_keeps_post_mutation_ui_host_bootstrap_shell_contract(
    wdcalculator_settings_env, login
):
    """Post-mutation UI host shell must preserve late bootstrap ordering plus initial base UI render."""
    client = login

    response = client.get("/wdcalculator")

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    estimate_mutation_bridge_init_idx = body.index(
        "WdCalculatorEstimateMutationBridge.initEstimateMutationBridge();"
    )
    post_mutation_ui_host_bootstrap_config_idx = body.index(
        "WdCalculatorPostMutationUiHostBootstrap.configure({"
    )
    post_mutation_ui_host_bootstrap_init_idx = body.index(
        "WdCalculatorPostMutationUiHostBootstrap.initPostMutationUiHostBootstrap();"
    )

    assert "WdCalculatorLateBootstrap.configure({" not in body
    assert "WdCalculatorLateBootstrap.initLateBootstrap();" not in body
    assert "WdCalculatorSidebarBootstrap.configure({" not in body
    assert "WdCalculatorSidebarBootstrap.initSidebarBootstrap();" not in body
    assert "const loadSidebarEstimates = sidebarEstimatesApi.loadSidebarEstimates;" not in body
    assert "WdCalculatorRefreshAfterSave.configure({" not in body
    assert "WdCalculatorUrlBootstrap.configure({" not in body
    assert "initUrlBootstrap();" not in body
    assert "renderInitialBaseComponentsUi();" not in body
    assert "WdCalculatorPostMutationUiBootstrap.configure({" not in body
    assert "WdCalculatorPostMutationUiBootstrap.initPostMutationUiBootstrap();" not in body
    assert (
        "WdCalculatorPostMutationUiHostBootstrap.configure({\n        postMutationUiBootstrap: WdCalculatorPostMutationUiBootstrap,\n        lateBootstrap: WdCalculatorLateBootstrap,\n        sidebarBootstrap: WdCalculatorSidebarBootstrap,\n        refreshAfterSave: WdCalculatorRefreshAfterSave,\n        urlBootstrap: WdCalculatorUrlBootstrap,\n        initSidebarEstimates: window.initWdCalculatorSidebarEstimates,\n        loadEstimateToForm: loadSavedEstimateToForm,"
        in body
    )
    assert "resetInputFormToNewEstimate," in body
    assert "setTimeoutImpl: setTimeout,\n        renderInitialBaseComponentsUi," in body
    assert (
        estimate_mutation_bridge_init_idx
        < post_mutation_ui_host_bootstrap_config_idx
        < post_mutation_ui_host_bootstrap_init_idx
    )


def test_wdcalculator_page_keeps_estimate_mutation_bridge_shell_contract(
    wdcalculator_settings_env, login
):
    """Estimate-mutation bridge shell must preserve reset/load/add/list/save configure+init ordering."""
    client = login

    response = client.get("/wdcalculator")

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    load_initial_products_idx = body.index("loadInitialProducts();")
    estimate_mutation_bridge_config_idx = body.index("WdCalculatorEstimateMutationBridge.configure({")
    estimate_mutation_bridge_init_idx = body.index(
        "WdCalculatorEstimateMutationBridge.initEstimateMutationBridge();"
    )
    post_mutation_ui_host_bootstrap_config_idx = body.index(
        "WdCalculatorPostMutationUiHostBootstrap.configure({"
    )

    assert "WdCalculatorResetInputFormKeepCustomer.configure({" not in body
    assert "WdCalculatorLoadEstimateToInputForm.configure({" not in body
    assert "WdCalculatorLoadSavedEstimateToForm.configure({" not in body
    assert "WdCalculatorAddEstimate.configure({" not in body
    assert "WdCalculatorEstimateListEvents.configure({" not in body
    assert "WdCalculatorSaveEstimate.configure({" not in body
    assert "initAddEstimateButton();" not in body
    assert "initEstimateListEvents();" not in body
    assert "initSaveEstimateButton();" not in body
    assert (
        "WdCalculatorEstimateMutationBridge.configure({\n        resetFormModule: WdCalculatorResetInputFormKeepCustomer,\n        loadInputModule: WdCalculatorLoadEstimateToInputForm,\n        loadSavedModule: WdCalculatorLoadSavedEstimateToForm,\n        addEstimateModule: WdCalculatorAddEstimate,\n        listEventsModule: WdCalculatorEstimateListEvents,\n        saveEstimateModule: WdCalculatorSaveEstimate,"
        in body
    )
    assert "setEditingEstimateId,\n        getEstimatesLength," in body
    assert "setLoadingState,\n        getEditingEstimateId," in body
    assert "setCurrentDatabaseEstimateId,\n        setEstimates," in body
    assert "collectCurrentEstimate,\n        resetInputFormKeepCustomerName,\n        resetInputFormToNewEstimate," in body
    assert "getLoadingState,\n        loadEstimateToInputForm," in body
    assert "getCurrentDatabaseEstimateId,\n        collectNotes," in body
    assert (
        load_initial_products_idx
        < estimate_mutation_bridge_config_idx
        < estimate_mutation_bridge_init_idx
        < post_mutation_ui_host_bootstrap_config_idx
    )


def test_wdcalculator_page_keeps_loading_database_bootstrap_shell_contract(
    wdcalculator_settings_env, login
):
    """Loading/database host shell must preserve state seed ordering while delegating to the seed helper."""
    client = login

    response = client.get("/wdcalculator")

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    loading_alias_idx = body.index(
        "const {\n        getLoadingState,\n        setLoadingState,\n    } = WdCalculatorLoadingState;"
    )
    current_db_alias_idx = body.index(
        "const {\n        getCurrentDatabaseEstimateId,\n        setCurrentDatabaseEstimateId,\n    } = WdCalculatorCurrentDatabaseEstimateId;"
    )
    loading_database_host_bootstrap_config_idx = body.index(
        "WdCalculatorLoadingDatabaseHostBootstrap.configure({"
    )
    loading_database_host_bootstrap_init_idx = body.index(
        "WdCalculatorLoadingDatabaseHostBootstrap.initLoadingDatabaseHostBootstrap();"
    )
    totals_startup_terminal_host_bootstrap_config_idx = body.index(
        "WdCalculatorTotalsStartupTerminalHostBootstrap.configure({"
    )

    assert "WdCalculatorLoadingState.configure({" not in body
    assert "WdCalculatorCurrentDatabaseEstimateId.configure({" not in body
    assert "WdCalculatorLoadingDatabaseBootstrap.configure({" not in body
    assert "WdCalculatorLoadingDatabaseBootstrap.initLoadingDatabaseBootstrap();" not in body
    assert (
        "WdCalculatorLoadingDatabaseHostBootstrap.configure({\n        loadingDatabaseBootstrap: WdCalculatorLoadingDatabaseBootstrap,\n        loadingState: WdCalculatorLoadingState,\n        currentDatabaseEstimateIdState: WdCalculatorCurrentDatabaseEstimateId,\n        initialLoadingValue: false,\n        initialCurrentDatabaseEstimateId: null,"
        in body
    )
    assert (
        loading_alias_idx
        < current_db_alias_idx
        < loading_database_host_bootstrap_config_idx
        < loading_database_host_bootstrap_init_idx
        < totals_startup_terminal_host_bootstrap_config_idx
    )


def test_wdcalculator_page_keeps_products_editing_host_bootstrap_shell_contract(
    wdcalculator_settings_env, login
):
    """Products/editing host shell must preserve state seed ordering while delegating to the seed helper."""
    client = login

    response = client.get("/wdcalculator")

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    products_alias_idx = body.index(
        "const {\n        getProducts,\n        setProducts,\n    } = WdCalculatorProductsState;"
    )
    editing_alias_idx = body.index(
        "const {\n        getEditingEstimateId,\n        setEditingEstimateId,\n    } = WdCalculatorEditingEstimateId;"
    )
    products_editing_host_bootstrap_config_idx = body.index(
        "WdCalculatorProductsEditingHostBootstrap.configure({"
    )
    products_editing_host_bootstrap_init_idx = body.index(
        "WdCalculatorProductsEditingHostBootstrap.initProductsEditingHostBootstrap();"
    )
    primary_ui_bootstrap_config_idx = body.index("WdCalculatorPrimaryUiBootstrap.configure({")

    assert "WdCalculatorProductsState.configure({" not in body
    assert "WdCalculatorEditingEstimateId.configure({" not in body
    assert "WdCalculatorProductsEditingBootstrap.configure({" not in body
    assert "WdCalculatorProductsEditingBootstrap.initProductsEditingBootstrap();" not in body
    assert (
        "WdCalculatorProductsEditingHostBootstrap.configure({\n        productsEditingBootstrap: WdCalculatorProductsEditingBootstrap,\n        productsState: WdCalculatorProductsState,\n        editingEstimateIdState: WdCalculatorEditingEstimateId,\n        initialProducts: [],\n        initialEditingEstimateId: null,"
        in body
    )
    assert (
        products_alias_idx
        < editing_alias_idx
        < products_editing_host_bootstrap_config_idx
        < products_editing_host_bootstrap_init_idx
        < primary_ui_bootstrap_config_idx
    )


def test_wdcalculator_page_keeps_primary_ui_bootstrap_shell_contract(
    wdcalculator_settings_env, login
):
    """Primary UI configure/destructure bridge should stay in the primary-ui bootstrap shell."""
    client = login

    response = client.get("/wdcalculator")

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    products_editing_host_bootstrap_init_idx = body.index(
        "WdCalculatorProductsEditingHostBootstrap.initProductsEditingHostBootstrap();"
    )
    primary_ui_bootstrap_config_idx = body.index("WdCalculatorPrimaryUiBootstrap.configure({")
    primary_ui_bootstrap_init_idx = body.index(
        "WdCalculatorPrimaryUiBootstrap.initPrimaryUiBootstrap();"
    )
    current_estimate_config_idx = body.index("WdCalculatorCurrentEstimateOrchestration.configure({")

    assert "WdCalculatorBaseComponentsUI.configure({" not in body
    assert "WdCalculatorCouponDisplayHelpers.configure({" not in body
    assert "WdCalculatorAdditionalOptionsUI.configure({" not in body
    assert (
        "WdCalculatorPrimaryUiBootstrap.configure({\n        baseComponentsUi: WdCalculatorBaseComponentsUI,\n        couponDisplayHelpers: WdCalculatorCouponDisplayHelpers,\n        additionalOptionsUi: WdCalculatorAdditionalOptionsUI,\n        getProducts,\n        getCalculateEstimate: () => calculateEstimate,\n        defaultCouponValue: DEFAULT_COUPON_VALUE,\n        getCategories: () => wdCalculatorCategories,"
        in body
    )
    assert "readAdditionalOptionRowsFromUI,\n    } = WdCalculatorPrimaryUiBootstrap.initPrimaryUiBootstrap();" in body
    assert (
        products_editing_host_bootstrap_init_idx
        < primary_ui_bootstrap_config_idx
        < primary_ui_bootstrap_init_idx
        < current_estimate_config_idx
    )


def test_wdcalculator_page_keeps_catalog_buttons_host_bootstrap_shell_contract(
    wdcalculator_settings_env, login
):
    """Catalog/button host shell should preserve the catalog-buttons bootstrap configure trio."""
    client = login

    response = client.get("/wdcalculator")

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    current_estimate_config_idx = body.index("WdCalculatorCurrentEstimateOrchestration.configure({")
    catalog_buttons_host_bootstrap_config_idx = body.index(
        "WdCalculatorCatalogButtonsHostBootstrap.configure({"
    )
    catalog_buttons_host_bootstrap_init_idx = body.index(
        "WdCalculatorCatalogButtonsHostBootstrap.initCatalogButtonsHostBootstrap();"
    )
    coupon_search_render_host_bootstrap_config_idx = body.index(
        "WdCalculatorCouponSearchRenderHostBootstrap.configure({"
    )

    assert "WdCalculatorAddOptionButton.configure({" not in body
    assert "WdCalculatorCalculateButton.configure({" not in body
    assert "WdCalculatorProductCatalogUI.configure({" not in body
    assert "WdCalculatorCatalogButtonsBootstrap.configure({" not in body
    assert "WdCalculatorCatalogButtonsBootstrap.initCatalogButtonsBootstrap();" not in body
    assert (
        "WdCalculatorCatalogButtonsHostBootstrap.configure({\n        catalogButtonsBootstrap: WdCalculatorCatalogButtonsBootstrap,\n        addOptionButton: WdCalculatorAddOptionButton,\n        calculateButton: WdCalculatorCalculateButton,\n        productCatalogUi: WdCalculatorProductCatalogUI,\n        documentRef: document,\n        appendAdditionalOptionRow,\n        calculateEstimate,\n        getProducts,\n        setProducts,\n        getCalculateEstimate: () => calculateEstimate,\n        updateBaseProductSelectOptions,\n        ensureBaseComponentsUI,"
        in body
    )
    assert (
        current_estimate_config_idx
        < catalog_buttons_host_bootstrap_config_idx
        < catalog_buttons_host_bootstrap_init_idx
        < coupon_search_render_host_bootstrap_config_idx
    )


def test_wdcalculator_page_keeps_coupon_search_render_host_bootstrap_shell_contract(
    wdcalculator_settings_env, login
):
    """Coupon/search/render host wrapper should stay as the single host shell entrypoint."""
    client = login

    response = client.get("/wdcalculator")

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    catalog_buttons_host_bootstrap_init_idx = body.index(
        "WdCalculatorCatalogButtonsHostBootstrap.initCatalogButtonsHostBootstrap();"
    )
    coupon_search_render_host_bootstrap_config_idx = body.index(
        "WdCalculatorCouponSearchRenderHostBootstrap.configure({"
    )
    coupon_search_render_host_bootstrap_init_idx = body.index(
        "WdCalculatorCouponSearchRenderHostBootstrap.initCouponSearchRenderHostBootstrap();"
    )
    totals_startup_terminal_host_bootstrap_config_idx = body.index(
        "WdCalculatorTotalsStartupTerminalHostBootstrap.configure({"
    )

    assert "WdCalculatorCouponShippingWiring.configure({" not in body
    assert "WdCalculatorSearchResultsLoad.configure({" not in body
    assert "WdCalculatorRenderEstimatesList.configure({" not in body
    assert "WdCalculatorCouponSearchRenderBootstrap.configure({" not in body
    assert "WdCalculatorCouponSearchRenderBootstrap.initCouponSearchRenderBootstrap();" not in body
    assert (
        "WdCalculatorCouponSearchRenderHostBootstrap.configure({\n        couponSearchRenderBootstrap: WdCalculatorCouponSearchRenderBootstrap,\n        couponShippingWiring: WdCalculatorCouponShippingWiring,\n        searchResultsLoad: WdCalculatorSearchResultsLoad,\n        renderEstimatesList: WdCalculatorRenderEstimatesList,\n        defaultCouponValue: DEFAULT_COUPON_VALUE,\n        getEstimates,\n        calculateEstimate,\n        calculateTotalEstimates,\n        getCouponValue,\n        formatNumber,\n        loadEstimateToForm: loadSavedEstimateToForm,\n        escapeHtml,\n        formatNotesText: WdCalculatorNotesUI.formatNotesText,\n        onRenderComplete: calculateTotalEstimates,\n        getProducts,"
        in body
    )
    assert (
        catalog_buttons_host_bootstrap_init_idx
        < coupon_search_render_host_bootstrap_config_idx
        < coupon_search_render_host_bootstrap_init_idx
        < totals_startup_terminal_host_bootstrap_config_idx
    )


def test_wdcalculator_page_keeps_loading_state_helper_wiring_contract(
    wdcalculator_settings_env, login
):
    """Loading-state helper must replace raw host loading flag storage."""
    client = login

    response = client.get("/wdcalculator")

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    loading_alias_idx = body.index(
        "const {\n        getLoadingState,\n        setLoadingState,\n    } = WdCalculatorLoadingState;"
    )
    loading_database_host_bootstrap_config_idx = body.index(
        "WdCalculatorLoadingDatabaseHostBootstrap.configure({"
    )
    totals_startup_terminal_host_bootstrap_config_idx = body.index(
        "WdCalculatorTotalsStartupTerminalHostBootstrap.configure({"
    )

    assert "let isLoadingEstimate = false;" not in body
    assert "WdCalculatorLoadingState.configure({" not in body
    assert (
        "WdCalculatorLoadingDatabaseHostBootstrap.configure({\n        loadingDatabaseBootstrap: WdCalculatorLoadingDatabaseBootstrap,\n        loadingState: WdCalculatorLoadingState,\n        currentDatabaseEstimateIdState: WdCalculatorCurrentDatabaseEstimateId,\n        initialLoadingValue: false,\n        initialCurrentDatabaseEstimateId: null,"
        in body
    )
    assert "setLoadingState,\n        getEditingEstimateId" in body
    assert "getLoadingState,\n        loadEstimateToInputForm" in body
    assert (
        loading_alias_idx
        < loading_database_host_bootstrap_config_idx
        < totals_startup_terminal_host_bootstrap_config_idx
    )


def test_wdcalculator_page_keeps_current_database_estimate_id_helper_wiring_contract(
    wdcalculator_settings_env, login
):
    """Current DB estimate id helper must replace raw host scalar storage."""
    client = login

    response = client.get("/wdcalculator")

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    current_db_alias_idx = body.index(
        "const {\n        getCurrentDatabaseEstimateId,\n        setCurrentDatabaseEstimateId,\n    } = WdCalculatorCurrentDatabaseEstimateId;"
    )
    loading_database_host_bootstrap_config_idx = body.index(
        "WdCalculatorLoadingDatabaseHostBootstrap.configure({"
    )
    totals_startup_terminal_host_bootstrap_config_idx = body.index(
        "WdCalculatorTotalsStartupTerminalHostBootstrap.configure({"
    )

    assert "let currentDatabaseEstimateId = null;" not in body
    assert "WdCalculatorCurrentDatabaseEstimateId.configure({" not in body
    assert (
        "WdCalculatorLoadingDatabaseHostBootstrap.configure({\n        loadingDatabaseBootstrap: WdCalculatorLoadingDatabaseBootstrap,\n        loadingState: WdCalculatorLoadingState,\n        currentDatabaseEstimateIdState: WdCalculatorCurrentDatabaseEstimateId,\n        initialLoadingValue: false,\n        initialCurrentDatabaseEstimateId: null,"
        in body
    )
    assert "setCurrentDatabaseEstimateId,\n        setEstimates" in body
    assert "getCurrentDatabaseEstimateId,\n        collectNotes,\n        getCouponValue," in body
    assert (
        current_db_alias_idx
        < loading_database_host_bootstrap_config_idx
        < totals_startup_terminal_host_bootstrap_config_idx
    )


def test_wdcalculator_page_keeps_products_state_helper_wiring_contract(
    wdcalculator_settings_env, login
):
    """Products-state helper must replace raw host products storage."""
    client = login

    response = client.get("/wdcalculator")

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    products_alias_idx = body.index(
        "const {\n        getProducts,\n        setProducts,\n    } = WdCalculatorProductsState;"
    )
    products_host_bootstrap_config_idx = body.index(
        "WdCalculatorProductsEditingHostBootstrap.configure({"
    )
    primary_ui_bootstrap_config_idx = body.index("WdCalculatorPrimaryUiBootstrap.configure({")
    current_estimate_config_idx = body.index("WdCalculatorCurrentEstimateOrchestration.configure({")
    catalog_buttons_host_bootstrap_config_idx = body.index(
        "WdCalculatorCatalogButtonsHostBootstrap.configure({"
    )
    post_mutation_ui_host_bootstrap_config_idx = body.index(
        "WdCalculatorPostMutationUiHostBootstrap.configure({"
    )

    assert "let products = [];" not in body
    assert "WdCalculatorProductsState.configure({" not in body
    assert "WdCalculatorProductsEditingBootstrap.configure({" not in body
    assert (
        "WdCalculatorProductsEditingHostBootstrap.configure({\n        productsEditingBootstrap: WdCalculatorProductsEditingBootstrap,\n        productsState: WdCalculatorProductsState,\n        editingEstimateIdState: WdCalculatorEditingEstimateId,\n        initialProducts: [],\n        initialEditingEstimateId: null,"
        in body
    )
    assert (
        "WdCalculatorPrimaryUiBootstrap.configure({\n        baseComponentsUi: WdCalculatorBaseComponentsUI,\n        couponDisplayHelpers: WdCalculatorCouponDisplayHelpers,\n        additionalOptionsUi: WdCalculatorAdditionalOptionsUI,\n        getProducts,"
        in body
    )
    assert "WdCalculatorCurrentEstimateOrchestration.configure({\n        getProducts," in body
    assert (
        "WdCalculatorCatalogButtonsHostBootstrap.configure({\n        catalogButtonsBootstrap: WdCalculatorCatalogButtonsBootstrap,\n        addOptionButton: WdCalculatorAddOptionButton,\n        calculateButton: WdCalculatorCalculateButton,\n        productCatalogUi: WdCalculatorProductCatalogUI,\n        documentRef: document,\n        appendAdditionalOptionRow,\n        calculateEstimate,\n        getProducts,\n        setProducts,"
        in body
    )
    assert "renderEstimatesList,\n        getProducts," in body
    assert (
        products_alias_idx
        < products_host_bootstrap_config_idx
        < primary_ui_bootstrap_config_idx
        < current_estimate_config_idx
        < catalog_buttons_host_bootstrap_config_idx
        < post_mutation_ui_host_bootstrap_config_idx
    )


def test_wdcalculator_page_keeps_editing_estimate_id_helper_wiring_contract(
    wdcalculator_settings_env, login
):
    """Editing estimate id helper must replace raw host scalar storage."""
    client = login

    response = client.get("/wdcalculator")

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    editing_alias_idx = body.index(
        "const {\n        getEditingEstimateId,\n        setEditingEstimateId,\n    } = WdCalculatorEditingEstimateId;"
    )
    products_editing_host_bootstrap_config_idx = body.index(
        "WdCalculatorProductsEditingHostBootstrap.configure({"
    )
    current_estimate_config_idx = body.index("WdCalculatorCurrentEstimateOrchestration.configure({")
    totals_startup_terminal_host_bootstrap_config_idx = body.index(
        "WdCalculatorTotalsStartupTerminalHostBootstrap.configure({"
    )
    estimate_mutation_bridge_config_idx = body.index("WdCalculatorEstimateMutationBridge.configure({")

    assert "let editingEstimateId = null;" not in body
    assert "WdCalculatorEditingEstimateId.configure({" not in body
    assert "WdCalculatorProductsEditingBootstrap.configure({" not in body
    assert (
        "WdCalculatorProductsEditingHostBootstrap.configure({\n        productsEditingBootstrap: WdCalculatorProductsEditingBootstrap,\n        productsState: WdCalculatorProductsState,\n        editingEstimateIdState: WdCalculatorEditingEstimateId,\n        initialProducts: [],\n        initialEditingEstimateId: null,"
        in body
    )
    assert "WdCalculatorCurrentEstimateOrchestration.configure({\n        getProducts,\n        getEditingEstimateId," in body
    assert (
        "WdCalculatorEstimateMutationBridge.configure({\n        resetFormModule: WdCalculatorResetInputFormKeepCustomer,"
        in body
    )
    assert (
        "WdCalculatorTotalsStartupTerminalHostBootstrap.configure({\n        totalsStartupTerminalBootstrap: WdCalculatorTotalsStartupTerminalBootstrap,\n        totalEstimatesDisplay: WdCalculatorTotalEstimatesDisplay,\n        startupInit: WdCalculatorStartupInit,\n        terminalInit: WdCalculatorTerminalInit,\n        getEstimates,\n        getEditingEstimateId,"
        in body
    )
    assert "setEditingEstimateId,\n        getEstimatesLength," in body
    assert "setLoadingState,\n        getEditingEstimateId," in body
    assert "getEditingEstimateId,\n        getEstimates,\n        normalizeId," in body
    assert "collectCurrentEstimate,\n        resetInputFormKeepCustomerName,\n        resetInputFormToNewEstimate," in body
    assert (
        editing_alias_idx
        < products_editing_host_bootstrap_config_idx
        < current_estimate_config_idx
        < totals_startup_terminal_host_bootstrap_config_idx
        < estimate_mutation_bridge_config_idx
    )


def test_wdcalculator_page_keeps_estimates_state_helper_wiring_contract(
    wdcalculator_settings_env, login
):
    """Estimates-state helper must replace raw host estimates storage."""
    client = login

    response = client.get("/wdcalculator")

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    estimates_alias_idx = body.index(
        "const {\n        getEstimates,\n        getEstimatesLength,\n        setEstimates,\n    } = WdCalculatorEstimatesState;"
    )
    estimates_early_host_bootstrap_config_idx = body.index(
        "WdCalculatorEstimatesEarlyHostBootstrap.configure({"
    )
    current_estimate_config_idx = body.index("WdCalculatorCurrentEstimateOrchestration.configure({")
    coupon_search_render_host_bootstrap_config_idx = body.index(
        "WdCalculatorCouponSearchRenderHostBootstrap.configure({"
    )
    totals_startup_terminal_host_bootstrap_config_idx = body.index(
        "WdCalculatorTotalsStartupTerminalHostBootstrap.configure({"
    )
    estimate_mutation_bridge_config_idx = body.index("WdCalculatorEstimateMutationBridge.configure({")
    post_mutation_ui_host_bootstrap_config_idx = body.index(
        "WdCalculatorPostMutationUiHostBootstrap.configure({"
    )

    assert "let estimates = [];" not in body
    assert "WdCalculatorEstimatesState.configure({" not in body
    assert "WdCalculatorEarlyBootstrap.configure({" not in body
    assert "WdCalculatorEstimatesEarlyBootstrap.configure({" not in body
    assert (
        "WdCalculatorEstimatesEarlyHostBootstrap.configure({\n        estimatesEarlyBootstrap: WdCalculatorEstimatesEarlyBootstrap,\n        estimatesState: WdCalculatorEstimatesState,\n        earlyBootstrap: WdCalculatorEarlyBootstrap,\n        unsavedExitGuard: WdCalculatorUnsavedExitGuard,\n        layoutSyncWiring: WdCalculatorLayoutSyncWiring,\n        initialEstimates: [],\n        getEstimates,"
        in body
    )
    assert (
        "WdCalculatorCurrentEstimateOrchestration.configure({\n        getProducts,\n        getEditingEstimateId,\n        getEstimates,"
        in body
    )
    assert (
        "WdCalculatorCouponSearchRenderHostBootstrap.configure({\n        couponSearchRenderBootstrap: WdCalculatorCouponSearchRenderBootstrap,\n        couponShippingWiring: WdCalculatorCouponShippingWiring,\n        searchResultsLoad: WdCalculatorSearchResultsLoad,\n        renderEstimatesList: WdCalculatorRenderEstimatesList,\n        defaultCouponValue: DEFAULT_COUPON_VALUE,\n        getEstimates,\n        calculateEstimate,\n        calculateTotalEstimates,\n        getCouponValue,\n        formatNumber,\n        loadEstimateToForm: loadSavedEstimateToForm,\n        escapeHtml,\n        formatNotesText: WdCalculatorNotesUI.formatNotesText,\n        onRenderComplete: calculateTotalEstimates,\n        getProducts,"
        in body
    )
    assert (
        "WdCalculatorTotalsStartupTerminalHostBootstrap.configure({\n        totalsStartupTerminalBootstrap: WdCalculatorTotalsStartupTerminalBootstrap,\n        totalEstimatesDisplay: WdCalculatorTotalEstimatesDisplay,\n        startupInit: WdCalculatorStartupInit,\n        terminalInit: WdCalculatorTerminalInit,\n        getEstimates,"
        in body
    )
    assert (
        "WdCalculatorEstimateMutationBridge.configure({\n        resetFormModule: WdCalculatorResetInputFormKeepCustomer,"
        in body
    )
    assert "setEditingEstimateId,\n        getEstimatesLength," in body
    assert "setLoadingState,\n        getEditingEstimateId,\n        getEstimates," in body
    assert "setCurrentDatabaseEstimateId,\n        setEstimates," in body
    assert "getEditingEstimateId,\n        getEstimates,\n        normalizeId," in body
    assert "getLoadingState,\n        loadEstimateToInputForm," in body
    assert "getCurrentDatabaseEstimateId,\n        collectNotes," in body
    assert "formatNumber,\n        setEstimates," in body
    assert (
        estimates_alias_idx
        < estimates_early_host_bootstrap_config_idx
        < current_estimate_config_idx
        < coupon_search_render_host_bootstrap_config_idx
        < totals_startup_terminal_host_bootstrap_config_idx
        < estimate_mutation_bridge_config_idx
        < post_mutation_ui_host_bootstrap_config_idx
    )


def test_wdcalculator_products_api_keeps_legacy_success_shape(
    wdcalculator_settings_env, login
):
    """Product catalog loader must keep the legacy `{success, products}` payload shape."""
    client = login

    response = client.get("/api/wdcalculator/products")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["success"] is True
    assert isinstance(payload["products"], list)
    first_product = payload["products"][0]
    assert first_product["id"] == 1
    assert first_product["name"] == "Seed Product"
    assert first_product["pricing_type"] == "30cm"
    assert first_product["additional_options"] == []
    assert first_product["coupon_type"] == "percentage"
    assert first_product["coupon_value"] == 0
    assert first_product["price_30cm"] == 1000
    assert first_product["price_1cm"] == 10


def test_wdcalculator_product_settings_page_exposes_category(wdcalculator_settings_env, login):
    """제품 설정 페이지는 제품 카테고리 입력칸과 목록 컬럼을 노출해야 한다."""
    client = login

    response = client.get("/wdcalculator/product-settings")

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert 'id="productCategory"' in body
    assert 'name="category"' in body
    assert "<th>카테고리</th>" in body


def test_wdcalculator_product_save_persists_category(wdcalculator_settings_env, login):
    """제품 저장 시 category가 그대로 보존·반환되어야 한다(드롭다운 카테고리 그룹핑 근거)."""
    client = login

    save_response = client.post(
        "/api/wdcalculator/products",
        json={
            "name": "몰딩(푸쉬)",
            "category": "몰딩",
            "pricing_type": "1m",
            "additional_options": [],
            "coupon_type": "percentage",
            "coupon_value": 0,
            "price_1m": 50000,
        },
    )

    assert save_response.status_code == 200
    assert save_response.get_json()["success"] is True

    reloaded = client.get("/api/wdcalculator/products").get_json()["products"]
    saved = next(product for product in reloaded if product["name"] == "몰딩(푸쉬)")
    assert saved["category"] == "몰딩"


def test_wdcalculator_calculator_page_includes_category_picker_assets(wdcalculator_settings_env, login):
    """계산기 페이지는 카테고리 2단 피커 자산(js/css)을 로드해야 한다."""
    client = login

    response = client.get("/wdcalculator")

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "js/wdcalculator/category-picker.js" in body
    assert "css/wdcalculator/category-picker.css" in body
    # primary-form(셀렉트 생성) 이후 category-picker(셀렉트 enhance)가 로드돼야 한다.
    assert body.index("js/wdcalculator/primary-form.js") < body.index(
        "js/wdcalculator/category-picker.js"
    )


def test_wdcalculator_product_settings_orders_by_category_then_name(wdcalculator_settings_env, login):
    """제품 목록은 카테고리 → 제품명 순(미분류 맨 뒤)으로 정렬되어야 한다."""
    client = login
    payloads = [
        {"name": "ZZ제품", "category": "몰딩"},
        {"name": "AA제품", "category": "몰딩"},
        {"name": "MM제품", "category": "가구"},
    ]
    for payload in payloads:
        payload.update(
            {
                "pricing_type": "1m",
                "additional_options": [],
                "coupon_type": "percentage",
                "coupon_value": 0,
                "price_1m": 1000,
            }
        )
        assert client.post("/api/wdcalculator/products", json=payload).get_json()["success"] is True

    body = client.get("/wdcalculator/product-settings").get_data(as_text=True)
    # '가구' < '몰딩' < 미분류(Seed Product), 같은 카테고리 내 이름 오름차순(AA < ZZ).
    i_mm = body.index("<strong>MM제품</strong>")
    i_aa = body.index("<strong>AA제품</strong>")
    i_zz = body.index("<strong>ZZ제품</strong>")
    i_seed = body.index("<strong>Seed Product</strong>")
    assert i_mm < i_aa < i_zz < i_seed


def test_wdcalculator_calculate_save_and_load_estimate_smoke(wdcalculator_settings_env, login):
    """Core WDCalculator API flow must keep calculate -> save -> load roundtrip working."""
    client = login

    calculate_response = client.post(
        "/api/wdcalculator/calculate",
        json={
            "product_id": 1,
            "width_mm": 300,
            "additional_options": [],
            "coupon_type": "percentage",
            "coupon_value": 0,
        },
    )

    assert calculate_response.status_code == 200
    calculate_payload = calculate_response.get_json()
    assert calculate_payload["success"] is True
    assert calculate_payload["base_price"] == 1000
    assert calculate_payload["final_price"] == 1000

    estimate_data = {
        "items": [{"product_id": 1, "width_mm": 300}],
        "totals": {
            "base_price": calculate_payload["base_price"],
            "final_price": calculate_payload["final_price"],
        },
    }
    save_response = client.post(
        "/api/wdcalculator/save-estimate",
        json={"customer_name": "WD Smoke", "estimate_data": estimate_data},
    )

    assert save_response.status_code == 200
    save_payload = save_response.get_json()
    assert save_payload["success"] is True
    assert isinstance(save_payload["estimate_id"], int)

    load_response = client.get(f"/api/wdcalculator/estimate/{save_payload['estimate_id']}")

    assert load_response.status_code == 200
    load_payload = load_response.get_json()
    assert load_payload["success"] is True
    assert load_payload["estimate"]["customer_name"] == "WD Smoke"
    assert load_payload["estimate"]["estimate_data"] == estimate_data


def test_wdcalculator_search_and_delete_estimate_smoke(wdcalculator_settings_env, login):
    """Sidebar estimate APIs must preserve search -> delete behavior."""
    client = login
    estimate_data = {
        "items": [{"product_id": 1, "width_mm": 300}],
        "basePrice": 1000,
        "additionalPrice": 500,
        "totalPrice": 1500,
    }

    save_response = client.post(
        "/api/wdcalculator/save-estimate",
        json={"customer_name": "WD Sidebar", "estimate_data": estimate_data},
    )

    assert save_response.status_code == 200
    saved_id = save_response.get_json()["estimate_id"]

    search_response = client.get("/api/wdcalculator/search-estimates?customer_name=Sidebar")

    assert search_response.status_code == 200
    search_payload = search_response.get_json()
    assert search_payload["success"] is True
    matched_estimate = next(
        estimate for estimate in search_payload["estimates"] if estimate["id"] == saved_id
    )
    assert matched_estimate["customer_name"] == "WD Sidebar"
    assert matched_estimate["estimate_data"] == estimate_data
    assert matched_estimate["created_at"]

    delete_response = client.delete(f"/api/wdcalculator/estimate/{saved_id}")

    assert delete_response.status_code == 200
    delete_payload = delete_response.get_json()
    assert delete_payload["success"] is True

    post_delete_search = client.get("/api/wdcalculator/search-estimates?customer_name=Sidebar")
    post_delete_payload = post_delete_search.get_json()
    assert post_delete_payload["success"] is True
    assert all(estimate["id"] != saved_id for estimate in post_delete_payload["estimates"])


def test_wdcalculator_search_orders_api_keeps_legacy_success_shape(
    wdcalculator_settings_env, login
):
    """Order-match search must keep the legacy `{success, orders, count}` payload surface."""
    client = login
    order = _create_order(
        customer_name="WD Match Customer",
        phone="010-9876-5432",
        address="Busan",
        product="Kitchen",
        status="DRAWING",
    )

    response = client.get("/api/wdcalculator/search-orders?customer_name=Match Customer")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["success"] is True
    assert payload["count"] == 1
    assert isinstance(payload["orders"], list)
    order_payload = payload["orders"][0]
    assert order_payload["id"] == order.id
    assert order_payload["customer_name"] == "WD Match Customer"
    assert order_payload["phone"] == "010-9876-5432"
    assert order_payload["address"] == "Busan"
    assert order_payload["product"] == "Kitchen"
    assert order_payload["status"] == "DRAWING"
    assert order_payload["received_date"] == "2026-04-12"


def test_wdcalculator_search_orders_matches_erp_order_structured_customer(
    wdcalculator_settings_env, login
):
    """ERP Order matching must search/display structured customer fields, not only flat legacy columns."""
    client = login
    order = _create_order(
        customer_name="ERP Order",
        phone="000-0000-0000",
        address="-",
        product="ERP Order",
        status="DRAWING",
        is_erp_order=True,
        structured_data={
            "workflow": {"stage": "DRAWING"},
            "parties": {
                "customer": {
                    "name": "ERP 매칭 고객",
                    "phone": "010-3333-4444",
                }
            },
            "site": {
                "address_full": "서울 강남구 ERP로 10",
                "address_main": "서울 강남구 ERP로 10",
            },
            "items": [{"product_name": "ERP 붙박이장"}],
        },
    )
    order_id = order.id

    response = client.get(
        "/api/wdcalculator/search-orders?customer_name="
        "%EC%9E%90%EB%8F%99%EB%A7%A4%EC%B9%AD"
    )
    assert response.status_code == 200
    assert response.get_json()["count"] == 0

    response = client.get(
        "/api/wdcalculator/search-orders?customer_name="
        "%EB%A7%A4%EC%B9%AD%20%EA%B3%A0%EA%B0%9D"
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["success"] is True
    assert payload["count"] == 1
    order_payload = payload["orders"][0]
    assert order_payload["id"] == order_id
    assert order_payload["customer_name"] == "ERP 매칭 고객"
    assert order_payload["phone"] == "010-3333-4444"
    assert order_payload["address"] == "서울 강남구 ERP로 10"
    assert order_payload["product"] == "ERP 붙박이장"

    save_response = client.post(
        "/api/wdcalculator/save-estimate",
        json={
            "customer_name": "ERP 매칭 고객",
            "estimate_data": {"items": [{"product_id": 1, "width_mm": 300}]},
        },
    )
    estimate_id = save_response.get_json()["estimate_id"]
    match_response = client.post(
        "/api/wdcalculator/match-order",
        json={"estimate_id": estimate_id, "order_id": order_id},
    )

    assert match_response.status_code == 200
    match_payload = match_response.get_json()
    assert match_payload["success"] is True
    match_row = wd_calculator_session.query(EstimateOrderMatch).filter(
        EstimateOrderMatch.id == match_payload["match_id"]
    ).first()
    assert match_row is not None
    assert match_row.estimate_id == estimate_id
    assert match_row.order_id == order_id


def test_wdcalculator_match_order_api_keeps_legacy_success_shape(
    wdcalculator_settings_env, login
):
    """Order-match save path must keep the legacy success/message/match_id payload."""
    client = login
    order = _create_order(customer_name="WD Match Save")
    order_id = order.id
    save_response = client.post(
        "/api/wdcalculator/save-estimate",
        json={
            "customer_name": "WD Match Save",
            "estimate_data": {"items": [{"product_id": 1, "width_mm": 300}]},
        },
    )
    estimate_id = save_response.get_json()["estimate_id"]

    response = client.post(
        "/api/wdcalculator/match-order",
        json={"estimate_id": estimate_id, "order_id": order_id},
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["success"] is True
    assert payload["message"] == "견적과 주문이 매칭되었습니다."
    assert isinstance(payload["match_id"], int)
    match_row = wd_calculator_session.query(EstimateOrderMatch).filter(
        EstimateOrderMatch.id == payload["match_id"]
    ).first()
    assert match_row is not None
    assert match_row.estimate_id == estimate_id
    assert match_row.order_id == order_id


def test_wdcalculator_order_estimates_returns_erp_deposit_for_matched_card(
    wdcalculator_settings_env, login
):
    """Matched estimate cards must receive ERP Order deposits, not only legacy payment_amount."""
    client = login
    order = _create_order(
        customer_name="ERP Order",
        payment_amount=0,
        is_erp_order=True,
        structured_data={
            "payment": {"deposit": {"amount": 100000}},
            "payments": {"deposit": {"amount": 50000}},
        },
    )
    order_id = order.id
    save_response = client.post(
        "/api/wdcalculator/save-estimate",
        json={
            "customer_name": "ERP Deposit Card",
            "estimate_data": {"items": [{"product_id": 1, "width_mm": 300}]},
        },
    )
    estimate_id = save_response.get_json()["estimate_id"]
    match_response = client.post(
        "/api/wdcalculator/match-order",
        json={"estimate_id": estimate_id, "order_id": order_id},
    )
    assert match_response.status_code == 200
    assert match_response.get_json()["success"] is True

    response = client.get(f"/api/wdcalculator/order-estimates/{order_id}")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["success"] is True
    assert payload["count"] == 1
    assert payload["estimates"][0]["id"] == estimate_id
    assert payload["order_payment_amount"] == 100000
    assert payload["order_payment_label"] == "예약금(선금)"
    assert payload["order_payment"]["amount"] == 100000
    assert payload["order_payment"]["payment_amount"] == 100000
    assert payload["order_payment"]["deposit_amount"] == 100000


def test_wdcalculator_products_persist_in_db_after_seed_file_changes(wdcalculator_settings_env, login):
    """Saved products must come from DB, not revert to file seed."""
    client = login

    initial_response = client.get("/api/wdcalculator/products")
    assert initial_response.status_code == 200
    initial_products = initial_response.get_json()["products"]
    assert initial_products[0]["name"] == "Seed Product"

    save_response = client.post(
        "/api/wdcalculator/products",
        json={
            "id": 1,
            "name": "Updated Product",
            "pricing_type": "30cm",
            "additional_options": [],
            "coupon_type": "percentage",
            "coupon_value": 0,
            "price_30cm": 2222,
            "price_1cm": 22,
        },
    )
    assert save_response.status_code == 200
    assert save_response.get_json()["success"] is True

    _write_json(
        wdcalculator_settings_env["products_path"],
        {
            "products": [
                {
                    "id": 1,
                    "name": "Wrong Seed Value",
                    "pricing_type": "30cm",
                    "additional_options": [],
                    "coupon_type": "percentage",
                    "coupon_value": 0,
                    "price_30cm": 9999,
                    "price_1cm": 99,
                }
            ]
        },
    )

    wd_calculator_session.expire_all()
    reloaded_response = client.get("/api/wdcalculator/products")
    reloaded_products = reloaded_response.get_json()["products"]
    assert reloaded_products[0]["name"] == "Updated Product"
    assert reloaded_products[0]["price_30cm"] == 2222

    wd_calculator_session.expire_all()
    settings = wd_calculator_session.query(WDCalculatorProductSettings).filter(
        WDCalculatorProductSettings.id == 1
    ).first()
    assert settings is not None
    assert settings.products[0]["name"] == "Updated Product"


def test_wdcalculator_additional_options_persist_in_db_after_seed_file_changes(wdcalculator_settings_env, login):
    """Additional options must keep DB state even if seed files change."""
    client = login

    initial_response = client.get("/api/wdcalculator/additional-options/categories")
    assert initial_response.status_code == 200
    initial_categories = initial_response.get_json()["categories"]
    assert initial_categories[0]["name"] == "기본 옵션"

    save_response = client.post(
        "/api/wdcalculator/additional-options/categories/1/options",
        json={"name": "신규 추가옵션", "price": 12345},
    )
    assert save_response.status_code == 200
    assert save_response.get_json()["success"] is True

    _write_json(
        wdcalculator_settings_env["additional_path"],
        {
            "categories": [
                {
                    "id": 1,
                    "name": "파일 기준값",
                    "options": [],
                }
            ]
        },
    )

    wd_calculator_session.expire_all()
    reloaded_response = client.get("/api/wdcalculator/additional-options/categories")
    reloaded_categories = reloaded_response.get_json()["categories"]

    assert reloaded_categories[0]["name"] == "기본 옵션"
    assert any(
        option["name"] == "신규 추가옵션"
        for option in reloaded_categories[0]["options"]
    )


def test_wdcalculator_notes_persist_in_db_after_seed_file_changes(wdcalculator_settings_env, login):
    """Notes categories must keep DB state even if seed files change."""
    client = login

    initial_response = client.get("/api/wdcalculator/notes/categories")
    assert initial_response.status_code == 200
    initial_categories = initial_response.get_json()["categories"]
    assert initial_categories[0]["name"] == "기본 비고"

    save_response = client.post(
        "/api/wdcalculator/notes/categories/1/options",
        json={"name": "신규 비고 문구"},
    )
    assert save_response.status_code == 200
    assert save_response.get_json()["success"] is True

    _write_json(
        wdcalculator_settings_env["notes_path"],
        {
            "categories": [
                {
                    "id": 1,
                    "name": "파일 비고 기준값",
                    "options": [],
                }
            ]
        },
    )

    wd_calculator_session.expire_all()
    reloaded_response = client.get("/api/wdcalculator/notes/categories")
    reloaded_categories = reloaded_response.get_json()["categories"]

    assert reloaded_categories[0]["name"] == "기본 비고"
    assert any(
        option["name"] == "신규 비고 문구"
        for option in reloaded_categories[0]["options"]
    )
