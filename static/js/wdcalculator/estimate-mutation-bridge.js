(function () {
    var WdCalculatorEstimateMutationBridge = window.WdCalculatorEstimateMutationBridge || {};

    (function (ns) {
        var resetFormModule = null;
        var loadInputModule = null;
        var loadSavedModule = null;
        var addEstimateModule = null;
        var listEventsModule = null;
        var saveEstimateModule = null;

        var setEditingEstimateId = function () {};
        var getEstimatesLength = function () {
            return 0;
        };
        var ensureBaseComponentsUI = function () {};
        var resetNotesToEmpty = function () {};
        var recalculate = function () {};

        var setLoadingState = function () {};
        var getEditingEstimateId = function () {
            return null;
        };
        var getEstimates = function () {
            return [];
        };
        var normalizeId = function (value) {
            return value;
        };
        var isSameId = function (left, right) {
            return left === right;
        };
        var loadAdditionalOptionRows = function () {};
        var loadNotes = function () {};
        var calculateEstimate = function () {};

        var setCurrentDatabaseEstimateId = function () {};
        var setEstimates = function () {};
        var generateEstimateId = function () {
            return String(Date.now());
        };
        var formatNumber = function (num) {
            return Math.round(Number(num) || 0).toLocaleString("ko-KR");
        };
        var renderEstimatesList = function () {};
        var reloadImpl = function () {};

        var collectCurrentEstimate = function () {
            return null;
        };
        var resetInputFormKeepCustomerName = function () {};
        var getLoadingState = function () {
            return false;
        };
        var loadEstimateToInputForm = function () {};
        var setTimeoutImpl = window.setTimeout ? window.setTimeout.bind(window) : function (fn) {
            fn();
            return 1;
        };

        var getCurrentDatabaseEstimateId = function () {
            return null;
        };
        var collectNotes = function () {
            return "";
        };
        var getCouponValue = function () {
            return 0;
        };
        var resolveAggregateTotals = function () {
            return {
                totalBasePrice: 0,
                totalAdditionalPrice: 0,
                totalPrice: 0,
            };
        };
        var refreshAfterSave = function () {};

        var documentRef = document;
        var confirmImpl = window.confirm ? window.confirm.bind(window) : function () {
            return true;
        };
        var alertImpl = window.alert ? window.alert.bind(window) : function () {};
        var consoleRef = window.console || console;
        var fetchImpl = typeof window.fetch === "function" ? window.fetch.bind(window) : function () {
            return Promise.reject(new Error("fetch is not available"));
        };

        function configure(options) {
            var opts = options || {};

            if (opts.resetFormModule) {
                resetFormModule = opts.resetFormModule;
            }
            if (opts.loadInputModule) {
                loadInputModule = opts.loadInputModule;
            }
            if (opts.loadSavedModule) {
                loadSavedModule = opts.loadSavedModule;
            }
            if (opts.addEstimateModule) {
                addEstimateModule = opts.addEstimateModule;
            }
            if (opts.listEventsModule) {
                listEventsModule = opts.listEventsModule;
            }
            if (opts.saveEstimateModule) {
                saveEstimateModule = opts.saveEstimateModule;
            }

            if (typeof opts.setEditingEstimateId === "function") {
                setEditingEstimateId = opts.setEditingEstimateId;
            }
            if (typeof opts.getEstimatesLength === "function") {
                getEstimatesLength = opts.getEstimatesLength;
            }
            if (typeof opts.ensureBaseComponentsUI === "function") {
                ensureBaseComponentsUI = opts.ensureBaseComponentsUI;
            }
            if (typeof opts.resetNotesToEmpty === "function") {
                resetNotesToEmpty = opts.resetNotesToEmpty;
            }
            if (typeof opts.recalculate === "function") {
                recalculate = opts.recalculate;
            }

            if (typeof opts.setLoadingState === "function") {
                setLoadingState = opts.setLoadingState;
            }
            if (typeof opts.getEditingEstimateId === "function") {
                getEditingEstimateId = opts.getEditingEstimateId;
            }
            if (typeof opts.getEstimates === "function") {
                getEstimates = opts.getEstimates;
            }
            if (typeof opts.normalizeId === "function") {
                normalizeId = opts.normalizeId;
            }
            if (typeof opts.isSameId === "function") {
                isSameId = opts.isSameId;
            }
            if (typeof opts.loadAdditionalOptionRows === "function") {
                loadAdditionalOptionRows = opts.loadAdditionalOptionRows;
            }
            if (typeof opts.loadNotes === "function") {
                loadNotes = opts.loadNotes;
            }
            if (typeof opts.calculateEstimate === "function") {
                calculateEstimate = opts.calculateEstimate;
            }

            if (typeof opts.setCurrentDatabaseEstimateId === "function") {
                setCurrentDatabaseEstimateId = opts.setCurrentDatabaseEstimateId;
            }
            if (typeof opts.setEstimates === "function") {
                setEstimates = opts.setEstimates;
            }
            if (typeof opts.generateEstimateId === "function") {
                generateEstimateId = opts.generateEstimateId;
            }
            if (typeof opts.formatNumber === "function") {
                formatNumber = opts.formatNumber;
            }
            if (typeof opts.renderEstimatesList === "function") {
                renderEstimatesList = opts.renderEstimatesList;
            }
            if (typeof opts.reloadImpl === "function") {
                reloadImpl = opts.reloadImpl;
            }

            if (typeof opts.collectCurrentEstimate === "function") {
                collectCurrentEstimate = opts.collectCurrentEstimate;
            }
            if (typeof opts.resetInputFormKeepCustomerName === "function") {
                resetInputFormKeepCustomerName = opts.resetInputFormKeepCustomerName;
            }
            if (typeof opts.getLoadingState === "function") {
                getLoadingState = opts.getLoadingState;
            }
            if (typeof opts.loadEstimateToInputForm === "function") {
                loadEstimateToInputForm = opts.loadEstimateToInputForm;
            }
            if (typeof opts.setTimeoutImpl === "function") {
                setTimeoutImpl = opts.setTimeoutImpl;
            }

            if (typeof opts.getCurrentDatabaseEstimateId === "function") {
                getCurrentDatabaseEstimateId = opts.getCurrentDatabaseEstimateId;
            }
            if (typeof opts.collectNotes === "function") {
                collectNotes = opts.collectNotes;
            }
            if (typeof opts.getCouponValue === "function") {
                getCouponValue = opts.getCouponValue;
            }
            if (typeof opts.resolveAggregateTotals === "function") {
                resolveAggregateTotals = opts.resolveAggregateTotals;
            }
            if (typeof opts.refreshAfterSave === "function") {
                refreshAfterSave = opts.refreshAfterSave;
            }

            if (opts.documentRef) {
                documentRef = opts.documentRef;
            }
            if (typeof opts.confirmImpl === "function") {
                confirmImpl = opts.confirmImpl;
            }
            if (typeof opts.alertImpl === "function") {
                alertImpl = opts.alertImpl;
            }
            if (opts.consoleRef) {
                consoleRef = opts.consoleRef;
            }
            if (typeof opts.fetchImpl === "function") {
                fetchImpl = opts.fetchImpl;
            }
        }

        function requireMethod(moduleObj, methodName, label) {
            if (!moduleObj || typeof moduleObj[methodName] !== "function") {
                throw new Error(label);
            }
            return moduleObj[methodName].bind(moduleObj);
        }

        function initEstimateMutationBridge() {
            requireMethod(
                resetFormModule,
                "configure",
                "WdCalculatorEstimateMutationBridge requires resetFormModule.configure"
            )({
                setEditingEstimateId: setEditingEstimateId,
                getEstimatesLength: getEstimatesLength,
                ensureBaseComponentsUI: ensureBaseComponentsUI,
                resetNotesToEmpty: resetNotesToEmpty,
                recalculate: recalculate,
                documentRef: documentRef,
                consoleRef: consoleRef,
            });

            requireMethod(
                loadInputModule,
                "configure",
                "WdCalculatorEstimateMutationBridge requires loadInputModule.configure"
            )({
                setLoadingState: setLoadingState,
                getEditingEstimateId: getEditingEstimateId,
                getEstimates: getEstimates,
                normalizeId: normalizeId,
                isSameId: isSameId,
                ensureBaseComponentsUI: ensureBaseComponentsUI,
                resetNotesToEmpty: resetNotesToEmpty,
                loadAdditionalOptionRows: loadAdditionalOptionRows,
                loadNotes: loadNotes,
                setEditingEstimateId: setEditingEstimateId,
                calculateEstimate: calculateEstimate,
                documentRef: documentRef,
                consoleRef: consoleRef,
                confirmImpl: confirmImpl,
                alertImpl: alertImpl,
            });

            requireMethod(
                loadSavedModule,
                "configure",
                "WdCalculatorEstimateMutationBridge requires loadSavedModule.configure"
            )({
                setCurrentDatabaseEstimateId: setCurrentDatabaseEstimateId,
                setEstimates: setEstimates,
                generateEstimateId: generateEstimateId,
                formatNumber: formatNumber,
                renderEstimatesList: renderEstimatesList,
                ensureBaseComponentsUI: ensureBaseComponentsUI,
                calculateEstimate: calculateEstimate,
                resetNotesToEmpty: resetNotesToEmpty,
                documentRef: documentRef,
                confirmImpl: confirmImpl,
                reloadImpl: reloadImpl,
            });

            requireMethod(
                addEstimateModule,
                "configure",
                "WdCalculatorEstimateMutationBridge requires addEstimateModule.configure"
            )({
                getEditingEstimateId: getEditingEstimateId,
                setEditingEstimateId: setEditingEstimateId,
                getEstimates: getEstimates,
                collectCurrentEstimate: collectCurrentEstimate,
                normalizeId: normalizeId,
                isSameId: isSameId,
                generateEstimateId: generateEstimateId,
                renderEstimatesList: renderEstimatesList,
                resetInputFormKeepCustomerName: resetInputFormKeepCustomerName,
                documentRef: documentRef,
                alertImpl: alertImpl,
                consoleRef: consoleRef,
            });
            requireMethod(
                addEstimateModule,
                "initAddEstimateButton",
                "WdCalculatorEstimateMutationBridge requires addEstimateModule.initAddEstimateButton"
            )();

            requireMethod(
                listEventsModule,
                "configure",
                "WdCalculatorEstimateMutationBridge requires listEventsModule.configure"
            )({
                getLoadingState: getLoadingState,
                getEstimates: getEstimates,
                setEstimates: setEstimates,
                getEditingEstimateId: getEditingEstimateId,
                setEditingEstimateId: setEditingEstimateId,
                loadEstimateToInputForm: loadEstimateToInputForm,
                renderEstimatesList: renderEstimatesList,
                formatNumber: formatNumber,
                normalizeId: normalizeId,
                isSameId: isSameId,
                documentRef: documentRef,
                confirmImpl: confirmImpl,
                consoleRef: consoleRef,
                setTimeoutImpl: setTimeoutImpl,
            });
            requireMethod(
                listEventsModule,
                "initEstimateListEvents",
                "WdCalculatorEstimateMutationBridge requires listEventsModule.initEstimateListEvents"
            )();

            requireMethod(
                saveEstimateModule,
                "configure",
                "WdCalculatorEstimateMutationBridge requires saveEstimateModule.configure"
            )({
                getCurrentDatabaseEstimateId: getCurrentDatabaseEstimateId,
                setCurrentDatabaseEstimateId: setCurrentDatabaseEstimateId,
                getEstimates: getEstimates,
                collectCurrentEstimate: collectCurrentEstimate,
                generateEstimateId: generateEstimateId,
                collectNotes: collectNotes,
                getCouponValue: getCouponValue,
                resolveAggregateTotals: resolveAggregateTotals,
                refreshAfterSave: refreshAfterSave,
                documentRef: documentRef,
                fetchImpl: fetchImpl,
                alertImpl: alertImpl,
                consoleRef: consoleRef,
            });
            requireMethod(
                saveEstimateModule,
                "initSaveEstimateButton",
                "WdCalculatorEstimateMutationBridge requires saveEstimateModule.initSaveEstimateButton"
            )();
        }

        ns.configure = configure;
        ns.initEstimateMutationBridge = initEstimateMutationBridge;
    })(WdCalculatorEstimateMutationBridge);

    window.WdCalculatorEstimateMutationBridge = WdCalculatorEstimateMutationBridge;
})();
