/**
 * WDCalculator composition canonical chunk (Wave 5 W5-B2).
 * Merged from prior bootstrap/host-bootstrap modules; see run record for removal list.
 * DO NOT add new *-host-bootstrap.js files; extend this chunk instead.
 */


/* ---- included: early-bootstrap.js ---- */
(function () {
    var WdCalculatorEarlyBootstrap = window.WdCalculatorEarlyBootstrap || {};

    (function (ns) {
        var unsavedExitGuard = null;
        var layoutSyncWiring = null;
        var getEstimates = function () {
            return [];
        };
        var windowRef = window;
        var requestLayoutSync = function () {};

        function configure(options) {
            var opts = options || {};
            if (opts.unsavedExitGuard) {
                unsavedExitGuard = opts.unsavedExitGuard;
            }
            if (opts.layoutSyncWiring) {
                layoutSyncWiring = opts.layoutSyncWiring;
            }
            if (typeof opts.getEstimates === "function") {
                getEstimates = opts.getEstimates;
            }
            if (opts.windowRef) {
                windowRef = opts.windowRef;
            }
            if (typeof opts.requestLayoutSync === "function") {
                requestLayoutSync = opts.requestLayoutSync;
            }
        }

        function initEarlyBootstrap() {
            if (unsavedExitGuard && typeof unsavedExitGuard.configure === "function") {
                unsavedExitGuard.configure({
                    getEstimates: getEstimates,
                    windowRef: windowRef,
                });
            }
            if (unsavedExitGuard && typeof unsavedExitGuard.initUnsavedExitGuard === "function") {
                unsavedExitGuard.initUnsavedExitGuard();
            }

            if (layoutSyncWiring && typeof layoutSyncWiring.configure === "function") {
                layoutSyncWiring.configure({
                    windowRef: windowRef,
                    requestLayoutSync: requestLayoutSync,
                });
            }
            if (layoutSyncWiring && typeof layoutSyncWiring.initLayoutSyncWiring === "function") {
                layoutSyncWiring.initLayoutSyncWiring();
            }
        }

        ns.configure = configure;
        ns.initEarlyBootstrap = initEarlyBootstrap;
    })(WdCalculatorEarlyBootstrap);

    window.WdCalculatorEarlyBootstrap = WdCalculatorEarlyBootstrap;
})();


/* ---- included: sidebar-bootstrap.js ---- */
(function () {
    var WdCalculatorSidebarBootstrap = window.WdCalculatorSidebarBootstrap || {};

    (function (ns) {
        var initSidebarEstimates = function () {};
        var loadEstimateToForm = function () {};
        var formatNumber =
            typeof window !== "undefined" && typeof window.formatNumber === "function"
                ? window.formatNumber
                : function (num) {
                      return Math.round(Number(num) || 0).toLocaleString("ko-KR");
                  };

        function configure(options) {
            var opts = options || {};
            if (typeof opts.initSidebarEstimates === "function") {
                initSidebarEstimates = opts.initSidebarEstimates;
            }
            if (typeof opts.loadEstimateToForm === "function") {
                loadEstimateToForm = opts.loadEstimateToForm;
            }
            if (typeof opts.formatNumber === "function") {
                formatNumber = opts.formatNumber;
            }
        }

        /**
         * Builds sidebar estimates API ({ loadSidebarEstimates, deleteEstimate }).
         * If the configured init returns a non-object (legacy noop), fall back to
         * window.initWdCalculatorSidebarEstimates from estimate-lifecycle.js.
         */
        function initSidebarBootstrap() {
            var options = {
                loadEstimateToForm: loadEstimateToForm,
                formatNumber: formatNumber,
            };
            var api = null;
            if (typeof initSidebarEstimates === "function") {
                api = initSidebarEstimates(options);
            }
            if (api && typeof api.loadSidebarEstimates === "function") {
                return api;
            }
            var fallback =
                typeof window !== "undefined" && typeof window.initWdCalculatorSidebarEstimates === "function"
                    ? window.initWdCalculatorSidebarEstimates
                    : null;
            if (fallback) {
                if (typeof console !== "undefined" && typeof console.warn === "function") {
                    console.warn(
                        "WDCalculator: sidebar init returned no API; using window.initWdCalculatorSidebarEstimates fallback."
                    );
                }
                return fallback(options);
            }
            throw new Error(
                "WDCalculator: sidebar estimates unavailable. Load estimate-lifecycle.js and ensure initWdCalculatorSidebarEstimates returns { loadSidebarEstimates }."
            );
        }

        ns.configure = configure;
        ns.initSidebarBootstrap = initSidebarBootstrap;
    })(WdCalculatorSidebarBootstrap);

    window.WdCalculatorSidebarBootstrap = WdCalculatorSidebarBootstrap;
})();


/* ---- included: primary-ui-bootstrap.js ---- */
(function () {
    var WdCalculatorPrimaryUiBootstrap = window.WdCalculatorPrimaryUiBootstrap || {};

    (function (ns) {
        var baseComponentsUi = null;
        var couponDisplayHelpers = null;
        var additionalOptionsUi = null;
        var getProducts = null;
        var getCalculateEstimate = null;
        var defaultCouponValue = 0;
        var getCategories = null;

        function configure(options) {
            var opts = options || {};
            if (opts.baseComponentsUi) {
                baseComponentsUi = opts.baseComponentsUi;
            }
            if (opts.couponDisplayHelpers) {
                couponDisplayHelpers = opts.couponDisplayHelpers;
            }
            if (opts.additionalOptionsUi) {
                additionalOptionsUi = opts.additionalOptionsUi;
            }
            if (typeof opts.getProducts === "function") {
                getProducts = opts.getProducts;
            }
            if (typeof opts.getCalculateEstimate === "function") {
                getCalculateEstimate = opts.getCalculateEstimate;
            }
            if (Object.prototype.hasOwnProperty.call(opts, "defaultCouponValue")) {
                defaultCouponValue = opts.defaultCouponValue;
            }
            if (typeof opts.getCategories === "function") {
                getCategories = opts.getCategories;
            }
        }

        function requireMethod(moduleObj, methodName, label) {
            if (!moduleObj || typeof moduleObj[methodName] !== "function") {
                throw new Error(label);
            }
            return moduleObj[methodName].bind(moduleObj);
        }

        function requireFunction(moduleObj, exportName, label) {
            if (!moduleObj || typeof moduleObj[exportName] !== "function") {
                throw new Error(label);
            }
            return moduleObj[exportName];
        }

        function initPrimaryUiBootstrap() {
            requireMethod(
                baseComponentsUi,
                "configure",
                "WdCalculatorPrimaryUiBootstrap requires baseComponentsUi.configure"
            )({
                getProducts: getProducts,
                getCalculateEstimate: getCalculateEstimate,
            });

            requireMethod(
                couponDisplayHelpers,
                "configure",
                "WdCalculatorPrimaryUiBootstrap requires couponDisplayHelpers.configure"
            )({
                defaultCouponValue: defaultCouponValue,
            });

            requireMethod(
                additionalOptionsUi,
                "configure",
                "WdCalculatorPrimaryUiBootstrap requires additionalOptionsUi.configure"
            )({
                getCategories: getCategories,
                getCalculateEstimate: getCalculateEstimate,
            });

            return {
                getProductsOptionsHtml: requireFunction(
                    baseComponentsUi,
                    "getProductsOptionsHtml",
                    "WdCalculatorPrimaryUiBootstrap requires baseComponentsUi.getProductsOptionsHtml"
                ),
                renderBaseComponentRow: requireFunction(
                    baseComponentsUi,
                    "renderBaseComponentRow",
                    "WdCalculatorPrimaryUiBootstrap requires baseComponentsUi.renderBaseComponentRow"
                ),
                ensureBaseComponentsUI: requireFunction(
                    baseComponentsUi,
                    "ensureBaseComponentsUI",
                    "WdCalculatorPrimaryUiBootstrap requires baseComponentsUi.ensureBaseComponentsUI"
                ),
                readBaseComponentsFromUI: requireFunction(
                    baseComponentsUi,
                    "readBaseComponentsFromUI",
                    "WdCalculatorPrimaryUiBootstrap requires baseComponentsUi.readBaseComponentsFromUI"
                ),
                updateBaseProductSelectOptions: requireFunction(
                    baseComponentsUi,
                    "updateBaseProductSelectOptions",
                    "WdCalculatorPrimaryUiBootstrap requires baseComponentsUi.updateBaseProductSelectOptions"
                ),
                initBaseComponentsLiveInteractions: requireFunction(
                    baseComponentsUi,
                    "initBaseComponentsLiveInteractions",
                    "WdCalculatorPrimaryUiBootstrap requires baseComponentsUi.initBaseComponentsLiveInteractions"
                ),
                getCouponValue: requireFunction(
                    couponDisplayHelpers,
                    "getCouponValue",
                    "WdCalculatorPrimaryUiBootstrap requires couponDisplayHelpers.getCouponValue"
                ),
                applyFinalPriceStyle: requireFunction(
                    couponDisplayHelpers,
                    "applyFinalPriceStyle",
                    "WdCalculatorPrimaryUiBootstrap requires couponDisplayHelpers.applyFinalPriceStyle"
                ),
                applyCouponDiscountStyle: requireFunction(
                    couponDisplayHelpers,
                    "applyCouponDiscountStyle",
                    "WdCalculatorPrimaryUiBootstrap requires couponDisplayHelpers.applyCouponDiscountStyle"
                ),
                appendAdditionalOptionRow: requireFunction(
                    additionalOptionsUi,
                    "appendAdditionalOptionRow",
                    "WdCalculatorPrimaryUiBootstrap requires additionalOptionsUi.appendAdditionalOptionRow"
                ),
                loadAdditionalOptionRows: requireFunction(
                    additionalOptionsUi,
                    "loadAdditionalOptionRows",
                    "WdCalculatorPrimaryUiBootstrap requires additionalOptionsUi.loadAdditionalOptionRows"
                ),
                readAdditionalOptionRowsFromUI: requireFunction(
                    additionalOptionsUi,
                    "readAdditionalOptionRowsFromUI",
                    "WdCalculatorPrimaryUiBootstrap requires additionalOptionsUi.readAdditionalOptionRowsFromUI"
                ),
            };
        }

        ns.configure = configure;
        ns.initPrimaryUiBootstrap = initPrimaryUiBootstrap;
    })(WdCalculatorPrimaryUiBootstrap);

    window.WdCalculatorPrimaryUiBootstrap = WdCalculatorPrimaryUiBootstrap;
})();


/* ---- included: catalog-buttons-bootstrap.js ---- */
(function () {
    var WdCalculatorCatalogButtonsBootstrap =
        window.WdCalculatorCatalogButtonsBootstrap || {};

    (function (ns) {
        var addOptionButton = null;
        var calculateButton = null;
        var productCatalogUi = null;
        var documentRef = null;
        var appendAdditionalOptionRow = null;
        var calculateEstimate = null;
        var getProducts = null;
        var setProducts = null;
        var getCalculateEstimate = null;
        var updateBaseProductSelectOptions = null;
        var ensureBaseComponentsUI = null;

        function configure(options) {
            var opts = options || {};
            if (opts.addOptionButton) {
                addOptionButton = opts.addOptionButton;
            }
            if (opts.calculateButton) {
                calculateButton = opts.calculateButton;
            }
            if (opts.productCatalogUi) {
                productCatalogUi = opts.productCatalogUi;
            }
            if (opts.documentRef) {
                documentRef = opts.documentRef;
            }
            if (typeof opts.appendAdditionalOptionRow === "function") {
                appendAdditionalOptionRow = opts.appendAdditionalOptionRow;
            }
            if (typeof opts.calculateEstimate === "function") {
                calculateEstimate = opts.calculateEstimate;
            }
            if (typeof opts.getProducts === "function") {
                getProducts = opts.getProducts;
            }
            if (typeof opts.setProducts === "function") {
                setProducts = opts.setProducts;
            }
            if (typeof opts.getCalculateEstimate === "function") {
                getCalculateEstimate = opts.getCalculateEstimate;
            }
            if (typeof opts.updateBaseProductSelectOptions === "function") {
                updateBaseProductSelectOptions = opts.updateBaseProductSelectOptions;
            }
            if (typeof opts.ensureBaseComponentsUI === "function") {
                ensureBaseComponentsUI = opts.ensureBaseComponentsUI;
            }
        }

        function requireMethod(moduleObj, methodName, label) {
            if (!moduleObj || typeof moduleObj[methodName] !== "function") {
                throw new Error(label);
            }
            return moduleObj[methodName].bind(moduleObj);
        }

        function initCatalogButtonsBootstrap() {
            requireMethod(
                addOptionButton,
                "configure",
                "WdCalculatorCatalogButtonsBootstrap requires addOptionButton.configure"
            )({
                documentRef: documentRef,
                appendAdditionalOptionRow: appendAdditionalOptionRow,
            });

            requireMethod(
                calculateButton,
                "configure",
                "WdCalculatorCatalogButtonsBootstrap requires calculateButton.configure"
            )({
                documentRef: documentRef,
                calculateEstimate: calculateEstimate,
            });

            requireMethod(
                productCatalogUi,
                "configure",
                "WdCalculatorCatalogButtonsBootstrap requires productCatalogUi.configure"
            )({
                getProducts: getProducts,
                setProducts: setProducts,
                getCalculateEstimate: getCalculateEstimate,
                updateBaseProductSelectOptions: updateBaseProductSelectOptions,
                ensureBaseComponentsUI: ensureBaseComponentsUI,
            });
        }

        ns.configure = configure;
        ns.initCatalogButtonsBootstrap = initCatalogButtonsBootstrap;
    })(WdCalculatorCatalogButtonsBootstrap);

    window.WdCalculatorCatalogButtonsBootstrap = WdCalculatorCatalogButtonsBootstrap;
})();


/* ---- included: catalog-buttons-host-bootstrap.js ---- */
(function () {
    var WdCalculatorCatalogButtonsHostBootstrap =
        window.WdCalculatorCatalogButtonsHostBootstrap || {};

    (function (ns) {
        var catalogButtonsBootstrap = null;
        var addOptionButton = null;
        var calculateButton = null;
        var productCatalogUi = null;
        var documentRef = null;
        var appendAdditionalOptionRow = null;
        var calculateEstimate = null;
        var getProducts = null;
        var setProducts = null;
        var getCalculateEstimate = null;
        var updateBaseProductSelectOptions = null;
        var ensureBaseComponentsUI = null;

        function configure(options) {
            var opts = options || {};
            if (opts.catalogButtonsBootstrap) {
                catalogButtonsBootstrap = opts.catalogButtonsBootstrap;
            }
            if (opts.addOptionButton) {
                addOptionButton = opts.addOptionButton;
            }
            if (opts.calculateButton) {
                calculateButton = opts.calculateButton;
            }
            if (opts.productCatalogUi) {
                productCatalogUi = opts.productCatalogUi;
            }
            if (opts.documentRef) {
                documentRef = opts.documentRef;
            }
            if (typeof opts.appendAdditionalOptionRow === "function") {
                appendAdditionalOptionRow = opts.appendAdditionalOptionRow;
            }
            if (typeof opts.calculateEstimate === "function") {
                calculateEstimate = opts.calculateEstimate;
            }
            if (typeof opts.getProducts === "function") {
                getProducts = opts.getProducts;
            }
            if (typeof opts.setProducts === "function") {
                setProducts = opts.setProducts;
            }
            if (typeof opts.getCalculateEstimate === "function") {
                getCalculateEstimate = opts.getCalculateEstimate;
            }
            if (typeof opts.updateBaseProductSelectOptions === "function") {
                updateBaseProductSelectOptions = opts.updateBaseProductSelectOptions;
            }
            if (typeof opts.ensureBaseComponentsUI === "function") {
                ensureBaseComponentsUI = opts.ensureBaseComponentsUI;
            }
        }

        function requireMethod(moduleObj, methodName, label) {
            if (!moduleObj || typeof moduleObj[methodName] !== "function") {
                throw new Error(label);
            }
            return moduleObj[methodName].bind(moduleObj);
        }

        function initCatalogButtonsHostBootstrap() {
            requireMethod(
                catalogButtonsBootstrap,
                "configure",
                "WdCalculatorCatalogButtonsHostBootstrap requires catalogButtonsBootstrap.configure"
            )({
                addOptionButton: addOptionButton,
                calculateButton: calculateButton,
                productCatalogUi: productCatalogUi,
                documentRef: documentRef,
                appendAdditionalOptionRow: appendAdditionalOptionRow,
                calculateEstimate: calculateEstimate,
                getProducts: getProducts,
                setProducts: setProducts,
                getCalculateEstimate: getCalculateEstimate,
                updateBaseProductSelectOptions: updateBaseProductSelectOptions,
                ensureBaseComponentsUI: ensureBaseComponentsUI,
            });

            return requireMethod(
                catalogButtonsBootstrap,
                "initCatalogButtonsBootstrap",
                "WdCalculatorCatalogButtonsHostBootstrap requires catalogButtonsBootstrap.initCatalogButtonsBootstrap"
            )();
        }

        ns.configure = configure;
        ns.initCatalogButtonsHostBootstrap = initCatalogButtonsHostBootstrap;
    })(WdCalculatorCatalogButtonsHostBootstrap);

    window.WdCalculatorCatalogButtonsHostBootstrap =
        WdCalculatorCatalogButtonsHostBootstrap;
})();


/* ---- included: coupon-search-render-bootstrap.js ---- */
(function () {
    var WdCalculatorCouponSearchRenderBootstrap =
        window.WdCalculatorCouponSearchRenderBootstrap || {};

    (function (ns) {
        var couponShippingWiring = null;
        var searchResultsLoad = null;
        var renderEstimatesList = null;
        var defaultCouponValue = 0;
        var getEstimates = null;
        var calculateEstimate = null;
        var calculateTotalEstimates = null;
        var getCouponValue = null;
        var loadEstimateToForm = null;
        var formatNumber = null;
        var escapeHtml = null;
        var formatNotesText = null;
        var onRenderComplete = null;
        var getProducts = function () {
            return [];
        };

        function configure(options) {
            var opts = options || {};
            if (opts.couponShippingWiring) {
                couponShippingWiring = opts.couponShippingWiring;
            }
            if (opts.searchResultsLoad) {
                searchResultsLoad = opts.searchResultsLoad;
            }
            if (opts.renderEstimatesList) {
                renderEstimatesList = opts.renderEstimatesList;
            }
            if (Object.prototype.hasOwnProperty.call(opts, "defaultCouponValue")) {
                defaultCouponValue = opts.defaultCouponValue;
            }
            if (typeof opts.getEstimates === "function") {
                getEstimates = opts.getEstimates;
            }
            if (typeof opts.calculateEstimate === "function") {
                calculateEstimate = opts.calculateEstimate;
            }
            if (typeof opts.calculateTotalEstimates === "function") {
                calculateTotalEstimates = opts.calculateTotalEstimates;
            }
            if (typeof opts.getCouponValue === "function") {
                getCouponValue = opts.getCouponValue;
            }
            if (typeof opts.loadEstimateToForm === "function") {
                loadEstimateToForm = opts.loadEstimateToForm;
            }
            if (typeof opts.formatNumber === "function") {
                formatNumber = opts.formatNumber;
            }
            if (typeof opts.escapeHtml === "function") {
                escapeHtml = opts.escapeHtml;
            }
            if (typeof opts.formatNotesText === "function") {
                formatNotesText = opts.formatNotesText;
            }
            if (typeof opts.onRenderComplete === "function") {
                onRenderComplete = opts.onRenderComplete;
            }
            if (typeof opts.getProducts === "function") {
                getProducts = opts.getProducts;
            }
        }

        function requireMethod(moduleObj, methodName, label) {
            if (!moduleObj || typeof moduleObj[methodName] !== "function") {
                throw new Error(label);
            }
            return moduleObj[methodName].bind(moduleObj);
        }

        function initCouponSearchRenderBootstrap() {
            requireMethod(
                couponShippingWiring,
                "configure",
                "WdCalculatorCouponSearchRenderBootstrap requires couponShippingWiring.configure"
            )({
                defaultCouponValue: defaultCouponValue,
                getEstimates: getEstimates,
                calculateEstimate: calculateEstimate,
                calculateTotalEstimates: calculateTotalEstimates,
                getCouponValue: getCouponValue,
            });

            requireMethod(
                searchResultsLoad,
                "configure",
                "WdCalculatorCouponSearchRenderBootstrap requires searchResultsLoad.configure"
            )({
                loadEstimateToForm: loadEstimateToForm,
                formatNumber: formatNumber,
            });

            requireMethod(
                renderEstimatesList,
                "configure",
                "WdCalculatorCouponSearchRenderBootstrap requires renderEstimatesList.configure"
            )({
                getEstimates: getEstimates,
                formatNumber: formatNumber,
                escapeHtml: escapeHtml,
                formatNotesText: formatNotesText,
                onRenderComplete: onRenderComplete,
                getProducts: getProducts,
            });
        }

        ns.configure = configure;
        ns.initCouponSearchRenderBootstrap = initCouponSearchRenderBootstrap;
    })(WdCalculatorCouponSearchRenderBootstrap);

    window.WdCalculatorCouponSearchRenderBootstrap =
        WdCalculatorCouponSearchRenderBootstrap;
})();


/* ---- included: coupon-search-render-host-bootstrap.js ---- */
(function () {
    var WdCalculatorCouponSearchRenderHostBootstrap =
        window.WdCalculatorCouponSearchRenderHostBootstrap || {};

    (function (ns) {
        var couponSearchRenderBootstrap = null;
        var couponShippingWiring = null;
        var searchResultsLoad = null;
        var renderEstimatesList = null;
        var defaultCouponValue = 0;
        var getEstimates = null;
        var calculateEstimate = null;
        var calculateTotalEstimates = null;
        var getCouponValue = null;
        var loadEstimateToForm = null;
        var formatNumber = null;
        var escapeHtml = null;
        var formatNotesText = null;
        var onRenderComplete = null;
        var getProducts = null;

        function configure(options) {
            var opts = options || {};
            if (opts.couponSearchRenderBootstrap) {
                couponSearchRenderBootstrap = opts.couponSearchRenderBootstrap;
            }
            if (opts.couponShippingWiring) {
                couponShippingWiring = opts.couponShippingWiring;
            }
            if (opts.searchResultsLoad) {
                searchResultsLoad = opts.searchResultsLoad;
            }
            if (opts.renderEstimatesList) {
                renderEstimatesList = opts.renderEstimatesList;
            }
            if (Object.prototype.hasOwnProperty.call(opts, "defaultCouponValue")) {
                defaultCouponValue = opts.defaultCouponValue;
            }
            if (typeof opts.getEstimates === "function") {
                getEstimates = opts.getEstimates;
            }
            if (typeof opts.calculateEstimate === "function") {
                calculateEstimate = opts.calculateEstimate;
            }
            if (typeof opts.calculateTotalEstimates === "function") {
                calculateTotalEstimates = opts.calculateTotalEstimates;
            }
            if (typeof opts.getCouponValue === "function") {
                getCouponValue = opts.getCouponValue;
            }
            if (typeof opts.loadEstimateToForm === "function") {
                loadEstimateToForm = opts.loadEstimateToForm;
            }
            if (typeof opts.formatNumber === "function") {
                formatNumber = opts.formatNumber;
            }
            if (typeof opts.escapeHtml === "function") {
                escapeHtml = opts.escapeHtml;
            }
            if (typeof opts.formatNotesText === "function") {
                formatNotesText = opts.formatNotesText;
            }
            if (typeof opts.onRenderComplete === "function") {
                onRenderComplete = opts.onRenderComplete;
            }
            if (typeof opts.getProducts === "function") {
                getProducts = opts.getProducts;
            }
        }

        function requireMethod(moduleObj, methodName, label) {
            if (!moduleObj || typeof moduleObj[methodName] !== "function") {
                throw new Error(label);
            }
            return moduleObj[methodName].bind(moduleObj);
        }

        function initCouponSearchRenderHostBootstrap() {
            requireMethod(
                couponSearchRenderBootstrap,
                "configure",
                "WdCalculatorCouponSearchRenderHostBootstrap requires couponSearchRenderBootstrap.configure"
            )({
                couponShippingWiring: couponShippingWiring,
                searchResultsLoad: searchResultsLoad,
                renderEstimatesList: renderEstimatesList,
                defaultCouponValue: defaultCouponValue,
                getEstimates: getEstimates,
                calculateEstimate: calculateEstimate,
                calculateTotalEstimates: calculateTotalEstimates,
                getCouponValue: getCouponValue,
                loadEstimateToForm: loadEstimateToForm,
                formatNumber: formatNumber,
                escapeHtml: escapeHtml,
                formatNotesText: formatNotesText,
                onRenderComplete: onRenderComplete,
                getProducts: getProducts,
            });

            return requireMethod(
                couponSearchRenderBootstrap,
                "initCouponSearchRenderBootstrap",
                "WdCalculatorCouponSearchRenderHostBootstrap requires couponSearchRenderBootstrap.initCouponSearchRenderBootstrap"
            )();
        }

        ns.configure = configure;
        ns.initCouponSearchRenderHostBootstrap = initCouponSearchRenderHostBootstrap;
    })(WdCalculatorCouponSearchRenderHostBootstrap);

    window.WdCalculatorCouponSearchRenderHostBootstrap =
        WdCalculatorCouponSearchRenderHostBootstrap;
})();


/* ---- included: late-bootstrap.js ---- */
(function () {
    var WdCalculatorLateBootstrap = window.WdCalculatorLateBootstrap || {};

    (function (ns) {
        var sidebarBootstrap = null;
        var refreshAfterSave = null;
        var urlBootstrap = null;
        var initSidebarEstimates = function () {};
        var loadEstimateToForm = function () {};
        var formatNumber = function (num) {
            return Math.round(Number(num) || 0).toLocaleString("ko-KR");
        };
        var setEstimates = function () {};
        var resetInputFormKeepCustomerName = function () {};
        var resetInputFormToNewEstimate = function () {};
        var renderEstimatesList = function () {};
        var getProducts = function () {
            return [];
        };
        var documentRef = document;
        var consoleRef = window.console || console;
        var setTimeoutImpl = window.setTimeout ? window.setTimeout.bind(window) : function (fn) {
            fn();
            return 1;
        };

        function configure(options) {
            var opts = options || {};
            if (opts.sidebarBootstrap) {
                sidebarBootstrap = opts.sidebarBootstrap;
            }
            if (opts.refreshAfterSave) {
                refreshAfterSave = opts.refreshAfterSave;
            }
            if (opts.urlBootstrap) {
                urlBootstrap = opts.urlBootstrap;
            }
            if (typeof opts.initSidebarEstimates === "function") {
                initSidebarEstimates = opts.initSidebarEstimates;
            }
            if (typeof opts.loadEstimateToForm === "function") {
                loadEstimateToForm = opts.loadEstimateToForm;
            }
            if (typeof opts.formatNumber === "function") {
                formatNumber = opts.formatNumber;
            }
            if (typeof opts.setEstimates === "function") {
                setEstimates = opts.setEstimates;
            }
            if (typeof opts.resetInputFormKeepCustomerName === "function") {
                resetInputFormKeepCustomerName = opts.resetInputFormKeepCustomerName;
            }
            if (typeof opts.resetInputFormToNewEstimate === "function") {
                resetInputFormToNewEstimate = opts.resetInputFormToNewEstimate;
            }
            if (typeof opts.renderEstimatesList === "function") {
                renderEstimatesList = opts.renderEstimatesList;
            }
            if (typeof opts.getProducts === "function") {
                getProducts = opts.getProducts;
            }
            if (opts.documentRef) {
                documentRef = opts.documentRef;
            }
            if (opts.consoleRef) {
                consoleRef = opts.consoleRef;
            }
            if (typeof opts.setTimeoutImpl === "function") {
                setTimeoutImpl = opts.setTimeoutImpl;
            }
        }

        function initLateBootstrap() {
            if (sidebarBootstrap && typeof sidebarBootstrap.configure === "function") {
                sidebarBootstrap.configure({
                    initSidebarEstimates: initSidebarEstimates,
                    loadEstimateToForm: loadEstimateToForm,
                    formatNumber: formatNumber,
                });
            }
            if (!sidebarBootstrap || typeof sidebarBootstrap.initSidebarBootstrap !== "function") {
                throw new Error("WdCalculatorLateBootstrap requires sidebarBootstrap.initSidebarBootstrap");
            }

            var sidebarEstimatesApi = sidebarBootstrap.initSidebarBootstrap();
            if (!sidebarEstimatesApi || typeof sidebarEstimatesApi.loadSidebarEstimates !== "function") {
                throw new Error(
                    "WDCalculator: initLateBootstrap expected { loadSidebarEstimates } from sidebarBootstrap.initSidebarBootstrap"
                );
            }
            var loadSidebarEstimates = sidebarEstimatesApi.loadSidebarEstimates;

            if (refreshAfterSave && typeof refreshAfterSave.configure === "function") {
                refreshAfterSave.configure({
                    setEstimates: setEstimates,
                    resetInputFormKeepCustomerName: resetInputFormKeepCustomerName,
                    resetInputFormToNewEstimate: resetInputFormToNewEstimate,
                    renderEstimatesList: renderEstimatesList,
                    loadSidebarEstimates: loadSidebarEstimates,
                    documentRef: documentRef,
                    consoleRef: consoleRef,
                    setTimeoutImpl: setTimeoutImpl,
                });
            }

            if (urlBootstrap && typeof urlBootstrap.configure === "function") {
                urlBootstrap.configure({
                    getProducts: getProducts,
                    loadEstimateToForm: loadEstimateToForm,
                    loadSidebarEstimates: loadSidebarEstimates,
                });
            }
            if (urlBootstrap && typeof urlBootstrap.initUrlBootstrap === "function") {
                urlBootstrap.initUrlBootstrap();
            }

            return sidebarEstimatesApi;
        }

        ns.configure = configure;
        ns.initLateBootstrap = initLateBootstrap;
    })(WdCalculatorLateBootstrap);

    window.WdCalculatorLateBootstrap = WdCalculatorLateBootstrap;
})();


/* ---- included: startup-init.js ---- */
/**
 * WDCalculator startup init shell.
 * Keeps early startup call order outside the host giant script.
 */
var WdCalculatorStartupInit = window.WdCalculatorStartupInit || {};

(function (ns) {
    var categories = [];
    var consoleRef = typeof console !== "undefined" ? console : { warn: function () {} };
    var bindProductSelect = function () {};
    var initBaseComponentsLiveInteractions = function () {};
    var initAddOptionButton = function () {};
    var initCalculateButton = function () {};
    var initSearchResultsLoadBridge = function () {};
    var bindOrderMatchButtons = function () {};
    var initCouponShippingWiring = function () {};

    function configure(options) {
        var opts = options || {};
        if (Object.prototype.hasOwnProperty.call(opts, "categories")) {
            categories = opts.categories;
        }
        if (opts.consoleRef && typeof opts.consoleRef.warn === "function") {
            consoleRef = opts.consoleRef;
        }
        if (typeof opts.bindProductSelect === "function") {
            bindProductSelect = opts.bindProductSelect;
        }
        if (typeof opts.initBaseComponentsLiveInteractions === "function") {
            initBaseComponentsLiveInteractions = opts.initBaseComponentsLiveInteractions;
        }
        if (typeof opts.initAddOptionButton === "function") {
            initAddOptionButton = opts.initAddOptionButton;
        }
        if (typeof opts.initCalculateButton === "function") {
            initCalculateButton = opts.initCalculateButton;
        }
        if (typeof opts.initSearchResultsLoadBridge === "function") {
            initSearchResultsLoadBridge = opts.initSearchResultsLoadBridge;
        }
        if (typeof opts.bindOrderMatchButtons === "function") {
            bindOrderMatchButtons = opts.bindOrderMatchButtons;
        }
        if (typeof opts.initCouponShippingWiring === "function") {
            initCouponShippingWiring = opts.initCouponShippingWiring;
        }
    }

    function warnIfCategoriesEmpty() {
        if (!categories || categories.length === 0) {
            consoleRef.warn("카테고리 데이터가 없습니다. 제품 설정에서 추가 옵션을 등록해주세요.");
        }
    }

    function initStartupInteractions() {
        bindProductSelect();
        initBaseComponentsLiveInteractions();
        initAddOptionButton();
        initCalculateButton();
        initSearchResultsLoadBridge();
        bindOrderMatchButtons();
        initCouponShippingWiring();
        warnIfCategoriesEmpty();
    }

    ns.configure = configure;
    ns.warnIfCategoriesEmpty = warnIfCategoriesEmpty;
    ns.initStartupInteractions = initStartupInteractions;
})(WdCalculatorStartupInit);

window.WdCalculatorStartupInit = WdCalculatorStartupInit;


/* ---- included: terminal-init.js ---- */
/**
 * WDCalculator terminal init shell.
 * Keeps direct terminal bootstrap calls outside the host giant script.
 */
var WdCalculatorTerminalInit = window.WdCalculatorTerminalInit || {};

(function (ns) {
    var loadProducts = function () {};
    var ensureBaseComponentsUI = function () {};

    function configure(options) {
        var opts = options || {};
        if (typeof opts.loadProducts === "function") {
            loadProducts = opts.loadProducts;
        }
        if (typeof opts.ensureBaseComponentsUI === "function") {
            ensureBaseComponentsUI = opts.ensureBaseComponentsUI;
        }
    }

    function loadInitialProducts() {
        return loadProducts();
    }

    function renderInitialBaseComponentsUi() {
        return ensureBaseComponentsUI();
    }

    ns.configure = configure;
    ns.loadInitialProducts = loadInitialProducts;
    ns.renderInitialBaseComponentsUi = renderInitialBaseComponentsUi;
})(WdCalculatorTerminalInit);

window.WdCalculatorTerminalInit = WdCalculatorTerminalInit;


/* ---- included: totals-startup-terminal-bootstrap.js ---- */
(function () {
    var WdCalculatorTotalsStartupTerminalBootstrap =
        window.WdCalculatorTotalsStartupTerminalBootstrap || {};

    (function (ns) {
        var totalEstimatesDisplay = null;
        var startupInit = null;
        var terminalInit = null;
        var getEstimates = null;
        var getEditingEstimateId = null;
        var getCouponValue = null;
        var resolveAggregateTotals = null;
        var collectNotes = null;
        var formatNumber = null;
        var applyFinalPriceStyle = null;
        var applyCouponDiscountStyle = null;
        var documentRef = null;
        var alertImpl = null;
        var consoleRef = null;
        var categories = null;
        var bindProductSelect = null;
        var initBaseComponentsLiveInteractions = null;
        var initAddOptionButton = null;
        var initCalculateButton = null;
        var initSearchResultsLoadBridge = null;
        var bindOrderMatchButtons = null;
        var initCouponShippingWiring = null;
        var loadProducts = null;
        var ensureBaseComponentsUI = null;

        function configure(options) {
            var opts = options || {};
            if (opts.totalEstimatesDisplay) {
                totalEstimatesDisplay = opts.totalEstimatesDisplay;
            }
            if (opts.startupInit) {
                startupInit = opts.startupInit;
            }
            if (opts.terminalInit) {
                terminalInit = opts.terminalInit;
            }
            if (typeof opts.getEstimates === "function") {
                getEstimates = opts.getEstimates;
            }
            if (typeof opts.getEditingEstimateId === "function") {
                getEditingEstimateId = opts.getEditingEstimateId;
            }
            if (typeof opts.getCouponValue === "function") {
                getCouponValue = opts.getCouponValue;
            }
            if (typeof opts.resolveAggregateTotals === "function") {
                resolveAggregateTotals = opts.resolveAggregateTotals;
            }
            if (typeof opts.collectNotes === "function") {
                collectNotes = opts.collectNotes;
            }
            if (typeof opts.formatNumber === "function") {
                formatNumber = opts.formatNumber;
            }
            if (typeof opts.applyFinalPriceStyle === "function") {
                applyFinalPriceStyle = opts.applyFinalPriceStyle;
            }
            if (typeof opts.applyCouponDiscountStyle === "function") {
                applyCouponDiscountStyle = opts.applyCouponDiscountStyle;
            }
            if (opts.documentRef) {
                documentRef = opts.documentRef;
            }
            if (typeof opts.alertImpl === "function") {
                alertImpl = opts.alertImpl;
            }
            if (opts.consoleRef) {
                consoleRef = opts.consoleRef;
            }
            if (Object.prototype.hasOwnProperty.call(opts, "categories")) {
                categories = opts.categories;
            }
            if (typeof opts.bindProductSelect === "function") {
                bindProductSelect = opts.bindProductSelect;
            }
            if (typeof opts.initBaseComponentsLiveInteractions === "function") {
                initBaseComponentsLiveInteractions = opts.initBaseComponentsLiveInteractions;
            }
            if (typeof opts.initAddOptionButton === "function") {
                initAddOptionButton = opts.initAddOptionButton;
            }
            if (typeof opts.initCalculateButton === "function") {
                initCalculateButton = opts.initCalculateButton;
            }
            if (typeof opts.initSearchResultsLoadBridge === "function") {
                initSearchResultsLoadBridge = opts.initSearchResultsLoadBridge;
            }
            if (typeof opts.bindOrderMatchButtons === "function") {
                bindOrderMatchButtons = opts.bindOrderMatchButtons;
            }
            if (typeof opts.initCouponShippingWiring === "function") {
                initCouponShippingWiring = opts.initCouponShippingWiring;
            }
            if (typeof opts.loadProducts === "function") {
                loadProducts = opts.loadProducts;
            }
            if (typeof opts.ensureBaseComponentsUI === "function") {
                ensureBaseComponentsUI = opts.ensureBaseComponentsUI;
            }
        }

        function requireMethod(moduleObj, methodName, label) {
            if (!moduleObj || typeof moduleObj[methodName] !== "function") {
                throw new Error(label);
            }
            return moduleObj[methodName].bind(moduleObj);
        }

        function initTotalsStartupTerminalBootstrap() {
            requireMethod(
                totalEstimatesDisplay,
                "configure",
                "WdCalculatorTotalsStartupTerminalBootstrap requires totalEstimatesDisplay.configure"
            )({
                getEstimates: getEstimates,
                getEditingEstimateId: getEditingEstimateId,
                getCouponValue: getCouponValue,
                resolveAggregateTotals: resolveAggregateTotals,
                collectNotes: collectNotes,
                formatNumber: formatNumber,
                applyFinalPriceStyle: applyFinalPriceStyle,
                applyCouponDiscountStyle: applyCouponDiscountStyle,
                documentRef: documentRef,
                alertImpl: alertImpl,
                consoleRef: consoleRef,
            });

            requireMethod(
                startupInit,
                "configure",
                "WdCalculatorTotalsStartupTerminalBootstrap requires startupInit.configure"
            )({
                categories: categories,
                consoleRef: consoleRef,
                bindProductSelect: bindProductSelect,
                initBaseComponentsLiveInteractions: initBaseComponentsLiveInteractions,
                initAddOptionButton: initAddOptionButton,
                initCalculateButton: initCalculateButton,
                initSearchResultsLoadBridge: initSearchResultsLoadBridge,
                bindOrderMatchButtons: bindOrderMatchButtons,
                initCouponShippingWiring: initCouponShippingWiring,
            });

            requireMethod(
                terminalInit,
                "configure",
                "WdCalculatorTotalsStartupTerminalBootstrap requires terminalInit.configure"
            )({
                loadProducts: loadProducts,
                ensureBaseComponentsUI: ensureBaseComponentsUI,
            });

            requireMethod(
                startupInit,
                "initStartupInteractions",
                "WdCalculatorTotalsStartupTerminalBootstrap requires startupInit.initStartupInteractions"
            )();
        }

        ns.configure = configure;
        ns.initTotalsStartupTerminalBootstrap = initTotalsStartupTerminalBootstrap;
    })(WdCalculatorTotalsStartupTerminalBootstrap);

    window.WdCalculatorTotalsStartupTerminalBootstrap =
        WdCalculatorTotalsStartupTerminalBootstrap;
})();


/* ---- included: totals-startup-terminal-host-bootstrap.js ---- */
(function () {
    var WdCalculatorTotalsStartupTerminalHostBootstrap =
        window.WdCalculatorTotalsStartupTerminalHostBootstrap || {};

    (function (ns) {
        var totalsStartupTerminalBootstrap = null;
        var totalEstimatesDisplay = null;
        var startupInit = null;
        var terminalInit = null;
        var getEstimates = null;
        var getEditingEstimateId = null;
        var getCouponValue = null;
        var resolveAggregateTotals = null;
        var collectNotes = null;
        var formatNumber = null;
        var applyFinalPriceStyle = null;
        var applyCouponDiscountStyle = null;
        var documentRef = null;
        var alertImpl = null;
        var consoleRef = null;
        var categories = null;
        var bindProductSelect = null;
        var initBaseComponentsLiveInteractions = null;
        var initAddOptionButton = null;
        var initCalculateButton = null;
        var initSearchResultsLoadBridge = null;
        var bindOrderMatchButtons = null;
        var initCouponShippingWiring = null;
        var loadProducts = null;
        var ensureBaseComponentsUI = null;

        function configure(options) {
            var opts = options || {};
            if (opts.totalsStartupTerminalBootstrap) {
                totalsStartupTerminalBootstrap = opts.totalsStartupTerminalBootstrap;
            }
            if (opts.totalEstimatesDisplay) {
                totalEstimatesDisplay = opts.totalEstimatesDisplay;
            }
            if (opts.startupInit) {
                startupInit = opts.startupInit;
            }
            if (opts.terminalInit) {
                terminalInit = opts.terminalInit;
            }
            if (typeof opts.getEstimates === "function") {
                getEstimates = opts.getEstimates;
            }
            if (typeof opts.getEditingEstimateId === "function") {
                getEditingEstimateId = opts.getEditingEstimateId;
            }
            if (typeof opts.getCouponValue === "function") {
                getCouponValue = opts.getCouponValue;
            }
            if (typeof opts.resolveAggregateTotals === "function") {
                resolveAggregateTotals = opts.resolveAggregateTotals;
            }
            if (typeof opts.collectNotes === "function") {
                collectNotes = opts.collectNotes;
            }
            if (typeof opts.formatNumber === "function") {
                formatNumber = opts.formatNumber;
            }
            if (typeof opts.applyFinalPriceStyle === "function") {
                applyFinalPriceStyle = opts.applyFinalPriceStyle;
            }
            if (typeof opts.applyCouponDiscountStyle === "function") {
                applyCouponDiscountStyle = opts.applyCouponDiscountStyle;
            }
            if (opts.documentRef) {
                documentRef = opts.documentRef;
            }
            if (typeof opts.alertImpl === "function") {
                alertImpl = opts.alertImpl;
            }
            if (opts.consoleRef) {
                consoleRef = opts.consoleRef;
            }
            if (Object.prototype.hasOwnProperty.call(opts, "categories")) {
                categories = opts.categories;
            }
            if (typeof opts.bindProductSelect === "function") {
                bindProductSelect = opts.bindProductSelect;
            }
            if (typeof opts.initBaseComponentsLiveInteractions === "function") {
                initBaseComponentsLiveInteractions = opts.initBaseComponentsLiveInteractions;
            }
            if (typeof opts.initAddOptionButton === "function") {
                initAddOptionButton = opts.initAddOptionButton;
            }
            if (typeof opts.initCalculateButton === "function") {
                initCalculateButton = opts.initCalculateButton;
            }
            if (typeof opts.initSearchResultsLoadBridge === "function") {
                initSearchResultsLoadBridge = opts.initSearchResultsLoadBridge;
            }
            if (typeof opts.bindOrderMatchButtons === "function") {
                bindOrderMatchButtons = opts.bindOrderMatchButtons;
            }
            if (typeof opts.initCouponShippingWiring === "function") {
                initCouponShippingWiring = opts.initCouponShippingWiring;
            }
            if (typeof opts.loadProducts === "function") {
                loadProducts = opts.loadProducts;
            }
            if (typeof opts.ensureBaseComponentsUI === "function") {
                ensureBaseComponentsUI = opts.ensureBaseComponentsUI;
            }
        }

        function requireMethod(moduleObj, methodName, label) {
            if (!moduleObj || typeof moduleObj[methodName] !== "function") {
                throw new Error(label);
            }
            return moduleObj[methodName].bind(moduleObj);
        }

        function initTotalsStartupTerminalHostBootstrap() {
            requireMethod(
                totalsStartupTerminalBootstrap,
                "configure",
                "WdCalculatorTotalsStartupTerminalHostBootstrap requires totalsStartupTerminalBootstrap.configure"
            )({
                totalEstimatesDisplay: totalEstimatesDisplay,
                startupInit: startupInit,
                terminalInit: terminalInit,
                getEstimates: getEstimates,
                getEditingEstimateId: getEditingEstimateId,
                getCouponValue: getCouponValue,
                resolveAggregateTotals: resolveAggregateTotals,
                collectNotes: collectNotes,
                formatNumber: formatNumber,
                applyFinalPriceStyle: applyFinalPriceStyle,
                applyCouponDiscountStyle: applyCouponDiscountStyle,
                documentRef: documentRef,
                alertImpl: alertImpl,
                consoleRef: consoleRef,
                categories: categories,
                bindProductSelect: bindProductSelect,
                initBaseComponentsLiveInteractions: initBaseComponentsLiveInteractions,
                initAddOptionButton: initAddOptionButton,
                initCalculateButton: initCalculateButton,
                initSearchResultsLoadBridge: initSearchResultsLoadBridge,
                bindOrderMatchButtons: bindOrderMatchButtons,
                initCouponShippingWiring: initCouponShippingWiring,
                loadProducts: loadProducts,
                ensureBaseComponentsUI: ensureBaseComponentsUI,
            });

            return requireMethod(
                totalsStartupTerminalBootstrap,
                "initTotalsStartupTerminalBootstrap",
                "WdCalculatorTotalsStartupTerminalHostBootstrap requires totalsStartupTerminalBootstrap.initTotalsStartupTerminalBootstrap"
            )();
        }

        ns.configure = configure;
        ns.initTotalsStartupTerminalHostBootstrap = initTotalsStartupTerminalHostBootstrap;
    })(WdCalculatorTotalsStartupTerminalHostBootstrap);

    window.WdCalculatorTotalsStartupTerminalHostBootstrap =
        WdCalculatorTotalsStartupTerminalHostBootstrap;
})();


/* ---- included: notes-ui-bootstrap.js ---- */
(function () {
    var WdCalculatorNotesUiBootstrap = window.WdCalculatorNotesUiBootstrap || {};

    (function (ns) {
        var notesUi = null;

        function configure(options) {
            var opts = options || {};
            if (opts.notesUi) {
                notesUi = opts.notesUi;
            }
        }

        function requireMethod(moduleObj, methodName, label) {
            if (!moduleObj || typeof moduleObj[methodName] !== "function") {
                throw new Error(label);
            }
            return moduleObj[methodName].bind(moduleObj);
        }

        function initNotesUiBootstrap() {
            return requireMethod(
                notesUi,
                "initNotesUi",
                "WdCalculatorNotesUiBootstrap requires notesUi.initNotesUi"
            )();
        }

        ns.configure = configure;
        ns.initNotesUiBootstrap = initNotesUiBootstrap;
    })(WdCalculatorNotesUiBootstrap);

    window.WdCalculatorNotesUiBootstrap = WdCalculatorNotesUiBootstrap;
})();


/* ---- included: notes-ui-host-bootstrap.js ---- */
(function () {
    var WdCalculatorNotesUiHostBootstrap =
        window.WdCalculatorNotesUiHostBootstrap || {};

    (function (ns) {
        var notesUiBootstrap = null;
        var notesUi = null;

        function configure(options) {
            var opts = options || {};
            if (opts.notesUiBootstrap) {
                notesUiBootstrap = opts.notesUiBootstrap;
            }
            if (opts.notesUi) {
                notesUi = opts.notesUi;
            }
        }

        function requireMethod(moduleObj, methodName, label) {
            if (!moduleObj || typeof moduleObj[methodName] !== "function") {
                throw new Error(label);
            }
            return moduleObj[methodName].bind(moduleObj);
        }

        function initNotesUiHostBootstrap() {
            requireMethod(
                notesUiBootstrap,
                "configure",
                "WdCalculatorNotesUiHostBootstrap requires notesUiBootstrap.configure"
            )({
                notesUi: notesUi,
            });

            return requireMethod(
                notesUiBootstrap,
                "initNotesUiBootstrap",
                "WdCalculatorNotesUiHostBootstrap requires notesUiBootstrap.initNotesUiBootstrap"
            )();
        }

        ns.configure = configure;
        ns.initNotesUiHostBootstrap = initNotesUiHostBootstrap;
    })(WdCalculatorNotesUiHostBootstrap);

    window.WdCalculatorNotesUiHostBootstrap = WdCalculatorNotesUiHostBootstrap;
})();


/* ---- included: post-mutation-ui-bootstrap.js ---- */
(function () {
    var WdCalculatorPostMutationUiBootstrap =
        window.WdCalculatorPostMutationUiBootstrap || {};

    (function (ns) {
        var lateBootstrap = null;
        var sidebarBootstrap = null;
        var refreshAfterSave = null;
        var urlBootstrap = null;
        var initSidebarEstimates = null;
        var loadEstimateToForm = null;
        var formatNumber = null;
        var setEstimates = null;
        var resetInputFormKeepCustomerName = null;
        var resetInputFormToNewEstimate = null;
        var renderEstimatesList = null;
        var getProducts = null;
        var documentRef = null;
        var consoleRef = null;
        var setTimeoutImpl = null;
        var renderInitialBaseComponentsUi = null;

        function configure(options) {
            var opts = options || {};
            if (opts.lateBootstrap) {
                lateBootstrap = opts.lateBootstrap;
            }
            if (opts.sidebarBootstrap) {
                sidebarBootstrap = opts.sidebarBootstrap;
            }
            if (opts.refreshAfterSave) {
                refreshAfterSave = opts.refreshAfterSave;
            }
            if (opts.urlBootstrap) {
                urlBootstrap = opts.urlBootstrap;
            }
            if (typeof opts.initSidebarEstimates === "function") {
                initSidebarEstimates = opts.initSidebarEstimates;
            }
            if (typeof opts.loadEstimateToForm === "function") {
                loadEstimateToForm = opts.loadEstimateToForm;
            }
            if (typeof opts.formatNumber === "function") {
                formatNumber = opts.formatNumber;
            }
            if (typeof opts.setEstimates === "function") {
                setEstimates = opts.setEstimates;
            }
            if (typeof opts.resetInputFormKeepCustomerName === "function") {
                resetInputFormKeepCustomerName = opts.resetInputFormKeepCustomerName;
            }
            if (typeof opts.resetInputFormToNewEstimate === "function") {
                resetInputFormToNewEstimate = opts.resetInputFormToNewEstimate;
            }
            if (typeof opts.renderEstimatesList === "function") {
                renderEstimatesList = opts.renderEstimatesList;
            }
            if (typeof opts.getProducts === "function") {
                getProducts = opts.getProducts;
            }
            if (opts.documentRef) {
                documentRef = opts.documentRef;
            }
            if (opts.consoleRef) {
                consoleRef = opts.consoleRef;
            }
            if (typeof opts.setTimeoutImpl === "function") {
                setTimeoutImpl = opts.setTimeoutImpl;
            }
            if (typeof opts.renderInitialBaseComponentsUi === "function") {
                renderInitialBaseComponentsUi = opts.renderInitialBaseComponentsUi;
            }
        }

        function requireMethod(moduleObj, methodName, label) {
            if (!moduleObj || typeof moduleObj[methodName] !== "function") {
                throw new Error(label);
            }
            return moduleObj[methodName].bind(moduleObj);
        }

        function requireFunction(fn, label) {
            if (typeof fn !== "function") {
                throw new Error(label);
            }
            return fn;
        }

        function initPostMutationUiBootstrap() {
            requireMethod(
                lateBootstrap,
                "configure",
                "WdCalculatorPostMutationUiBootstrap requires lateBootstrap.configure"
            )({
                sidebarBootstrap: sidebarBootstrap,
                refreshAfterSave: refreshAfterSave,
                urlBootstrap: urlBootstrap,
                initSidebarEstimates: initSidebarEstimates,
                loadEstimateToForm: loadEstimateToForm,
                formatNumber: formatNumber,
                setEstimates: setEstimates,
                resetInputFormKeepCustomerName: resetInputFormKeepCustomerName,
                resetInputFormToNewEstimate: resetInputFormToNewEstimate,
                renderEstimatesList: renderEstimatesList,
                getProducts: getProducts,
                documentRef: documentRef,
                consoleRef: consoleRef,
                setTimeoutImpl: setTimeoutImpl,
            });

            var sidebarEstimatesApi = requireMethod(
                lateBootstrap,
                "initLateBootstrap",
                "WdCalculatorPostMutationUiBootstrap requires lateBootstrap.initLateBootstrap"
            )();

            requireFunction(
                renderInitialBaseComponentsUi,
                "WdCalculatorPostMutationUiBootstrap requires renderInitialBaseComponentsUi"
            )();

            return sidebarEstimatesApi;
        }

        ns.configure = configure;
        ns.initPostMutationUiBootstrap = initPostMutationUiBootstrap;
    })(WdCalculatorPostMutationUiBootstrap);

    window.WdCalculatorPostMutationUiBootstrap =
        WdCalculatorPostMutationUiBootstrap;
})();


/* ---- included: post-mutation-ui-host-bootstrap.js ---- */
(function () {
    var WdCalculatorPostMutationUiHostBootstrap =
        window.WdCalculatorPostMutationUiHostBootstrap || {};

    (function (ns) {
        var postMutationUiBootstrap = null;
        var lateBootstrap = null;
        var sidebarBootstrap = null;
        var refreshAfterSave = null;
        var urlBootstrap = null;
        var initSidebarEstimates = null;
        var loadEstimateToForm = null;
        var formatNumber = null;
        var setEstimates = null;
        var resetInputFormKeepCustomerName = null;
        var resetInputFormToNewEstimate = null;
        var renderEstimatesList = null;
        var getProducts = null;
        var documentRef = null;
        var consoleRef = null;
        var setTimeoutImpl = null;
        var renderInitialBaseComponentsUi = null;

        function configure(options) {
            var opts = options || {};
            if (opts.postMutationUiBootstrap) {
                postMutationUiBootstrap = opts.postMutationUiBootstrap;
            }
            if (opts.lateBootstrap) {
                lateBootstrap = opts.lateBootstrap;
            }
            if (opts.sidebarBootstrap) {
                sidebarBootstrap = opts.sidebarBootstrap;
            }
            if (opts.refreshAfterSave) {
                refreshAfterSave = opts.refreshAfterSave;
            }
            if (opts.urlBootstrap) {
                urlBootstrap = opts.urlBootstrap;
            }
            if (typeof opts.initSidebarEstimates === "function") {
                initSidebarEstimates = opts.initSidebarEstimates;
            }
            if (typeof opts.loadEstimateToForm === "function") {
                loadEstimateToForm = opts.loadEstimateToForm;
            }
            if (typeof opts.formatNumber === "function") {
                formatNumber = opts.formatNumber;
            }
            if (typeof opts.setEstimates === "function") {
                setEstimates = opts.setEstimates;
            }
            if (typeof opts.resetInputFormKeepCustomerName === "function") {
                resetInputFormKeepCustomerName = opts.resetInputFormKeepCustomerName;
            }
            if (typeof opts.resetInputFormToNewEstimate === "function") {
                resetInputFormToNewEstimate = opts.resetInputFormToNewEstimate;
            }
            if (typeof opts.renderEstimatesList === "function") {
                renderEstimatesList = opts.renderEstimatesList;
            }
            if (typeof opts.getProducts === "function") {
                getProducts = opts.getProducts;
            }
            if (opts.documentRef) {
                documentRef = opts.documentRef;
            }
            if (opts.consoleRef) {
                consoleRef = opts.consoleRef;
            }
            if (typeof opts.setTimeoutImpl === "function") {
                setTimeoutImpl = opts.setTimeoutImpl;
            }
            if (typeof opts.renderInitialBaseComponentsUi === "function") {
                renderInitialBaseComponentsUi = opts.renderInitialBaseComponentsUi;
            }
        }

        function requireMethod(moduleObj, methodName, label) {
            if (!moduleObj || typeof moduleObj[methodName] !== "function") {
                throw new Error(label);
            }
            return moduleObj[methodName].bind(moduleObj);
        }

        function initPostMutationUiHostBootstrap() {
            requireMethod(
                postMutationUiBootstrap,
                "configure",
                "WdCalculatorPostMutationUiHostBootstrap requires postMutationUiBootstrap.configure"
            )({
                lateBootstrap: lateBootstrap,
                sidebarBootstrap: sidebarBootstrap,
                refreshAfterSave: refreshAfterSave,
                urlBootstrap: urlBootstrap,
                initSidebarEstimates: initSidebarEstimates,
                loadEstimateToForm: loadEstimateToForm,
                formatNumber: formatNumber,
                setEstimates: setEstimates,
                resetInputFormKeepCustomerName: resetInputFormKeepCustomerName,
                resetInputFormToNewEstimate: resetInputFormToNewEstimate,
                renderEstimatesList: renderEstimatesList,
                getProducts: getProducts,
                documentRef: documentRef,
                consoleRef: consoleRef,
                setTimeoutImpl: setTimeoutImpl,
                renderInitialBaseComponentsUi: renderInitialBaseComponentsUi,
            });

            return requireMethod(
                postMutationUiBootstrap,
                "initPostMutationUiBootstrap",
                "WdCalculatorPostMutationUiHostBootstrap requires postMutationUiBootstrap.initPostMutationUiBootstrap"
            )();
        }

        ns.configure = configure;
        ns.initPostMutationUiHostBootstrap = initPostMutationUiHostBootstrap;
    })(WdCalculatorPostMutationUiHostBootstrap);

    window.WdCalculatorPostMutationUiHostBootstrap =
        WdCalculatorPostMutationUiHostBootstrap;
})();


/* ---- included: loading-database-bootstrap.js ---- */
(function () {
    var WdCalculatorLoadingDatabaseBootstrap =
        window.WdCalculatorLoadingDatabaseBootstrap || {};

    (function (ns) {
        var loadingState = null;
        var currentDatabaseEstimateIdState = null;
        var initialLoadingValue = false;
        var initialCurrentDatabaseEstimateId = null;

        function configure(options) {
            var opts = options || {};
            if (opts.loadingState) {
                loadingState = opts.loadingState;
            }
            if (opts.currentDatabaseEstimateIdState) {
                currentDatabaseEstimateIdState = opts.currentDatabaseEstimateIdState;
            }
            if (Object.prototype.hasOwnProperty.call(opts, "initialLoadingValue")) {
                initialLoadingValue = opts.initialLoadingValue;
            }
            if (
                Object.prototype.hasOwnProperty.call(
                    opts,
                    "initialCurrentDatabaseEstimateId"
                )
            ) {
                initialCurrentDatabaseEstimateId = opts.initialCurrentDatabaseEstimateId;
            }
        }

        function requireMethod(moduleObj, methodName, label) {
            if (!moduleObj || typeof moduleObj[methodName] !== "function") {
                throw new Error(label);
            }
            return moduleObj[methodName].bind(moduleObj);
        }

        function initLoadingDatabaseBootstrap() {
            requireMethod(
                loadingState,
                "configure",
                "WdCalculatorLoadingDatabaseBootstrap requires loadingState.configure"
            )({
                initialValue: initialLoadingValue,
            });

            requireMethod(
                currentDatabaseEstimateIdState,
                "configure",
                "WdCalculatorLoadingDatabaseBootstrap requires currentDatabaseEstimateIdState.configure"
            )({
                initialValue: initialCurrentDatabaseEstimateId,
            });
        }

        ns.configure = configure;
        ns.initLoadingDatabaseBootstrap = initLoadingDatabaseBootstrap;
    })(WdCalculatorLoadingDatabaseBootstrap);

    window.WdCalculatorLoadingDatabaseBootstrap = WdCalculatorLoadingDatabaseBootstrap;
})();


/* ---- included: loading-database-host-bootstrap.js ---- */
(function () {
    var WdCalculatorLoadingDatabaseHostBootstrap =
        window.WdCalculatorLoadingDatabaseHostBootstrap || {};

    (function (ns) {
        var loadingDatabaseBootstrap = null;
        var loadingState = null;
        var currentDatabaseEstimateIdState = null;
        var initialLoadingValue = false;
        var initialCurrentDatabaseEstimateId = null;

        function configure(options) {
            var opts = options || {};
            if (opts.loadingDatabaseBootstrap) {
                loadingDatabaseBootstrap = opts.loadingDatabaseBootstrap;
            }
            if (opts.loadingState) {
                loadingState = opts.loadingState;
            }
            if (opts.currentDatabaseEstimateIdState) {
                currentDatabaseEstimateIdState = opts.currentDatabaseEstimateIdState;
            }
            if (Object.prototype.hasOwnProperty.call(opts, "initialLoadingValue")) {
                initialLoadingValue = opts.initialLoadingValue;
            }
            if (
                Object.prototype.hasOwnProperty.call(
                    opts,
                    "initialCurrentDatabaseEstimateId"
                )
            ) {
                initialCurrentDatabaseEstimateId = opts.initialCurrentDatabaseEstimateId;
            }
        }

        function requireMethod(moduleObj, methodName, label) {
            if (!moduleObj || typeof moduleObj[methodName] !== "function") {
                throw new Error(label);
            }
            return moduleObj[methodName].bind(moduleObj);
        }

        function initLoadingDatabaseHostBootstrap() {
            requireMethod(
                loadingDatabaseBootstrap,
                "configure",
                "WdCalculatorLoadingDatabaseHostBootstrap requires loadingDatabaseBootstrap.configure"
            )({
                loadingState: loadingState,
                currentDatabaseEstimateIdState: currentDatabaseEstimateIdState,
                initialLoadingValue: initialLoadingValue,
                initialCurrentDatabaseEstimateId: initialCurrentDatabaseEstimateId,
            });

            return requireMethod(
                loadingDatabaseBootstrap,
                "initLoadingDatabaseBootstrap",
                "WdCalculatorLoadingDatabaseHostBootstrap requires loadingDatabaseBootstrap.initLoadingDatabaseBootstrap"
            )();
        }

        ns.configure = configure;
        ns.initLoadingDatabaseHostBootstrap = initLoadingDatabaseHostBootstrap;
    })(WdCalculatorLoadingDatabaseHostBootstrap);

    window.WdCalculatorLoadingDatabaseHostBootstrap =
        WdCalculatorLoadingDatabaseHostBootstrap;
})();


/* ---- included: products-editing-bootstrap.js ---- */
(function () {
    var WdCalculatorProductsEditingBootstrap = window.WdCalculatorProductsEditingBootstrap || {};

    (function (ns) {
        var productsState = null;
        var editingEstimateIdState = null;
        var initialProducts = [];
        var initialEditingEstimateId = null;

        function normalizeInitialProducts(nextInitialProducts) {
            return Array.isArray(nextInitialProducts) ? nextInitialProducts : [];
        }

        function configure(options) {
            var opts = options || {};
            if (opts.productsState) {
                productsState = opts.productsState;
            }
            if (opts.editingEstimateIdState) {
                editingEstimateIdState = opts.editingEstimateIdState;
            }
            if (Object.prototype.hasOwnProperty.call(opts, "initialProducts")) {
                initialProducts = normalizeInitialProducts(opts.initialProducts);
            }
            if (Object.prototype.hasOwnProperty.call(opts, "initialEditingEstimateId")) {
                initialEditingEstimateId = opts.initialEditingEstimateId;
            }
        }

        function requireMethod(moduleObj, methodName, label) {
            if (!moduleObj || typeof moduleObj[methodName] !== "function") {
                throw new Error(label);
            }
            return moduleObj[methodName].bind(moduleObj);
        }

        function initProductsEditingBootstrap() {
            requireMethod(
                productsState,
                "configure",
                "WdCalculatorProductsEditingBootstrap requires productsState.configure"
            )({
                initialProducts: initialProducts,
            });

            requireMethod(
                editingEstimateIdState,
                "configure",
                "WdCalculatorProductsEditingBootstrap requires editingEstimateIdState.configure"
            )({
                initialValue: initialEditingEstimateId,
            });
        }

        ns.configure = configure;
        ns.initProductsEditingBootstrap = initProductsEditingBootstrap;
    })(WdCalculatorProductsEditingBootstrap);

    window.WdCalculatorProductsEditingBootstrap = WdCalculatorProductsEditingBootstrap;
})();


/* ---- included: products-editing-host-bootstrap.js ---- */
(function () {
    var WdCalculatorProductsEditingHostBootstrap =
        window.WdCalculatorProductsEditingHostBootstrap || {};

    (function (ns) {
        var productsEditingBootstrap = null;
        var productsState = null;
        var editingEstimateIdState = null;
        var initialProducts = [];
        var initialEditingEstimateId = null;

        function configure(options) {
            var opts = options || {};
            if (opts.productsEditingBootstrap) {
                productsEditingBootstrap = opts.productsEditingBootstrap;
            }
            if (opts.productsState) {
                productsState = opts.productsState;
            }
            if (opts.editingEstimateIdState) {
                editingEstimateIdState = opts.editingEstimateIdState;
            }
            if (Object.prototype.hasOwnProperty.call(opts, "initialProducts")) {
                initialProducts = opts.initialProducts;
            }
            if (Object.prototype.hasOwnProperty.call(opts, "initialEditingEstimateId")) {
                initialEditingEstimateId = opts.initialEditingEstimateId;
            }
        }

        function requireMethod(moduleObj, methodName, label) {
            if (!moduleObj || typeof moduleObj[methodName] !== "function") {
                throw new Error(label);
            }
            return moduleObj[methodName].bind(moduleObj);
        }

        function initProductsEditingHostBootstrap() {
            requireMethod(
                productsEditingBootstrap,
                "configure",
                "WdCalculatorProductsEditingHostBootstrap requires productsEditingBootstrap.configure"
            )({
                productsState: productsState,
                editingEstimateIdState: editingEstimateIdState,
                initialProducts: initialProducts,
                initialEditingEstimateId: initialEditingEstimateId,
            });

            return requireMethod(
                productsEditingBootstrap,
                "initProductsEditingBootstrap",
                "WdCalculatorProductsEditingHostBootstrap requires productsEditingBootstrap.initProductsEditingBootstrap"
            )();
        }

        ns.configure = configure;
        ns.initProductsEditingHostBootstrap = initProductsEditingHostBootstrap;
    })(WdCalculatorProductsEditingHostBootstrap);

    window.WdCalculatorProductsEditingHostBootstrap =
        WdCalculatorProductsEditingHostBootstrap;
})();


/* ---- included: estimates-early-bootstrap.js ---- */
(function () {
    var WdCalculatorEstimatesEarlyBootstrap = window.WdCalculatorEstimatesEarlyBootstrap || {};

    (function (ns) {
        var estimatesState = null;
        var earlyBootstrap = null;
        var unsavedExitGuard = null;
        var layoutSyncWiring = null;
        var initialEstimates = [];
        var getEstimates = null;
        var windowRef = window;
        var requestLayoutSync = function () {};

        function normalizeInitialEstimates(nextInitialEstimates) {
            return Array.isArray(nextInitialEstimates) ? nextInitialEstimates : [];
        }

        function configure(options) {
            var opts = options || {};
            if (opts.estimatesState) {
                estimatesState = opts.estimatesState;
            }
            if (opts.earlyBootstrap) {
                earlyBootstrap = opts.earlyBootstrap;
            }
            if (opts.unsavedExitGuard) {
                unsavedExitGuard = opts.unsavedExitGuard;
            }
            if (opts.layoutSyncWiring) {
                layoutSyncWiring = opts.layoutSyncWiring;
            }
            if (Object.prototype.hasOwnProperty.call(opts, "initialEstimates")) {
                initialEstimates = normalizeInitialEstimates(opts.initialEstimates);
            }
            if (typeof opts.getEstimates === "function") {
                getEstimates = opts.getEstimates;
            }
            if (opts.windowRef) {
                windowRef = opts.windowRef;
            }
            if (typeof opts.requestLayoutSync === "function") {
                requestLayoutSync = opts.requestLayoutSync;
            }
        }

        function requireMethod(moduleObj, methodName, label) {
            if (!moduleObj || typeof moduleObj[methodName] !== "function") {
                throw new Error(label);
            }
            return moduleObj[methodName].bind(moduleObj);
        }

        function resolveGetEstimates() {
            if (typeof getEstimates === "function") {
                return getEstimates;
            }
            return requireMethod(
                estimatesState,
                "getEstimates",
                "WdCalculatorEstimatesEarlyBootstrap requires estimatesState.getEstimates"
            );
        }

        function initEstimatesEarlyBootstrap() {
            requireMethod(
                estimatesState,
                "configure",
                "WdCalculatorEstimatesEarlyBootstrap requires estimatesState.configure"
            )({
                initialEstimates: initialEstimates,
            });

            requireMethod(
                earlyBootstrap,
                "configure",
                "WdCalculatorEstimatesEarlyBootstrap requires earlyBootstrap.configure"
            )({
                unsavedExitGuard: unsavedExitGuard,
                layoutSyncWiring: layoutSyncWiring,
                getEstimates: resolveGetEstimates(),
                windowRef: windowRef,
                requestLayoutSync: requestLayoutSync,
            });

            requireMethod(
                earlyBootstrap,
                "initEarlyBootstrap",
                "WdCalculatorEstimatesEarlyBootstrap requires earlyBootstrap.initEarlyBootstrap"
            )();
        }

        ns.configure = configure;
        ns.initEstimatesEarlyBootstrap = initEstimatesEarlyBootstrap;
    })(WdCalculatorEstimatesEarlyBootstrap);

    window.WdCalculatorEstimatesEarlyBootstrap = WdCalculatorEstimatesEarlyBootstrap;
})();


/* ---- included: estimates-early-host-bootstrap.js ---- */
(function () {
    var WdCalculatorEstimatesEarlyHostBootstrap =
        window.WdCalculatorEstimatesEarlyHostBootstrap || {};

    (function (ns) {
        var estimatesEarlyBootstrap = null;
        var estimatesState = null;
        var earlyBootstrap = null;
        var unsavedExitGuard = null;
        var layoutSyncWiring = null;
        var initialEstimates = [];
        var getEstimates = null;
        var windowRef = null;
        var requestLayoutSync = null;

        function configure(options) {
            var opts = options || {};
            if (opts.estimatesEarlyBootstrap) {
                estimatesEarlyBootstrap = opts.estimatesEarlyBootstrap;
            }
            if (opts.estimatesState) {
                estimatesState = opts.estimatesState;
            }
            if (opts.earlyBootstrap) {
                earlyBootstrap = opts.earlyBootstrap;
            }
            if (opts.unsavedExitGuard) {
                unsavedExitGuard = opts.unsavedExitGuard;
            }
            if (opts.layoutSyncWiring) {
                layoutSyncWiring = opts.layoutSyncWiring;
            }
            if (Object.prototype.hasOwnProperty.call(opts, "initialEstimates")) {
                initialEstimates = opts.initialEstimates;
            }
            if (typeof opts.getEstimates === "function") {
                getEstimates = opts.getEstimates;
            }
            if (opts.windowRef) {
                windowRef = opts.windowRef;
            }
            if (typeof opts.requestLayoutSync === "function") {
                requestLayoutSync = opts.requestLayoutSync;
            }
        }

        function requireMethod(moduleObj, methodName, label) {
            if (!moduleObj || typeof moduleObj[methodName] !== "function") {
                throw new Error(label);
            }
            return moduleObj[methodName].bind(moduleObj);
        }

        function initEstimatesEarlyHostBootstrap() {
            requireMethod(
                estimatesEarlyBootstrap,
                "configure",
                "WdCalculatorEstimatesEarlyHostBootstrap requires estimatesEarlyBootstrap.configure"
            )({
                estimatesState: estimatesState,
                earlyBootstrap: earlyBootstrap,
                unsavedExitGuard: unsavedExitGuard,
                layoutSyncWiring: layoutSyncWiring,
                initialEstimates: initialEstimates,
                getEstimates: getEstimates,
                windowRef: windowRef,
                requestLayoutSync: requestLayoutSync,
            });

            return requireMethod(
                estimatesEarlyBootstrap,
                "initEstimatesEarlyBootstrap",
                "WdCalculatorEstimatesEarlyHostBootstrap requires estimatesEarlyBootstrap.initEstimatesEarlyBootstrap"
            )();
        }

        ns.configure = configure;
        ns.initEstimatesEarlyHostBootstrap = initEstimatesEarlyHostBootstrap;
    })(WdCalculatorEstimatesEarlyHostBootstrap);

    window.WdCalculatorEstimatesEarlyHostBootstrap =
        WdCalculatorEstimatesEarlyHostBootstrap;
})();

