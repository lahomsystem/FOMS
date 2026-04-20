/**
 * Contract freeze: saveEstimateBtn clone/replace + save fetch orchestration in
 * static/js/wdcalculator/save-estimate.js.
 */
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const repoRoot = path.join(__dirname, "..", "..");
const helperPath = path.join(
    repoRoot,
    "static",
    "js",
    "wdcalculator",
    "estimate-lifecycle.js"
);
const helperSrc = fs.readFileSync(helperPath, "utf8");
const templatePath = helperPath;

function assertEq(actual, expected, label) {
    if (actual !== expected) {
        throw new Error(`${label}: expected ${JSON.stringify(expected)}, got ${JSON.stringify(actual)}`);
    }
}

function assertDeepEqual(actual, expected, label) {
    const actualJson = JSON.stringify(actual);
    const expectedJson = JSON.stringify(expected);
    if (actualJson !== expectedJson) {
        throw new Error(`${label}: expected ${expectedJson}, got ${actualJson}`);
    }
}

function assertIncludes(text, fragment, label) {
    if (!String(text).includes(fragment)) {
        throw new Error(`${label}: expected ${JSON.stringify(text)} to include ${JSON.stringify(fragment)}`);
    }
}

function clone(value) {
    if (value === undefined) {
        return undefined;
    }
    return JSON.parse(JSON.stringify(value));
}

class El {
    constructor(tag, opts = {}) {
        this.tagName = String(tag).toUpperCase();
        this.id = opts.id || "";
        this.className = opts.className || "";
        this.innerHTML = opts.innerHTML || "";
        this.value = opts.value || "";
        this.checked = !!opts.checked;
        this.disabled = !!opts.disabled;
        this.children = [];
        this.parentNode = null;
        this.listeners = {};
        this._ids = opts.ids || {};
        if (this.id) {
            this._ids[this.id] = this;
        }
    }

    appendChild(child) {
        child.parentNode = this;
        this.children.push(child);
        if (child.id) {
            this._ids[child.id] = child;
        }
        return child;
    }

    addEventListener(type, fn) {
        if (!this.listeners[type]) {
            this.listeners[type] = [];
        }
        this.listeners[type].push(fn);
    }

    cloneNode() {
        return new El(this.tagName, {
            id: this.id,
            className: this.className,
            innerHTML: this.innerHTML,
            value: this.value,
            checked: this.checked,
            disabled: this.disabled,
            ids: this._ids,
        });
    }

    dispatchEvent(event) {
        const evt = event || {};
        evt.type = evt.type || "";
        evt.target = evt.target || this;
        evt.currentTarget = this;
        const handlers = this.listeners[evt.type] || [];
        handlers.forEach((fn) => fn.call(this, evt));
    }
}

function buildSandbox(spec = {}) {
    const ids = {};
    const events = [];
    const alerts = [];
    const warnings = [];
    const errors = [];
    const fetchCalls = [];
    const parent = new El("div", { ids });

    const saveEstimateBtn = new El("button", {
        id: "saveEstimateBtn",
        innerHTML: spec.initialButtonHtml || '<i class="fas fa-save"></i> 저장',
        ids,
    });
    parent.appendChild(saveEstimateBtn);
    parent.replaceChild = function (next, prev) {
        const idx = this.children.indexOf(prev);
        if (idx >= 0) {
            this.children[idx] = next;
            next.parentNode = this;
            prev.parentNode = null;
        }
        if (next.id) {
            ids[next.id] = next;
        }
        events.push(["replaceChild", prev.id, next.id]);
        return prev;
    };

    const customerName = new El("input", {
        id: "customerName",
        value: spec.customerName === undefined ? " WD Save " : spec.customerName,
        ids,
    });
    const shippingCost = new El("input", {
        id: "shippingCost",
        value: spec.shippingCost === undefined ? "3000" : String(spec.shippingCost),
        ids,
    });
    const shippingIncluded = new El("input", {
        id: "shippingIncluded",
        checked: spec.shippingIncluded === undefined ? false : !!spec.shippingIncluded,
        ids,
    });
    const headerPrimary = new El("div", { className: "header-primary", ids });
    const headerTitle = headerPrimary.appendChild(new El("h6", { ids }));

    const state = {
        currentDatabaseEstimateId:
            spec.currentDatabaseEstimateId === undefined ? null : spec.currentDatabaseEstimateId,
        estimates: clone(spec.estimates || []),
    };

    const document = {
        getElementById(id) {
            return ids[id] || null;
        },
        querySelector(selector) {
            if (selector === ".header-primary h6") {
                return headerTitle;
            }
            return null;
        },
    };

    function getCurrentDatabaseEstimateId() {
        return state.currentDatabaseEstimateId;
    }

    function setCurrentDatabaseEstimateId(next) {
        state.currentDatabaseEstimateId = next;
        events.push(["setCurrentDatabaseEstimateId", next]);
    }

    function getEstimates() {
        return state.estimates;
    }

    function collectCurrentEstimate() {
        events.push(["collectCurrentEstimate"]);
        return clone(spec.currentEstimate === undefined ? null : spec.currentEstimate);
    }

    function generateEstimateId() {
        events.push(["generateEstimateId"]);
        return spec.generatedEstimateId || "generated-1";
    }

    function collectNotes() {
        events.push(["collectNotes"]);
        return spec.notes === undefined ? "기본 비고" : spec.notes;
    }

    function getCouponValue() {
        events.push(["getCouponValue"]);
        return spec.couponValue === undefined ? 11000 : spec.couponValue;
    }

    function resolveAggregateTotals(estimatesToSave, couponValue, shippingCostValue, shippingIncludedValue) {
        events.push([
            "resolveAggregateTotals",
            clone(estimatesToSave),
            couponValue,
            shippingCostValue,
            shippingIncludedValue,
        ]);
        if (spec.aggregateError) {
            throw spec.aggregateError;
        }
        return clone(
            spec.aggregateResult || {
                totalBasePrice: 100000,
                totalAdditionalPrice: 5000,
                totalPrice: 105000,
            }
        );
    }

    function refreshAfterSave(savedId) {
        events.push(["refreshAfterSave", savedId]);
    }

    function fetchImpl(url, options) {
        fetchCalls.push({
            url,
            options: {
                method: options.method,
                headers: clone(options.headers),
                body: options.body,
            },
        });
        if (spec.fetchReject) {
            return Promise.reject(spec.fetchReject);
        }
        const responseData =
            spec.fetchResponse === undefined
                ? { success: true, message: "saved", estimate_id: 77 }
                : spec.fetchResponse;
        return Promise.resolve({
            json() {
                return Promise.resolve(clone(responseData));
            },
        });
    }

    function alertImpl(message) {
        alerts.push(message);
    }

    const consoleRef = {
        warn(...args) {
            warnings.push(args.join(" "));
        },
        error(...args) {
            errors.push(args.join(" "));
        },
    };

    const sandbox = {
        window: {},
        globalThis: null,
        document,
        getCurrentDatabaseEstimateId,
        setCurrentDatabaseEstimateId,
        getEstimates,
        collectCurrentEstimate,
        generateEstimateId,
        collectNotes,
        getCouponValue,
        resolveAggregateTotals,
        refreshAfterSave,
        fetchImpl,
        alertImpl,
        consoleRef,
    };
    sandbox.globalThis = sandbox;

    vm.createContext(sandbox);
    vm.runInContext(
        [
            helperSrc,
            `
            window.WdCalculatorSaveEstimate.configure({
                getCurrentDatabaseEstimateId: getCurrentDatabaseEstimateId,
                setCurrentDatabaseEstimateId: setCurrentDatabaseEstimateId,
                getEstimates: getEstimates,
                collectCurrentEstimate: collectCurrentEstimate,
                generateEstimateId: generateEstimateId,
                collectNotes: collectNotes,
                getCouponValue: getCouponValue,
                resolveAggregateTotals: resolveAggregateTotals,
                refreshAfterSave: refreshAfterSave,
                documentRef: document,
                fetchImpl: fetchImpl,
                alertImpl: alertImpl,
                consoleRef: consoleRef
            });
            `,
        ].join("\n\n"),
        sandbox,
        { filename: templatePath }
    );

    return {
        ids,
        state,
        events,
        alerts,
        warnings,
        errors,
        fetchCalls,
        headerTitle,
        init() {
            return vm.runInContext("window.WdCalculatorSaveEstimate.initSaveEstimateButton();", sandbox, {
                filename: templatePath,
            });
        },
        async handle(buttonExpr) {
            sandbox.__buttonExpr = buttonExpr;
            return vm.runInContext(
                "window.WdCalculatorSaveEstimate.handleSaveEstimate(__buttonExpr);",
                sandbox,
                { filename: templatePath }
            );
        },
        async clickCurrentButton() {
            const btn = ids.saveEstimateBtn;
            btn.dispatchEvent({ type: "click", target: btn });
            await Promise.resolve();
            await Promise.resolve();
        },
    };
}

function scenarioInitClonesAndRebindsSaveButton() {
    const env = buildSandbox();

    env.init();

    assertDeepEqual(env.events[0], ["replaceChild", "saveEstimateBtn", "saveEstimateBtn"], "init clones and replaces save button before binding");
    assertEq(env.ids.saveEstimateBtn.listeners.click.length, 1, "init binds a single click listener on the cloned button");
}

async function scenarioMissingCustomerAlertsBeforeSave() {
    const env = buildSandbox({ customerName: "   " });
    const button = env.init();

    await env.handle(button);

    assertEq(env.alerts[0], "고객명을 입력해주세요.", "missing-customer path alerts immediately");
    assertEq(env.fetchCalls.length, 0, "missing-customer path does not call fetch");
}

async function scenarioEmptyEstimatesUsesCurrentEstimateFallback() {
    const env = buildSandbox({
        estimates: [],
        currentDatabaseEstimateId: 55,
        currentEstimate: {
            productName: "Wardrobe",
            totalPrice: 120000,
        },
        generatedEstimateId: "generated-save-1",
        notes: "세이브 비고",
        couponValue: 5000,
        shippingCost: 7000,
        shippingIncluded: false,
        aggregateResult: {
            totalBasePrice: 100000,
            totalAdditionalPrice: 20000,
            totalPrice: 120000,
        },
        fetchResponse: {
            success: true,
            message: "저장 완료",
            estimate_id: 901,
        },
    });
    const button = env.init();

    await env.handle(button);

    assertDeepEqual(
        env.events.slice(1, 5),
        [
            ["collectCurrentEstimate"],
            ["generateEstimateId"],
            ["collectNotes"],
            ["getCouponValue"],
        ],
        "empty-estimates path collects current estimate and save inputs before aggregate totals"
    );
    assertEq(env.events[5][0], "resolveAggregateTotals", "empty-estimates path computes aggregate totals");
    assertEq(env.events[5][2], 5000, "empty-estimates path passes coupon value into aggregate totals");
    assertEq(env.events[5][3], 7000, "empty-estimates path passes shipping cost into aggregate totals");
    assertEq(env.events[5][4], false, "empty-estimates path passes shippingIncluded into aggregate totals");
    assertDeepEqual(
        env.events[5][1][0],
        { productName: "Wardrobe", totalPrice: 120000, id: "generated-save-1" },
        "empty-estimates path injects generated id into synthesized estimate before aggregate totals"
    );
    const fetchPayload = JSON.parse(env.fetchCalls[0].options.body);
    assertEq(fetchPayload.estimate_id, 55, "save payload uses currentDatabaseEstimateId");
    assertEq(fetchPayload.customer_name, "WD Save", "save payload trims customer name");
    assertEq(fetchPayload.estimate_data.totalBasePrice, 100000, "save payload keeps totalBasePrice");
    assertEq(fetchPayload.estimate_data.totalAdditionalPrice, 20000, "save payload keeps totalAdditionalPrice");
    assertEq(fetchPayload.estimate_data.totalPrice, 120000, "save payload keeps totalPrice");
    assertEq(fetchPayload.estimate_data.coupon_discount, 5000, "save payload keeps coupon_discount");
    assertEq(fetchPayload.estimate_data.shipping_cost, 7000, "save payload keeps shipping_cost");
    assertEq(fetchPayload.estimate_data.shipping_included, false, "save payload keeps shipping_included");
    assertEq(fetchPayload.estimate_data.notes, "세이브 비고", "save payload keeps notes");
    assertDeepEqual(
        fetchPayload.estimate_data.estimates[0],
        { productName: "Wardrobe", totalPrice: 120000, id: "generated-save-1" },
        "save payload keeps synthesized estimate data"
    );
    assertEq(button.disabled, false, "successful save restores disabled state");
    assertEq(button.innerHTML, '<i class="fas fa-save"></i> 저장', "successful save restores original button text");
    assertEq(env.alerts[0], "저장 완료", "successful save surfaces backend success message");
    assertDeepEqual(env.events[6], ["refreshAfterSave", 901], "successful save triggers refresh (full reset runs inside refresh)");
    assertEq(
        env.events.some((entry) => entry[0] === "setCurrentDatabaseEstimateId"),
        false,
        "successful save does not set DB estimate id client-side; refresh clears edit state"
    );
}

async function scenarioAggregateErrorAlertsWithoutFetch() {
    const env = buildSandbox({
        estimates: [{ id: "draft-1", totalPrice: 1000 }],
        aggregateError: new Error("aggregate failed"),
    });
    const button = env.init();

    await env.handle(button);

    assertEq(env.fetchCalls.length, 0, "aggregate-error path does not call fetch");
    assertEq(env.alerts[0], "aggregate failed", "aggregate-error path alerts helper error message");
    assertIncludes(env.errors.join("\n"), "Error: aggregate failed", "aggregate-error path logs thrown error");
}

async function scenarioFailedResponseRestoresButtonAndSkipsRefresh() {
    const env = buildSandbox({
        estimates: [{ id: "draft-1", totalPrice: 1000 }],
        fetchResponse: {
            success: false,
            message: "저장 실패",
        },
    });
    const button = env.init();

    await env.handle(button);

    assertEq(button.disabled, false, "failed-response path restores button disabled state");
    assertEq(button.innerHTML, '<i class="fas fa-save"></i> 저장', "failed-response path restores button text");
    assertEq(env.alerts[0], "저장 실패", "failed-response path alerts backend message");
    assertEq(env.events.some((entry) => entry[0] === "refreshAfterSave"), false, "failed-response path does not refresh saved list");
}

async function scenarioFetchErrorRestoresButtonAndShowsGenericAlert() {
    const env = buildSandbox({
        estimates: [{ id: "draft-1", totalPrice: 1000 }],
        fetchReject: new Error("network down"),
    });
    const button = env.init();

    await env.handle(button);

    assertEq(button.disabled, false, "fetch-error path restores button disabled state");
    assertEq(button.innerHTML, '<i class="fas fa-save"></i> 저장', "fetch-error path restores button text");
    assertEq(env.alerts[0], "견적 저장 중 오류가 발생했습니다.", "fetch-error path shows generic alert");
    assertIncludes(env.errors.join("\n"), "Error: Error: network down", "fetch-error path logs request failure");
}

async function main() {
    scenarioInitClonesAndRebindsSaveButton();
    await scenarioMissingCustomerAlertsBeforeSave();
    await scenarioEmptyEstimatesUsesCurrentEstimateFallback();
    await scenarioAggregateErrorAlertsWithoutFetch();
    await scenarioFailedResponseRestoresButtonAndSkipsRefresh();
    await scenarioFetchErrorRestoresButtonAndShowsGenericAlert();
    console.log("wdcalculator save-estimate contract checks passed");
}

main().catch((error) => {
    console.error(error);
    process.exit(1);
});
