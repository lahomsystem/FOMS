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

const helper = sandbox.WdCalculatorNotesUiBootstrap;
if (!helper) {
    throw new Error("WdCalculatorNotesUiBootstrap was not defined");
}

const calls = [];
const expectedResult = "notes-ready";

helper.configure({
    notesUi: {
        initNotesUi() {
            calls.push("notesUi.initNotesUi");
            return expectedResult;
        },
    },
});

const result = helper.initNotesUiBootstrap();

assertEq(calls.length, 1, "notes ui bootstrap call count");
assertEq(calls[0], "notesUi.initNotesUi", "notes ui bootstrap preserves target");
assertEq(result, expectedResult, "notes ui bootstrap preserves return value");

process.exit(0);
