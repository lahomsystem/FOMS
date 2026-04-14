/**
 * Freezes WDCalculator coupon helpers (WdCalculatorCouponDisplayHelpers) from
 * static/js/wdcalculator/primary-form.js (W5-B3 merged chunk).
 */
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const repoRoot = path.join(__dirname, "..", "..");
const helperPath = path.join(repoRoot, "static", "js", "wdcalculator", "primary-form.js");
const helperSrc = fs.readFileSync(helperPath, "utf8");

const ids = {};
const warnLogs = [];
const sandbox = {
    console: {
        warn: function () {
            warnLogs.push(Array.from(arguments));
        },
        log: function () {},
        error: function () {},
        info: function () {},
    },
    document: {
        getElementById: function (id) {
            return ids[id] || null;
        },
    },
};
sandbox.window = sandbox;
sandbox.globalThis = sandbox;

vm.createContext(sandbox);
vm.runInContext(helperSrc, sandbox);

const helpers = sandbox.WdCalculatorCouponDisplayHelpers;
if (!helpers || typeof helpers.getCouponValue !== "function") {
    throw new Error("coupon-display helpers did not load");
}
helpers.configure({ defaultCouponValue: 11000 });

function assertEq(actual, expected, label) {
    if (actual !== expected) {
        throw new Error((label || "assert") + ": expected " + JSON.stringify(expected) + ", got " + JSON.stringify(actual));
    }
}

function makeDisplayEl() {
    return {
        style: {},
        className: "",
    };
}

// --- getCouponValue contract ---
delete ids.globalCouponValue;
warnLogs.length = 0;
assertEq(helpers.getCouponValue(), 11000, "missing coupon input falls back to default");
assertEq(warnLogs.length, 1, "missing coupon input warns once");

ids.globalCouponValue = { value: "" };
warnLogs.length = 0;
assertEq(helpers.getCouponValue(), 11000, "empty coupon input falls back to default");
assertEq(warnLogs.length, 0, "empty coupon input does not warn");

ids.globalCouponValue.value = "0";
assertEq(helpers.getCouponValue(), 0, "zero coupon input stays zero");

ids.globalCouponValue.value = "12345";
assertEq(helpers.getCouponValue(), 12345, "numeric coupon input parses");

ids.globalCouponValue.value = "12345abc";
assertEq(helpers.getCouponValue(), 12345, "parseInt-style coupon parsing stays intact");

ids.globalCouponValue.value = "-1";
warnLogs.length = 0;
assertEq(helpers.getCouponValue(), 11000, "negative coupon input falls back to default");
assertEq(warnLogs.length, 1, "negative coupon input warns once");

ids.globalCouponValue.value = "abc";
warnLogs.length = 0;
assertEq(helpers.getCouponValue(), 11000, "non-numeric coupon input falls back to default");
assertEq(warnLogs.length, 1, "non-numeric coupon input warns once");

// --- applyFinalPriceStyle contract ---
const finalPriceEl = makeDisplayEl();
helpers.applyFinalPriceStyle(finalPriceEl);
assertEq(finalPriceEl.style.fontSize, "2.4rem", "final price font size");
assertEq(finalPriceEl.style.fontWeight, "900", "final price font weight");
assertEq(finalPriceEl.style.color, "#0d6efd", "final price color");
assertEq(finalPriceEl.style.lineHeight, "1.1", "final price line height");
assertEq(finalPriceEl.className, "final-price-display mb-2", "final price class");
helpers.applyFinalPriceStyle(null);

// --- applyCouponDiscountStyle contract ---
const discountEl = makeDisplayEl();
helpers.applyCouponDiscountStyle(discountEl, true);
assertEq(discountEl.style.color, "#dc3545", "discount color");
assertEq(discountEl.style.fontWeight, "700", "discount font weight");
assertEq(discountEl.className, "coupon-discount", "discount class");

const noDiscountEl = makeDisplayEl();
helpers.applyCouponDiscountStyle(noDiscountEl, false);
assertEq(noDiscountEl.style.color, "#6c757d", "no-discount color");
assertEq(noDiscountEl.style.fontWeight, "400", "no-discount font weight");
assertEq(noDiscountEl.className, "text-muted", "no-discount class");
helpers.applyCouponDiscountStyle(null, false);

