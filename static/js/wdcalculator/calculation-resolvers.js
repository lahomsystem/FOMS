(function () {
    var WdCalculatorCalculationResolvers = window.WdCalculatorCalculationResolvers || {};

    (function (ns) {
        function resolveCurrentEstimateMath(baseComponents, products, optionRows) {
            var fn = window.wdcComputeCurrentEstimateMath;
            if (typeof fn !== "function") {
                throw new Error(
                    "WDCalculator: current estimate math helper is not loaded (js/wdcalculator/current-estimate-math.js). Please reload the page."
                );
            }
            return fn(baseComponents, products, optionRows);
        }

        function resolveAggregateTotals(estimatesList, couponValue, shippingCost, shippingIncluded) {
            var fn = window.wdcComputeAggregateTotals;
            if (typeof fn !== "function") {
                throw new Error(
                    "WDCalculator: aggregate totals helper is not loaded (js/wdcalculator/estimate-totals.js). Please reload the page."
                );
            }
            return fn(estimatesList, couponValue, shippingCost, shippingIncluded);
        }

        ns.resolveCurrentEstimateMath = resolveCurrentEstimateMath;
        ns.resolveAggregateTotals = resolveAggregateTotals;
    })(WdCalculatorCalculationResolvers);

    window.WdCalculatorCalculationResolvers = WdCalculatorCalculationResolvers;
})();
