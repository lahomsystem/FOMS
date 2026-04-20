/**
 * Loads pricing-core.js in a VM and asserts the aggregate totals contract surface.
 * Invoked by pytest via `node`.
 */
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const repoRoot = path.join(__dirname, "..", "..");
const helperPath = path.join(repoRoot, "static", "js", "wdcalculator", "pricing-core.js");
const code = fs.readFileSync(helperPath, "utf8");

const sandbox = {
    window: null,
    globalThis: null,
    document: {},
    console,
};
sandbox.window = sandbox;
sandbox.globalThis = sandbox;
vm.createContext(sandbox);
vm.runInContext(code, sandbox);

const wdc = sandbox.wdcComputeAggregateTotals;
if (typeof wdc !== "function") {
    throw new Error("wdcComputeAggregateTotals not defined on sandbox");
}

function assertEq(actual, expected, label) {
    if (actual !== expected) {
        throw new Error((label || "assert") + ": expected " + expected + ", got " + actual);
    }
}

function assertOk(cond, label) {
    if (!cond) {
        throw new Error(label || "assertion failed");
    }
}

// Normal aggregate: two rows, no coupon/shipping
let r = wdc(
    [
        { basePrice: 100, additionalPrice: 50 },
        { basePrice: 200, additionalPrice: 0 },
    ],
    0,
    0,
    true
);
assertEq(r.totalBasePrice, 300, "totalBasePrice");
assertEq(r.totalAdditionalPrice, 50, "totalAdditionalPrice");
assertEq(r.totalPrice, 350, "totalPrice");
assertEq(r.totalEstimate, 350, "totalEstimate");
assertEq(r.finalPrice, 350, "finalPrice");

// Coupon larger than subtotal -> clamp post-coupon to 0
r = wdc([{ basePrice: 100, additionalPrice: 0 }], 500, 0, true);
assertEq(r.totalEstimate, 0, "clamped totalEstimate");
assertEq(r.finalPrice, 0, "final after clamp");

// Shipping excluded: final equals post-coupon total (shipping ignored for final)
r = wdc([{ basePrice: 100, additionalPrice: 0 }], 0, 50, false);
assertEq(r.totalEstimate, 100, "post-coupon with no coupon");
assertEq(r.finalPrice, 100, "final shipping excluded");

// Missing base/additional fields do not yield NaN
r = wdc([{}, { basePrice: 10 }], 0, 0, true);
assertOk(!Number.isNaN(r.totalBasePrice), "totalBasePrice NaN");
assertOk(!Number.isNaN(r.totalAdditionalPrice), "totalAdditionalPrice NaN");
assertOk(!Number.isNaN(r.totalPrice), "totalPrice NaN");
assertEq(r.totalBasePrice, 10, "sum base with missing fields");
assertEq(r.totalAdditionalPrice, 0, "sum additional with missing fields");

process.exit(0);
