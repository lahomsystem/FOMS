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
        for (var i = 0; i < list.length; i++) {
            if (list[i].id === productId) {
                return list[i];
            }
        }
        return null;
    }

    /**
     * @param {Array<object>} baseComponents
     * @param {Array<object>} products
     * @param {(n: number) => string} formatNumber
     */
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
                            compData = {
                                mode: "manual",
                                widthMm: widthMm,
                                additionalFees: additionalFees,
                                manualPricing: { pricing_type: "1m", price_1m: price1m },
                            };
                            detailLines.push("직접입력(1m) " + formatNumber(widthMm) + "mm");
                            displayParts.push("직접입력(1m) " + formatNumber(widthMm) + "mm");
                        }
                    } else {
                        var price30 = Number(comp.manualPricing && comp.manualPricing.price_30cm) || 0;
                        var price1 = Number(comp.manualPricing && comp.manualPricing.price_1cm) || 0;
                        if (price30 > 0 && price1 > 0) {
                            var units30cm = Math.floor(widthMm / 300);
                            var remainderMm = widthMm % 300;
                            var units1cm = Math.floor(remainderMm / 10);
                            compPrice = units30cm * price30 + units1cm * price1;
                            compData = {
                                mode: "manual",
                                widthMm: widthMm,
                                additionalFees: additionalFees,
                                manualPricing: {
                                    pricing_type: "30cm",
                                    price_30cm: price30,
                                    price_1cm: price1,
                                },
                            };
                            detailLines.push("직접입력(30cm) " + formatNumber(widthMm) + "mm");
                            displayParts.push("직접입력(30cm) " + formatNumber(widthMm) + "mm");
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
                            compData = {
                                mode: "select",
                                productId: productId,
                                widthMm: widthMm,
                                additionalFees: additionalFees,
                            };
                            detailLines.push(product.name + " " + formatNumber(widthMm) + "mm");
                            displayParts.push(product.name + " " + formatNumber(widthMm) + "mm");
                        }
                    }
                }
            }

            var totalAdditionalFee = 0;
            for (var f = 0; f < additionalFees.length; f++) {
                totalAdditionalFee += Number(additionalFees[f].amount) || 0;
            }
            if (Object.keys(compData).length === 0 && totalAdditionalFee > 0) {
                compData = {
                    mode: comp.mode || "select",
                    widthMm: widthMm,
                    additionalFees: additionalFees,
                };
                if (comp.mode === "manual" && comp.manualPricing) {
                    compData.manualPricing = comp.manualPricing;
                } else {
                    compData.productId = comp.productId || null;
                }
                if (widthMm <= 0) {
                    for (var j = 0; j < additionalFees.length; j++) {
                        var feeA = additionalFees[j];
                        var amtA = Number(feeA.amount) || 0;
                        if (amtA > 0) {
                            var feeNameA = feeA.name ? feeA.name + " " : "";
                            displayParts.push(feeNameA + "추가금 " + formatNumber(amtA) + "원");
                        }
                    }
                }
            }

            for (var k = 0; k < additionalFees.length; k++) {
                var fee = additionalFees[k];
                var amount = Number(fee.amount) || 0;
                if (amount > 0) {
                    compPrice += amount;
                    var feeName = fee.name ? fee.name + " " : "";
                    detailLines.push("+ " + feeName + "추가금 " + formatNumber(amount) + "원");
                    if (widthMm > 0) {
                        displayParts.push("+ " + feeName + "추가금 " + formatNumber(amount) + "원");
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

    function wdcComputeCurrentEstimateMath(baseComponents, products, optionRows, formatNumber) {
        var fmt = resolveFormatNumber(formatNumber);
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
