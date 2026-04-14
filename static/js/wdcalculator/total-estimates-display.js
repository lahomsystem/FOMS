(function () {
    function fallbackFormatNumber(num) {
        return Math.round(Number(num) || 0).toLocaleString("ko-KR");
    }

    var WdCalculatorTotalEstimatesDisplay = window.WdCalculatorTotalEstimatesDisplay || {};

    (function (ns) {
        var getEstimates = function () {
            return [];
        };
        var getEditingEstimateId = function () {
            return null;
        };
        var getCouponValue = function () {
            return 0;
        };
        var resolveAggregateTotals = function () {
            throw new Error("WDCalculator total estimates display helper is not configured.");
        };
        var collectNotes = function () {
            return "";
        };
        var formatNumber = window.formatNumber || fallbackFormatNumber;
        var applyFinalPriceStyle = function () {};
        var applyCouponDiscountStyle = function () {};
        var documentRef = document;
        var alertImpl = window.alert ? window.alert.bind(window) : function () {};
        var consoleRef = window.console || console;

        function configure(options) {
            var opts = options || {};
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
        }

        function resetCurrentSummaryForEmptyState() {
            documentRef.getElementById("totalBasePrice").textContent = "0원";
            documentRef.getElementById("totalAdditionalPrice").textContent = "0원";
            documentRef.getElementById("totalPrice").textContent = "0원";
            documentRef.getElementById("finalPrice").textContent = "0원";
            documentRef.getElementById("baseEstimateDetail").textContent = "";
            documentRef.getElementById("additionalOptionsDetail").textContent = "";
        }

        function buildBaseDetails(estimates) {
            return estimates
                .map(function (estimate) {
                    return estimate.productName + " " + formatNumber(estimate.widthMm) + "mm";
                })
                .join(", ");
        }

        function buildAdditionalDetails(estimates) {
            var optionMap = new Map();

            estimates.forEach(function (estimate) {
                (estimate.options || []).forEach(function (option) {
                    var amount = (option.price || 0) * (option.quantity || 1);
                    if (optionMap.has(option.name)) {
                        var previous = optionMap.get(option.name);
                        optionMap.set(option.name, {
                            quantity: previous.quantity + (option.quantity || 0),
                            amount: previous.amount + amount,
                        });
                    } else {
                        optionMap.set(option.name, {
                            quantity: option.quantity || 0,
                            amount: amount,
                        });
                    }
                });
            });

            return Array.from(optionMap.entries())
                .map(function (entry) {
                    var name = entry[0];
                    var value = entry[1];
                    return name + " × " + value.quantity + " (" + formatNumber(value.amount) + "원)";
                })
                .join(", ");
        }

        function updateNotesDisplay() {
            var notesDisplaySection = documentRef.getElementById("notesDisplaySection");
            var notesDisplay = documentRef.getElementById("notesDisplay");
            var notes = collectNotes();

            if (notes && notesDisplaySection && notesDisplay) {
                notesDisplay.textContent = notes;
                notesDisplaySection.style.display = "block";
            } else if (notesDisplaySection) {
                notesDisplaySection.style.display = "none";
            }
        }

        function updateCurrentSummary(agg, couponValue, baseDetails, additionalDetails, couponInfoText) {
            documentRef.getElementById("totalBasePrice").textContent = formatNumber(agg.totalBasePrice) + "원";
            documentRef.getElementById("totalAdditionalPrice").textContent =
                formatNumber(agg.totalAdditionalPrice) + "원";
            documentRef.getElementById("totalPrice").textContent = formatNumber(agg.totalPrice) + "원";

            var finalPriceEl = documentRef.getElementById("finalPrice");
            if (finalPriceEl) {
                finalPriceEl.textContent = formatNumber(agg.finalPrice) + "원";
                applyFinalPriceStyle(finalPriceEl);
            }

            var couponInfoEl = documentRef.getElementById("couponInfo");
            if (couponInfoEl) {
                couponInfoEl.textContent = couponInfoText;
                applyCouponDiscountStyle(couponInfoEl, couponValue > 0);
            }

            documentRef.getElementById("baseEstimateDetail").textContent = baseDetails;
            documentRef.getElementById("additionalOptionsDetail").textContent = additionalDetails || "";
            updateNotesDisplay();
        }

        function updateOverallSummary(agg, couponValue) {
            var totalEstimatesSummaryEl = documentRef.getElementById("totalEstimatesSummary");
            if (totalEstimatesSummaryEl) {
                totalEstimatesSummaryEl.style.display = "block";
            }

            documentRef.getElementById("totalAllBasePrice").textContent =
                formatNumber(agg.totalBasePrice) + "원";
            documentRef.getElementById("totalAllAdditionalPrice").textContent =
                formatNumber(agg.totalAdditionalPrice) + "원";

            var totalAllPriceEl = documentRef.getElementById("totalAllPrice");
            if (totalAllPriceEl) {
                totalAllPriceEl.textContent = formatNumber(agg.totalPrice) + "원";
            }

            var totalAllFinalPriceEl = documentRef.getElementById("totalAllFinalPrice");
            if (totalAllFinalPriceEl) {
                totalAllFinalPriceEl.textContent = formatNumber(agg.finalPrice) + "원";
                applyFinalPriceStyle(totalAllFinalPriceEl);
            }

            var totalAllCouponInfoEl = documentRef.getElementById("totalAllCouponInfo");
            if (totalAllCouponInfoEl) {
                totalAllCouponInfoEl.textContent =
                    couponValue > 0
                        ? formatNumber(couponValue) + "할인(쿠폰적용)"
                        : "쿠폰가 미적용";
                applyCouponDiscountStyle(totalAllCouponInfoEl, couponValue > 0);
            }
        }

        function calculateTotalEstimates() {
            var estimates = getEstimates() || [];
            if (!estimates.length) {
                resetCurrentSummaryForEmptyState();
                return;
            }

            var couponValue = getCouponValue();
            var shippingCostInput = documentRef.getElementById("shippingCost");
            var shippingCost = shippingCostInput ? parseFloat(shippingCostInput.value) || 0 : 0;
            var shippingIncludedCheckbox = documentRef.getElementById("shippingIncluded");
            var shippingIncluded = shippingIncludedCheckbox ? shippingIncludedCheckbox.checked : true;

            var agg;
            try {
                agg = resolveAggregateTotals(estimates, couponValue, shippingCost, shippingIncluded);
            } catch (error) {
                consoleRef.error(error);
                alertImpl(error.message || String(error));
                return;
            }

            var couponInfoText =
                couponValue > 0 ? formatNumber(couponValue) + "원 할인" : "쿠폰가 미적용";
            var baseDetails = buildBaseDetails(estimates);
            var additionalDetails = buildAdditionalDetails(estimates);

            if (!getEditingEstimateId()) {
                updateCurrentSummary(agg, couponValue, baseDetails, additionalDetails, couponInfoText);
            }

            updateOverallSummary(agg, couponValue);
        }

        ns.calculateTotalEstimates = calculateTotalEstimates;
        ns.configure = configure;
    })(WdCalculatorTotalEstimatesDisplay);

    window.WdCalculatorTotalEstimatesDisplay = WdCalculatorTotalEstimatesDisplay;
})();
