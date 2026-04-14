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

const helper = sandbox.WdCalculatorCatalogButtonsHostBootstrap;
if (!helper) {
    throw new Error("WdCalculatorCatalogButtonsHostBootstrap was not defined");
}

const callLog = [];
const addOptionButton = { name: "add-option-button" };
const calculateButton = { name: "calculate-button" };
const productCatalogUi = { name: "product-catalog-ui" };
const documentRef = { body: {} };
const appendAdditionalOptionRow = () => "append";
const calculateEstimate = () => "calculate";
const getProducts = () => [{ id: 1 }];
const setProducts = () => "set";
const getCalculateEstimate = () => calculateEstimate;
const updateBaseProductSelectOptions = () => "update";
const ensureBaseComponentsUI = () => "ensure";
const expectedResult = "catalog-buttons-host-ok";

helper.configure({
    catalogButtonsBootstrap: {
        configure(options) {
            callLog.push(["catalogButtonsBootstrap.configure", options]);
        },
        initCatalogButtonsBootstrap() {
            callLog.push(["catalogButtonsBootstrap.initCatalogButtonsBootstrap"]);
            return expectedResult;
        },
    },
    addOptionButton,
    calculateButton,
    productCatalogUi,
    documentRef,
    appendAdditionalOptionRow,
    calculateEstimate,
    getProducts,
    setProducts,
    getCalculateEstimate,
    updateBaseProductSelectOptions,
    ensureBaseComponentsUI,
});

const result = helper.initCatalogButtonsHostBootstrap();

assertEq(callLog.length, 2, "catalog buttons host bootstrap call count");
assertEq(
    callLog[0][0],
    "catalogButtonsBootstrap.configure",
    "catalog buttons host configure order"
);
assertEq(
    callLog[0][1].addOptionButton,
    addOptionButton,
    "catalog buttons host addOptionButton"
);
assertEq(
    callLog[0][1].calculateButton,
    calculateButton,
    "catalog buttons host calculateButton"
);
assertEq(
    callLog[0][1].productCatalogUi,
    productCatalogUi,
    "catalog buttons host productCatalogUi"
);
assertEq(callLog[0][1].documentRef, documentRef, "catalog buttons host documentRef");
assertEq(
    callLog[0][1].appendAdditionalOptionRow,
    appendAdditionalOptionRow,
    "catalog buttons host appendAdditionalOptionRow"
);
assertEq(
    callLog[0][1].calculateEstimate,
    calculateEstimate,
    "catalog buttons host calculateEstimate"
);
assertEq(callLog[0][1].getProducts, getProducts, "catalog buttons host getProducts");
assertEq(callLog[0][1].setProducts, setProducts, "catalog buttons host setProducts");
assertEq(
    callLog[0][1].getCalculateEstimate,
    getCalculateEstimate,
    "catalog buttons host getCalculateEstimate"
);
assertEq(
    callLog[0][1].updateBaseProductSelectOptions,
    updateBaseProductSelectOptions,
    "catalog buttons host updateBaseProductSelectOptions"
);
assertEq(
    callLog[0][1].ensureBaseComponentsUI,
    ensureBaseComponentsUI,
    "catalog buttons host ensureBaseComponentsUI"
);
assertEq(
    callLog[1][0],
    "catalogButtonsBootstrap.initCatalogButtonsBootstrap",
    "catalog buttons host init order"
);
assertEq(result, expectedResult, "catalog buttons host return value");

process.exit(0);
