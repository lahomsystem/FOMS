const fs = require("fs");
const path = require("path");
const vm = require("vm");

const repoRoot = path.join(__dirname, "..", "..");
const helperPath = path.join(
    repoRoot,
    "static",
    "js",
    "wdcalculator",
    "current-database-estimate-id.js"
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
    Object,
};
sandbox.window = sandbox;
sandbox.globalThis = sandbox;

vm.createContext(sandbox);
vm.runInContext(helperSrc, sandbox);

const helper = sandbox.WdCalculatorCurrentDatabaseEstimateId;
if (!helper) {
    throw new Error("WdCalculatorCurrentDatabaseEstimateId was not defined");
}

assertEq(helper.getCurrentDatabaseEstimateId(), null, "default currentDatabaseEstimateId");
assertEq(helper.setCurrentDatabaseEstimateId(123), 123, "set id returns value");
assertEq(helper.getCurrentDatabaseEstimateId(), 123, "get after set");
helper.configure({ initialValue: "db-456" });
assertEq(helper.getCurrentDatabaseEstimateId(), "db-456", "configure updates currentDatabaseEstimateId");
assertEq(helper.setCurrentDatabaseEstimateId(null), null, "set null clears value");

process.exit(0);
