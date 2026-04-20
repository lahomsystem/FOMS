/**
 * Contract freeze: helper-load resolvers inside
 * static/js/wdcalculator/pricing-core.js.
 */
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const repoRoot = path.join(__dirname, "..", "..");
const helperPath = path.join(repoRoot, "static", "js", "wdcalculator", "pricing-core.js");
const helperSrc = fs.readFileSync(helperPath, "utf8");

function assertEq(actual, expected, label) {
    if (actual !== expected) {
        throw new Error(`${label}: expected ${JSON.stringify(expected)}, got ${JSON.stringify(actual)}`);
    }
}

function assertDeepEqual(actual, expected, label) {
    const actualJson = JSON.stringify(actual);
    const expectedJson = JSON.stringify(expected);
    if (actualJson !== expectedJson) {
        throw new Error(`${label}: expected ${expectedJson}, got ${actualJson}`);
    }
}

function buildSandbox(spec = {}) {
    const events = [];
    const sandbox = {
        window: {},
        document: {},
        globalThis: null,
    };
    sandbox.globalThis = sandbox;

    vm.createContext(sandbox);
    vm.runInContext(helperSrc, sandbox, { filename: helperPath });

    sandbox.window.wdcComputeCurrentEstimateMath = spec.withCurrentHelper === false
        ? undefined
        : function (baseComponents, products, optionRows) {
              events.push(["current", baseComponents, products, optionRows]);
              return spec.currentResult || { ok: "current" };
          };
    sandbox.window.wdcComputeAggregateTotals = spec.withAggregateHelper === false
        ? undefined
        : function (estimatesList, couponValue, shippingCost, shippingIncluded) {
              events.push([
                  "aggregate",
                  estimatesList,
                  couponValue,
                  shippingCost,
                  shippingIncluded,
              ]);
              return spec.aggregateResult || { ok: "aggregate" };
          };

    return {
        events,
        invokeCurrent(baseComponents, products, optionRows) {
            sandbox.baseComponentsArg = baseComponents;
            sandbox.productsArg = products;
            sandbox.optionRowsArg = optionRows;
            return vm.runInContext(
                "window.WdCalculatorCalculationResolvers.resolveCurrentEstimateMath(baseComponentsArg, productsArg, optionRowsArg);",
                sandbox,
                { filename: helperPath }
            );
        },
        invokeAggregate(estimatesList, couponValue, shippingCost, shippingIncluded) {
            sandbox.estimatesArg = estimatesList;
            sandbox.couponArg = couponValue;
            sandbox.shippingArg = shippingCost;
            sandbox.shippingIncludedArg = shippingIncluded;
            return vm.runInContext(
                "window.WdCalculatorCalculationResolvers.resolveAggregateTotals(estimatesArg, couponArg, shippingArg, shippingIncludedArg);",
                sandbox,
                { filename: helperPath }
            );
        },
    };
}

function scenarioCurrentResolverPassesThroughArgumentsAndReturnValue() {
    const env = buildSandbox({
        currentResult: { basePriceCalculate: 12345 },
    });

    const result = env.invokeCurrent([{ widthMm: 900 }], [{ id: 1 }], [{ name: "LED" }]);

    assertDeepEqual(
        env.events[0],
        ["current", [{ widthMm: 900 }], [{ id: 1 }], [{ name: "LED" }]],
        "current resolver passes through base/products/options arguments"
    );
    assertDeepEqual(
        result,
        { basePriceCalculate: 12345 },
        "current resolver returns helper result unchanged"
    );
}

function scenarioAggregateResolverPassesThroughArgumentsAndReturnValue() {
    const env = buildSandbox({
        aggregateResult: { finalPrice: 209000 },
    });

    const result = env.invokeAggregate([{ id: "est-1" }], 11000, 3000, false);

    assertDeepEqual(
        env.events[0],
        ["aggregate", [{ id: "est-1" }], 11000, 3000, false],
        "aggregate resolver passes through estimates/coupon/shipping arguments"
    );
    assertDeepEqual(
        result,
        { finalPrice: 209000 },
        "aggregate resolver returns helper result unchanged"
    );
}

function scenarioCurrentResolverThrowsClearLoadOrderError() {
    const env = buildSandbox({ withCurrentHelper: false });

    try {
        env.invokeCurrent([], [], []);
        throw new Error("expected current resolver to throw");
    } catch (error) {
        assertEq(
            error.message,
            "WDCalculator: current estimate math helper is not loaded (js/wdcalculator/pricing-core.js). Please reload the page.",
            "current resolver preserves load-order error message"
        );
    }
}

function scenarioAggregateResolverThrowsClearLoadOrderError() {
    const env = buildSandbox({ withAggregateHelper: false });

    try {
        env.invokeAggregate([], 0, 0, true);
        throw new Error("expected aggregate resolver to throw");
    } catch (error) {
        assertEq(
            error.message,
            "WDCalculator: aggregate totals helper is not loaded (js/wdcalculator/pricing-core.js). Please reload the page.",
            "aggregate resolver preserves load-order error message"
        );
    }
}

function main() {
    scenarioCurrentResolverPassesThroughArgumentsAndReturnValue();
    scenarioAggregateResolverPassesThroughArgumentsAndReturnValue();
    scenarioCurrentResolverThrowsClearLoadOrderError();
    scenarioAggregateResolverThrowsClearLoadOrderError();
    console.log("wdcalculator calculation resolvers contract checks passed");
}

main();
