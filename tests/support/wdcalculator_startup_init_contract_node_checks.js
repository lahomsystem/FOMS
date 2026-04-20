/**
 * Contract freeze: startup init shell wiring in
 * static/js/wdcalculator/startup-init.js.
 */
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const repoRoot = path.join(__dirname, "..", "..");
const helperPath = path.join(repoRoot, "static", "js", "wdcalculator", "composition.js");
const helperSrc = fs.readFileSync(helperPath, "utf8");
const EMPTY_WARNING = "카테고리 데이터가 없습니다. 제품 설정에서 추가 옵션을 등록해주세요.";

function assertEq(actual, expected, label) {
    if (actual !== expected) {
        throw new Error(`${label}: expected ${JSON.stringify(expected)}, got ${JSON.stringify(actual)}`);
    }
}

function assertArrayEq(actual, expected, label) {
    const actualJson = JSON.stringify(actual);
    const expectedJson = JSON.stringify(expected);
    if (actualJson !== expectedJson) {
        throw new Error(`${label}: expected ${expectedJson}, got ${actualJson}`);
    }
}

function buildSandbox(spec) {
    const callOrder = [];
    const warns = [];
    const sandbox = {
        window: {},
        document: {},
        globalThis: null,
        consoleRef: {
            warn(message) {
                warns.push(String(message));
            },
        },
        bindProductSelect() {
            callOrder.push("bindProductSelect");
        },
        initBaseComponentsLiveInteractions() {
            callOrder.push("initBaseComponentsLiveInteractions");
        },
        initAddOptionButton() {
            callOrder.push("initAddOptionButton");
        },
        initCalculateButton() {
            callOrder.push("initCalculateButton");
        },
        initSearchResultsLoadBridge() {
            callOrder.push("initSearchResultsLoadBridge");
        },
        bindOrderMatchButtons() {
            callOrder.push("bindOrderMatchButtons");
        },
        initCouponShippingWiring() {
            callOrder.push("initCouponShippingWiring");
        },
    };
    sandbox.globalThis = sandbox;

    vm.createContext(sandbox);
    vm.runInContext(
        [
            helperSrc,
            `
            window.WdCalculatorStartupInit.configure({
                categories: ${JSON.stringify(spec.categories || [])},
                consoleRef: consoleRef,
                bindProductSelect: bindProductSelect,
                initBaseComponentsLiveInteractions: initBaseComponentsLiveInteractions,
                initAddOptionButton: initAddOptionButton,
                initCalculateButton: initCalculateButton,
                initSearchResultsLoadBridge: initSearchResultsLoadBridge,
                bindOrderMatchButtons: bindOrderMatchButtons,
                initCouponShippingWiring: initCouponShippingWiring
            });
            `,
        ].join("\n\n"),
        sandbox,
        { filename: helperPath }
    );

    return {
        callOrder,
        warns,
        init() {
            vm.runInContext("window.WdCalculatorStartupInit.initStartupInteractions();", sandbox, {
                filename: helperPath,
            });
        },
    };
}

function scenarioInitPreservesStartupCallOrderAndWarnsWhenCategoriesMissing() {
    const env = buildSandbox({ categories: [] });
    env.init();
    assertArrayEq(
        env.callOrder,
        [
            "bindProductSelect",
            "initBaseComponentsLiveInteractions",
            "initAddOptionButton",
            "initCalculateButton",
            "initSearchResultsLoadBridge",
            "bindOrderMatchButtons",
            "initCouponShippingWiring",
        ],
        "startup init preserves call order"
    );
    assertEq(env.warns.length, 1, "startup init warns once when categories are empty");
    assertEq(env.warns[0], EMPTY_WARNING, "startup init keeps exact empty-category warning");
}

function scenarioInitSkipsWarningWhenCategoriesExist() {
    const env = buildSandbox({ categories: [{ id: 1, name: "기본 옵션" }] });
    env.init();
    assertEq(env.warns.length, 0, "startup init does not warn when categories exist");
}

function main() {
    scenarioInitPreservesStartupCallOrderAndWarnsWhenCategoriesMissing();
    scenarioInitSkipsWarningWhenCategoriesExist();
    console.log("wdcalculator startup-init contract checks passed");
}

main();
