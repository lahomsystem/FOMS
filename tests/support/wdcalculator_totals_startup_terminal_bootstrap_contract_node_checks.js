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

const helper = sandbox.WdCalculatorTotalsStartupTerminalBootstrap;
if (!helper) {
    throw new Error("WdCalculatorTotalsStartupTerminalBootstrap was not defined");
}

const callLog = [];
const getEstimates = () => [{ id: 1 }];
const getEditingEstimateId = () => 3;
const getCouponValue = () => 11000;
const resolveAggregateTotals = () => ({ finalPrice: 10 });
const collectNotes = () => "notes";
const formatNumber = () => "formatted";
const applyFinalPriceStyle = () => "final-style";
const applyCouponDiscountStyle = () => "coupon-style";
const documentRef = { body: {} };
const alertImpl = () => {};
const consoleRef = { warn() {}, error() {} };
const categories = [{ id: 1, name: "옵션" }];
const bindProductSelect = () => {};
const initBaseComponentsLiveInteractions = () => {};
const initAddOptionButton = () => {};
const initCalculateButton = () => {};
const initSearchResultsLoadBridge = () => {};
const bindOrderMatchButtons = () => {};
const initCouponShippingWiring = () => {};
const loadProducts = () => {};
const ensureBaseComponentsUI = () => {};

helper.configure({
    totalEstimatesDisplay: {
        configure(options) {
            callLog.push(["totalEstimatesDisplay.configure", options]);
        },
    },
    startupInit: {
        configure(options) {
            callLog.push(["startupInit.configure", options]);
        },
        initStartupInteractions() {
            callLog.push(["startupInit.initStartupInteractions"]);
        },
    },
    terminalInit: {
        configure(options) {
            callLog.push(["terminalInit.configure", options]);
        },
    },
    getEstimates,
    getEditingEstimateId,
    getCouponValue,
    resolveAggregateTotals,
    collectNotes,
    formatNumber,
    applyFinalPriceStyle,
    applyCouponDiscountStyle,
    documentRef,
    alertImpl,
    consoleRef,
    categories,
    bindProductSelect,
    initBaseComponentsLiveInteractions,
    initAddOptionButton,
    initCalculateButton,
    initSearchResultsLoadBridge,
    bindOrderMatchButtons,
    initCouponShippingWiring,
    loadProducts,
    ensureBaseComponentsUI,
});

helper.initTotalsStartupTerminalBootstrap();

assertEq(callLog.length, 4, "totals/startup/terminal bootstrap call count");
assertEq(
    callLog[0][0],
    "totalEstimatesDisplay.configure",
    "total estimates configure order"
);
assertEq(callLog[0][1].getEstimates, getEstimates, "total estimates getEstimates");
assertEq(
    callLog[0][1].getEditingEstimateId,
    getEditingEstimateId,
    "total estimates getEditingEstimateId"
);
assertEq(
    callLog[0][1].getCouponValue,
    getCouponValue,
    "total estimates getCouponValue"
);
assertEq(
    callLog[0][1].resolveAggregateTotals,
    resolveAggregateTotals,
    "total estimates resolveAggregateTotals"
);
assertEq(callLog[0][1].collectNotes, collectNotes, "total estimates collectNotes");
assertEq(callLog[0][1].formatNumber, formatNumber, "total estimates formatNumber");
assertEq(
    callLog[0][1].applyFinalPriceStyle,
    applyFinalPriceStyle,
    "total estimates applyFinalPriceStyle"
);
assertEq(
    callLog[0][1].applyCouponDiscountStyle,
    applyCouponDiscountStyle,
    "total estimates applyCouponDiscountStyle"
);
assertEq(callLog[0][1].documentRef, documentRef, "total estimates documentRef");
assertEq(callLog[0][1].alertImpl, alertImpl, "total estimates alertImpl");
assertEq(callLog[0][1].consoleRef, consoleRef, "total estimates consoleRef");

assertEq(callLog[1][0], "startupInit.configure", "startup init configure order");
assertEq(callLog[1][1].categories, categories, "startup init categories");
assertEq(callLog[1][1].consoleRef, consoleRef, "startup init consoleRef");
assertEq(
    callLog[1][1].bindProductSelect,
    bindProductSelect,
    "startup init bindProductSelect"
);
assertEq(
    callLog[1][1].initBaseComponentsLiveInteractions,
    initBaseComponentsLiveInteractions,
    "startup init initBaseComponentsLiveInteractions"
);
assertEq(
    callLog[1][1].initAddOptionButton,
    initAddOptionButton,
    "startup init initAddOptionButton"
);
assertEq(
    callLog[1][1].initCalculateButton,
    initCalculateButton,
    "startup init initCalculateButton"
);
assertEq(
    callLog[1][1].initSearchResultsLoadBridge,
    initSearchResultsLoadBridge,
    "startup init initSearchResultsLoadBridge"
);
assertEq(
    callLog[1][1].bindOrderMatchButtons,
    bindOrderMatchButtons,
    "startup init bindOrderMatchButtons"
);
assertEq(
    callLog[1][1].initCouponShippingWiring,
    initCouponShippingWiring,
    "startup init initCouponShippingWiring"
);

assertEq(callLog[2][0], "terminalInit.configure", "terminal init configure order");
assertEq(callLog[2][1].loadProducts, loadProducts, "terminal init loadProducts");
assertEq(
    callLog[2][1].ensureBaseComponentsUI,
    ensureBaseComponentsUI,
    "terminal init ensureBaseComponentsUI"
);

assertEq(
    callLog[3][0],
    "startupInit.initStartupInteractions",
    "startup init call order"
);

process.exit(0);
