(function () {
    var WdCalculatorLoadEstimateToInputForm = window.WdCalculatorLoadEstimateToInputForm || {};

    (function (ns) {
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
        var ensureBaseComponentsUI = function () {};
        var resetNotesToEmpty = function () {};
        var loadAdditionalOptionRows = function () {};
        var loadNotes = function () {};
        var setEditingEstimateId = function () {};
        var calculateEstimate = function () {};
        var documentRef = document;
        var consoleRef = window.console || console;
        var confirmImpl = window.confirm ? window.confirm.bind(window) : function () {
            return true;
        };
        var alertImpl = window.alert ? window.alert.bind(window) : function () {};

        function configure(options) {
            var opts = options || {};
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
            if (typeof opts.ensureBaseComponentsUI === "function") {
                ensureBaseComponentsUI = opts.ensureBaseComponentsUI;
            }
            if (typeof opts.resetNotesToEmpty === "function") {
                resetNotesToEmpty = opts.resetNotesToEmpty;
            }
            if (typeof opts.loadAdditionalOptionRows === "function") {
                loadAdditionalOptionRows = opts.loadAdditionalOptionRows;
            }
            if (typeof opts.loadNotes === "function") {
                loadNotes = opts.loadNotes;
            }
            if (typeof opts.setEditingEstimateId === "function") {
                setEditingEstimateId = opts.setEditingEstimateId;
            }
            if (typeof opts.calculateEstimate === "function") {
                calculateEstimate = opts.calculateEstimate;
            }
            if (opts.documentRef) {
                documentRef = opts.documentRef;
            }
            if (opts.consoleRef) {
                consoleRef = opts.consoleRef;
            }
            if (typeof opts.confirmImpl === "function") {
                confirmImpl = opts.confirmImpl;
            }
            if (typeof opts.alertImpl === "function") {
                alertImpl = opts.alertImpl;
            }
        }

        function buildLegacyBaseComponents(estimate) {
            var legacy = [];
            if (estimate.manualPricing) {
                legacy.push({
                    mode: "manual",
                    widthMm: estimate.widthMm || 0,
                    manualPricing: estimate.manualPricing,
                });
            } else if (estimate.productId) {
                legacy.push({
                    mode: "select",
                    widthMm: estimate.widthMm || 0,
                    productId: estimate.productId,
                });
            } else {
                legacy.push({ mode: "select" });
            }
            return legacy;
        }

        function loadEstimateToInputForm(estimateId) {
            setLoadingState(true);

            try {
                var editingEstimateId = getEditingEstimateId();
                var estimates = getEstimates() || [];

                if (editingEstimateId) {
                    var currentEstimate = estimates.find(function (est) {
                        return isSameId(est.id, editingEstimateId);
                    });
                    if (currentEstimate) {
                        var hasChanges = confirmImpl(
                            "현재 수정 중인 견적이 있습니다. 다른 견적을 불러오시겠습니까?\n(현재 수정 내용은 저장되지 않습니다)"
                        );
                        if (!hasChanges) {
                            return;
                        }
                    }
                }

                var normalizedId = normalizeId(estimateId);
                if (!normalizedId) {
                    consoleRef.error("Invalid estimate ID");
                    alertImpl("잘못된 견적 ID입니다.");
                    return;
                }

                var estimate = estimates.find(function (est) {
                    return isSameId(est.id, normalizedId);
                });
                if (!estimate) {
                    consoleRef.error("견적을 찾을 수 없습니다.");
                    consoleRef.error("Requested ID:", normalizedId);
                    consoleRef.error(
                        "Available IDs:",
                        estimates.map(function (item) {
                            return item.id;
                        })
                    );
                    alertImpl("견적을 찾을 수 없습니다. (ID: " + normalizedId + ")");
                    return;
                }

                documentRef.getElementById("additionalOptionsContainer").innerHTML = "";
                resetNotesToEmpty();

                if (estimate.baseComponents && Array.isArray(estimate.baseComponents) && estimate.baseComponents.length > 0) {
                    ensureBaseComponentsUI(estimate.baseComponents);
                } else {
                    ensureBaseComponentsUI(buildLegacyBaseComponents(estimate));
                }

                var container = documentRef.getElementById("additionalOptionsContainer");
                loadAdditionalOptionRows(container, estimate.options, {
                    formatPriceOnInput: true,
                });
                loadNotes(estimate.notes || "");

                setEditingEstimateId(estimate.id);

                var addEstimateBtn = documentRef.getElementById("addEstimateBtn");
                addEstimateBtn.innerHTML = '<i class="fas fa-save"></i> 견적 수정 적용';
                addEstimateBtn.style.display = "block";

                var scrollTarget =
                    documentRef.getElementById("baseComponentsContainer") ||
                    documentRef.getElementById("customerName") ||
                    documentRef.querySelector(".header-primary");
                if (scrollTarget && typeof scrollTarget.scrollIntoView === "function") {
                    scrollTarget.scrollIntoView({ behavior: "smooth", block: "center" });
                }

                calculateEstimate();
            } catch (error) {
                consoleRef.error("Error in loadEstimateToInputForm:", error);
                alertImpl("견적을 불러오는 중 오류가 발생했습니다: " + (error.message || error));
            } finally {
                setLoadingState(false);
            }
        }

        ns.configure = configure;
        ns.loadEstimateToInputForm = loadEstimateToInputForm;
    })(WdCalculatorLoadEstimateToInputForm);

    window.WdCalculatorLoadEstimateToInputForm = WdCalculatorLoadEstimateToInputForm;
})();
