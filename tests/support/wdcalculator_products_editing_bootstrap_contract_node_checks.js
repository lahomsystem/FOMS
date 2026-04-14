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

const helper = sandbox.WdCalculatorProductsEditingBootstrap;
if (!helper) {
    throw new Error("WdCalculatorProductsEditingBootstrap was not defined");
}

const callLog = [];
const initialProducts = [{ id: 1, name: "Seed Product" }];
const initialEditingEstimateId = "editing-id";

helper.configure({
    productsState: {
        configure(options) {
            callLog.push(["products.configure", options]);
        },
    },
    editingEstimateIdState: {
        configure(options) {
            callLog.push(["editing.configure", options]);
        },
    },
    initialProducts,
    initialEditingEstimateId,
});

helper.initProductsEditingBootstrap();

assertEq(callLog.length, 2, "products editing bootstrap call count");
assertEq(callLog[0][0], "products.configure", "products configure order");
assertEq(callLog[0][1].initialProducts, initialProducts, "products configure initialProducts");
assertEq(callLog[1][0], "editing.configure", "editing configure order");
assertEq(
    callLog[1][1].initialValue,
    initialEditingEstimateId,
    "editing configure initialValue"
);

process.exit(0);
