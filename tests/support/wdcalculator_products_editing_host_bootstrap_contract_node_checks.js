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

const helper = sandbox.WdCalculatorProductsEditingHostBootstrap;
if (!helper) {
    throw new Error("WdCalculatorProductsEditingHostBootstrap was not defined");
}

const callLog = [];
const productsState = { name: "products-state" };
const editingEstimateIdState = { name: "editing-state" };
const initialProducts = [{ id: 1, name: "seed" }];
const initialEditingEstimateId = "editing-id";
const expectedResult = "products-editing-host-ok";

helper.configure({
    productsEditingBootstrap: {
        configure(options) {
            callLog.push(["productsEditingBootstrap.configure", options]);
        },
        initProductsEditingBootstrap() {
            callLog.push(["productsEditingBootstrap.initProductsEditingBootstrap"]);
            return expectedResult;
        },
    },
    productsState,
    editingEstimateIdState,
    initialProducts,
    initialEditingEstimateId,
});

const result = helper.initProductsEditingHostBootstrap();

assertEq(callLog.length, 2, "products editing host bootstrap call count");
assertEq(
    callLog[0][0],
    "productsEditingBootstrap.configure",
    "products editing host configure order"
);
assertEq(callLog[0][1].productsState, productsState, "products editing host productsState");
assertEq(
    callLog[0][1].editingEstimateIdState,
    editingEstimateIdState,
    "products editing host editingEstimateIdState"
);
assertEq(
    callLog[0][1].initialProducts,
    initialProducts,
    "products editing host initialProducts"
);
assertEq(
    callLog[0][1].initialEditingEstimateId,
    initialEditingEstimateId,
    "products editing host initialEditingEstimateId"
);
assertEq(
    callLog[1][0],
    "productsEditingBootstrap.initProductsEditingBootstrap",
    "products editing host init order"
);
assertEq(result, expectedResult, "products editing host return value");

process.exit(0);
