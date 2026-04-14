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

const helper = sandbox.WdCalculatorCatalogButtonsBootstrap;
if (!helper) {
    throw new Error("WdCalculatorCatalogButtonsBootstrap was not defined");
}

const callLog = [];
const documentRef = { body: {} };
const appendAdditionalOptionRow = () => "append";
const calculateEstimate = () => "calculate";
const getProducts = () => [{ id: 1 }];
const setProducts = () => "set";
const getCalculateEstimate = () => calculateEstimate;
const updateBaseProductSelectOptions = () => "update";
const ensureBaseComponentsUI = () => "ensure";

helper.configure({
    addOptionButton: {
        configure(options) {
            callLog.push(["addOption.configure", options]);
        },
    },
    calculateButton: {
        configure(options) {
            callLog.push(["calculateButton.configure", options]);
        },
    },
    productCatalogUi: {
        configure(options) {
            callLog.push(["productCatalog.configure", options]);
        },
    },
    documentRef,
    appendAdditionalOptionRow,
    calculateEstimate,
    getProducts,
    setProducts,
    getCalculateEstimate,
    updateBaseProductSelectOptions,
    ensureBaseComponentsUI,
});

helper.initCatalogButtonsBootstrap();

assertEq(callLog.length, 3, "catalog buttons bootstrap call count");
assertEq(callLog[0][0], "addOption.configure", "add option configure order");
assertEq(callLog[0][1].documentRef, documentRef, "add option documentRef");
assertEq(
    callLog[0][1].appendAdditionalOptionRow,
    appendAdditionalOptionRow,
    "add option appendAdditionalOptionRow"
);
assertEq(
    callLog[1][0],
    "calculateButton.configure",
    "calculate button configure order"
);
assertEq(callLog[1][1].documentRef, documentRef, "calculate button documentRef");
assertEq(
    callLog[1][1].calculateEstimate,
    calculateEstimate,
    "calculate button calculateEstimate"
);
assertEq(
    callLog[2][0],
    "productCatalog.configure",
    "product catalog configure order"
);
assertEq(callLog[2][1].getProducts, getProducts, "product catalog getProducts");
assertEq(callLog[2][1].setProducts, setProducts, "product catalog setProducts");
assertEq(
    callLog[2][1].getCalculateEstimate,
    getCalculateEstimate,
    "product catalog getCalculateEstimate"
);
assertEq(
    callLog[2][1].updateBaseProductSelectOptions,
    updateBaseProductSelectOptions,
    "product catalog updateBaseProductSelectOptions"
);
assertEq(
    callLog[2][1].ensureBaseComponentsUI,
    ensureBaseComponentsUI,
    "product catalog ensureBaseComponentsUI"
);

process.exit(0);
