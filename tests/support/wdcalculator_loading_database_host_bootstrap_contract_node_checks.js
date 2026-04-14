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

const helper = sandbox.WdCalculatorLoadingDatabaseHostBootstrap;
if (!helper) {
    throw new Error("WdCalculatorLoadingDatabaseHostBootstrap was not defined");
}

const callLog = [];
const loadingState = { name: "loading-state" };
const currentDatabaseEstimateIdState = { name: "current-db-state" };
const initialLoadingValue = true;
const initialCurrentDatabaseEstimateId = "db-id";
const expectedResult = "host-bootstrap-ok";

helper.configure({
    loadingDatabaseBootstrap: {
        configure(options) {
            callLog.push(["loadingDatabaseBootstrap.configure", options]);
        },
        initLoadingDatabaseBootstrap() {
            callLog.push(["loadingDatabaseBootstrap.initLoadingDatabaseBootstrap"]);
            return expectedResult;
        },
    },
    loadingState,
    currentDatabaseEstimateIdState,
    initialLoadingValue,
    initialCurrentDatabaseEstimateId,
});

const result = helper.initLoadingDatabaseHostBootstrap();

assertEq(callLog.length, 2, "loading database host bootstrap call count");
assertEq(
    callLog[0][0],
    "loadingDatabaseBootstrap.configure",
    "loading database host configure order"
);
assertEq(callLog[0][1].loadingState, loadingState, "loading database host loadingState");
assertEq(
    callLog[0][1].currentDatabaseEstimateIdState,
    currentDatabaseEstimateIdState,
    "loading database host currentDatabaseEstimateIdState"
);
assertEq(
    callLog[0][1].initialLoadingValue,
    initialLoadingValue,
    "loading database host initialLoadingValue"
);
assertEq(
    callLog[0][1].initialCurrentDatabaseEstimateId,
    initialCurrentDatabaseEstimateId,
    "loading database host initialCurrentDatabaseEstimateId"
);
assertEq(
    callLog[1][0],
    "loadingDatabaseBootstrap.initLoadingDatabaseBootstrap",
    "loading database host init order"
);
assertEq(result, expectedResult, "loading database host return value");

process.exit(0);
