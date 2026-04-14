/**
 * Contract freeze: terminal init shell wiring in
 * static/js/wdcalculator/terminal-init.js.
 */
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const repoRoot = path.join(__dirname, "..", "..");
const helperPath = path.join(repoRoot, "static", "js", "wdcalculator", "composition.js");
const helperSrc = fs.readFileSync(helperPath, "utf8");

function assertEq(actual, expected, label) {
    if (actual !== expected) {
        throw new Error(`${label}: expected ${JSON.stringify(expected)}, got ${JSON.stringify(actual)}`);
    }
}

function buildSandbox() {
    const calls = [];
    const sandbox = {
        window: {},
        document: {},
        globalThis: null,
        loadProducts() {
            calls.push("loadProducts");
            return "products-loaded";
        },
        ensureBaseComponentsUI() {
            calls.push("ensureBaseComponentsUI");
            return "base-ui-rendered";
        },
    };
    sandbox.globalThis = sandbox;

    vm.createContext(sandbox);
    vm.runInContext(
        [
            helperSrc,
            `
            window.WdCalculatorTerminalInit.configure({
                loadProducts: loadProducts,
                ensureBaseComponentsUI: ensureBaseComponentsUI
            });
            `,
        ].join("\n\n"),
        sandbox,
        { filename: helperPath }
    );

    return {
        calls,
        callLoadInitialProducts() {
            return vm.runInContext("window.WdCalculatorTerminalInit.loadInitialProducts();", sandbox, {
                filename: helperPath,
            });
        },
        callRenderInitialBaseComponentsUi() {
            return vm.runInContext(
                "window.WdCalculatorTerminalInit.renderInitialBaseComponentsUi();",
                sandbox,
                { filename: helperPath }
            );
        },
    };
}

function scenarioLoadInitialProductsPassesThroughLoadProducts() {
    const env = buildSandbox();
    const result = env.callLoadInitialProducts();
    assertEq(result, "products-loaded", "terminal init returns loadProducts result");
    assertEq(env.calls.length, 1, "terminal init calls loadProducts once");
    assertEq(env.calls[0], "loadProducts", "terminal init preserves loadProducts target");
}

function scenarioRenderInitialBaseComponentsUiPassesThroughEnsureBaseComponentsUi() {
    const env = buildSandbox();
    const result = env.callRenderInitialBaseComponentsUi();
    assertEq(result, "base-ui-rendered", "terminal init returns ensureBaseComponentsUI result");
    assertEq(env.calls.length, 1, "terminal init calls ensureBaseComponentsUI once");
    assertEq(env.calls[0], "ensureBaseComponentsUI", "terminal init preserves base UI target");
}

function main() {
    scenarioLoadInitialProductsPassesThroughLoadProducts();
    scenarioRenderInitialBaseComponentsUiPassesThroughEnsureBaseComponentsUi();
    console.log("wdcalculator terminal-init contract checks passed");
}

main();
