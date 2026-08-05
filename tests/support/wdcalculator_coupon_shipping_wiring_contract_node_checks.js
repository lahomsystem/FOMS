/**
 * Freezes WDCalculator coupon/shipping listener wiring from
 * static/js/wdcalculator/pricing-core.js.
 */
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const repoRoot = path.join(__dirname, "..", "..");
const helperPath = path.join(repoRoot, "static", "js", "wdcalculator", "pricing-core.js");
const helperSrc = fs.readFileSync(helperPath, "utf8");

function assertEq(actual, expected, label) {
    if (actual !== expected) {
        throw new Error(`${label}: expected ${JSON.stringify(expected)}, got ${JSON.stringify(actual)}`);
    }
}

function assertIncludes(text, fragment, label) {
    if (!String(text).includes(fragment)) {
        throw new Error(`${label}: expected ${JSON.stringify(text)} to include ${JSON.stringify(fragment)}`);
    }
}

class El {
    constructor(id, opts = {}) {
        this.id = id;
        this._value = "";
        this.value = opts.value || "";
        this.checked = Boolean(opts.checked);
        this.listeners = {};
    }

    get value() {
        return this._value;
    }

    set value(next) {
        this._value = next == null ? "" : String(next);
    }

    addEventListener(type, handler) {
        if (!this.listeners[type]) {
            this.listeners[type] = [];
        }
        this.listeners[type].push(handler);
    }

    dispatchEvent(event) {
        const payload = Object.assign({}, event || {}, { target: this });
        (this.listeners[payload.type] || []).forEach((handler) => {
            handler.call(this, payload);
        });
    }
}

function buildSandbox(spec = {}) {
    const ids = {
        shippingCost: new El("shippingCost", { value: spec.shippingCost || "" }),
        shippingIncluded: new El("shippingIncluded", { checked: spec.shippingIncluded !== false }),
    };
    if (spec.includeCoupon !== false) {
        ids.globalCouponValue = new El("globalCouponValue", {
            value: spec.couponValue == null ? "" : spec.couponValue,
        });
    }

    const callLog = {
        calculateEstimate: 0,
        calculateTotalEstimates: 0,
        getCouponValue: 0,
        timeouts: [],
        errors: [],
        logs: [],
    };

    const sandbox = {
        window: null,
        globalThis: null,
        document: {
            getElementById(id) {
                return ids[id] || null;
            },
        },
        DEFAULT_COUPON_VALUE: 11000,
        estimates: Array.isArray(spec.estimates) ? spec.estimates.slice() : [],
        calculateEstimate() {
            callLog.calculateEstimate += 1;
        },
        calculateTotalEstimates() {
            callLog.calculateTotalEstimates += 1;
        },
        getCouponValue() {
            callLog.getCouponValue += 1;
            const couponEl = ids.globalCouponValue;
            if (!couponEl) {
                return sandbox.DEFAULT_COUPON_VALUE;
            }
            const parsed = parseInt(couponEl.value, 10);
            return Number.isFinite(parsed) ? parsed : sandbox.DEFAULT_COUPON_VALUE;
        },
        setTimeout(fn, delay) {
            callLog.timeouts.push(delay);
            fn();
            return callLog.timeouts.length;
        },
        clearTimeout() {},
        console: {
            log() {
                callLog.logs.push(Array.from(arguments));
            },
            warn() {},
            error() {
                callLog.errors.push(Array.from(arguments));
            },
        },
        parseInt,
        parseFloat,
        Number,
        String,
        Array,
        Math,
        JSON,
    };
    sandbox.window = sandbox;
    sandbox.globalThis = sandbox;

    vm.createContext(sandbox);
    vm.runInContext(helperSrc, sandbox, { filename: helperPath });
    vm.runInContext(
        [
            "WdCalculatorCouponShippingWiring.configure({",
            "  defaultCouponValue: DEFAULT_COUPON_VALUE,",
            "  getEstimates: function () { return estimates; },",
            "  calculateEstimate: calculateEstimate,",
            "  calculateTotalEstimates: calculateTotalEstimates,",
            "  getCouponValue: getCouponValue",
            "});",
            "WdCalculatorCouponShippingWiring.initCouponShippingWiring();",
        ].join("\n"),
        sandbox,
        { filename: helperPath }
    );

    return {
        ids,
        callLog,
        resetCalls() {
            callLog.calculateEstimate = 0;
            callLog.calculateTotalEstimates = 0;
            callLog.getCouponValue = 0;
            callLog.timeouts = [];
            callLog.errors = [];
            callLog.logs = [];
        },
    };
}

function scenarioEmptyCouponStaysEmptyAndRunsInitialRecalc() {
    const env = buildSandbox({
        couponValue: "",
        estimates: [{ id: 1 }],
    });

    assertEq(env.ids.globalCouponValue.value, "", "empty coupon input stays empty (no default injection; empty = 0 discount)");
    assertEq(env.callLog.calculateEstimate, 1, "initial coupon wiring triggers calculateEstimate once");
    assertEq(env.callLog.calculateTotalEstimates, 1, "initial coupon wiring triggers aggregate recalc once when estimates exist");
    assertEq(env.callLog.timeouts.length, 1, "initial coupon wiring schedules one timeout");
    assertEq(env.callLog.timeouts[0], 500, "initial coupon wiring keeps 500ms timeout");
}

function scenarioZeroCouponStaysZeroAndSkipsInitialAggregateWithoutEstimates() {
    const env = buildSandbox({
        couponValue: "0",
        estimates: [],
    });

    assertEq(env.ids.globalCouponValue.value, "0", "zero coupon input stays zero (user-entered 0 is respected)");
    assertEq(env.callLog.calculateEstimate, 1, "initial coupon wiring still triggers calculateEstimate once");
    assertEq(env.callLog.calculateTotalEstimates, 0, "initial coupon wiring skips aggregate recalc when estimates are empty");
    assertEq(env.callLog.timeouts.length, 1, "zero coupon path still schedules one timeout");
    assertEq(env.callLog.timeouts[0], 500, "zero coupon path keeps 500ms timeout");
}

function scenarioShippingListenersRecalcOnlyWhenEstimatesExist() {
    const env = buildSandbox({
        couponValue: "12000",
        estimates: [{ id: 1 }],
    });
    env.resetCalls();

    env.ids.shippingCost.dispatchEvent({ type: "input" });
    env.ids.shippingCost.dispatchEvent({ type: "change" });
    env.ids.shippingIncluded.dispatchEvent({ type: "change" });

    assertEq(env.callLog.calculateEstimate, 0, "shipping listeners do not trigger item estimate recalc");
    assertEq(env.callLog.calculateTotalEstimates, 3, "shipping listeners trigger aggregate recalc on each event");
}

function scenarioShippingListenersSkipAggregateWithoutEstimates() {
    const env = buildSandbox({
        couponValue: "12000",
        estimates: [],
    });
    env.resetCalls();

    env.ids.shippingCost.dispatchEvent({ type: "input" });
    env.ids.shippingCost.dispatchEvent({ type: "change" });
    env.ids.shippingIncluded.dispatchEvent({ type: "change" });

    assertEq(env.callLog.calculateEstimate, 0, "shipping listeners still do not trigger item estimate recalc");
    assertEq(env.callLog.calculateTotalEstimates, 0, "shipping listeners skip aggregate recalc when estimates are empty");
}

function scenarioCouponEventsTriggerExpectedRecalcPaths() {
    const env = buildSandbox({
        couponValue: "13000",
        estimates: [{ id: 1 }],
    });
    env.resetCalls();

    env.ids.globalCouponValue.value = "15000";
    env.ids.globalCouponValue.dispatchEvent({ type: "input" });
    env.ids.globalCouponValue.dispatchEvent({ type: "change" });
    env.ids.globalCouponValue.dispatchEvent({ type: "blur" });

    assertEq(env.callLog.calculateEstimate, 3, "coupon events trigger calculateEstimate on input/change/blur");
    assertEq(env.callLog.calculateTotalEstimates, 3, "coupon events trigger aggregate recalc when estimates exist");
    assertEq(env.callLog.getCouponValue, 3, "coupon events read coupon value on each recalculation path");
    assertEq(env.callLog.timeouts.length, 1, "coupon input event keeps delayed recalculation");
    assertEq(env.callLog.timeouts[0], 100, "coupon input event keeps 100ms timeout");
}

function scenarioMissingCouponInputLogsError() {
    const env = buildSandbox({
        includeCoupon: false,
        estimates: [],
    });

    assertEq(env.callLog.errors.length, 1, "missing coupon input logs one error");
    assertIncludes(env.callLog.errors[0][0], "쿠폰 입력 필드를 찾을 수 없습니다", "missing coupon input preserves legacy error message");
}

scenarioEmptyCouponStaysEmptyAndRunsInitialRecalc();
scenarioZeroCouponStaysZeroAndSkipsInitialAggregateWithoutEstimates();
scenarioShippingListenersRecalcOnlyWhenEstimatesExist();
scenarioShippingListenersSkipAggregateWithoutEstimates();
scenarioCouponEventsTriggerExpectedRecalcPaths();
scenarioMissingCouponInputLogsError();

process.stdout.write("wdcalculator_coupon_shipping_wiring_contract_node_checks: ok\n");
