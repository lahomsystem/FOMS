/**
 * Contract freeze: resetInputFormKeepCustomerName helper in
 * static/js/wdcalculator/reset-input-form-keep-customer.js.
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

function assertIncludes(text, expected, label) {
    if (!String(text).includes(expected)) {
        throw new Error(`${label}: expected ${JSON.stringify(text)} to include ${JSON.stringify(expected)}`);
    }
}

class El {
    constructor(tag, opts = {}) {
        this.tagName = String(tag).toUpperCase();
        this.id = opts.id || "";
        this.value = opts.value || "";
        this.innerHTML = opts.innerHTML || "";
        this.textContent = opts.textContent || "";
        this.style = { display: opts.display || "" };
    }
}

function buildSandbox(spec = {}) {
    const ids = {};
    const logs = [];
    const events = [];
    const state = {
        editingEstimateId: spec.initialEditingEstimateId || "editing-123",
        currentDatabaseEstimateId: spec.initialCurrentDatabaseEstimateId || 9876,
        estimatesLength: spec.estimatesLength || 0,
    };

    [
        new El("input", { id: "customerName", value: spec.customerName || "  Alice  " }),
        new El("div", { id: "additionalOptionsContainer", innerHTML: spec.additionalOptionsHtml || "<div>filled</div>" }),
        new El("div", { id: "productInfo", display: "block" }),
        new El("div", { id: "baseEstimateSection", display: "block" }),
        new El("div", { id: "totalBasePrice", textContent: "12,000원" }),
        new El("div", { id: "totalAdditionalPrice", textContent: "3,000원" }),
        new El("div", { id: "totalPrice", textContent: "15,000원" }),
        new El("div", { id: "finalPrice", textContent: "14,000원" }),
        new El("div", { id: "baseEstimateDetail", textContent: "기존 기본" }),
        new El("div", { id: "additionalOptionsDetail", textContent: "기존 옵션" }),
        new El("button", { id: "addEstimateBtn", innerHTML: "<i>old</i>", display: "block" }),
        new El("button", { id: "saveEstimateBtn", display: spec.initialSaveDisplay || "block" }),
    ].forEach((el) => {
        ids[el.id] = el;
    });

    const document = {
        getElementById(id) {
            return ids[id] || null;
        },
    };

    function setEditingEstimateId(next) {
        events.push(["setEditingEstimateId", next]);
        if (spec.setEditingThrows) {
            ids.customerName.value = spec.customerNameDuringOuterCatch || "  Changed In Catch  ";
            throw new Error("editing reset failed");
        }
        state.editingEstimateId = next;
    }

    function getEstimatesLength() {
        return state.estimatesLength;
    }

    function ensureBaseComponentsUI(arg) {
        events.push(["ensureBaseComponentsUI", arg]);
        if (spec.ensureBaseThrows) {
            throw new Error("base reset failed");
        }
    }

    function resetNotesToEmpty() {
        events.push(["resetNotesToEmpty"]);
        if (spec.notesResetThrows) {
            throw new Error("notes reset failed");
        }
    }

    function recalculate() {
        events.push(["recalculate"]);
        if (spec.recalculateThrows) {
            throw new Error("recalculate failed");
        }
    }

    const sandbox = {
        window: {},
        globalThis: null,
        document,
        console: {
            error(...args) {
                logs.push(args.map((arg) => String(arg)).join(" "));
            },
        },
        setEditingEstimateId,
        getEstimatesLength,
        ensureBaseComponentsUI,
        resetNotesToEmpty,
        recalculate,
    };
    sandbox.globalThis = sandbox;

    vm.createContext(sandbox);
    vm.runInContext(
        [
            helperSrc,
            `
            window.WdCalculatorResetInputFormKeepCustomer.configure({
                setEditingEstimateId: setEditingEstimateId,
                getEstimatesLength: getEstimatesLength,
                ensureBaseComponentsUI: ensureBaseComponentsUI,
                resetNotesToEmpty: resetNotesToEmpty,
                recalculate: recalculate,
                documentRef: document,
                consoleRef: console,
            });
            `,
        ].join("\n\n"),
        sandbox,
        { filename: templatePath }
    );

    return {
        ids,
        logs,
        events,
        state,
        run() {
            vm.runInContext(
                "window.WdCalculatorResetInputFormKeepCustomer.resetInputFormKeepCustomerName();",
                sandbox,
                { filename: templatePath }
            );
        },
    };
}

function scenarioHappyPathResetsUiAndKeepsCustomer() {
    const env = buildSandbox({
        customerName: "  Alice  ",
        estimatesLength: 0,
    });

    env.run();

    assertEq(env.events[0][0], "setEditingEstimateId", "happy path clears editing state first");
    assertEq(env.events[0][1], null, "happy path sets editing state to null");
    assertEq(env.state.editingEstimateId, null, "happy path stores cleared editing state");
    assertEq(env.state.currentDatabaseEstimateId, 9876, "happy path keeps currentDatabaseEstimateId untouched");
    assertEq(env.events[1][0], "ensureBaseComponentsUI", "happy path resets base components");
    assertEq(env.events[1][1], null, "happy path resets base components with null");
    assertEq(env.events[2][0], "resetNotesToEmpty", "happy path resets notes");
    assertEq(env.events[3][0], "recalculate", "happy path recalculates at the end");

    assertEq(env.ids.additionalOptionsContainer.innerHTML, "", "happy path clears additional options");
    assertEq(env.ids.productInfo.style.display, "none", "happy path hides product info");
    assertEq(env.ids.baseEstimateSection.style.display, "none", "happy path hides base estimate section");
    assertEq(env.ids.totalBasePrice.textContent, "0원", "happy path resets totalBasePrice");
    assertEq(env.ids.totalAdditionalPrice.textContent, "0원", "happy path resets totalAdditionalPrice");
    assertEq(env.ids.totalPrice.textContent, "0원", "happy path resets totalPrice");
    assertEq(env.ids.finalPrice.textContent, "0원", "happy path resets finalPrice");
    assertEq(env.ids.baseEstimateDetail.textContent, "", "happy path resets base detail");
    assertEq(env.ids.additionalOptionsDetail.textContent, "", "happy path resets options detail");
    assertEq(env.ids.addEstimateBtn.innerHTML, '<i class="fas fa-plus"></i> 견적 추가', "happy path resets add button label");
    assertEq(env.ids.addEstimateBtn.style.display, "none", "happy path hides add button");
    assertEq(env.ids.saveEstimateBtn.style.display, "none", "happy path hides save button when estimates are empty");
    assertEq(env.ids.customerName.value, "Alice", "happy path restores trimmed customer name");
}

function scenarioSaveButtonRemainsWhenDraftsExist() {
    const env = buildSandbox({
        estimatesLength: 2,
        initialSaveDisplay: "block",
    });

    env.run();

    assertEq(
        env.ids.saveEstimateBtn.style.display,
        "block",
        "drafts path keeps save button visible when estimates remain"
    );
}

function scenarioInnerFailuresAreLoggedButFlowContinues() {
    const env = buildSandbox({
        ensureBaseThrows: true,
        notesResetThrows: true,
    });

    env.run();

    assertEq(env.events[0][0], "setEditingEstimateId", "inner-failure path still clears editing state");
    assertEq(env.events[1][0], "ensureBaseComponentsUI", "inner-failure path still attempts base reset");
    assertEq(env.events[2][0], "resetNotesToEmpty", "inner-failure path still attempts notes reset");
    assertEq(env.events[3][0], "recalculate", "inner-failure path still recalculates");
    assertEq(env.ids.additionalOptionsContainer.innerHTML, "", "inner-failure path still clears options");
    assertEq(env.ids.customerName.value, "Alice", "inner-failure path still restores customer name");
    assertIncludes(env.logs.join("\n"), "Error resetting base components:", "inner-failure logs base reset error");
    assertIncludes(env.logs.join("\n"), "Error resetting notes:", "inner-failure logs notes reset error");
}

function scenarioOuterCatchReReadsCustomerName() {
    const env = buildSandbox({
        setEditingThrows: true,
        customerNameDuringOuterCatch: "  Changed In Catch  ",
    });

    env.run();

    assertEq(env.events.length, 1, "outer-catch path stops after editing reset failure");
    assertEq(
        env.ids.customerName.value,
        "Changed In Catch",
        "outer-catch path re-reads and restores the latest trimmed customer name"
    );
    assertEq(
        env.state.currentDatabaseEstimateId,
        9876,
        "outer-catch path keeps currentDatabaseEstimateId untouched"
    );
    assertIncludes(
        env.logs.join("\n"),
        "Critical error in resetInputFormKeepCustomerName:",
        "outer-catch path logs critical error"
    );
}

function main() {
    scenarioHappyPathResetsUiAndKeepsCustomer();
    scenarioSaveButtonRemainsWhenDraftsExist();
    scenarioInnerFailuresAreLoggedButFlowContinues();
    scenarioOuterCatchReReadsCustomerName();
    console.log("wdcalculator reset-input-form-keep-customer contract checks passed");
}

main();
