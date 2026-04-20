/**
 * Contract freeze: calculate button wiring (WdCalculatorCalculateButton) in
 * static/js/wdcalculator/primary-form.js (W5-B3 merged chunk).
 */
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const repoRoot = path.join(__dirname, "..", "..");
const helperPath = path.join(repoRoot, "static", "js", "wdcalculator", "primary-form.js");
const helperSrc = fs.readFileSync(helperPath, "utf8");

function assertEq(actual, expected, label) {
    if (actual !== expected) {
        throw new Error(`${label}: expected ${JSON.stringify(expected)}, got ${JSON.stringify(actual)}`);
    }
}

function createButton() {
    return {
        listeners: {},
        addEventListener(name, handler) {
            this.listeners[name] = handler;
        },
        click() {
            if (typeof this.listeners.click === "function") {
                this.listeners.click();
            }
        },
    };
}

function buildSandbox(spec = {}) {
    const events = [];
    const calculateBtn = spec.withButton === false ? null : createButton();
    const documentRef = {
        getElementById(id) {
            if (id === "calculateBtn") {
                return calculateBtn;
            }
            return null;
        },
    };

    const sandbox = {
        window: null,
        document: {
            getElementById(id) {
                if (id === "calculateBtn") {
                    return calculateBtn;
                }
                return null;
            },
        },
        documentRef,
        calculateEstimate() {
            events.push("calculateEstimate");
        },
        globalThis: null,
        console,
    };
    sandbox.window = sandbox;
    sandbox.globalThis = sandbox;

    vm.createContext(sandbox);
    vm.runInContext(helperSrc, sandbox, { filename: helperPath });
    vm.runInContext(
        `
        window.WdCalculatorCalculateButton.configure({
            documentRef: documentRef,
            calculateEstimate: calculateEstimate
        });
        `,
        sandbox,
        { filename: helperPath }
    );

    return {
        calculateBtn,
        events,
        init() {
            vm.runInContext("window.WdCalculatorCalculateButton.initCalculateButton();", sandbox, {
                filename: helperPath,
            });
        },
        invokeDirect() {
            vm.runInContext("window.WdCalculatorCalculateButton.handleCalculateButtonClick();", sandbox, {
                filename: helperPath,
            });
        },
    };
}

function scenarioInitBindsClickListenerWhenButtonExists() {
    const env = buildSandbox();
    env.init();
    assertEq(typeof env.calculateBtn.listeners.click, "function", "init binds calculate click listener");
}

function scenarioClickCallsCalculateEstimateOnce() {
    const env = buildSandbox();
    env.init();
    env.calculateBtn.click();
    assertEq(env.events.length, 1, "click calls calculateEstimate once");
    assertEq(env.events[0], "calculateEstimate", "click preserves calculateEstimate bridge");
}

function scenarioMissingButtonSkipsBinding() {
    const env = buildSandbox({ withButton: false });
    env.init();
    assertEq(env.events.length, 0, "missing button does not trigger calculateEstimate");
}

function scenarioDirectHandlerStillCallsCalculateEstimate() {
    const env = buildSandbox();
    env.invokeDirect();
    assertEq(env.events.length, 1, "direct handler forwards calculateEstimate once");
}

function main() {
    scenarioInitBindsClickListenerWhenButtonExists();
    scenarioClickCallsCalculateEstimateOnce();
    scenarioMissingButtonSkipsBinding();
    scenarioDirectHandlerStillCallsCalculateEstimate();
    console.log("wdcalculator calculate-button contract checks passed");
}

main();
