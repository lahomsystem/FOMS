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

const helper = sandbox.WdCalculatorPostMutationUiBootstrap;
if (!helper) {
    throw new Error("WdCalculatorPostMutationUiBootstrap was not defined");
}

const callLog = [];
const sidebarBootstrap = { initSidebarBootstrap() {} };
const refreshAfterSave = { configure() {} };
const urlBootstrap = { configure() {}, initUrlBootstrap() {} };
const initSidebarEstimates = () => "init-sidebar";
const loadEstimateToForm = () => "load-estimate";
const formatNumber = () => "format";
const setEstimates = () => "set-estimates";
const resetInputFormKeepCustomerName = () => "reset-form";
const resetInputFormToNewEstimate = () => "reset-new";
const renderEstimatesList = () => "render-list";
const getProducts = () => [{ id: 1 }];
const documentRef = { body: {} };
const consoleRef = { log() {} };
const setTimeoutImpl = () => 1;
const lateBootstrapResult = { loadSidebarEstimates() {} };
const renderInitialBaseComponentsUi = () => {
    callLog.push(["renderInitialBaseComponentsUi"]);
};

helper.configure({
    lateBootstrap: {
        configure(options) {
            callLog.push(["lateBootstrap.configure", options]);
        },
        initLateBootstrap() {
            callLog.push(["lateBootstrap.initLateBootstrap"]);
            return lateBootstrapResult;
        },
    },
    sidebarBootstrap,
    refreshAfterSave,
    urlBootstrap,
    initSidebarEstimates,
    loadEstimateToForm,
    formatNumber,
    setEstimates,
    resetInputFormKeepCustomerName,
    resetInputFormToNewEstimate,
    renderEstimatesList,
    getProducts,
    documentRef,
    consoleRef,
    setTimeoutImpl,
    renderInitialBaseComponentsUi,
});

const result = helper.initPostMutationUiBootstrap();

assertEq(callLog.length, 3, "post-mutation-ui bootstrap call count");
assertEq(
    callLog[0][0],
    "lateBootstrap.configure",
    "late bootstrap configure order"
);
assertEq(
    callLog[0][1].sidebarBootstrap,
    sidebarBootstrap,
    "late bootstrap sidebarBootstrap"
);
assertEq(
    callLog[0][1].refreshAfterSave,
    refreshAfterSave,
    "late bootstrap refreshAfterSave"
);
assertEq(callLog[0][1].urlBootstrap, urlBootstrap, "late bootstrap urlBootstrap");
assertEq(
    callLog[0][1].initSidebarEstimates,
    initSidebarEstimates,
    "late bootstrap initSidebarEstimates"
);
assertEq(
    callLog[0][1].loadEstimateToForm,
    loadEstimateToForm,
    "late bootstrap loadEstimateToForm"
);
assertEq(callLog[0][1].formatNumber, formatNumber, "late bootstrap formatNumber");
assertEq(callLog[0][1].setEstimates, setEstimates, "late bootstrap setEstimates");
assertEq(
    callLog[0][1].resetInputFormKeepCustomerName,
    resetInputFormKeepCustomerName,
    "late bootstrap resetInputFormKeepCustomerName"
);
assertEq(
    callLog[0][1].resetInputFormToNewEstimate,
    resetInputFormToNewEstimate,
    "late bootstrap resetInputFormToNewEstimate"
);
assertEq(
    callLog[0][1].renderEstimatesList,
    renderEstimatesList,
    "late bootstrap renderEstimatesList"
);
assertEq(callLog[0][1].getProducts, getProducts, "late bootstrap getProducts");
assertEq(callLog[0][1].documentRef, documentRef, "late bootstrap documentRef");
assertEq(callLog[0][1].consoleRef, consoleRef, "late bootstrap consoleRef");
assertEq(
    callLog[0][1].setTimeoutImpl,
    setTimeoutImpl,
    "late bootstrap setTimeoutImpl"
);
assertEq(
    callLog[1][0],
    "lateBootstrap.initLateBootstrap",
    "late bootstrap init order"
);
assertEq(
    callLog[2][0],
    "renderInitialBaseComponentsUi",
    "base components render order"
);
assertEq(result, lateBootstrapResult, "post-mutation-ui bootstrap return value");

process.exit(0);
