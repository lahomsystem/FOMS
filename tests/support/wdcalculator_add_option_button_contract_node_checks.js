/**
 * Contract freeze: add-option button wiring (WdCalculatorAddOptionButton) in
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

function assertDeepEqual(actual, expected, label) {
    const actualJson = JSON.stringify(actual);
    const expectedJson = JSON.stringify(expected);
    if (actualJson !== expectedJson) {
        throw new Error(`${label}: expected ${expectedJson}, got ${actualJson}`);
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
    const addOptionBtn = spec.withButton === false ? null : createButton();
    const container = spec.withContainer === false ? null : { id: "additionalOptionsContainer" };
    const documentRef = {
        getElementById(id) {
            if (id === "addOptionBtn") {
                return addOptionBtn;
            }
            if (id === "additionalOptionsContainer") {
                return container;
            }
            return null;
        },
    };

    const sandbox = {
        window: null,
        document: {
            getElementById(id) {
                if (id === "addOptionBtn") {
                    return addOptionBtn;
                }
                if (id === "additionalOptionsContainer") {
                    return container;
                }
                return null;
            },
        },
        documentRef,
        appendAdditionalOptionRow(containerArg, optionsArg) {
            events.push(["appendAdditionalOptionRow", containerArg, optionsArg]);
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
        window.WdCalculatorAddOptionButton.configure({
            documentRef: documentRef,
            appendAdditionalOptionRow: appendAdditionalOptionRow
        });
        `,
        sandbox,
        { filename: helperPath }
    );

    return {
        addOptionBtn,
        events,
        init() {
            vm.runInContext("window.WdCalculatorAddOptionButton.initAddOptionButton();", sandbox, {
                filename: helperPath,
            });
        },
        invokeDirect() {
            vm.runInContext("window.WdCalculatorAddOptionButton.handleAddOptionButtonClick();", sandbox, {
                filename: helperPath,
            });
        },
    };
}

function scenarioInitBindsClickListenerWhenButtonExists() {
    const env = buildSandbox();
    env.init();
    assertEq(typeof env.addOptionBtn.listeners.click, "function", "init binds add-option click listener");
}

function scenarioClickAppendsSelectModeRowToContainer() {
    const env = buildSandbox();
    env.init();
    env.addOptionBtn.click();

    assertEq(env.events.length, 1, "click forwards to appendAdditionalOptionRow once");
    assertEq(env.events[0][1].id, "additionalOptionsContainer", "click resolves container by id");
    assertDeepEqual(
        env.events[0][2],
        {
            forceMode: "select",
            formatPriceOnInput: false,
        },
        "click preserves select-mode/raw-price options"
    );
}

function scenarioMissingButtonSkipsBinding() {
    const env = buildSandbox({ withButton: false });
    env.init();
    assertEq(env.events.length, 0, "missing button does not append rows during init");
}

function scenarioMissingContainerStillForwardsNullContainer() {
    const env = buildSandbox({ withContainer: false });
    env.invokeDirect();
    assertEq(env.events.length, 1, "direct handler still forwards append call");
    assertEq(env.events[0][1], null, "missing container is forwarded as null");
}

function main() {
    scenarioInitBindsClickListenerWhenButtonExists();
    scenarioClickAppendsSelectModeRowToContainer();
    scenarioMissingButtonSkipsBinding();
    scenarioMissingContainerStillForwardsNullContainer();
    console.log("wdcalculator add-option-button contract checks passed");
}

main();
