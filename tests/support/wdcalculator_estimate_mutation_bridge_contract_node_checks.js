const fs = require("fs");
const path = require("path");
const vm = require("vm");

const repoRoot = path.join(__dirname, "..", "..");
const helperPath = path.join(repoRoot, "static", "js", "wdcalculator", "estimate-lifecycle.js");
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

const helper = sandbox.WdCalculatorEstimateMutationBridge;
if (!helper) {
    throw new Error("WdCalculatorEstimateMutationBridge was not defined");
}

const callLog = [];

const setEditingEstimateId = () => {};
const getEstimatesLength = () => 2;
const ensureBaseComponentsUI = () => {};
const resetNotesToEmpty = () => {};
const recalculate = () => {};
const setLoadingState = () => {};
const getEditingEstimateId = () => "editing-id";
const getEstimates = () => [];
const normalizeId = (value) => value;
const isSameId = (left, right) => left === right;
const loadAdditionalOptionRows = () => {};
const loadNotes = () => {};
const calculateEstimate = () => {};
const setCurrentDatabaseEstimateId = () => {};
const setEstimates = () => {};
const generateEstimateId = () => "generated-id";
const formatNumber = () => {};
const renderEstimatesList = () => {};
const reloadImpl = () => {};
const collectCurrentEstimate = () => ({ id: "estimate-1" });
const resetInputFormKeepCustomerName = () => {};
const getLoadingState = () => false;
const loadEstimateToInputForm = () => {};
const setTimeoutImpl = () => 1;
const getCurrentDatabaseEstimateId = () => "db-estimate-id";
const collectNotes = () => "notes";
const getCouponValue = () => 1000;
const resolveAggregateTotals = () => ({ totalBasePrice: 1, totalAdditionalPrice: 2, totalPrice: 3 });
const refreshAfterSave = () => {};
const documentRef = { name: "document-ref" };
const confirmImpl = () => true;
const alertImpl = () => {};
const consoleRef = { log() {}, error() {}, warn() {} };
const fetchImpl = () => Promise.resolve();

helper.configure({
    resetFormModule: {
        configure(options) {
            callLog.push(["reset.configure", options]);
        },
    },
    loadInputModule: {
        configure(options) {
            callLog.push(["load-input.configure", options]);
        },
    },
    loadSavedModule: {
        configure(options) {
            callLog.push(["load-saved.configure", options]);
        },
    },
    addEstimateModule: {
        configure(options) {
            callLog.push(["add.configure", options]);
        },
        initAddEstimateButton() {
            callLog.push(["add.init"]);
        },
    },
    listEventsModule: {
        configure(options) {
            callLog.push(["list.configure", options]);
        },
        initEstimateListEvents() {
            callLog.push(["list.init"]);
        },
    },
    saveEstimateModule: {
        configure(options) {
            callLog.push(["save.configure", options]);
        },
        initSaveEstimateButton() {
            callLog.push(["save.init"]);
        },
    },
    setEditingEstimateId,
    getEstimatesLength,
    ensureBaseComponentsUI,
    resetNotesToEmpty,
    recalculate,
    setLoadingState,
    getEditingEstimateId,
    getEstimates,
    normalizeId,
    isSameId,
    loadAdditionalOptionRows,
    loadNotes,
    calculateEstimate,
    setCurrentDatabaseEstimateId,
    setEstimates,
    generateEstimateId,
    formatNumber,
    renderEstimatesList,
    reloadImpl,
    collectCurrentEstimate,
    resetInputFormKeepCustomerName,
    getLoadingState,
    loadEstimateToInputForm,
    setTimeoutImpl,
    getCurrentDatabaseEstimateId,
    collectNotes,
    getCouponValue,
    resolveAggregateTotals,
    refreshAfterSave,
    documentRef,
    confirmImpl,
    alertImpl,
    consoleRef,
    fetchImpl,
});

helper.initEstimateMutationBridge();

assertEq(callLog.length, 9, "estimate mutation bridge call count");

assertEq(callLog[0][0], "reset.configure", "reset configure order");
assertEq(callLog[0][1].setEditingEstimateId, setEditingEstimateId, "reset configure setEditingEstimateId");
assertEq(callLog[0][1].getEstimatesLength, getEstimatesLength, "reset configure getEstimatesLength");
assertEq(callLog[0][1].ensureBaseComponentsUI, ensureBaseComponentsUI, "reset configure ensureBaseComponentsUI");
assertEq(callLog[0][1].resetNotesToEmpty, resetNotesToEmpty, "reset configure resetNotesToEmpty");
assertEq(callLog[0][1].recalculate, recalculate, "reset configure recalculate");
assertEq(callLog[0][1].documentRef, documentRef, "reset configure documentRef");
assertEq(callLog[0][1].consoleRef, consoleRef, "reset configure consoleRef");

assertEq(callLog[1][0], "load-input.configure", "load input configure order");
assertEq(callLog[1][1].setLoadingState, setLoadingState, "load input configure setLoadingState");
assertEq(callLog[1][1].getEditingEstimateId, getEditingEstimateId, "load input configure getEditingEstimateId");
assertEq(callLog[1][1].getEstimates, getEstimates, "load input configure getEstimates");
assertEq(callLog[1][1].normalizeId, normalizeId, "load input configure normalizeId");
assertEq(callLog[1][1].isSameId, isSameId, "load input configure isSameId");
assertEq(
    callLog[1][1].ensureBaseComponentsUI,
    ensureBaseComponentsUI,
    "load input configure ensureBaseComponentsUI"
);
assertEq(callLog[1][1].resetNotesToEmpty, resetNotesToEmpty, "load input configure resetNotesToEmpty");
assertEq(callLog[1][1].loadAdditionalOptionRows, loadAdditionalOptionRows, "load input configure loadAdditionalOptionRows");
assertEq(callLog[1][1].loadNotes, loadNotes, "load input configure loadNotes");
assertEq(
    callLog[1][1].setEditingEstimateId,
    setEditingEstimateId,
    "load input configure setEditingEstimateId"
);
assertEq(callLog[1][1].calculateEstimate, calculateEstimate, "load input configure calculateEstimate");
assertEq(callLog[1][1].documentRef, documentRef, "load input configure documentRef");
assertEq(callLog[1][1].consoleRef, consoleRef, "load input configure consoleRef");
assertEq(callLog[1][1].confirmImpl, confirmImpl, "load input configure confirmImpl");
assertEq(callLog[1][1].alertImpl, alertImpl, "load input configure alertImpl");

assertEq(callLog[2][0], "load-saved.configure", "load saved configure order");
assertEq(
    callLog[2][1].setCurrentDatabaseEstimateId,
    setCurrentDatabaseEstimateId,
    "load saved configure setCurrentDatabaseEstimateId"
);
assertEq(callLog[2][1].setEstimates, setEstimates, "load saved configure setEstimates");
assertEq(callLog[2][1].generateEstimateId, generateEstimateId, "load saved configure generateEstimateId");
assertEq(callLog[2][1].formatNumber, formatNumber, "load saved configure formatNumber");
assertEq(callLog[2][1].renderEstimatesList, renderEstimatesList, "load saved configure renderEstimatesList");
assertEq(
    callLog[2][1].ensureBaseComponentsUI,
    ensureBaseComponentsUI,
    "load saved configure ensureBaseComponentsUI"
);
assertEq(callLog[2][1].calculateEstimate, calculateEstimate, "load saved configure calculateEstimate");
assertEq(callLog[2][1].resetNotesToEmpty, resetNotesToEmpty, "load saved configure resetNotesToEmpty");
assertEq(callLog[2][1].documentRef, documentRef, "load saved configure documentRef");
assertEq(callLog[2][1].confirmImpl, confirmImpl, "load saved configure confirmImpl");
assertEq(callLog[2][1].reloadImpl, reloadImpl, "load saved configure reloadImpl");

assertEq(callLog[3][0], "add.configure", "add configure order");
assertEq(callLog[3][1].getEditingEstimateId, getEditingEstimateId, "add configure getEditingEstimateId");
assertEq(callLog[3][1].setEditingEstimateId, setEditingEstimateId, "add configure setEditingEstimateId");
assertEq(callLog[3][1].getEstimates, getEstimates, "add configure getEstimates");
assertEq(callLog[3][1].collectCurrentEstimate, collectCurrentEstimate, "add configure collectCurrentEstimate");
assertEq(callLog[3][1].normalizeId, normalizeId, "add configure normalizeId");
assertEq(callLog[3][1].isSameId, isSameId, "add configure isSameId");
assertEq(callLog[3][1].generateEstimateId, generateEstimateId, "add configure generateEstimateId");
assertEq(callLog[3][1].renderEstimatesList, renderEstimatesList, "add configure renderEstimatesList");
assertEq(
    callLog[3][1].resetInputFormKeepCustomerName,
    resetInputFormKeepCustomerName,
    "add configure resetInputFormKeepCustomerName"
);
assertEq(callLog[3][1].documentRef, documentRef, "add configure documentRef");
assertEq(callLog[3][1].alertImpl, alertImpl, "add configure alertImpl");
assertEq(callLog[3][1].consoleRef, consoleRef, "add configure consoleRef");
assertEq(callLog[4][0], "add.init", "add init order");

assertEq(callLog[5][0], "list.configure", "list configure order");
assertEq(callLog[5][1].getLoadingState, getLoadingState, "list configure getLoadingState");
assertEq(callLog[5][1].getEstimates, getEstimates, "list configure getEstimates");
assertEq(callLog[5][1].setEstimates, setEstimates, "list configure setEstimates");
assertEq(callLog[5][1].getEditingEstimateId, getEditingEstimateId, "list configure getEditingEstimateId");
assertEq(callLog[5][1].setEditingEstimateId, setEditingEstimateId, "list configure setEditingEstimateId");
assertEq(
    callLog[5][1].loadEstimateToInputForm,
    loadEstimateToInputForm,
    "list configure loadEstimateToInputForm"
);
assertEq(callLog[5][1].renderEstimatesList, renderEstimatesList, "list configure renderEstimatesList");
assertEq(callLog[5][1].formatNumber, formatNumber, "list configure formatNumber");
assertEq(callLog[5][1].normalizeId, normalizeId, "list configure normalizeId");
assertEq(callLog[5][1].isSameId, isSameId, "list configure isSameId");
assertEq(callLog[5][1].documentRef, documentRef, "list configure documentRef");
assertEq(callLog[5][1].confirmImpl, confirmImpl, "list configure confirmImpl");
assertEq(callLog[5][1].consoleRef, consoleRef, "list configure consoleRef");
assertEq(callLog[5][1].setTimeoutImpl, setTimeoutImpl, "list configure setTimeoutImpl");
assertEq(callLog[6][0], "list.init", "list init order");

assertEq(callLog[7][0], "save.configure", "save configure order");
assertEq(
    callLog[7][1].getCurrentDatabaseEstimateId,
    getCurrentDatabaseEstimateId,
    "save configure getCurrentDatabaseEstimateId"
);
assertEq(callLog[7][1].setCurrentDatabaseEstimateId, setCurrentDatabaseEstimateId, "save configure setCurrentDatabaseEstimateId");
assertEq(callLog[7][1].getEstimates, getEstimates, "save configure getEstimates");
assertEq(callLog[7][1].collectCurrentEstimate, collectCurrentEstimate, "save configure collectCurrentEstimate");
assertEq(callLog[7][1].generateEstimateId, generateEstimateId, "save configure generateEstimateId");
assertEq(callLog[7][1].collectNotes, collectNotes, "save configure collectNotes");
assertEq(callLog[7][1].getCouponValue, getCouponValue, "save configure getCouponValue");
assertEq(
    callLog[7][1].resolveAggregateTotals,
    resolveAggregateTotals,
    "save configure resolveAggregateTotals"
);
assertEq(callLog[7][1].refreshAfterSave, refreshAfterSave, "save configure refreshAfterSave");
assertEq(callLog[7][1].documentRef, documentRef, "save configure documentRef");
assertEq(callLog[7][1].fetchImpl, fetchImpl, "save configure fetchImpl");
assertEq(callLog[7][1].alertImpl, alertImpl, "save configure alertImpl");
assertEq(callLog[7][1].consoleRef, consoleRef, "save configure consoleRef");
assertEq(callLog[8][0], "save.init", "save init order");

process.exit(0);
