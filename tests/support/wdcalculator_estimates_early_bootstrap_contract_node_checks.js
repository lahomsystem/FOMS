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

const sandbox = {
    window: null,
    globalThis: null,
    console,
    document: {},
};
sandbox.window = sandbox;
sandbox.globalThis = sandbox;

vm.createContext(sandbox);
vm.runInContext(helperSrc, sandbox);

const helper = sandbox.WdCalculatorEstimatesEarlyBootstrap;
if (!helper) {
    throw new Error("WdCalculatorEstimatesEarlyBootstrap was not defined");
}

const callLog = [];
const initialEstimates = [{ id: "estimate-1" }];
const unsavedExitGuard = { name: "unsaved-exit-guard" };
const layoutSyncWiring = { name: "layout-sync-wiring" };
const getEstimates = () => initialEstimates;
const windowRef = { name: "window-ref" };
const requestLayoutSync = () => "layout-sync";

helper.configure({
    estimatesState: {
        configure(options) {
            callLog.push(["estimates.configure", options]);
        },
        getEstimates,
    },
    earlyBootstrap: {
        configure(options) {
            callLog.push(["early.configure", options]);
        },
        initEarlyBootstrap() {
            callLog.push(["early.init"]);
        },
    },
    unsavedExitGuard,
    layoutSyncWiring,
    initialEstimates,
    getEstimates,
    windowRef,
    requestLayoutSync,
});

helper.initEstimatesEarlyBootstrap();

assertEq(callLog.length, 3, "estimates early bootstrap call count");
assertEq(callLog[0][0], "estimates.configure", "estimates configure order");
assertEq(callLog[0][1].initialEstimates, initialEstimates, "estimates configure initialEstimates");
assertEq(callLog[1][0], "early.configure", "early configure order");
assertEq(callLog[1][1].unsavedExitGuard, unsavedExitGuard, "early configure unsavedExitGuard");
assertEq(callLog[1][1].layoutSyncWiring, layoutSyncWiring, "early configure layoutSyncWiring");
assertEq(callLog[1][1].getEstimates, getEstimates, "early configure getEstimates");
assertEq(callLog[1][1].windowRef, windowRef, "early configure windowRef");
assertEq(callLog[1][1].requestLayoutSync, requestLayoutSync, "early configure requestLayoutSync");
assertEq(callLog[2][0], "early.init", "early init order");

process.exit(0);
