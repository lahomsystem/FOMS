const fs = require("fs");
const path = require("path");
const vm = require("vm");

const repoRoot = path.join(__dirname, "..", "..");
const helperPath = path.join(repoRoot, "static", "js", "wdcalculator", "estimate-lifecycle.js");
const helperSrc = fs.readFileSync(helperPath, "utf8");

function assertEq(actual, expected, label) {
    if (actual !== expected) {
        throw new Error(`${label}: expected ${JSON.stringify(expected)}, got ${JSON.stringify(actual)}`);
    }
}

const sandbox = {
    window: null,
    globalThis: null,
    document: {},
    console,
    Array,
    Object,
};
sandbox.window = sandbox;
sandbox.globalThis = sandbox;

vm.createContext(sandbox);
vm.runInContext(helperSrc, sandbox);

const helper = sandbox.WdCalculatorEstimatesState;
if (!helper) {
    throw new Error("WdCalculatorEstimatesState was not defined");
}

const liveReference = helper.getEstimates();
assertEq(Array.isArray(liveReference), true, "default estimates array");
assertEq(helper.getEstimatesLength(), 0, "default estimates length");

helper.configure({
    initialEstimates: [{ id: "estimate-1", displayName: "One" }],
});
assertEq(helper.getEstimates(), liveReference, "configure keeps stable array reference");
assertEq(helper.getEstimatesLength(), 1, "configure updates estimates length");
assertEq(liveReference[0].id, "estimate-1", "configure populates live array");

const replacement = [{ id: "estimate-2" }, { id: "estimate-3" }];
assertEq(helper.setEstimates(replacement), liveReference, "setEstimates returns stable array reference");
assertEq(helper.getEstimates(), liveReference, "getEstimates returns same live reference");
assertEq(helper.getEstimatesLength(), 2, "setEstimates updates length");
assertEq(liveReference[1].id, "estimate-3", "setEstimates replaces contents");

liveReference.push({ id: "estimate-4" });
assertEq(helper.getEstimatesLength(), 3, "in-place mutation stays visible through helper");

helper.setEstimates(null);
assertEq(helper.getEstimates(), liveReference, "non-array set keeps stable array reference");
assertEq(helper.getEstimatesLength(), 0, "non-array set clears estimates");

process.exit(0);
