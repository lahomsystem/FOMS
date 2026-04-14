(function () {
    var WdCalculatorCurrentEstimateOrchestration =
        window.WdCalculatorCurrentEstimateOrchestration || {};

    (function (ns) {
        var getProducts = function () {
            return [];
        };
        var getEditingEstimateId = function () {
            return null;
        };
        var getEstimates = function () {
            return [];
        };
        var readBaseComponentsFromUI = function () {
            return [];
        };
        var readAdditionalOptionRowsFromUI = function () {
            return [];
        };
        var resolveCurrentEstimateMath = function () {
            return {
                basePriceCalculate: 0,
                basePriceCollect: 0,
                baseEstimateDetail: "",
                normalizedComponents: [],
                displayParts: [],
                options: [],
                additionalPrice: 0,
                additionalOptionsDetail: "",
                totalPriceCalculate: 0,
                totalPriceCollect: 0,
            };
        };
        var getCouponValue = function () {
            return 0;
        };
        var formatNumber = function (value) {
            return String(value || 0);
        };
        var applyFinalPriceStyle = function () {};
        var applyCouponDiscountStyle = function () {};
        var collectNotes = function () {
            return "";
        };
        var documentRef = document;
        var alertImpl = typeof window.alert === "function" ? window.alert.bind(window) : function () {};
        var consoleRef = window.console || console;

        function configure(options) {
            var opts = options || {};
            if (typeof opts.getProducts === "function") {
                getProducts = opts.getProducts;
            }
            if (typeof opts.getEditingEstimateId === "function") {
                getEditingEstimateId = opts.getEditingEstimateId;
            }
            if (typeof opts.getEstimates === "function") {
                getEstimates = opts.getEstimates;
            }
            if (typeof opts.readBaseComponentsFromUI === "function") {
                readBaseComponentsFromUI = opts.readBaseComponentsFromUI;
            }
            if (typeof opts.readAdditionalOptionRowsFromUI === "function") {
                readAdditionalOptionRowsFromUI = opts.readAdditionalOptionRowsFromUI;
            }
            if (typeof opts.resolveCurrentEstimateMath === "function") {
                resolveCurrentEstimateMath = opts.resolveCurrentEstimateMath;
            }
            if (typeof opts.getCouponValue === "function") {
                getCouponValue = opts.getCouponValue;
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
            if (typeof opts.collectNotes === "function") {
                collectNotes = opts.collectNotes;
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
        }

        function logError(error) {
            if (consoleRef && typeof consoleRef.error === "function") {
                consoleRef.error(error);
            }
        }

        function resolveMathState() {
            var baseComponents = readBaseComponentsFromUI();
            if (!baseComponents.length) {
                return {
                    hasBaseComponents: false,
                };
            }

            var optionRows = readAdditionalOptionRowsFromUI();
            try {
                return {
                    hasBaseComponents: true,
                    math: resolveCurrentEstimateMath(baseComponents, getProducts(), optionRows),
                };
            } catch (error) {
                logError(error);
                alertImpl(error.message || String(error));
                return {
                    hasBaseComponents: true,
                    error: error,
                };
            }
        }

        function resetCalculatedDisplay() {
            documentRef.getElementById("baseEstimateSection").style.display = "none";
            documentRef.getElementById("totalBasePrice").textContent = "0원";
            documentRef.getElementById("totalAdditionalPrice").textContent = "0원";
            documentRef.getElementById("totalPrice").textContent = "0원";
            documentRef.getElementById("finalPrice").textContent = "0원";
            documentRef.getElementById("baseEstimateDetail").textContent = "";
            documentRef.getElementById("additionalOptionsDetail").textContent = "";
        }

        function syncActionButtons(basePrice, additionalPrice) {
            var addEstimateBtn = documentRef.getElementById("addEstimateBtn");
            var saveEstimateBtn = documentRef.getElementById("saveEstimateBtn");
            var estimates = getEstimates() || [];

            if (getEditingEstimateId()) {
                addEstimateBtn.style.display = "block";
                return;
            }

            if (basePrice > 0 || additionalPrice > 0) {
                addEstimateBtn.innerHTML = '<i class="fas fa-plus"></i> 견적 추가';
                addEstimateBtn.style.display = "block";
                if (estimates.length > 0 || basePrice > 0 || additionalPrice > 0) {
                    saveEstimateBtn.style.display = "block";
                }
                return;
            }

            addEstimateBtn.style.display = "none";
            if (estimates.length === 0) {
                saveEstimateBtn.style.display = "none";
            }
        }

        function calculateEstimate() {
            var state = resolveMathState();
            if (!state.hasBaseComponents) {
                resetCalculatedDisplay();
                return;
            }
            if (state.error) {
                return;
            }

            var math = state.math;
            var basePrice = math.basePriceCalculate;
            var baseEstimateDetail = math.baseEstimateDetail;
            if (!baseEstimateDetail) {
                documentRef.getElementById("baseEstimateSection").style.display = "none";
                return;
            }

            documentRef.getElementById("baseEstimateDetail").textContent = baseEstimateDetail;

            var additionalPrice = math.additionalPrice;
            var additionalOptionsDetail = math.additionalOptionsDetail || "";
            documentRef.getElementById("additionalOptionsDetail").textContent = additionalOptionsDetail;

            var totalPrice = math.totalPriceCalculate;
            var couponValue = getCouponValue();
            var finalPrice = Math.max(0, totalPrice - couponValue);
            var couponInfoText =
                couponValue > 0 ? formatNumber(couponValue) + "원 할인" : "쿠폰가 미적용";

            documentRef.getElementById("baseEstimateSection").style.display = "block";
            documentRef.getElementById("basePriceDisplay").textContent = formatNumber(basePrice) + "원";
            documentRef.getElementById("totalBasePrice").textContent = formatNumber(basePrice) + "원";
            documentRef.getElementById("totalAdditionalPrice").textContent =
                formatNumber(additionalPrice) + "원";
            documentRef.getElementById("totalPrice").textContent = formatNumber(totalPrice) + "원";

            var finalPriceEl = documentRef.getElementById("finalPrice");
            if (finalPriceEl) {
                finalPriceEl.textContent = formatNumber(finalPrice) + "원";
                applyFinalPriceStyle(finalPriceEl);
            }

            var couponInfoEl = documentRef.getElementById("couponInfo");
            if (couponInfoEl) {
                couponInfoEl.textContent = couponInfoText;
                applyCouponDiscountStyle(couponInfoEl, couponValue > 0);
            }

            syncActionButtons(basePrice, additionalPrice);
        }

        function collectCurrentEstimate() {
            var state = resolveMathState();
            if (!state.hasBaseComponents || state.error) {
                return null;
            }

            var math = state.math;
            var normalizedComponents = math.normalizedComponents;
            var displayParts = math.displayParts;

            if (!normalizedComponents.length) {
                return null;
            }

            var defaultDisplayName =
                normalizedComponents.length >= 2
                    ? "복합 기본 (" + normalizedComponents.length + "건)"
                    : displayParts[0] || "기본 구성";

            return {
                productId: null,
                productName:
                    normalizedComponents.length >= 2
                        ? "복합 기본"
                        : displayParts[0] || "기본 구성",
                displayName: defaultDisplayName,
                widthMm: 0,
                basePrice: math.basePriceCollect,
                options: math.options,
                additionalPrice: math.additionalPrice,
                totalPrice: math.totalPriceCollect,
                baseComponents: normalizedComponents,
                notes: collectNotes(),
            };
        }

        ns.configure = configure;
        ns.calculateEstimate = calculateEstimate;
        ns.collectCurrentEstimate = collectCurrentEstimate;
    })(WdCalculatorCurrentEstimateOrchestration);

    window.WdCalculatorCurrentEstimateOrchestration = WdCalculatorCurrentEstimateOrchestration;
})();
