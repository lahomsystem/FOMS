/**
 * Contract freeze: sidebar bootstrap wiring in
 * static/js/wdcalculator/sidebar-bootstrap.js.
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
    const events = [];
    const sidebarApi = {
        loadSidebarEstimates() {},
        deleteEstimate() {},
    };

    const sandbox = {
        window: {},
        document: {},
        loadEstimateToForm() {},
        formatNumber() {},
        sidebarApi,
        initSidebarEstimates(options) {
            events.push({
                sameLoadEstimateRef: options.loadEstimateToForm === sandbox.loadEstimateToForm,
                sameFormatNumberRef: options.formatNumber === sandbox.formatNumber,
            });
            return sidebarApi;
        },
        globalThis: null,
    };
    sandbox.globalThis = sandbox;

    vm.createContext(sandbox);
    vm.runInContext(
        [
            helperSrc,
            `
            window.WdCalculatorSidebarBootstrap.configure({
                initSidebarEstimates: initSidebarEstimates,
                loadEstimateToForm: loadEstimateToForm,
                formatNumber: formatNumber
            });
            `,
        ].join("\n\n"),
        sandbox,
        { filename: helperPath }
    );

    return {
        events,
        init() {
            vm.runInContext(
                `
                var result = window.WdCalculatorSidebarBootstrap.initSidebarBootstrap();
                globalThis.__sidebarBootstrapResult = {
                    sameLoadSidebarRef: result.loadSidebarEstimates === sidebarApi.loadSidebarEstimates,
                    sameDeleteRef: result.deleteEstimate === sidebarApi.deleteEstimate
                };
                `,
                sandbox,
                { filename: helperPath }
            );
            return sandbox.__sidebarBootstrapResult;
        },
    };
}

function scenarioInitPassesThroughExactBootstrapOptions() {
    const env = buildSandbox();
    env.init();
    assertEq(env.events.length, 1, "bootstrap calls initSidebarEstimates once");
    assertEq(env.events[0].sameLoadEstimateRef, true, "bootstrap preserves loadEstimateToForm reference");
    assertEq(env.events[0].sameFormatNumberRef, true, "bootstrap preserves formatNumber reference");
}

function scenarioInitReturnsSidebarApiWithoutWrapping() {
    const env = buildSandbox();
    const result = env.init();
    assertEq(result.sameLoadSidebarRef, true, "bootstrap returns original loadSidebarEstimates reference");
    assertEq(result.sameDeleteRef, true, "bootstrap returns original deleteEstimate reference");
}

function main() {
    scenarioInitPassesThroughExactBootstrapOptions();
    scenarioInitReturnsSidebarApiWithoutWrapping();
    console.log("wdcalculator sidebar-bootstrap contract checks passed");
}

main();
