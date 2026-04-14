/**
 * Contract freeze: addEstimateBtn local add/update orchestration +
 * follow-up save-button listener in static/js/wdcalculator/add-estimate.js.
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
    "add-estimate.js"
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
        this.innerHTML = opts.innerHTML || "";
        this.value = opts.value || "";
        this.style = { display: opts.display || "" };
        this.listeners = {};
        this.onclick = opts.onclick || null;
        this._ids = opts.ids || {};
        if (this.id) {
            this._ids[this.id] = this;
        }
    }

    addEventListener(type, fn) {
        if (!this.listeners[type]) {
            this.listeners[type] = [];
        }
        this.listeners[type].push(fn);
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
    const logs = [];
    const errors = [];

    const addEstimateBtn = new El("button", {
        id: "addEstimateBtn",
        innerHTML: spec.initialAddHtml || '<i class="fas fa-edit"></i> 수정',
        ids,
        onclick: spec.originalOnclick || null,
    });
    const saveEstimateBtn = new El("button", {
        id: "saveEstimateBtn",
        display: spec.initialSaveDisplay || "none",
        ids,
    });

    const document = {
        getElementById(id) {
            return ids[id] || null;
        },
    };

    const state = {
        editingEstimateId:
            spec.initialEditingEstimateId === undefined ? null : spec.initialEditingEstimateId,
        estimates: clone(spec.estimates || []),
    };

    function getEditingEstimateId() {
        return state.editingEstimateId;
    }

    function setEditingEstimateId(next) {
        state.editingEstimateId = next;
        events.push(["setEditingEstimateId", next]);
    }

    function getEstimates() {
        return state.estimates;
    }

    function collectCurrentEstimate() {
        events.push(["collectCurrentEstimate"]);
        return clone(spec.currentEstimate === undefined ? null : spec.currentEstimate);
    }

    function normalizeId(value) {
        events.push(["normalizeId", value]);
        if (spec.normalizeIdResult !== undefined) {
            return spec.normalizeIdResult;
        }
        if (value === null || value === undefined || value === "") {
            return null;
        }
        return String(value);
    }

    function isSameId(left, right) {
        events.push(["isSameId", left, right]);
        return String(left) === String(right);
    }

    function generateEstimateId() {
        events.push(["generateEstimateId"]);
        return spec.generatedEstimateId || "generated-estimate-1";
    }

    function renderEstimatesList() {
        events.push(["renderEstimatesList"]);
    }

    function resetInputFormKeepCustomerName() {
        events.push(["resetInputFormKeepCustomerName"]);
    }

    function alertImpl(message) {
        alerts.push(message);
    }

    const consoleRef = {
        log(...args) {
            logs.push(args.join(" "));
        },
        error(...args) {
            errors.push(args.join(" "));
        },
    };

    const sandbox = {
        window: {},
        globalThis: null,
        document,
        getEditingEstimateId,
        setEditingEstimateId,
        getEstimates,
        collectCurrentEstimate,
        normalizeId,
        isSameId,
        generateEstimateId,
        renderEstimatesList,
        resetInputFormKeepCustomerName,
        alertImpl,
        consoleRef,
    };
    sandbox.globalThis = sandbox;

    vm.createContext(sandbox);
    vm.runInContext(
        [
            helperSrc,
            `
            window.WdCalculatorAddEstimate.configure({
                getEditingEstimateId: getEditingEstimateId,
                setEditingEstimateId: setEditingEstimateId,
                getEstimates: getEstimates,
                collectCurrentEstimate: collectCurrentEstimate,
                normalizeId: normalizeId,
                isSameId: isSameId,
                generateEstimateId: generateEstimateId,
                renderEstimatesList: renderEstimatesList,
                resetInputFormKeepCustomerName: resetInputFormKeepCustomerName,
                documentRef: document,
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
        logs,
        errors,
        init() {
            return vm.runInContext("window.WdCalculatorAddEstimate.initAddEstimateButton();", sandbox, {
                filename: templatePath,
            });
        },
        handle(buttonExpr) {
            sandbox.__buttonExpr = buttonExpr;
            return vm.runInContext("window.WdCalculatorAddEstimate.handleAddEstimate(__buttonExpr);", sandbox, {
                filename: templatePath,
            });
        },
        clickCurrentButton() {
            const btn = ids.addEstimateBtn;
            btn.dispatchEvent({ type: "click", target: btn });
        },
    };
}

function scenarioInitBindsPrimaryAndFollowUpListeners() {
    const env = buildSandbox();

    env.init();

    assertEq(env.ids.addEstimateBtn.listeners.click.length, 2, "init binds primary and follow-up click listeners");
}

function scenarioAddModeGeneratesIdRendersAndShowsSaveButton() {
    const env = buildSandbox({
        estimates: [],
        currentEstimate: {
            productName: "Wardrobe",
            displayName: "Wardrobe 1200",
            baseComponents: [{ productId: 7, mode: "select", widthMm: 1200 }],
            totalPrice: 150000,
        },
        generatedEstimateId: "new-est-1",
        initialSaveDisplay: "none",
    });

    env.init();
    env.clickCurrentButton();

    assertDeepEqual(
        env.state.estimates[0],
        {
            productName: "Wardrobe",
            displayName: "Wardrobe 1200",
            baseComponents: [{ productId: 7, mode: "select", widthMm: 1200 }],
            totalPrice: 150000,
            id: "new-est-1",
        },
        "add-mode path appends generated id onto collected estimate"
    );
    assertEq(env.events[0][0], "collectCurrentEstimate", "add-mode path collects current estimate first");
    assertEq(env.events[2][0], "generateEstimateId", "add-mode path generates a new estimate id");
    assertEq(env.events[3][0], "renderEstimatesList", "add-mode path renders updated estimate list");
    assertEq(env.events[4][0], "resetInputFormKeepCustomerName", "add-mode path resets input form after render");
    assertEq(env.ids.saveEstimateBtn.style.display, "block", "follow-up listener keeps save button visible after add");
}

function scenarioUpdateModePreservesDisplayNameWhenProductIdentityMatches() {
    const env = buildSandbox({
        estimates: [
            {
                id: "draft-1",
                productName: "Old Name",
                displayName: "사용자 편집 이름",
                baseComponents: [{ productId: 11, mode: "select", widthMm: 1000 }],
                totalPrice: 1000,
            },
        ],
        initialEditingEstimateId: "draft-1",
        currentEstimate: {
            productName: "Latest Product",
            displayName: "자동 이름 1000",
            baseComponents: [{ productId: 11, mode: "select", widthMm: 1000 }],
            totalPrice: 1200,
        },
    });
    const button = env.init();

    env.handle(button);

    assertEq(env.state.estimates[0].id, "draft-1", "update-mode path keeps original estimate id");
    assertEq(env.state.estimates[0].displayName, "사용자 편집 이름", "update-mode path preserves edited displayName when identity matches");
    assertEq(env.state.estimates[0].productName, "Latest Product", "update-mode path still refreshes latest productName");
    assertEq(env.events[3][0], "setEditingEstimateId", "update-mode path clears editing state after successful update");
    assertEq(env.events[4][0], "renderEstimatesList", "update-mode path re-renders after mutation");
    assertEq(env.events[5][0], "resetInputFormKeepCustomerName", "update-mode path resets input form after render");
    assertEq(env.ids.addEstimateBtn.innerHTML, '<i class="fas fa-plus"></i> 견적 추가', "update-mode path restores add button label");
}

function scenarioWidthChangeRefreshesDisplayNameAndLogsReason() {
    const env = buildSandbox({
        estimates: [
            {
                id: "draft-2",
                productName: "Old Name",
                displayName: "기존 1000",
                baseComponents: [{ productId: 11, mode: "select", widthMm: 1000 }],
                totalPrice: 1000,
            },
        ],
        initialEditingEstimateId: "draft-2",
        currentEstimate: {
            productName: "Latest Product",
            displayName: "자동 1100",
            baseComponents: [{ productId: 11, mode: "select", widthMm: 1100 }],
            totalPrice: 1300,
        },
    });
    const button = env.init();

    env.handle(button);

    assertEq(env.state.estimates[0].displayName, "자동 1100", "width-change path refreshes displayName");
    assertEq(env.state.estimates[0].productName, "Latest Product", "width-change path refreshes productName");
    assertIncludes(env.logs.join("\n"), "제품 또는 가로 길이 변경 감지 - 최신 제품 이름으로 업데이트", "width-change path logs refresh reason");
}

function scenarioMissingEditingTargetAlertsAndStopsBeforeReset() {
    const env = buildSandbox({
        estimates: [{ id: "other-id", displayName: "다른 견적" }],
        initialEditingEstimateId: "missing-id",
        currentEstimate: {
            productName: "Latest Product",
            displayName: "자동 이름",
            baseComponents: [{ productId: 11, mode: "select", widthMm: 1000 }],
        },
    });
    const button = env.init();

    env.handle(button);

    assertEq(env.alerts[0], "수정할 견적을 찾을 수 없습니다.", "missing-target path alerts missing estimate");
    assertEq(env.events.some((entry) => entry[0] === "renderEstimatesList"), false, "missing-target path skips render");
    assertEq(env.events.some((entry) => entry[0] === "resetInputFormKeepCustomerName"), false, "missing-target path skips reset");
    assertIncludes(env.errors.join("\n"), "견적을 찾을 수 없습니다.", "missing-target path logs missing-estimate error");
    assertIncludes(env.errors.join("\n"), "editingEstimateId: missing-id", "missing-target path logs normalized editing id");
    assertIncludes(env.errors.join("\n"), "Available IDs: other-id", "missing-target path logs available ids");
}

function scenarioFollowUpListenerCallsOriginalOnclickAndShowsSaveButton() {
    const env = buildSandbox({
        estimates: [{ id: "existing-1" }],
        currentEstimate: null,
        initialSaveDisplay: "none",
    });
    env.ids.addEstimateBtn.onclick = function () {
        env.events.push(["originalAddEstimate"]);
    };

    env.init();
    env.clickCurrentButton();

    assertEq(env.alerts[0], "견적 정보를 입력해주세요.", "primary listener still surfaces missing-estimate alert");
    assertEq(
        env.events.some((entry) => JSON.stringify(entry) === JSON.stringify(["originalAddEstimate"])),
        true,
        "follow-up listener manually invokes original onclick"
    );
    assertEq(env.ids.saveEstimateBtn.style.display, "block", "follow-up listener shows save button when estimates already exist");
}

function main() {
    scenarioInitBindsPrimaryAndFollowUpListeners();
    scenarioAddModeGeneratesIdRendersAndShowsSaveButton();
    scenarioUpdateModePreservesDisplayNameWhenProductIdentityMatches();
    scenarioWidthChangeRefreshesDisplayNameAndLogsReason();
    scenarioMissingEditingTargetAlertsAndStopsBeforeReset();
    scenarioFollowUpListenerCallsOriginalOnclickAndShowsSaveButton();
    console.log("wdcalculator add-estimate contract checks passed");
}

main();
