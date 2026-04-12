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
