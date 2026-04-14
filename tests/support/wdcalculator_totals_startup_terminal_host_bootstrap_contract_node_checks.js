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

const helper = sandbox.WdCalculatorTotalsStartupTerminalHostBootstrap;
if (!helper) {
    throw new Error("WdCalculatorTotalsStartupTerminalHostBootstrap was not defined");
}

const callLog = [];
const totalEstimatesDisplay = { name: "total-estimates-display" };
const startupInit = { name: "startup-init" };
const terminalInit = { name: "terminal-init" };
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
const expectedResult = "totals-startup-terminal-host-ok";

helper.configure({
    totalsStartupTerminalBootstrap: {
        configure(options) {
            callLog.push(["totalsStartupTerminalBootstrap.configure", options]);
        },
        initTotalsStartupTerminalBootstrap() {
            callLog.push(["totalsStartupTerminalBootstrap.initTotalsStartupTerminalBootstrap"]);
            return expectedResult;
        },
    },
    totalEstimatesDisplay,
    startupInit,
    terminalInit,
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

const result = helper.initTotalsStartupTerminalHostBootstrap();

assertEq(callLog.length, 2, "totals startup terminal host bootstrap call count");
assertEq(
    callLog[0][0],
    "totalsStartupTerminalBootstrap.configure",
    "totals startup terminal host configure order"
);
assertEq(
    callLog[0][1].totalEstimatesDisplay,
    totalEstimatesDisplay,
    "totals startup terminal host totalEstimatesDisplay"
);
assertEq(callLog[0][1].startupInit, startupInit, "totals startup terminal host startupInit");
assertEq(
    callLog[0][1].terminalInit,
    terminalInit,
    "totals startup terminal host terminalInit"
);
assertEq(callLog[0][1].getEstimates, getEstimates, "totals startup terminal host getEstimates");
assertEq(
    callLog[0][1].getEditingEstimateId,
    getEditingEstimateId,
    "totals startup terminal host getEditingEstimateId"
);
assertEq(
    callLog[0][1].getCouponValue,
    getCouponValue,
    "totals startup terminal host getCouponValue"
);
assertEq(
    callLog[0][1].resolveAggregateTotals,
    resolveAggregateTotals,
    "totals startup terminal host resolveAggregateTotals"
);
assertEq(
    callLog[0][1].collectNotes,
    collectNotes,
    "totals startup terminal host collectNotes"
);
assertEq(callLog[0][1].formatNumber, formatNumber, "totals startup terminal host formatNumber");
assertEq(
    callLog[0][1].applyFinalPriceStyle,
    applyFinalPriceStyle,
    "totals startup terminal host applyFinalPriceStyle"
);
assertEq(
    callLog[0][1].applyCouponDiscountStyle,
    applyCouponDiscountStyle,
    "totals startup terminal host applyCouponDiscountStyle"
);
assertEq(callLog[0][1].documentRef, documentRef, "totals startup terminal host documentRef");
assertEq(callLog[0][1].alertImpl, alertImpl, "totals startup terminal host alertImpl");
assertEq(callLog[0][1].consoleRef, consoleRef, "totals startup terminal host consoleRef");
assertEq(callLog[0][1].categories, categories, "totals startup terminal host categories");
assertEq(
    callLog[0][1].bindProductSelect,
    bindProductSelect,
    "totals startup terminal host bindProductSelect"
);
assertEq(
    callLog[0][1].initBaseComponentsLiveInteractions,
    initBaseComponentsLiveInteractions,
    "totals startup terminal host initBaseComponentsLiveInteractions"
);
assertEq(
    callLog[0][1].initAddOptionButton,
    initAddOptionButton,
    "totals startup terminal host initAddOptionButton"
);
assertEq(
    callLog[0][1].initCalculateButton,
    initCalculateButton,
    "totals startup terminal host initCalculateButton"
);
assertEq(
    callLog[0][1].initSearchResultsLoadBridge,
    initSearchResultsLoadBridge,
    "totals startup terminal host initSearchResultsLoadBridge"
);
assertEq(
    callLog[0][1].bindOrderMatchButtons,
    bindOrderMatchButtons,
    "totals startup terminal host bindOrderMatchButtons"
);
assertEq(
    callLog[0][1].initCouponShippingWiring,
    initCouponShippingWiring,
    "totals startup terminal host initCouponShippingWiring"
);
assertEq(callLog[0][1].loadProducts, loadProducts, "totals startup terminal host loadProducts");
assertEq(
    callLog[0][1].ensureBaseComponentsUI,
    ensureBaseComponentsUI,
    "totals startup terminal host ensureBaseComponentsUI"
);
assertEq(
    callLog[1][0],
    "totalsStartupTerminalBootstrap.initTotalsStartupTerminalBootstrap",
    "totals startup terminal host init order"
);
assertEq(result, expectedResult, "totals startup terminal host return value");

process.exit(0);
