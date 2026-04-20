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

const helper = sandbox.WdCalculatorPrimaryUiBootstrap;
if (!helper) {
    throw new Error("WdCalculatorPrimaryUiBootstrap was not defined");
}

const callLog = [];
const getProducts = () => [{ id: 1 }];
const getCalculateEstimate = () => "calc";
const getCategories = () => [{ id: "cat-1" }];
const defaultCouponValue = 11000;

const exportsRef = {
    getProductsOptionsHtml() {},
    renderBaseComponentRow() {},
    ensureBaseComponentsUI() {},
    readBaseComponentsFromUI() {},
    updateBaseProductSelectOptions() {},
    initBaseComponentsLiveInteractions() {},
    getCouponValue() {},
    applyFinalPriceStyle() {},
    applyCouponDiscountStyle() {},
    appendAdditionalOptionRow() {},
    loadAdditionalOptionRows() {},
    readAdditionalOptionRowsFromUI() {},
};

helper.configure({
    baseComponentsUi: {
        configure(options) {
            callLog.push(["base.configure", options]);
        },
        getProductsOptionsHtml: exportsRef.getProductsOptionsHtml,
        renderBaseComponentRow: exportsRef.renderBaseComponentRow,
        ensureBaseComponentsUI: exportsRef.ensureBaseComponentsUI,
        readBaseComponentsFromUI: exportsRef.readBaseComponentsFromUI,
        updateBaseProductSelectOptions: exportsRef.updateBaseProductSelectOptions,
        initBaseComponentsLiveInteractions: exportsRef.initBaseComponentsLiveInteractions,
    },
    couponDisplayHelpers: {
        configure(options) {
            callLog.push(["coupon.configure", options]);
        },
        getCouponValue: exportsRef.getCouponValue,
        applyFinalPriceStyle: exportsRef.applyFinalPriceStyle,
        applyCouponDiscountStyle: exportsRef.applyCouponDiscountStyle,
    },
    additionalOptionsUi: {
        configure(options) {
            callLog.push(["additional.configure", options]);
        },
        appendAdditionalOptionRow: exportsRef.appendAdditionalOptionRow,
        loadAdditionalOptionRows: exportsRef.loadAdditionalOptionRows,
        readAdditionalOptionRowsFromUI: exportsRef.readAdditionalOptionRowsFromUI,
    },
    getProducts,
    getCalculateEstimate,
    defaultCouponValue,
    getCategories,
});

const exportedApi = helper.initPrimaryUiBootstrap();

assertEq(callLog.length, 3, "primary UI bootstrap call count");
assertEq(callLog[0][0], "base.configure", "base configure order");
assertEq(callLog[0][1].getProducts, getProducts, "base configure getProducts");
assertEq(
    callLog[0][1].getCalculateEstimate,
    getCalculateEstimate,
    "base configure getCalculateEstimate"
);
assertEq(callLog[1][0], "coupon.configure", "coupon configure order");
assertEq(
    callLog[1][1].defaultCouponValue,
    defaultCouponValue,
    "coupon configure defaultCouponValue"
);
assertEq(callLog[2][0], "additional.configure", "additional configure order");
assertEq(
    callLog[2][1].getCategories,
    getCategories,
    "additional configure getCategories"
);
assertEq(
    callLog[2][1].getCalculateEstimate,
    getCalculateEstimate,
    "additional configure getCalculateEstimate"
);

assertEq(
    exportedApi.getProductsOptionsHtml,
    exportsRef.getProductsOptionsHtml,
    "exported getProductsOptionsHtml"
);
assertEq(
    exportedApi.renderBaseComponentRow,
    exportsRef.renderBaseComponentRow,
    "exported renderBaseComponentRow"
);
assertEq(
    exportedApi.ensureBaseComponentsUI,
    exportsRef.ensureBaseComponentsUI,
    "exported ensureBaseComponentsUI"
);
assertEq(
    exportedApi.readBaseComponentsFromUI,
    exportsRef.readBaseComponentsFromUI,
    "exported readBaseComponentsFromUI"
);
assertEq(
    exportedApi.updateBaseProductSelectOptions,
    exportsRef.updateBaseProductSelectOptions,
    "exported updateBaseProductSelectOptions"
);
assertEq(
    exportedApi.initBaseComponentsLiveInteractions,
    exportsRef.initBaseComponentsLiveInteractions,
    "exported initBaseComponentsLiveInteractions"
);
assertEq(exportedApi.getCouponValue, exportsRef.getCouponValue, "exported getCouponValue");
assertEq(
    exportedApi.applyFinalPriceStyle,
    exportsRef.applyFinalPriceStyle,
    "exported applyFinalPriceStyle"
);
assertEq(
    exportedApi.applyCouponDiscountStyle,
    exportsRef.applyCouponDiscountStyle,
    "exported applyCouponDiscountStyle"
);
assertEq(
    exportedApi.appendAdditionalOptionRow,
    exportsRef.appendAdditionalOptionRow,
    "exported appendAdditionalOptionRow"
);
assertEq(
    exportedApi.loadAdditionalOptionRows,
    exportsRef.loadAdditionalOptionRows,
    "exported loadAdditionalOptionRows"
);
assertEq(
    exportedApi.readAdditionalOptionRowsFromUI,
    exportsRef.readAdditionalOptionRowsFromUI,
    "exported readAdditionalOptionRowsFromUI"
);

process.exit(0);
