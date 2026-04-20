const fs = require("fs");
const path = require("path");
const vm = require("vm");

const repoRoot = path.join(__dirname, "..", "..");
const helperPath = path.join(repoRoot, "static", "js", "wdcalculator", "composition.js");
const helperSrc = fs.readFileSync(helperPath, "utf8");

function assertEq(actual, expected, label) {
    if (actual !== expected) {
        throw new Error(
            `${label}: expected ${JSON.stringify(expected)}, got ${JSON.stringify(actual)}`
        );
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

const helper = sandbox.WdCalculatorEstimatesEarlyHostBootstrap;
if (!helper) {
    throw new Error("WdCalculatorEstimatesEarlyHostBootstrap was not defined");
}

const callLog = [];
const estimatesState = { name: "estimates-state" };
const earlyBootstrap = { name: "early-bootstrap" };
const unsavedExitGuard = { name: "unsaved-exit-guard" };
const layoutSyncWiring = { name: "layout-sync-wiring" };
const initialEstimates = [{ id: "estimate-1" }];
const getEstimates = () => initialEstimates;
const windowRef = { name: "window-ref" };
const requestLayoutSync = () => "layout-sync";
const expectedResult = "estimates-early-host-ok";

helper.configure({
    estimatesEarlyBootstrap: {
        configure(options) {
            callLog.push(["estimatesEarlyBootstrap.configure", options]);
        },
        initEstimatesEarlyBootstrap() {
            callLog.push(["estimatesEarlyBootstrap.initEstimatesEarlyBootstrap"]);
            return expectedResult;
        },
    },
    estimatesState,
    earlyBootstrap,
    unsavedExitGuard,
    layoutSyncWiring,
    initialEstimates,
    getEstimates,
    windowRef,
    requestLayoutSync,
});

const result = helper.initEstimatesEarlyHostBootstrap();

assertEq(callLog.length, 2, "estimates early host bootstrap call count");
assertEq(
    callLog[0][0],
    "estimatesEarlyBootstrap.configure",
    "estimates early host configure order"
);
assertEq(
    callLog[0][1].estimatesState,
    estimatesState,
    "estimates early host estimatesState"
);
assertEq(
    callLog[0][1].earlyBootstrap,
    earlyBootstrap,
    "estimates early host earlyBootstrap"
);
assertEq(
    callLog[0][1].unsavedExitGuard,
    unsavedExitGuard,
    "estimates early host unsavedExitGuard"
);
assertEq(
    callLog[0][1].layoutSyncWiring,
    layoutSyncWiring,
    "estimates early host layoutSyncWiring"
);
assertEq(
    callLog[0][1].initialEstimates,
    initialEstimates,
    "estimates early host initialEstimates"
);
assertEq(
    callLog[0][1].getEstimates,
    getEstimates,
    "estimates early host getEstimates"
);
assertEq(callLog[0][1].windowRef, windowRef, "estimates early host windowRef");
assertEq(
    callLog[0][1].requestLayoutSync,
    requestLayoutSync,
    "estimates early host requestLayoutSync"
);
assertEq(
    callLog[1][0],
    "estimatesEarlyBootstrap.initEstimatesEarlyBootstrap",
    "estimates early host init order"
);
assertEq(result, expectedResult, "estimates early host return value");

process.exit(0);
