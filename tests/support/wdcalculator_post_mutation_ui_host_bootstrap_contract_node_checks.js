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

const helper = sandbox.WdCalculatorPostMutationUiHostBootstrap;
if (!helper) {
    throw new Error("WdCalculatorPostMutationUiHostBootstrap was not defined");
}

const callLog = [];
const postMutationUiBootstrap = {
    configure(options) {
        callLog.push(["postMutationUiBootstrap.configure", options]);
    },
    initPostMutationUiBootstrap() {
        callLog.push(["postMutationUiBootstrap.initPostMutationUiBootstrap"]);
        return "post-mutation-ui-host-ok";
    },
};
const lateBootstrap = { name: "late-bootstrap" };
const sidebarBootstrap = { name: "sidebar-bootstrap" };
const refreshAfterSave = { name: "refresh-after-save" };
const urlBootstrap = { name: "url-bootstrap" };
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
const renderInitialBaseComponentsUi = () => "render-base-components";

helper.configure({
    postMutationUiBootstrap,
    lateBootstrap,
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

const result = helper.initPostMutationUiHostBootstrap();

assertEq(callLog.length, 2, "post mutation ui host bootstrap call count");
assertEq(
    callLog[0][0],
    "postMutationUiBootstrap.configure",
    "post mutation ui host configure order"
);
assertEq(callLog[0][1].lateBootstrap, lateBootstrap, "post mutation ui host lateBootstrap");
assertEq(
    callLog[0][1].sidebarBootstrap,
    sidebarBootstrap,
    "post mutation ui host sidebarBootstrap"
);
assertEq(
    callLog[0][1].refreshAfterSave,
    refreshAfterSave,
    "post mutation ui host refreshAfterSave"
);
assertEq(callLog[0][1].urlBootstrap, urlBootstrap, "post mutation ui host urlBootstrap");
assertEq(
    callLog[0][1].initSidebarEstimates,
    initSidebarEstimates,
    "post mutation ui host initSidebarEstimates"
);
assertEq(
    callLog[0][1].loadEstimateToForm,
    loadEstimateToForm,
    "post mutation ui host loadEstimateToForm"
);
assertEq(callLog[0][1].formatNumber, formatNumber, "post mutation ui host formatNumber");
assertEq(callLog[0][1].setEstimates, setEstimates, "post mutation ui host setEstimates");
assertEq(
    callLog[0][1].resetInputFormKeepCustomerName,
    resetInputFormKeepCustomerName,
    "post mutation ui host resetInputFormKeepCustomerName"
);
assertEq(
    callLog[0][1].resetInputFormToNewEstimate,
    resetInputFormToNewEstimate,
    "post mutation ui host resetInputFormToNewEstimate"
);
assertEq(
    callLog[0][1].renderEstimatesList,
    renderEstimatesList,
    "post mutation ui host renderEstimatesList"
);
assertEq(callLog[0][1].getProducts, getProducts, "post mutation ui host getProducts");
assertEq(callLog[0][1].documentRef, documentRef, "post mutation ui host documentRef");
assertEq(callLog[0][1].consoleRef, consoleRef, "post mutation ui host consoleRef");
assertEq(
    callLog[0][1].setTimeoutImpl,
    setTimeoutImpl,
    "post mutation ui host setTimeoutImpl"
);
assertEq(
    callLog[0][1].renderInitialBaseComponentsUi,
    renderInitialBaseComponentsUi,
    "post mutation ui host renderInitialBaseComponentsUi"
);
assertEq(
    callLog[1][0],
    "postMutationUiBootstrap.initPostMutationUiBootstrap",
    "post mutation ui host init order"
);
assertEq(result, "post-mutation-ui-host-ok", "post mutation ui host return value");

process.exit(0);
