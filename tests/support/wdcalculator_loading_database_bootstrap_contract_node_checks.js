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

const helper = sandbox.WdCalculatorLoadingDatabaseBootstrap;
if (!helper) {
    throw new Error("WdCalculatorLoadingDatabaseBootstrap was not defined");
}

const callLog = [];
const initialLoadingValue = true;
const initialCurrentDatabaseEstimateId = "db-estimate-id";

helper.configure({
    loadingState: {
        configure(options) {
            callLog.push(["loading.configure", options]);
        },
    },
    currentDatabaseEstimateIdState: {
        configure(options) {
            callLog.push(["currentDb.configure", options]);
        },
    },
    initialLoadingValue,
    initialCurrentDatabaseEstimateId,
});

helper.initLoadingDatabaseBootstrap();

assertEq(callLog.length, 2, "loading/database bootstrap call count");
assertEq(callLog[0][0], "loading.configure", "loading configure order");
assertEq(
    callLog[0][1].initialValue,
    initialLoadingValue,
    "loading configure initialValue"
);
assertEq(callLog[1][0], "currentDb.configure", "current DB configure order");
assertEq(
    callLog[1][1].initialValue,
    initialCurrentDatabaseEstimateId,
    "current DB configure initialValue"
);

process.exit(0);
