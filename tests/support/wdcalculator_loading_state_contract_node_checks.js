const fs = require("fs");
const path = require("path");
const vm = require("vm");

const repoRoot = path.join(__dirname, "..", "..");
const helperPath = path.join(
    repoRoot,
    "static",
    "js",
    "wdcalculator",
    "loading-state.js"
);
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
    Boolean,
    Object,
};
sandbox.window = sandbox;
sandbox.globalThis = sandbox;

vm.createContext(sandbox);
vm.runInContext(helperSrc, sandbox);

const helper = sandbox.WdCalculatorLoadingState;
if (!helper) {
    throw new Error("WdCalculatorLoadingState was not defined");
}

assertEq(helper.getLoadingState(), false, "default loading state");
assertEq(helper.setLoadingState(true), true, "set true returns true");
assertEq(helper.getLoadingState(), true, "get after set true");
helper.configure({ initialValue: 0 });
assertEq(helper.getLoadingState(), false, "configure coerces false");
assertEq(helper.setLoadingState("busy"), true, "set coerces truthy");
assertEq(helper.getLoadingState(), true, "get after truthy set");

process.exit(0);
