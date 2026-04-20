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

const helper = sandbox.WdCalculatorEarlyBootstrap;
if (!helper) {
    throw new Error("WdCalculatorEarlyBootstrap was not defined");
}

const callLog = [];
const getEstimates = () => ["estimate-1"];
const requestLayoutSync = () => "layout-sync";
const windowRef = { name: "window-ref" };

helper.configure({
    unsavedExitGuard: {
        configure(options) {
            callLog.push(["unsaved.configure", options]);
        },
        initUnsavedExitGuard() {
            callLog.push(["unsaved.init"]);
        },
    },
    layoutSyncWiring: {
        configure(options) {
            callLog.push(["layout.configure", options]);
        },
        initLayoutSyncWiring() {
            callLog.push(["layout.init"]);
        },
    },
    getEstimates,
    windowRef,
    requestLayoutSync,
});
helper.initEarlyBootstrap();

assertEq(callLog.length, 4, "bootstrap call count");
assertEq(callLog[0][0], "unsaved.configure", "unsaved configure order");
assertEq(callLog[0][1].getEstimates, getEstimates, "unsaved configure getEstimates");
assertEq(callLog[0][1].windowRef, windowRef, "unsaved configure windowRef");
assertEq(callLog[1][0], "unsaved.init", "unsaved init order");
assertEq(callLog[2][0], "layout.configure", "layout configure order");
assertEq(callLog[2][1].windowRef, windowRef, "layout configure windowRef");
assertEq(callLog[2][1].requestLayoutSync, requestLayoutSync, "layout configure requestLayoutSync");
assertEq(callLog[3][0], "layout.init", "layout init order");

process.exit(0);
