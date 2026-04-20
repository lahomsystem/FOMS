/**
 * Contract freeze: unsaved beforeunload guard in
 * static/js/wdcalculator/unsaved-exit-guard.js.
 */
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const repoRoot = path.join(__dirname, "..", "..");
const helperPath = path.join(
    repoRoot,
    "static",
    "js",
    "wdcalculator",
    "unsaved-exit-guard.js"
);
const helperSrc = fs.readFileSync(helperPath, "utf8");

function assertEq(actual, expected, label) {
    if (actual !== expected) {
        throw new Error(`${label}: expected ${JSON.stringify(expected)}, got ${JSON.stringify(actual)}`);
    }
}

function buildSandbox(spec = {}) {
    const registered = {};
    const events = [];
    const sandbox = {
        window: {
            addEventListener(name, handler) {
                registered[name] = handler;
                events.push(["addEventListener", name]);
            },
        },
        estimatesState: spec.estimates || [],
        globalThis: null,
    };
    sandbox.globalThis = sandbox;

    vm.createContext(sandbox);
    vm.runInContext(
        [
            helperSrc,
            `
            window.WdCalculatorUnsavedExitGuard.configure({
                getEstimates: function () {
                    return estimatesState;
                },
                windowRef: window
            });
            window.WdCalculatorUnsavedExitGuard.initUnsavedExitGuard();
            `,
        ].join("\n\n"),
        sandbox,
        { filename: helperPath }
    );

    return {
        events,
        dispatchBeforeUnload() {
            const event = {
                returnValue: undefined,
                prevented: false,
                preventDefault() {
                    this.prevented = true;
                },
            };
            const handler = registered.beforeunload;
            if (typeof handler !== "function") {
                throw new Error("beforeunload handler was not registered");
            }
            handler(event);
            return event;
        },
    };
}

function scenarioRegistersBeforeUnloadListener() {
    const env = buildSandbox({ estimates: [] });
    assertEq(env.events[0][0], "addEventListener", "guard registers window listener");
    assertEq(env.events[0][1], "beforeunload", "guard binds beforeunload event");
}

function scenarioNoUnsavedEstimatesLeavesEventUntouched() {
    const env = buildSandbox({ estimates: [] });
    const event = env.dispatchBeforeUnload();

    assertEq(event.prevented, false, "empty estimates do not prevent unload");
    assertEq(event.returnValue, undefined, "empty estimates do not set returnValue");
}

function scenarioUnsavedEstimatesPreventUnloadWithExactMessage() {
    const env = buildSandbox({ estimates: [{ id: "est-1" }] });
    const event = env.dispatchBeforeUnload();

    assertEq(event.prevented, true, "non-empty estimates prevent unload");
    assertEq(
        event.returnValue,
        "작성 중인 견적이 저장되지 않았습니다. 페이지를 떠나면 내용이 사라집니다.",
        "non-empty estimates preserve exact leave-warning message"
    );
}

function main() {
    scenarioRegistersBeforeUnloadListener();
    scenarioNoUnsavedEstimatesLeavesEventUntouched();
    scenarioUnsavedEstimatesPreventUnloadWithExactMessage();
    console.log("wdcalculator unsaved exit guard contract checks passed");
}

main();
