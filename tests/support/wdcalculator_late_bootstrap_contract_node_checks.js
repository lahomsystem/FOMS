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
    document: {},
    console,
};
sandbox.window = sandbox;
sandbox.globalThis = sandbox;

vm.createContext(sandbox);
vm.runInContext(helperSrc, sandbox);

const helper = sandbox.WdCalculatorLateBootstrap;
if (!helper) {
    throw new Error("WdCalculatorLateBootstrap was not defined");
}

const callLog = [];
const initSidebarEstimates = () => {};
const loadEstimateToForm = () => {};
const formatNumber = () => {};
const setEstimates = () => {};
const resetInputFormKeepCustomerName = () => {};
const renderEstimatesList = () => {};
const getProducts = () => [];
const documentRef = { name: "document-ref" };
const consoleRef = { name: "console-ref" };
const setTimeoutImpl = () => 1;
const sidebarApi = {
    loadSidebarEstimates() {},
    deleteEstimate() {},
};

helper.configure({
    sidebarBootstrap: {
        configure(options) {
            callLog.push(["sidebar.configure", options]);
        },
        initSidebarBootstrap() {
            callLog.push(["sidebar.init"]);
            return sidebarApi;
        },
    },
    refreshAfterSave: {
        configure(options) {
            callLog.push(["refresh.configure", options]);
        },
    },
    urlBootstrap: {
        configure(options) {
            callLog.push(["url.configure", options]);
        },
        initUrlBootstrap() {
            callLog.push(["url.init"]);
        },
    },
    initSidebarEstimates,
    loadEstimateToForm,
    formatNumber,
    setEstimates,
    resetInputFormKeepCustomerName,
    renderEstimatesList,
    getProducts,
    documentRef,
    consoleRef,
    setTimeoutImpl,
});

const result = helper.initLateBootstrap();

assertEq(callLog.length, 5, "late bootstrap call count");
assertEq(callLog[0][0], "sidebar.configure", "sidebar configure order");
assertEq(
    callLog[0][1].initSidebarEstimates,
    initSidebarEstimates,
    "sidebar configure initSidebarEstimates"
);
assertEq(
    callLog[0][1].loadEstimateToForm,
    loadEstimateToForm,
    "sidebar configure loadEstimateToForm"
);
assertEq(callLog[0][1].formatNumber, formatNumber, "sidebar configure formatNumber");
assertEq(callLog[1][0], "sidebar.init", "sidebar init order");
assertEq(callLog[2][0], "refresh.configure", "refresh configure order");
assertEq(callLog[2][1].setEstimates, setEstimates, "refresh configure setEstimates");
assertEq(
    callLog[2][1].resetInputFormKeepCustomerName,
    resetInputFormKeepCustomerName,
    "refresh configure resetInputFormKeepCustomerName"
);
assertEq(
    callLog[2][1].renderEstimatesList,
    renderEstimatesList,
    "refresh configure renderEstimatesList"
);
assertEq(
    callLog[2][1].loadSidebarEstimates,
    sidebarApi.loadSidebarEstimates,
    "refresh configure loadSidebarEstimates"
);
assertEq(callLog[2][1].documentRef, documentRef, "refresh configure documentRef");
assertEq(callLog[2][1].consoleRef, consoleRef, "refresh configure consoleRef");
assertEq(callLog[2][1].setTimeoutImpl, setTimeoutImpl, "refresh configure setTimeoutImpl");
assertEq(callLog[3][0], "url.configure", "url configure order");
assertEq(callLog[3][1].getProducts, getProducts, "url configure getProducts");
assertEq(callLog[3][1].loadEstimateToForm, loadEstimateToForm, "url configure loadEstimateToForm");
assertEq(
    callLog[3][1].loadSidebarEstimates,
    sidebarApi.loadSidebarEstimates,
    "url configure loadSidebarEstimates"
);
assertEq(callLog[4][0], "url.init", "url init order");
assertEq(result, sidebarApi, "late bootstrap returns original sidebar API");

process.exit(0);
