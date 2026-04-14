/**
 * Contract freeze: local estimate -> input-form restore helper in
 * static/js/wdcalculator/load-estimate-to-input-form.js.
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
    "load-estimate-to-input-form.js"
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
        this.children = [];
        this.parentElement = null;
        this.style = { display: opts.display || "" };
        this.scrollCalls = [];
        this._ids = opts.ids || {};
        if (this.id) {
            this._ids[this.id] = this;
        }
    }

    appendChild(child) {
        child.parentElement = this;
        this.children.push(child);
        if (child.id) {
            this._ids[child.id] = child;
        }
        return child;
    }

    scrollIntoView(options) {
        this.scrollCalls.push(options);
    }
}

function buildSandbox(spec = {}) {
    const ids = {};
    const events = [];
    const alerts = [];
    const confirms = [];
    const errors = [];

    const additionalOptionsContainer = new El("div", {
        id: "additionalOptionsContainer",
        innerHTML: spec.additionalOptionsHtml || "<div>stale</div>",
        ids,
    });
    const addEstimateBtn = new El("button", {
        id: "addEstimateBtn",
        innerHTML: spec.addEstimateHtml || "<i class=\"fas fa-plus\"></i> 견적 추가",
        display: spec.addEstimateDisplay || "none",
        ids,
    });
    const customerName = new El("input", {
        id: "customerName",
        value: spec.customerName || "Alice",
        ids,
    });
    const headerPrimary = new El("div", {
        className: "header-primary",
        ids,
    });
    const baseComponentsContainer = spec.includeBaseComponentsContainer === false
        ? null
        : new El("div", {
            id: "baseComponentsContainer",
            ids,
        });

    const state = {
        loadingTransitions: [],
        editingEstimateId:
            spec.initialEditingEstimateId === undefined ? null : spec.initialEditingEstimateId,
        estimates: clone(spec.estimates || []),
        confirmResult: spec.confirmResult === undefined ? true : spec.confirmResult,
    };

    const document = {
        getElementById(id) {
            return ids[id] || null;
        },
        querySelector(selector) {
            if (selector === ".header-primary") {
                return headerPrimary;
            }
            return null;
        },
    };

    function setLoadingState(next) {
        state.loadingTransitions.push(next);
        events.push(["setLoadingState", next]);
    }

    function getEditingEstimateId() {
        return state.editingEstimateId;
    }

    function getEstimates() {
        return state.estimates;
    }

    function normalizeId(value) {
        events.push(["normalizeId", value]);
        if (spec.normalizeReturns !== undefined) {
            return spec.normalizeReturns;
        }
        if (value === null || value === undefined || value === "") {
            return null;
        }
        return String(value);
    }

    function isSameId(left, right) {
        return String(left) === String(right);
    }

    function ensureBaseComponentsUI(arg) {
        events.push(["ensureBaseComponentsUI", clone(arg)]);
        if (spec.ensureBaseThrows) {
            throw new Error("base-components failed");
        }
    }

    function resetNotesToEmpty() {
        events.push(["resetNotesToEmpty"]);
    }

    function loadAdditionalOptionRows(container, options, opts) {
        events.push(["loadAdditionalOptionRows", container ? container.id : null, clone(options), clone(opts)]);
        if (spec.loadAdditionalThrows) {
            throw new Error("load additional options failed");
        }
    }

    function loadNotes(notes) {
        events.push(["loadNotes", notes]);
    }

    function setEditingEstimateId(next) {
        state.editingEstimateId = next;
        events.push(["setEditingEstimateId", next]);
    }

    function calculateEstimate() {
        events.push(["calculateEstimate"]);
        if (spec.calculateThrows) {
            throw new Error("calculate failed");
        }
    }

    function confirmImpl(message) {
        confirms.push(message);
        return state.confirmResult;
    }

    function alertImpl(message) {
        alerts.push(message);
    }

    const sandbox = {
        window: {},
        globalThis: null,
        document,
        console: {
            error(...args) {
                errors.push(args.map((arg) => String(arg)).join(" "));
            },
        },
        setLoadingState,
        getEditingEstimateId,
        getEstimates,
        normalizeId,
        isSameId,
        ensureBaseComponentsUI,
        resetNotesToEmpty,
        loadAdditionalOptionRows,
        loadNotes,
        setEditingEstimateId,
        calculateEstimate,
        confirmImpl,
        alertImpl,
    };
    sandbox.globalThis = sandbox;

    vm.createContext(sandbox);
    vm.runInContext(
        [
            helperSrc,
            `
            window.WdCalculatorLoadEstimateToInputForm.configure({
                setLoadingState: setLoadingState,
                getEditingEstimateId: getEditingEstimateId,
                getEstimates: getEstimates,
                normalizeId: normalizeId,
                isSameId: isSameId,
                ensureBaseComponentsUI: ensureBaseComponentsUI,
                resetNotesToEmpty: resetNotesToEmpty,
                loadAdditionalOptionRows: loadAdditionalOptionRows,
                loadNotes: loadNotes,
                setEditingEstimateId: setEditingEstimateId,
                calculateEstimate: calculateEstimate,
                documentRef: document,
                consoleRef: console,
                confirmImpl: confirmImpl,
                alertImpl: alertImpl,
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
        confirms,
        errors,
        headerPrimary,
        customerName,
        baseComponentsContainer,
        additionalOptionsContainer,
        addEstimateBtn,
        run(estimateId) {
            sandbox.__estimateId = estimateId;
            vm.runInContext(
                "window.WdCalculatorLoadEstimateToInputForm.loadEstimateToInputForm(__estimateId);",
                sandbox,
                { filename: templatePath }
            );
        },
    };
}

function scenarioHappyPathRestoresBaseComponentsAndUi() {
    const env = buildSandbox({
        estimates: [
            {
                id: "est-1",
                baseComponents: [{ mode: "select", widthMm: 2400, productId: 7 }],
                options: [{ name: "손잡이", price: 12000, quantity: 2 }],
                notes: "현장 메모",
            },
        ],
    });

    env.run("est-1");

    assertDeepEqual(
        env.state.loadingTransitions,
        [true, false],
        "happy path toggles loading state around helper execution"
    );
    assertEq(env.additionalOptionsContainer.innerHTML, "", "happy path clears additional options container");
    assertEq(env.events[1][0], "normalizeId", "happy path normalizes id after loading flag");
    assertEq(env.events[2][0], "resetNotesToEmpty", "happy path resets notes before loading");
    assertDeepEqual(
        env.events[3],
        ["ensureBaseComponentsUI", [{ mode: "select", widthMm: 2400, productId: 7 }]],
        "happy path restores base components directly"
    );
    assertDeepEqual(
        env.events[4],
        [
            "loadAdditionalOptionRows",
            "additionalOptionsContainer",
            [{ name: "손잡이", price: 12000, quantity: 2 }],
            { formatPriceOnInput: true },
        ],
        "happy path restores additional options with formatted input mode"
    );
    assertDeepEqual(env.events[5], ["loadNotes", "현장 메모"], "happy path restores per-estimate notes");
    assertDeepEqual(env.events[6], ["setEditingEstimateId", "est-1"], "happy path keeps original estimate id for edit mode");
    assertEq(env.events[7][0], "calculateEstimate", "happy path recalculates after restore");
    assertEq(env.addEstimateBtn.innerHTML, '<i class="fas fa-save"></i> 견적 수정 적용', "happy path switches add button to edit-apply label");
    assertEq(env.addEstimateBtn.style.display, "block", "happy path shows add button in edit mode");
    assertEq(env.baseComponentsContainer.scrollCalls.length, 1, "happy path scrolls base components container into view first");
    assertEq(env.alerts.length, 0, "happy path does not alert");
    assertEq(env.confirms.length, 0, "happy path does not prompt when not already editing");
}

function scenarioEditingConfirmCancelPreservesCurrentState() {
    const env = buildSandbox({
        initialEditingEstimateId: "est-1",
        confirmResult: false,
        estimates: [
            { id: "est-1", baseComponents: [{ mode: "select", productId: 1 }] },
            { id: "est-2", baseComponents: [{ mode: "select", productId: 2 }] },
        ],
    });

    env.run("est-2");

    assertDeepEqual(
        env.state.loadingTransitions,
        [true, false],
        "confirm-cancel path still unwinds loading state"
    );
    assertEq(env.confirms.length, 1, "confirm-cancel path prompts before replacing current edit");
    assertEq(env.additionalOptionsContainer.innerHTML, "<div>stale</div>", "confirm-cancel path leaves existing form state untouched");
    assertEq(env.events.some((entry) => entry[0] === "normalizeId"), false, "confirm-cancel path exits before id normalization");
    assertEq(env.events.some((entry) => entry[0] === "ensureBaseComponentsUI"), false, "confirm-cancel path does not reload base components");
}

function scenarioInvalidIdAlertsAndLogs() {
    const env = buildSandbox({
        estimates: [{ id: "est-1" }],
        normalizeReturns: null,
    });

    env.run("bad-id");

    assertDeepEqual(env.state.loadingTransitions, [true, false], "invalid-id path unwinds loading state");
    assertEq(env.alerts[0], "잘못된 견적 ID입니다.", "invalid-id path alerts invalid id");
    assertIncludes(env.errors.join("\n"), "Invalid estimate ID", "invalid-id path logs invalid id");
    assertEq(env.events.some((entry) => entry[0] === "ensureBaseComponentsUI"), false, "invalid-id path does not touch form restore helpers");
}

function scenarioMissingEstimateAlertsWithAvailableIds() {
    const env = buildSandbox({
        estimates: [{ id: "est-1" }, { id: "est-2" }],
    });

    env.run("est-404");

    assertDeepEqual(env.state.loadingTransitions, [true, false], "missing-estimate path unwinds loading state");
    assertEq(env.alerts[0], "견적을 찾을 수 없습니다. (ID: est-404)", "missing-estimate path alerts requested id");
    const allErrors = env.errors.join("\n");
    assertIncludes(allErrors, "견적을 찾을 수 없습니다.", "missing-estimate path logs missing estimate");
    assertIncludes(allErrors, "Requested ID:", "missing-estimate path logs requested id");
    assertIncludes(allErrors, "Available IDs:", "missing-estimate path logs available ids");
}

function scenarioLegacyManualFallbackUsesSingleManualRowAndCustomerScroll() {
    const env = buildSandbox({
        includeBaseComponentsContainer: false,
        estimates: [
            {
                id: "est-legacy",
                widthMm: 4470,
                manualPricing: { pricing_type: "30cm", price_30cm: 187000, price_1cm: 6230 },
                options: [{ name: "레거시 옵션", price: 33000, quantity: 1 }],
                notes: "legacy notes",
            },
        ],
    });

    env.run("est-legacy");

    assertDeepEqual(
        env.events[3],
        [
            "ensureBaseComponentsUI",
            [
                {
                    mode: "manual",
                    widthMm: 4470,
                    manualPricing: { pricing_type: "30cm", price_30cm: 187000, price_1cm: 6230 },
                },
            ],
        ],
        "legacy path converts manual pricing estimate to a single manual base-component row"
    );
    assertEq(env.customerName.scrollCalls.length, 1, "legacy path falls back to customerName for scroll target");
    assertDeepEqual(env.events[5], ["loadNotes", "legacy notes"], "legacy path still restores notes");
}

function scenarioCaughtErrorAlertsAndStillClearsLoadingState() {
    const env = buildSandbox({
        estimates: [
            {
                id: "est-error",
                baseComponents: [{ mode: "select", productId: 9 }],
                options: [{ name: "옵션", price: 1000, quantity: 1 }],
            },
        ],
        loadAdditionalThrows: true,
    });

    env.run("est-error");

    assertDeepEqual(env.state.loadingTransitions, [true, false], "error path still clears loading state in finally");
    assertIncludes(
        env.alerts[0],
        "견적을 불러오는 중 오류가 발생했습니다: load additional options failed",
        "error path surfaces caught error through alert"
    );
    assertIncludes(
        env.errors.join("\n"),
        "Error in loadEstimateToInputForm:",
        "error path logs helper failure"
    );
    assertEq(env.events.some((entry) => entry[0] === "setEditingEstimateId"), false, "error path stops before edit id is committed");
}

function main() {
    scenarioHappyPathRestoresBaseComponentsAndUi();
    scenarioEditingConfirmCancelPreservesCurrentState();
    scenarioInvalidIdAlertsAndLogs();
    scenarioMissingEstimateAlertsWithAvailableIds();
    scenarioLegacyManualFallbackUsesSingleManualRowAndCustomerScroll();
    scenarioCaughtErrorAlertsAndStillClearsLoadingState();
    console.log("wdcalculator load-estimate-to-input-form contract checks passed");
}

main();
