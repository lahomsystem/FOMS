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

const helper = sandbox.WdCalculatorNotesUiHostBootstrap;
if (!helper) {
    throw new Error("WdCalculatorNotesUiHostBootstrap was not defined");
}

const callLog = [];
const notesUi = { name: "notes-ui" };
const expectedResult = "notes-ui-host-ok";

helper.configure({
    notesUiBootstrap: {
        configure(options) {
            callLog.push(["notesUiBootstrap.configure", options]);
        },
        initNotesUiBootstrap() {
            callLog.push(["notesUiBootstrap.initNotesUiBootstrap"]);
            return expectedResult;
        },
    },
    notesUi,
});

const result = helper.initNotesUiHostBootstrap();

assertEq(callLog.length, 2, "notes ui host bootstrap call count");
assertEq(callLog[0][0], "notesUiBootstrap.configure", "notes ui host configure order");
assertEq(callLog[0][1].notesUi, notesUi, "notes ui host notesUi");
assertEq(
    callLog[1][0],
    "notesUiBootstrap.initNotesUiBootstrap",
    "notes ui host init order"
);
assertEq(result, expectedResult, "notes ui host return value");

process.exit(0);
