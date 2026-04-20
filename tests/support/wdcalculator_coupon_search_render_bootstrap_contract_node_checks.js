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

const helper = sandbox.WdCalculatorCouponSearchRenderBootstrap;
if (!helper) {
    throw new Error("WdCalculatorCouponSearchRenderBootstrap was not defined");
}

const callLog = [];
const defaultCouponValue = 11000;
const getEstimates = () => [{ id: 1 }];
const calculateEstimate = () => "calculate";
const calculateTotalEstimates = () => "calculateTotal";
const getCouponValue = () => 11000;
const loadEstimateToForm = () => "load";
const formatNumber = () => "format";
const escapeHtml = () => "escape";
const formatNotesText = () => "notes";
const onRenderComplete = () => "renderComplete";
const getProducts = () => [{ id: 1 }];

helper.configure({
    couponShippingWiring: {
        configure(options) {
            callLog.push(["couponShipping.configure", options]);
        },
    },
    searchResultsLoad: {
        configure(options) {
            callLog.push(["searchResults.configure", options]);
        },
    },
    renderEstimatesList: {
        configure(options) {
            callLog.push(["renderList.configure", options]);
        },
    },
    defaultCouponValue,
    getEstimates,
    calculateEstimate,
    calculateTotalEstimates,
    getCouponValue,
    loadEstimateToForm,
    formatNumber,
    escapeHtml,
    formatNotesText,
    onRenderComplete,
    getProducts,
});

helper.initCouponSearchRenderBootstrap();

assertEq(callLog.length, 3, "coupon/search/render bootstrap call count");
assertEq(
    callLog[0][0],
    "couponShipping.configure",
    "coupon shipping configure order"
);
assertEq(
    callLog[0][1].defaultCouponValue,
    defaultCouponValue,
    "coupon shipping defaultCouponValue"
);
assertEq(callLog[0][1].getEstimates, getEstimates, "coupon shipping getEstimates");
assertEq(
    callLog[0][1].calculateEstimate,
    calculateEstimate,
    "coupon shipping calculateEstimate"
);
assertEq(
    callLog[0][1].calculateTotalEstimates,
    calculateTotalEstimates,
    "coupon shipping calculateTotalEstimates"
);
assertEq(
    callLog[0][1].getCouponValue,
    getCouponValue,
    "coupon shipping getCouponValue"
);
assertEq(
    callLog[1][0],
    "searchResults.configure",
    "search results configure order"
);
assertEq(
    callLog[1][1].loadEstimateToForm,
    loadEstimateToForm,
    "search results loadEstimateToForm"
);
assertEq(callLog[1][1].formatNumber, formatNumber, "search results formatNumber");
assertEq(callLog[2][0], "renderList.configure", "render list configure order");
assertEq(callLog[2][1].getEstimates, getEstimates, "render list getEstimates");
assertEq(callLog[2][1].formatNumber, formatNumber, "render list formatNumber");
assertEq(callLog[2][1].escapeHtml, escapeHtml, "render list escapeHtml");
assertEq(
    callLog[2][1].formatNotesText,
    formatNotesText,
    "render list formatNotesText"
);
assertEq(
    callLog[2][1].onRenderComplete,
    onRenderComplete,
    "render list onRenderComplete"
);
assertEq(callLog[2][1].getProducts, getProducts, "render list getProducts");

process.exit(0);
