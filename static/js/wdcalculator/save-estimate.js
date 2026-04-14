(function () {
    var WdCalculatorSaveEstimate = window.WdCalculatorSaveEstimate || {};

    (function (ns) {
        var getCurrentDatabaseEstimateId = function () {
            return null;
        };
        var setCurrentDatabaseEstimateId = function () {};
        var getEstimates = function () {
            return [];
        };
        var collectCurrentEstimate = function () {
            return null;
        };
        var generateEstimateId = function () {
            return String(Date.now());
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
        var fetchImpl = typeof window.fetch === "function" ? window.fetch.bind(window) : function () {
            return Promise.reject(new Error("fetch is not available"));
        };
        var alertImpl = typeof window.alert === "function" ? window.alert.bind(window) : function () {};
        var consoleRef = window.console || console;

        function configure(options) {
            var opts = options || {};
            if (typeof opts.getCurrentDatabaseEstimateId === "function") {
                getCurrentDatabaseEstimateId = opts.getCurrentDatabaseEstimateId;
            }
            if (typeof opts.setCurrentDatabaseEstimateId === "function") {
                setCurrentDatabaseEstimateId = opts.setCurrentDatabaseEstimateId;
            }
            if (typeof opts.getEstimates === "function") {
                getEstimates = opts.getEstimates;
            }
            if (typeof opts.collectCurrentEstimate === "function") {
                collectCurrentEstimate = opts.collectCurrentEstimate;
            }
            if (typeof opts.generateEstimateId === "function") {
                generateEstimateId = opts.generateEstimateId;
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
            if (typeof opts.fetchImpl === "function") {
                fetchImpl = opts.fetchImpl;
            }
            if (typeof opts.alertImpl === "function") {
                alertImpl = opts.alertImpl;
            }
            if (opts.consoleRef) {
                consoleRef = opts.consoleRef;
            }
        }

        function updateHeaderTitle(customerName) {
            var headerTitle = documentRef.querySelector(".header-primary h6");
            if (headerTitle) {
                headerTitle.innerHTML =
                    '<i class="fas fa-edit me-2"></i>견적 수정: ' +
                    customerName +
                    ' <span class="badge bg-warning text-dark ms-2">수정모드</span>';
            }
        }

        function readShippingState() {
            var shippingCostInput = documentRef.getElementById("shippingCost");
            var shippingIncludedCheckbox = documentRef.getElementById("shippingIncluded");
            return {
                shippingCost: shippingCostInput ? parseFloat(shippingCostInput.value) || 0 : 0,
                shippingIncluded: shippingIncludedCheckbox ? shippingIncludedCheckbox.checked : true,
            };
        }

        function buildEstimatesToSave() {
            var estimatesToSave = getEstimates();
            if (estimatesToSave.length > 0) {
                return estimatesToSave;
            }

            var currentEstimate = collectCurrentEstimate();
            if (!currentEstimate) {
                alertImpl("저장할 견적이 없습니다. 먼저 견적을 계산해주세요.");
                return null;
            }
            currentEstimate.id = generateEstimateId();
            return [currentEstimate];
        }

        function buildEstimateData(estimatesToSave, notes, couponValue, shippingCost, shippingIncluded) {
            var aggSave = resolveAggregateTotals(estimatesToSave, couponValue, shippingCost, shippingIncluded);
            var couponDiscount = couponValue > 0 ? couponValue : 0;
            return {
                estimates: estimatesToSave,
                totalBasePrice: aggSave.totalBasePrice,
                totalAdditionalPrice: aggSave.totalAdditionalPrice,
                totalPrice: aggSave.totalPrice,
                coupon_discount: couponDiscount,
                shipping_cost: shippingCost,
                shipping_included: shippingIncluded,
                notes: notes,
            };
        }

        function restoreSaveButton(buttonEl, originalText) {
            buttonEl.disabled = false;
            buttonEl.innerHTML = originalText;
        }

        function handleSaveEstimate(buttonEl) {
            var customerNameEl = documentRef.getElementById("customerName");
            var customerName = customerNameEl ? customerNameEl.value.trim() : "";
            if (!customerName) {
                alertImpl("고객명을 입력해주세요.");
                return Promise.resolve(null);
            }

            var estimatesToSave = buildEstimatesToSave();
            if (!estimatesToSave) {
                return Promise.resolve(null);
            }

            var notes = collectNotes();
            var couponValue = getCouponValue();
            var shippingState = readShippingState();
            var estimateData;
            try {
                estimateData = buildEstimateData(
                    estimatesToSave,
                    notes,
                    couponValue,
                    shippingState.shippingCost,
                    shippingState.shippingIncluded
                );
            } catch (error) {
                consoleRef.error(error);
                alertImpl(error.message || String(error));
                return Promise.resolve(null);
            }

            var originalText = buttonEl.innerHTML;
            buttonEl.disabled = true;
            buttonEl.innerHTML = '<i class="fas fa-spinner fa-spin"></i> 저장 중...';

            return fetchImpl("/api/wdcalculator/save-estimate", {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                },
                body: JSON.stringify({
                    estimate_id: getCurrentDatabaseEstimateId(),
                    customer_name: customerName,
                    estimate_data: estimateData,
                }),
            })
                .then(function (response) {
                    return response.json();
                })
                .then(function (data) {
                    restoreSaveButton(buttonEl, originalText);

                    if (data.success) {
                        alertImpl(data.message);

                        if (data.estimate_id) {
                            setCurrentDatabaseEstimateId(data.estimate_id);
                            updateHeaderTitle(customerName);
                        }

                        refreshAfterSave(data.estimate_id || getCurrentDatabaseEstimateId());
                        return data;
                    }

                    alertImpl(data.message || "견적 저장 중 오류가 발생했습니다.");
                    return data;
                })
                .catch(function (error) {
                    restoreSaveButton(buttonEl, originalText);
                    consoleRef.error("Error:", error);
                    alertImpl("견적 저장 중 오류가 발생했습니다.");
                    return null;
                });
        }

        function initSaveEstimateButton() {
            var saveEstimateBtn = documentRef.getElementById("saveEstimateBtn");
            if (!saveEstimateBtn) {
                if (consoleRef && typeof consoleRef.warn === "function") {
                    consoleRef.warn("saveEstimateBtn element not found");
                }
                return null;
            }

            var newSaveBtn = saveEstimateBtn.cloneNode(true);
            saveEstimateBtn.parentNode.replaceChild(newSaveBtn, saveEstimateBtn);
            newSaveBtn.addEventListener("click", function () {
                handleSaveEstimate(newSaveBtn);
            });
            return newSaveBtn;
        }

        ns.configure = configure;
        ns.buildEstimateData = buildEstimateData;
        ns.handleSaveEstimate = handleSaveEstimate;
        ns.initSaveEstimateButton = initSaveEstimateButton;
    })(WdCalculatorSaveEstimate);

    window.WdCalculatorSaveEstimate = WdCalculatorSaveEstimate;
})();
