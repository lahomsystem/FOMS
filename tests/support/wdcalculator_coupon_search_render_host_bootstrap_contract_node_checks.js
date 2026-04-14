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

const helper = sandbox.WdCalculatorCouponSearchRenderHostBootstrap;
if (!helper) {
    throw new Error("WdCalculatorCouponSearchRenderHostBootstrap was not defined");
}

const callLog = [];
const couponShippingWiring = { name: "coupon-shipping-wiring" };
const searchResultsLoad = { name: "search-results-load" };
const renderEstimatesList = { name: "render-estimates-list" };
const defaultCouponValue = 11000;
const getEstimates = () => [{ id: 1 }];
const calculateEstimate = () => "calculate";
const calculateTotalEstimates = () => "calculate-total";
const getCouponValue = () => 11000;
const loadEstimateToForm = () => "load";
const formatNumber = () => "format";
const escapeHtml = () => "escape";
const formatNotesText = () => "notes";
const onRenderComplete = () => "render-complete";
const expectedResult = "coupon-search-render-host-ok";

helper.configure({
    couponSearchRenderBootstrap: {
        configure(options) {
            callLog.push(["couponSearchRenderBootstrap.configure", options]);
        },
        initCouponSearchRenderBootstrap() {
            callLog.push(["couponSearchRenderBootstrap.initCouponSearchRenderBootstrap"]);
            return expectedResult;
        },
    },
    couponShippingWiring,
    searchResultsLoad,
    renderEstimatesList,
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
});

const result = helper.initCouponSearchRenderHostBootstrap();

assertEq(callLog.length, 2, "coupon search render host bootstrap call count");
assertEq(
    callLog[0][0],
    "couponSearchRenderBootstrap.configure",
    "coupon search render host configure order"
);
assertEq(
    callLog[0][1].couponShippingWiring,
    couponShippingWiring,
    "coupon search render host couponShippingWiring"
);
assertEq(
    callLog[0][1].searchResultsLoad,
    searchResultsLoad,
    "coupon search render host searchResultsLoad"
);
assertEq(
    callLog[0][1].renderEstimatesList,
    renderEstimatesList,
    "coupon search render host renderEstimatesList"
);
assertEq(
    callLog[0][1].defaultCouponValue,
    defaultCouponValue,
    "coupon search render host defaultCouponValue"
);
assertEq(callLog[0][1].getEstimates, getEstimates, "coupon search render host getEstimates");
assertEq(
    callLog[0][1].calculateEstimate,
    calculateEstimate,
    "coupon search render host calculateEstimate"
);
assertEq(
    callLog[0][1].calculateTotalEstimates,
    calculateTotalEstimates,
    "coupon search render host calculateTotalEstimates"
);
assertEq(
    callLog[0][1].getCouponValue,
    getCouponValue,
    "coupon search render host getCouponValue"
);
assertEq(
    callLog[0][1].loadEstimateToForm,
    loadEstimateToForm,
    "coupon search render host loadEstimateToForm"
);
assertEq(
    callLog[0][1].formatNumber,
    formatNumber,
    "coupon search render host formatNumber"
);
assertEq(callLog[0][1].escapeHtml, escapeHtml, "coupon search render host escapeHtml");
assertEq(
    callLog[0][1].formatNotesText,
    formatNotesText,
    "coupon search render host formatNotesText"
);
assertEq(
    callLog[0][1].onRenderComplete,
    onRenderComplete,
    "coupon search render host onRenderComplete"
);
assertEq(
    callLog[1][0],
    "couponSearchRenderBootstrap.initCouponSearchRenderBootstrap",
    "coupon search render host init order"
);
assertEq(result, expectedResult, "coupon search render host return value");

process.exit(0);
