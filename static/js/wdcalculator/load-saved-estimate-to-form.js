(function () {
    var WdCalculatorLoadSavedEstimateToForm = window.WdCalculatorLoadSavedEstimateToForm || {};

    (function (ns) {
        var setCurrentDatabaseEstimateId = function () {};
        var setEstimates = function () {};
        var generateEstimateId = function () {
            return String(Date.now());
        };
        var formatNumber = function (value) {
            return String(value || 0);
        };
        var renderEstimatesList = function () {};
        var ensureBaseComponentsUI = function () {};
        var calculateEstimate = function () {};
        var resetNotesToEmpty = function () {};
        var documentRef = document;
        var confirmImpl = window.confirm ? window.confirm.bind(window) : function () {
            return true;
        };
        var reloadImpl = function () {
            if (window.location && typeof window.location.reload === "function") {
                window.location.reload();
            }
        };

        function configure(options) {
            var opts = options || {};
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
            if (typeof opts.ensureBaseComponentsUI === "function") {
                ensureBaseComponentsUI = opts.ensureBaseComponentsUI;
            }
            if (typeof opts.calculateEstimate === "function") {
                calculateEstimate = opts.calculateEstimate;
            }
            if (typeof opts.resetNotesToEmpty === "function") {
                resetNotesToEmpty = opts.resetNotesToEmpty;
            }
            if (opts.documentRef) {
                documentRef = opts.documentRef;
            }
            if (typeof opts.confirmImpl === "function") {
                confirmImpl = opts.confirmImpl;
            }
            if (typeof opts.reloadImpl === "function") {
                reloadImpl = opts.reloadImpl;
            }
        }

        function ensureResetEstimateButton() {
            var resetBtn = documentRef.getElementById("resetEstimateBtn");
            if (resetBtn) {
                return resetBtn;
            }

            var btnContainer = documentRef.querySelector(".header-primary");
            resetBtn = documentRef.createElement("button");
            resetBtn.id = "resetEstimateBtn";
            resetBtn.className = "btn btn-sm btn-light float-end";
            resetBtn.innerHTML = '<i class="fas fa-undo"></i> 새 견적 작성';
            resetBtn.onclick = function () {
                if (confirmImpl("현재 작성/수정 중인 내용을 초기화하고 새 견적을 작성하시겠습니까?")) {
                    reloadImpl();
                }
            };
            if (btnContainer && typeof btnContainer.appendChild === "function") {
                btnContainer.appendChild(resetBtn);
            }
            return resetBtn;
        }

        function hydrateEstimateItems(estimateData) {
            var globalNotes = estimateData.notes || "";
            return estimateData.estimates.map(function (est) {
                var newId = est.id ? String(est.id) : generateEstimateId();
                return {
                    id: newId,
                    productId: est.productId,
                    productName: est.productName,
                    displayName: est.displayName || ((est.productName || "") + " " + formatNumber(est.widthMm) + "mm"),
                    widthMm: est.widthMm,
                    basePrice: est.basePrice,
                    options: est.options || [],
                    additionalPrice: est.additionalPrice || 0,
                    totalPrice: est.totalPrice || 0,
                    baseComponents: est.baseComponents || null,
                    notes: est.notes || globalNotes,
                };
            });
        }

        function loadEstimateToForm(estimate) {
            setCurrentDatabaseEstimateId(estimate.id);

            var headerTitle = documentRef.querySelector(".header-primary h6");
            if (headerTitle) {
                headerTitle.innerHTML =
                    '<i class="fas fa-edit me-2"></i>견적 수정: ' +
                    estimate.customer_name +
                    ' <span class="badge bg-warning text-dark ms-2">수정모드</span>';
            }

            ensureResetEstimateButton();

            var estimateData = estimate.estimate_data || {};

            var customerNameEl = documentRef.getElementById("customerName");
            if (customerNameEl) {
                customerNameEl.value = estimate.customer_name;
            }

            var couponInput = documentRef.getElementById("globalCouponValue");
            if (couponInput) {
                couponInput.value = estimateData.coupon_discount || 0;
            }

            var shippingCostInput = documentRef.getElementById("shippingCost");
            if (shippingCostInput) {
                shippingCostInput.value = estimateData.shipping_cost || 0;
            }

            var shippingIncludedCheckbox = documentRef.getElementById("shippingIncluded");
            if (shippingIncludedCheckbox) {
                shippingIncludedCheckbox.checked =
                    estimateData.shipping_included !== undefined ? estimateData.shipping_included : true;
            }

            resetNotesToEmpty();
            setEstimates([]);

            if (estimateData.estimates && estimateData.estimates.length > 0) {
                setEstimates(hydrateEstimateItems(estimateData));
                renderEstimatesList();

                var saveBtnAfterLoad = documentRef.getElementById("saveEstimateBtn");
                if (saveBtnAfterLoad) {
                    saveBtnAfterLoad.style.display = "block";
                }

                ensureBaseComponentsUI();
                documentRef.getElementById("additionalOptionsContainer").innerHTML = "";
                documentRef.getElementById("productInfo").style.display = "none";
                documentRef.getElementById("baseEstimateSection").style.display = "none";
                documentRef.getElementById("addEstimateBtn").innerHTML = '<i class="fas fa-plus"></i> 견적 추가';
                documentRef.getElementById("addEstimateBtn").style.display = "none";
                calculateEstimate();
            }
        }

        ns.configure = configure;
        ns.loadEstimateToForm = loadEstimateToForm;
    })(WdCalculatorLoadSavedEstimateToForm);

    window.WdCalculatorLoadSavedEstimateToForm = WdCalculatorLoadSavedEstimateToForm;
})();
