const fs = require("fs");
const path = require("path");
const vm = require("vm");

const repoRoot = path.join(__dirname, "..", "..");
const helperPath = path.join(repoRoot, "static", "js", "wdcalculator", "products-state.js");
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
    Array,
    Object,
};
sandbox.window = sandbox;
sandbox.globalThis = sandbox;

vm.createContext(sandbox);
vm.runInContext(helperSrc, sandbox);

const helper = sandbox.WdCalculatorProductsState;
if (!helper) {
    throw new Error("WdCalculatorProductsState was not defined");
}

assertEq(Array.isArray(helper.getProducts()), true, "default products array");
assertEq(helper.getProducts().length, 0, "default products length");
const initialProducts = [{ id: 1, name: "A" }];
helper.configure({ initialProducts });
assertEq(helper.getProducts(), initialProducts, "configure keeps initial products reference");
const nextProducts = [{ id: 2, name: "B" }];
assertEq(helper.setProducts(nextProducts), nextProducts, "setProducts returns array");
assertEq(helper.getProducts(), nextProducts, "get after setProducts");
helper.setProducts(null);
assertEq(Array.isArray(helper.getProducts()), true, "non-array set coerces empty array");
assertEq(helper.getProducts().length, 0, "non-array set empties products");

process.exit(0);
