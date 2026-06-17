/**
 * Contract: spec-width-eval.js matches Python eval_spec_width_mm semantics.
 */
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const repoRoot = path.join(__dirname, "..", "..");
const srcPath = path.join(repoRoot, "static", "js", "wdcalculator", "spec-width-eval.js");
const src = fs.readFileSync(srcPath, "utf8");

function assertEq(actual, expected, label) {
    if (actual !== expected) {
        throw new Error(`${label}: expected ${JSON.stringify(expected)}, got ${JSON.stringify(actual)}`);
    }
}

const sandbox = {
    window: {},
    Math,
    Number,
    String,
    parseFloat,
    isNaN: Number.isNaN,
};
sandbox.window = sandbox;
vm.createContext(sandbox);
vm.runInContext(src, sandbox);

const evalFn = sandbox.evalSpecWidthMm;
const resolveFn = sandbox.resolveBaseWidthFromInput;
const formatFn = sandbox.formatBaseWidthDisplay;

const cases = [
    ["4450", 4450],
    ["4120+4121+2354", 10595],
    ["5700,4512,2300", 12512],
    ["2352+2100,2860", 7312],
    ["5700(2402+1864+1638)", 5700],
    ["1000(700,750)", 1000],
    ["3600x600", 3600],
    ["", 0],
    ["상담", 0],
    [null, 0],
];

for (const [input, expected] of cases) {
    assertEq(evalFn(input), expected, `evalSpecWidthMm(${input})`);
}

const resolved = resolveFn("4120+4121+2354");
assertEq(resolved.widthInput, "4120+4121+2354", "resolve widthInput");
assertEq(resolved.widthMm, 10595, "resolve widthMm");

const display = formatFn(
    { widthInput: "4120+4121+2354", widthMm: 10595 },
    (n) => String(n)
);
assertEq(display, "4120+4121+2354 (10595mm)", "formatBaseWidthDisplay composite");

const displaySimple = formatFn({ widthInput: "4470", widthMm: 4470 }, (n) => String(n));
assertEq(displaySimple, "4470mm", "formatBaseWidthDisplay simple");

console.log("wdcalculator_spec_width_eval_contract_node_checks: OK");
