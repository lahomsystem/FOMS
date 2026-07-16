/* --- included: current-estimate-math.js --- */
/**
 * Pure current-estimate pricing for WDCalculator: baseComponents + products + option rows.
 * Mirrors the historical inline current-estimate math while keeping fee-bearing rows
 * collectible even when base unit pricing is unresolved.
 *
 * @param {Array<object>} baseComponents - from readBaseComponentsFromUI()
 * @param {Array<object>} products - product catalog
 * @param {Array<{ name: string, price: number, quantity: number }>} optionRows - from DOM (valid rows only)
 * @param {(n: number) => string} [formatNumber] - defaults to global.formatNumber or ko-KR integer format
 * @returns {{
 *   basePriceCalculate: number,
 *   basePriceCollect: number,
 *   baseEstimateDetail: string,
 *   normalizedComponents: object[],
 *   displayParts: string[],
 *   options: { name: string, price: number, quantity: number }[],
 *   additionalPrice: number,
 *   additionalOptionsDetail: string,
 *   totalPriceCalculate: number,
 *   totalPriceCollect: number
 * }}
 */
(function (global) {
    "use strict";

    function defaultFormatNumber(num) {
        return Math.round(Number(num) || 0).toLocaleString("ko-KR");
    }

    function resolveFormatNumber(fmt) {
        if (typeof fmt === "function") {
            return fmt;
        }
        var g = global.formatNumber;
        if (typeof g === "function") {
            return g;
        }
        return defaultFormatNumber;
    }

    function findProduct(products, productId) {
        var list = products || [];
        if (productId === null || productId === undefined || productId === "") {
            return null;
        }
        var pid = Number(productId);
        var pidIsNum = !isNaN(pid);
        for (var i = 0; i < list.length; i++) {
            var row = list[i];
            if (!row) {
                continue;
            }
            if (pidIsNum && Number(row.id) === pid) {
                return row;
            }
            if (String(row.id) === String(productId)) {
                return row;
            }
        }
        return null;
    }

    /**
     * @param {Array<object>} baseComponents
     * @param {Array<object>} products
     * @param {(n: number) => string} formatNumber
     */
    function attachWidthFields(compData, comp) {
        var widthInput = String((comp && comp.widthInput) || "").trim();
        if (widthInput) {
            compData.widthInput = widthInput;
        }
        return compData;
    }

    function widthLabel(comp, formatNumber) {
        if (typeof formatBaseWidthDisplay === "function") {
            return formatBaseWidthDisplay(comp, formatNumber);
        }
        var w = Number(comp && comp.widthMm) || 0;
        return w > 0 ? formatNumber(w) + "mm" : "";
    }

    function computeBaseLayer(baseComponents, products, formatNumber) {
        var basePriceCalculate = 0;
        var basePriceCollect = 0;
        var detailLines = [];
        var normalizedComponents = [];
        var displayParts = [];

        for (var c = 0; c < baseComponents.length; c++) {
            var comp = baseComponents[c];
            var widthMm = Number(comp.widthMm) || 0;
            var additionalFees = comp.additionalFees || [];
            var compPrice = 0;
            var compData = {};

            if (widthMm > 0) {
                if (comp.mode === "manual") {
                    var pricingType = (comp.manualPricing && comp.manualPricing.pricing_type) || "30cm";
                    if (pricingType === "1m") {
                        var price1m = Number(comp.manualPricing && comp.manualPricing.price_1m) || 0;
                        if (price1m > 0) {
                            var meters = widthMm / 1000;
                            compPrice = meters * price1m;
                            compData = attachWidthFields(
                                {
                                mode: "manual",
                                widthMm: widthMm,
                                additionalFees: additionalFees,
                                manualPricing: { pricing_type: "1m", price_1m: price1m },
                                manualName: comp.manualName || "",
                                },
                                comp
                            );
                            var label1m = (comp.manualName && String(comp.manualName).trim()) || "직접입력(1m)";
                            detailLines.push(label1m + " " + widthLabel(compData, formatNumber));
                            displayParts.push(label1m + " " + widthLabel(compData, formatNumber));
                        }
                    } else {
                        var price30 = Number(comp.manualPricing && comp.manualPricing.price_30cm) || 0;
                        var price1 = Number(comp.manualPricing && comp.manualPricing.price_1cm) || 0;
                        if (price30 > 0 && price1 > 0) {
                            var units30cm = Math.floor(widthMm / 300);
                            var remainderMm = widthMm % 300;
                            var units1cm = Math.floor(remainderMm / 10);
                            compPrice = units30cm * price30 + units1cm * price1;
                            compData = attachWidthFields(
                                {
                                mode: "manual",
                                widthMm: widthMm,
                                additionalFees: additionalFees,
                                manualPricing: {
                                    pricing_type: "30cm",
                                    price_30cm: price30,
                                    price_1cm: price1,
                                },
                                manualName: comp.manualName || "",
                                },
                                comp
                            );
                            var label30 = (comp.manualName && String(comp.manualName).trim()) || "직접입력(30cm)";
                            detailLines.push(label30 + " " + widthLabel(compData, formatNumber));
                            displayParts.push(label30 + " " + widthLabel(compData, formatNumber));
                        }
                    }
                } else {
                    var productId = Number(comp.productId) || 0;
                    if (productId) {
                        var product = findProduct(products, productId);
                        if (product) {
                            if (product.pricing_type === "1m") {
                                compPrice = (widthMm / 1000) * (product.price_1m || 0);
                            } else if (product.pricing_type === "30cm") {
                                var u30 = Math.floor(widthMm / 300);
                                var rem = widthMm % 300;
                                var u1 = Math.floor(rem / 10);
                                compPrice =
                                    u30 * (product.price_30cm || 0) + u1 * (product.price_1cm || 0);
                            }
                            compData = attachWidthFields(
                                {
                                mode: "select",
                                productId: productId,
                                widthMm: widthMm,
                                additionalFees: additionalFees,
                                },
                                comp
                            );
                            detailLines.push(product.name + " " + widthLabel(compData, formatNumber));
                            displayParts.push(product.name + " " + widthLabel(compData, formatNumber));
                        }
                    }
                }
            }

            var totalAdditionalFee = 0;
            for (var f = 0; f < additionalFees.length; f++) {
                totalAdditionalFee += Number(additionalFees[f].amount) || 0;
            }
            if (Object.keys(compData).length === 0 && totalAdditionalFee > 0) {
                compData = attachWidthFields(
                    {
                    mode: comp.mode || "select",
                    widthMm: widthMm,
                    additionalFees: additionalFees,
                    },
                    comp
                );
                if (comp.mode === "manual" && comp.manualPricing) {
                    compData.manualPricing = comp.manualPricing;
                    compData.manualName = comp.manualName || "";
                } else {
                    compData.productId = comp.productId || null;
                }
                if (widthMm <= 0) {
                    for (var j = 0; j < additionalFees.length; j++) {
                        var feeA = additionalFees[j];
                        var amtA = Number(feeA.amount) || 0;
                        if (amtA > 0) {
                            var feeLabelA = feeA.name ? feeA.name + " " : "추가금 ";
                            displayParts.push(feeLabelA + formatNumber(amtA) + "원");
                        }
                    }
                }
            }

            for (var k = 0; k < additionalFees.length; k++) {
                var fee = additionalFees[k];
                var amount = Number(fee.amount) || 0;
                if (amount > 0) {
                    compPrice += amount;
                    var feeLabel = fee.name ? fee.name + " " : "추가금 ";
                    detailLines.push("+ " + feeLabel + formatNumber(amount) + "원");
                    if (widthMm > 0) {
                        displayParts.push("+ " + feeLabel + formatNumber(amount) + "원");
                    }
                }
            }

            basePriceCalculate += compPrice;

            if (Object.keys(compData).length > 0) {
                basePriceCollect += compPrice;
                normalizedComponents.push(compData);
            }
        }

        return {
            basePriceCalculate: basePriceCalculate,
            basePriceCollect: basePriceCollect,
            baseEstimateDetail: detailLines.join(" / "),
            normalizedComponents: normalizedComponents,
            displayParts: displayParts,
        };
    }

    /**
     * @param {Array<{ name: string, price: number, quantity: number }>} optionRows
     * @param {(n: number) => string} formatNumber
     */
    function computeOptionsLayer(optionRows, formatNumber) {
        var rows = optionRows || [];
        var additionalPrice = 0;
        var options = [];
        var additionalOptionsList = [];

        for (var i = 0; i < rows.length; i++) {
            var row = rows[i];
            if (!row || !row.name) {
                continue;
            }
            var price = Number(row.price) || 0;
            var quantity = Number(row.quantity) || 1;
            if (price <= 0) {
                continue;
            }
            var amount = price * quantity;
            additionalPrice += amount;
            options.push({ name: row.name, price: price, quantity: quantity });
            additionalOptionsList.push({ name: row.name, quantity: quantity, amount: amount });
        }

        var optionMap = new Map();
        for (var a = 0; a < additionalOptionsList.length; a++) {
            var opt = additionalOptionsList[a];
            if (optionMap.has(opt.name)) {
                var prev = optionMap.get(opt.name);
                optionMap.set(opt.name, {
                    quantity: prev.quantity + opt.quantity,
                    amount: prev.amount + opt.amount,
                });
            } else {
                optionMap.set(opt.name, { quantity: opt.quantity, amount: opt.amount });
            }
        }

        var parts = [];
        optionMap.forEach(function (v, name) {
            parts.push(name + " × " + v.quantity + " (" + formatNumber(v.amount) + "원)");
        });
        var additionalOptionsDetail = parts.join(", ");

        return {
            additionalPrice: additionalPrice,
            options: options,
            additionalOptionsDetail: additionalOptionsDetail,
        };
    }

    function validateBaseWidthComponents(baseComponents) {
        var list = baseComponents || [];
        for (var i = 0; i < list.length; i++) {
            var comp = list[i];
            var raw = String((comp && comp.widthInput) || "").trim();
            if (!raw) {
                continue;
            }
            var widthMm = Number(comp && comp.widthMm) || 0;
            if (widthMm > 0) {
                continue;
            }
            if (/^0+(\.0+)?$/.test(raw.replace(/\s/g, ""))) {
                continue;
            }
            throw new Error("가로(mm) 형식을 확인하세요: " + raw);
        }
    }

    function wdcComputeCurrentEstimateMath(baseComponents, products, optionRows, formatNumber) {
        var fmt = resolveFormatNumber(formatNumber);
        validateBaseWidthComponents(baseComponents);
        var baseLayer = computeBaseLayer(baseComponents, products, fmt);
        var optLayer = computeOptionsLayer(optionRows, fmt);
        var totalPriceCalculate = baseLayer.basePriceCalculate + optLayer.additionalPrice;
        var totalPriceCollect = baseLayer.basePriceCollect + optLayer.additionalPrice;
        return {
            basePriceCalculate: baseLayer.basePriceCalculate,
            basePriceCollect: baseLayer.basePriceCollect,
            baseEstimateDetail: baseLayer.baseEstimateDetail,
            normalizedComponents: baseLayer.normalizedComponents,
            displayParts: baseLayer.displayParts,
            options: optLayer.options,
            additionalPrice: optLayer.additionalPrice,
            additionalOptionsDetail: optLayer.additionalOptionsDetail,
            totalPriceCalculate: totalPriceCalculate,
            totalPriceCollect: totalPriceCollect,
        };
    }

    global.wdcComputeCurrentEstimateMath = wdcComputeCurrentEstimateMath;
})(typeof window !== "undefined" ? window : globalThis);

/* --- included: estimate-totals.js --- */
/**
 * Pure aggregate totals for the WDCalculator multi-estimate summary.
 *
 * For each estimate, sums `basePrice` into `totalBasePrice` and `additionalPrice` into
 * `totalAdditionalPrice`. Then `totalPrice = totalBasePrice + totalAdditionalPrice`.
 * Coupon applies once to that aggregate `totalPrice`. Shipping only adjusts the
 * aggregate `finalPrice` (included adds `shippingCost`; excluded leaves post-coupon total).
 *
 * Non-finite numeric inputs are treated as 0 so totals do not become NaN.
 *
 * @param {Array<{ basePrice?: number, additionalPrice?: number }>} estimates
 * @param {number} couponValue - raw coupon discount (same units as prices)
 * @param {number} shippingCost
 * @param {boolean} shippingIncluded - when true, finalPrice includes shippingCost
 * @returns {{
 *   totalBasePrice: number,
 *   totalAdditionalPrice: number,
 *   totalPrice: number,
 *   totalEstimate: number,
 *   finalPrice: number
 * }}
 */
(function (global) {
    "use strict";

    function finiteOrZero(v) {
        var n = Number(v);
        return Number.isFinite(n) ? n : 0;
    }

    function wdcComputeAggregateTotals(estimates, couponValue, shippingCost, shippingIncluded) {
        var list = estimates || [];
        var totalBasePrice = 0;
        var totalAdditionalPrice = 0;
        for (var i = 0; i < list.length; i++) {
            var est = list[i];
            if (est == null) {
                continue;
            }
            totalBasePrice += finiteOrZero(est.basePrice);
            totalAdditionalPrice += finiteOrZero(est.additionalPrice);
        }
        var totalPrice = totalBasePrice + totalAdditionalPrice;
        var totalEstimate = Math.max(0, totalPrice - finiteOrZero(couponValue));
        var ship = finiteOrZero(shippingCost);
        var included = shippingIncluded !== false;
        var finalPrice = included ? totalEstimate + ship : totalEstimate;
        return {
            totalBasePrice: totalBasePrice,
            totalAdditionalPrice: totalAdditionalPrice,
            totalPrice: totalPrice,
            totalEstimate: totalEstimate,
            finalPrice: finalPrice,
        };
    }

    global.wdcComputeAggregateTotals = wdcComputeAggregateTotals;
})(typeof window !== "undefined" ? window : globalThis);

/* --- included: calculation-resolvers.js --- */
(function () {
    var WdCalculatorCalculationResolvers = window.WdCalculatorCalculationResolvers || {};

    (function (ns) {
        function resolveCurrentEstimateMath(baseComponents, products, optionRows) {
            var fn = window.wdcComputeCurrentEstimateMath;
            if (typeof fn !== "function") {
                throw new Error(
                    "WDCalculator: current estimate math helper is not loaded (js/wdcalculator/pricing-core.js). Please reload the page."
                );
            }
            return fn(baseComponents, products, optionRows);
        }

        function resolveAggregateTotals(estimatesList, couponValue, shippingCost, shippingIncluded) {
            var fn = window.wdcComputeAggregateTotals;
            if (typeof fn !== "function") {
                throw new Error(
                    "WDCalculator: aggregate totals helper is not loaded (js/wdcalculator/pricing-core.js). Please reload the page."
                );
            }
            return fn(estimatesList, couponValue, shippingCost, shippingIncluded);
        }

        ns.resolveCurrentEstimateMath = resolveCurrentEstimateMath;
        ns.resolveAggregateTotals = resolveAggregateTotals;
    })(WdCalculatorCalculationResolvers);

    window.WdCalculatorCalculationResolvers = WdCalculatorCalculationResolvers;
})();

/* --- included: current-estimate-orchestration.js --- */
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
            var unitMeta = documentRef.getElementById("currentQuoteUnitPriceMeta");
            if (unitMeta) {
                unitMeta.textContent = "";
                unitMeta.classList.add("text-muted");
            }
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

            var upMeta = window.WdCalculatorUnitPriceMeta;
            var unitSlot = documentRef.getElementById("currentQuoteUnitPriceMeta");
            if (upMeta && unitSlot && typeof upMeta.deriveUnitPriceSummaryFromBaseComponents === "function") {
                var bcForMeta = readBaseComponentsFromUI();
                var unitSummary = upMeta.deriveUnitPriceSummaryFromBaseComponents(
                    bcForMeta,
                    getProducts(),
                    formatNumber
                );
                upMeta.fillElementWithLines(unitSlot, unitSummary, { fallbackText: "단가 정보 없음" });
            }

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

/* --- included: total-estimates-display.js --- */
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
            var shippingCost = shippingCostInput
                ? parseFloat(String(shippingCostInput.value).replace(/,/g, "")) || 0
                : 0;
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

/* --- included: coupon-shipping-wiring.js --- */
/**
 * WDCalculator coupon/shipping recalculation listener wiring.
 * Host keeps totals math and mutable estimate state.
 */
var WdCalculatorCouponShippingWiring = window.WdCalculatorCouponShippingWiring || {};

(function (ns) {
    var defaultCouponValue = 11000;
    var getEstimates = function () {
        return [];
    };
    var calculateEstimate = function () {};
    var calculateTotalEstimates = function () {};
    var getCouponValue = function () {
        return defaultCouponValue;
    };

    function configure(opts) {
        if (opts && typeof opts.defaultCouponValue === "number") {
            defaultCouponValue = opts.defaultCouponValue;
        }
        if (opts && typeof opts.getEstimates === "function") {
            getEstimates = opts.getEstimates;
        }
        if (opts && typeof opts.calculateEstimate === "function") {
            calculateEstimate = opts.calculateEstimate;
        }
        if (opts && typeof opts.calculateTotalEstimates === "function") {
            calculateTotalEstimates = opts.calculateTotalEstimates;
        }
        if (opts && typeof opts.getCouponValue === "function") {
            getCouponValue = opts.getCouponValue;
        }
    }

    function shouldRecalculateTotals() {
        return (getEstimates() || []).length > 0;
    }

    function bindShippingCostInput() {
        var shippingCostInputField = document.getElementById("shippingCost");
        if (shippingCostInputField) {
            shippingCostInputField.addEventListener("input", function () {
                if (shouldRecalculateTotals()) {
                    calculateTotalEstimates();
                }
            });
            shippingCostInputField.addEventListener("change", function () {
                if (shouldRecalculateTotals()) {
                    calculateTotalEstimates();
                }
            });
            console.log("배송비 입력 필드 이벤트 리스너 등록 완료");
        }
    }

    function bindShippingIncludedCheckbox() {
        var shippingIncludedCheckbox = document.getElementById("shippingIncluded");
        if (shippingIncludedCheckbox) {
            shippingIncludedCheckbox.addEventListener("change", function () {
                if (shouldRecalculateTotals()) {
                    calculateTotalEstimates();
                }
            });
            console.log("배송비 포함 여부 체크박스 이벤트 리스너 등록 완료");
        }
    }

    function bindCouponInput() {
        var couponInputField = document.getElementById("globalCouponValue");
        if (couponInputField) {
            if (!couponInputField.value || couponInputField.value === "0") {
                couponInputField.value = defaultCouponValue;
                console.log("쿠폰 입력 필드 초기값 설정:", defaultCouponValue);
            }

            couponInputField.addEventListener("input", function () {
                var newValue = this.value;
                console.log("쿠폰 값 변경됨 (input):", newValue);
                setTimeout(function () {
                    var currentValue = getCouponValue();
                    console.log("재계산 실행 - 쿠폰 값:", currentValue);
                    calculateEstimate();
                    if (shouldRecalculateTotals()) {
                        calculateTotalEstimates();
                    }
                }, 100);
            });

            couponInputField.addEventListener("change", function () {
                var newValue = this.value;
                console.log("쿠폰 값 확정됨 (change):", newValue);
                var currentValue = getCouponValue();
                console.log("재계산 실행 - 쿠폰 값:", currentValue);
                calculateEstimate();
                if (shouldRecalculateTotals()) {
                    calculateTotalEstimates();
                }
            });

            couponInputField.addEventListener("blur", function () {
                var newValue = this.value;
                console.log("쿠폰 입력 필드 포커스 아웃 (blur):", newValue);
                var currentValue = getCouponValue();
                console.log("재계산 실행 - 쿠폰 값:", currentValue);
                calculateEstimate();
                if (shouldRecalculateTotals()) {
                    calculateTotalEstimates();
                }
            });

            console.log("쿠폰 입력 필드 이벤트 리스너 등록 완료, 현재 값:", couponInputField.value);

            setTimeout(function () {
                console.log("초기 로드 후 계산 실행");
                calculateEstimate();
                if (shouldRecalculateTotals()) {
                    calculateTotalEstimates();
                }
            }, 500);
        } else {
            console.error("쿠폰 입력 필드를 찾을 수 없습니다!");
        }
    }

    function initCouponShippingWiring() {
        bindShippingCostInput();
        bindShippingIncludedCheckbox();
        bindCouponInput();
    }

    ns.configure = configure;
    ns.initCouponShippingWiring = initCouponShippingWiring;
})(WdCalculatorCouponShippingWiring);

window.WdCalculatorCouponShippingWiring = WdCalculatorCouponShippingWiring;

/* --- included: unit-price-meta.js --- */
(function () {
    var WdCalculatorUnitPriceMeta = window.WdCalculatorUnitPriceMeta || {};

    (function (ns) {
        var LS_KEY = "foms.wdcalculator.unitPriceMetaVisible";

        function isUnitPriceMetaVisible() {
            try {
                var raw = window.localStorage.getItem(LS_KEY);
                if (raw === null || raw === undefined) {
                    return true;
                }
                return raw === "1" || raw === "true";
            } catch (e) {
                return true;
            }
        }

        function setUnitPriceMetaVisible(visible) {
            try {
                window.localStorage.setItem(LS_KEY, visible ? "1" : "0");
            } catch (e) {
                /* ignore */
            }
        }

        function defaultFormatNumber(num) {
            return Math.round(Number(num) || 0).toLocaleString("ko-KR");
        }

        function resolveFormatNumber(fmt) {
            return typeof fmt === "function" ? fmt : defaultFormatNumber;
        }

        function findProduct(products, productId) {
            var list = products || [];
            if (productId === null || productId === undefined || productId === "") {
                return null;
            }
            var pid = Number(productId);
            var pidIsNum = !isNaN(pid);
            for (var i = 0; i < list.length; i++) {
                var row = list[i];
                if (!row) {
                    continue;
                }
                if (pidIsNum && Number(row.id) === pid) {
                    return row;
                }
                if (String(row.id) === String(productId)) {
                    return row;
                }
            }
            return null;
        }

        function formatCatalogUnitPrices(product, formatNumber) {
            if (!product) {
                return null;
            }
            var p1m = Number(product.price_1m) || 0;
            var p30 = Number(product.price_30cm) || 0;
            var p1c = Number(product.price_1cm) || 0;
            var pt = String(product.pricing_type || "");

            if (pt === "1m") {
                if (p1m <= 0) {
                    return null;
                }
                return "1m " + formatNumber(p1m) + "원";
            }
            if (pt === "30cm") {
                if (p30 <= 0 || p1c <= 0) {
                    return null;
                }
                return "30cm " + formatNumber(p30) + "원 / 1cm " + formatNumber(p1c) + "원";
            }
            if (p30 > 0 && p1c > 0) {
                return "30cm " + formatNumber(p30) + "원 / 1cm " + formatNumber(p1c) + "원";
            }
            if (p1m > 0) {
                return "1m " + formatNumber(p1m) + "원";
            }
            return null;
        }

        function formatManualUnitPrices(manualPricing, formatNumber) {
            if (!manualPricing) {
                return null;
            }
            var pt = manualPricing.pricing_type || "30cm";
            if (pt === "1m") {
                var p1m = Number(manualPricing.price_1m) || 0;
                if (p1m <= 0) {
                    return null;
                }
                return "1m " + formatNumber(p1m) + "원";
            }
            var p30 = Number(manualPricing.price_30cm) || 0;
            var p1c = Number(manualPricing.price_1cm) || 0;
            if (p30 <= 0 || p1c <= 0) {
                return null;
            }
            return "30cm " + formatNumber(p30) + "원 / 1cm " + formatNumber(p1c) + "원";
        }

        function deriveLinesFromBaseComponents(baseComponents, products, formatNumber) {
            var lines = [];
            var comps = baseComponents || [];
            for (var i = 0; i < comps.length; i++) {
                var comp = comps[i];
                var line = null;
                if (comp && comp.mode === "manual" && comp.manualPricing) {
                    line = formatManualUnitPrices(comp.manualPricing, formatNumber);
                }
                if (
                    !line &&
                    comp &&
                    ((comp.productId != null && comp.productId !== "") ||
                        (comp.product_id != null && comp.product_id !== ""))
                ) {
                    line = formatCatalogUnitPrices(
                        findProduct(
                            products,
                            comp.productId != null && comp.productId !== ""
                                ? comp.productId
                                : comp.product_id
                        ),
                        formatNumber
                    );
                }
                if (line) {
                    lines.push(line);
                }
            }
            return lines;
        }

        function estimateToBaseComponents(estimate) {
            if (!estimate) {
                return [];
            }
            if (estimate.baseComponents && estimate.baseComponents.length) {
                return estimate.baseComponents;
            }
            var w = Number(estimate.widthMm) || 0;
            var pid =
                estimate.productId != null && estimate.productId !== ""
                    ? estimate.productId
                    : estimate.product_id;
            if (pid) {
                return [
                    {
                        mode: "select",
                        productId: pid,
                        widthMm: w,
                        additionalFees: [],
                    },
                ];
            }
            return [];
        }

        function deriveUnitPriceSummaryFromBaseComponents(baseComponents, products, formatNumber) {
            var fmt = resolveFormatNumber(formatNumber);
            var lines = deriveLinesFromBaseComponents(baseComponents, products, fmt);
            return {
                lines: lines,
                isEmpty: lines.length === 0,
            };
        }

        function deriveEstimateUnitPriceSummary(estimate, products, formatNumber) {
            return deriveUnitPriceSummaryFromBaseComponents(estimateToBaseComponents(estimate), products, formatNumber);
        }

        function deriveSavedEstimateUnitSummary(est, products, formatNumber) {
            if (!est || !est.estimate_data || !Array.isArray(est.estimate_data.estimates)) {
                return { lines: [], isEmpty: true };
            }
            var lines = [];
            var fmt = resolveFormatNumber(formatNumber);
            est.estimate_data.estimates.forEach(function (sub) {
                var s = deriveEstimateUnitPriceSummary(sub, products, fmt);
                (s.lines || []).forEach(function (ln) {
                    lines.push(ln);
                });
            });
            return { lines: lines, isEmpty: lines.length === 0 };
        }

        function fillElementWithLines(el, summary, options) {
            var opts = options || {};
            if (!el) {
                return;
            }
            while (el.firstChild) {
                el.removeChild(el.firstChild);
            }
            if (!summary || summary.isEmpty) {
                el.textContent = opts.fallbackText || "단가 정보 없음";
                el.classList.add("text-muted");
                return;
            }
            el.classList.remove("text-muted");
            if (summary.lines.length === 1) {
                el.textContent = summary.lines[0];
                return;
            }
            summary.lines.forEach(function (line, idx) {
                var chip = document.createElement("span");
                chip.className = "wd-unit-price-chip";
                chip.textContent = line;
                el.appendChild(chip);
                if (idx < summary.lines.length - 1) {
                    el.appendChild(document.createTextNode(" "));
                }
            });
        }

        ns.LS_KEY = LS_KEY;
        ns.isUnitPriceMetaVisible = isUnitPriceMetaVisible;
        ns.setUnitPriceMetaVisible = setUnitPriceMetaVisible;
        ns.deriveUnitPriceSummaryFromBaseComponents = deriveUnitPriceSummaryFromBaseComponents;
        ns.deriveEstimateUnitPriceSummary = deriveEstimateUnitPriceSummary;
        ns.deriveSavedEstimateUnitSummary = deriveSavedEstimateUnitSummary;
        ns.fillElementWithLines = fillElementWithLines;
    })(WdCalculatorUnitPriceMeta);

    window.WdCalculatorUnitPriceMeta = WdCalculatorUnitPriceMeta;
})();
