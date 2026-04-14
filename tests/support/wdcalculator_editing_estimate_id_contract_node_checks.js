const fs = require("fs");
const path = require("path");
const vm = require("vm");

const repoRoot = path.join(__dirname, "..", "..");
const helperPath = path.join(repoRoot, "static", "js", "wdcalculator", "editing-estimate-id.js");
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

const helper = sandbox.WdCalculatorEditingEstimateId;
if (!helper) {
    throw new Error("WdCalculatorEditingEstimateId was not defined");
}

assertEq(helper.getEditingEstimateId(), null, "default editingEstimateId");
assertEq(helper.setEditingEstimateId("estimate-1"), "estimate-1", "set editingEstimateId");
assertEq(helper.getEditingEstimateId(), "estimate-1", "get after set");
helper.configure({ initialValue: 42 });
assertEq(helper.getEditingEstimateId(), 42, "configure updates editingEstimateId");
assertEq(helper.setEditingEstimateId(null), null, "set null clears editingEstimateId");

process.exit(0);
