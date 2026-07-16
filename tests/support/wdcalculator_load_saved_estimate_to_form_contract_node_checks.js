/**
 * Contract freeze: saved DB estimate -> form hydrate flow in
 * static/js/wdcalculator/load-saved-estimate-to-form.js.
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
        return "__undefined__";
    }
    return JSON.parse(JSON.stringify(value));
}

function extractBalancedBlock(src, start, sourceLabel, description) {
    let i = src.indexOf("{", start);
    if (i < 0) {
        throw new Error(`Opening brace not found for ${description} in ${sourceLabel}`);
    }
    let depth = 0;
    let state = "code";

    const scanExprClosing = (from) => {
        let j = from;
        let exprDepth = 1;
        while (exprDepth > 0 && j < src.length) {
            const ch = src[j];
            if (ch === "{") exprDepth++;
            else if (ch === "}") exprDepth--;
            j++;
        }
        return j - 1;
    };

    for (; i < src.length; i++) {
        const ch = src[i];
        const next = src[i + 1];

        if (state === "code") {
            if (ch === "/" && next === "/") {
                state = "lineComment";
                i++;
                continue;
            }
            if (ch === "/" && next === "*") {
                state = "blockComment";
                i++;
                continue;
            }
            if (ch === "'") {
                state = "single";
                continue;
            }
            if (ch === '"') {
                state = "double";
                continue;
            }
            if (ch === "`") {
                state = "template";
                continue;
            }
            if (ch === "{") depth++;
            else if (ch === "}") {
                depth--;
                if (depth === 0) {
                    return src.slice(start, i + 1);
                }
            }
        } else if (state === "lineComment") {
            if (ch === "\n" || ch === "\r") state = "code";
        } else if (state === "blockComment") {
            if (ch === "*" && next === "/") {
                state = "code";
                i++;
            }
        } else if (state === "single") {
            if (ch === "\\") {
                i++;
                continue;
            }
            if (ch === "'") state = "code";
        } else if (state === "double") {
            if (ch === "\\") {
                i++;
                continue;
            }
            if (ch === '"') state = "code";
        } else if (state === "template") {
            if (ch === "\\") {
                i++;
                continue;
            }
            if (ch === "`") {
                state = "code";
                continue;
            }
            if (ch === "$" && next === "{") {
                i = scanExprClosing(i + 2);
                continue;
            }
        }
    }

    throw new Error(`Unbalanced braces for ${description} in ${sourceLabel}`);
}

function extractFunctionSource(src, name, label) {
    const sourceLabel = label || templatePath;
    const needle = `function ${name}(`;
    const start = src.indexOf(needle);
    if (start === -1) {
        throw new Error(`Function ${name} not found in ${sourceLabel}`);
    }
    return extractBalancedBlock(src, start, sourceLabel, `function ${name}`);
}

class El {
    constructor(tag, opts = {}) {
        this.tagName = String(tag).toUpperCase();
        this.id = opts.id || "";
        this.className = opts.className || "";
        this.innerHTML = opts.innerHTML || "";
        this.value = opts.value || "";
        this.checked = !!opts.checked;
        this.children = [];
        this.parentNode = null;
        this.style = { display: opts.display || "" };
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
}

function buildSandbox(spec = {}) {
    const ids = {};
    const events = [];
    const confirms = [];
    let reloadCount = 0;
    let generatedIds = 0;
    let confirmRef = function () {
        return true;
    };
    let reloadRef = function () {};

    const headerPrimary = new El("div", { className: "header-primary", ids });
    const headerTitle = headerPrimary.appendChild(new El("h6", { ids }));
    if (spec.includeExistingResetBtn) {
        const existingResetBtn = new El("button", { id: "resetEstimateBtn", ids });
        existingResetBtn.className = "btn btn-sm btn-light float-end";
        existingResetBtn.innerHTML = "<i class=\"fas fa-undo\"></i> 기존 버튼";
        existingResetBtn.onclick = function () {
            if (confirmRef("현재 작성/수정 중인 내용을 초기화하고 새 견적을 작성하시겠습니까?")) {
                reloadRef();
            }
        };
        headerPrimary.appendChild(existingResetBtn);
    }

    const customerName = new El("input", { id: "customerName", value: "기존 고객", ids });
    const globalCouponValue = new El("input", { id: "globalCouponValue", value: "0", ids });
    const shippingCost = new El("input", { id: "shippingCost", value: "0", ids });
    const shippingIncluded = new El("input", { id: "shippingIncluded", checked: true, ids });
    const saveEstimateBtn = new El("button", {
        id: "saveEstimateBtn",
        display: spec.initialSaveDisplay || "none",
        ids,
    });
    const additionalOptionsContainer = new El("div", {
        id: "additionalOptionsContainer",
        innerHTML: spec.additionalOptionsHtml || "<div>stale</div>",
        ids,
    });
    const productInfo = new El("div", { id: "productInfo", display: "block", ids });
    const baseEstimateSection = new El("div", { id: "baseEstimateSection", display: "block", ids });
    const addEstimateBtn = new El("button", {
        id: "addEstimateBtn",
        innerHTML: spec.initialAddEstimateHtml || "<i class=\"fas fa-save\"></i> 견적 수정 적용",
        display: spec.initialAddEstimateDisplay || "block",
        ids,
    });

    const state = {
        currentDatabaseEstimateId: spec.initialCurrentDatabaseEstimateId || null,
        estimates: clone(spec.initialEstimates || ["draft"]),
    };

    const document = {
        getElementById(id) {
            return ids[id] || null;
        },
        querySelector(selector) {
            if (selector === ".header-primary h6") {
                return headerTitle;
            }
            if (selector === ".header-primary") {
                return headerPrimary;
            }
            return null;
        },
        createElement(tag) {
            return new El(tag, { ids });
        },
    };

    const sandbox = {
        window: {},
        globalThis: null,
        document,
        console,
        confirm(message) {
            confirms.push(message);
            return spec.confirmResult === undefined ? true : spec.confirmResult;
        },
        location: {
            reload() {
                reloadCount += 1;
            },
        },
        WdCalculatorNotesUI: {
            resetNotesToEmpty() {
                events.push(["resetNotesToEmpty"]);
            },
        },
        generateEstimateId() {
            generatedIds += 1;
            return `gen-${generatedIds}`;
        },
        formatNumber(value) {
            return Number(value || 0).toLocaleString("en-US");
        },
        renderEstimatesList() {
            events.push(["renderEstimatesList"]);
        },
        ensureBaseComponentsUI(...args) {
            events.push(["ensureBaseComponentsUI", clone(args.length ? args[0] : undefined)]);
        },
        calculateEstimate() {
            events.push(["calculateEstimate"]);
        },
    };
    sandbox.globalThis = sandbox;
    confirmRef = sandbox.confirm;
    reloadRef = sandbox.location.reload;

    Object.defineProperty(sandbox, "currentDatabaseEstimateId", {
        get() {
            return state.currentDatabaseEstimateId;
        },
        set(next) {
            state.currentDatabaseEstimateId = next;
            events.push(["setCurrentDatabaseEstimateId", next]);
        },
        configurable: true,
    });
    Object.defineProperty(sandbox, "estimates", {
        get() {
            return state.estimates;
        },
        set(next) {
            state.estimates = clone(next);
            events.push(["setEstimates", clone(next)]);
        },
        configurable: true,
    });

    vm.createContext(sandbox);
    vm.runInContext(
        [
            helperSrc,
            `
            window.WdCalculatorLoadSavedEstimateToForm.configure({
                setCurrentDatabaseEstimateId: function (next) { currentDatabaseEstimateId = next; },
                setEstimates: function (next) { estimates = next; },
                generateEstimateId: generateEstimateId,
                formatNumber: formatNumber,
                renderEstimatesList: renderEstimatesList,
                ensureBaseComponentsUI: ensureBaseComponentsUI,
                calculateEstimate: calculateEstimate,
                resetNotesToEmpty: WdCalculatorNotesUI.resetNotesToEmpty,
                documentRef: document,
                confirmImpl: confirm,
                reloadImpl: location.reload
            });
            `,
        ].join("\n\n"),
        sandbox,
        { filename: helperPath }
    );

    return {
        ids,
        state,
        events,
        confirms,
        get reloadCount() {
            return reloadCount;
        },
        headerPrimary,
        headerTitle,
        customerName,
        globalCouponValue,
        shippingCost,
        shippingIncluded,
        saveEstimateBtn,
        additionalOptionsContainer,
        productInfo,
        baseEstimateSection,
        addEstimateBtn,
        run(estimate) {
            sandbox.__estimate = estimate;
            vm.runInContext(
                "window.WdCalculatorLoadSavedEstimateToForm.loadEstimateToForm(__estimate);",
                sandbox,
                { filename: helperPath }
            );
        },
    };
}

function scenarioHappyPathHydratesSavedEstimateIntoForm() {
    const env = buildSandbox();

    env.run({
        id: 77,
        customer_name: "홍길동",
        estimate_data: {
            coupon_discount: 11000,
            shipping_cost: 4000,
            shipping_included: false,
            notes: "전체 비고",
            estimates: [
                {
                    id: 123,
                    productId: 7,
                    productName: "Wardrobe",
                    widthMm: 2400,
                    basePrice: 1000,
                    options: [{ name: "손잡이", price: 1000 }],
                    additionalPrice: 200,
                    totalPrice: 1200,
                    baseComponents: [{ mode: "select", productId: 7 }],
                    notes: "개별 비고",
                },
                {
                    productId: 8,
                    productName: "Desk",
                    widthMm: 1200,
                    basePrice: 500,
                    options: [],
                    additionalPrice: 0,
                    totalPrice: 500,
                    baseComponents: null,
                },
            ],
        },
    });

    assertDeepEqual(
        env.events.slice(0, 6),
        [
            ["setCurrentDatabaseEstimateId", 77],
            ["resetNotesToEmpty"],
            ["setEstimates", []],
            [
                "setEstimates",
                [
                    {
                        id: "123",
                        productId: 7,
                        productName: "Wardrobe",
                        displayName: "Wardrobe 2,400mm",
                        widthMm: 2400,
                        basePrice: 1000,
                        options: [{ name: "손잡이", price: 1000 }],
                        additionalPrice: 200,
                        totalPrice: 1200,
                        baseComponents: [{ mode: "select", productId: 7 }],
                        notes: "개별 비고",
                    },
                    {
                        id: "gen-1",
                        productId: 8,
                        productName: "Desk",
                        displayName: "Desk 1,200mm",
                        widthMm: 1200,
                        basePrice: 500,
                        options: [],
                        additionalPrice: 0,
                        totalPrice: 500,
                        baseComponents: null,
                        notes: "전체 비고",
                    },
                ],
            ],
            ["renderEstimatesList"],
            ["ensureBaseComponentsUI", "__undefined__"],
        ],
        "happy path preserves state transition and line-item mapping order"
    );
    assertEq(env.events[6][0], "calculateEstimate", "happy path recalculates after resetting form");
    assertEq(env.state.currentDatabaseEstimateId, 77, "happy path stores DB estimate id");
    assertIncludes(env.headerTitle.innerHTML, "견적 수정: 홍길동", "happy path updates header title");
    assertIncludes(env.headerTitle.innerHTML, "수정모드", "happy path keeps edit badge in header");
    assertEq(env.customerName.value, "홍길동", "happy path hydrates customer name");
    assertEq(env.globalCouponValue.value, "11,000", "happy path hydrates coupon discount (T5 콤마 표시)");
    assertEq(env.shippingCost.value, "4,000", "happy path hydrates shipping cost (T5 콤마 표시)");
    assertEq(env.shippingIncluded.checked, false, "happy path hydrates shipping-included checkbox");
    assertEq(env.saveEstimateBtn.style.display, "block", "happy path shows save button");
    assertEq(env.additionalOptionsContainer.innerHTML, "", "happy path clears additional options container");
    assertEq(env.productInfo.style.display, "none", "happy path hides product info");
    assertEq(env.baseEstimateSection.style.display, "none", "happy path hides base estimate section");
    assertEq(env.addEstimateBtn.innerHTML, '<i class="fas fa-plus"></i> 견적 추가', "happy path resets add button label");
    assertEq(env.addEstimateBtn.style.display, "none", "happy path hides add button");
    assertEq(env.ids.resetEstimateBtn.id, "resetEstimateBtn", "happy path creates reset button");
    assertEq(env.headerPrimary.children.filter((child) => child.id === "resetEstimateBtn").length, 1, "happy path appends reset button once");

    env.ids.resetEstimateBtn.onclick();
    assertEq(env.confirms.length, 1, "reset button prompts before reload");
    assertEq(env.reloadCount, 1, "reset button reloads page after confirmation");
}

function scenarioEmptyEstimateListOnlyHydratesHeaderAndInputs() {
    const env = buildSandbox();

    env.run({
        id: 88,
        customer_name: "빈 배열 고객",
        estimate_data: {
            coupon_discount: 0,
            shipping_cost: 0,
            shipping_included: true,
            notes: "빈 비고",
            estimates: [],
        },
    });

    assertDeepEqual(
        env.events,
        [
            ["setCurrentDatabaseEstimateId", 88],
            ["resetNotesToEmpty"],
            ["setEstimates", []],
        ],
        "empty-estimates path stops before render/reset/calculate side effects"
    );
    assertEq(env.customerName.value, "빈 배열 고객", "empty-estimates path still hydrates customer name");
    assertEq(env.additionalOptionsContainer.innerHTML, "<div>stale</div>", "empty-estimates path leaves additional options untouched");
    assertEq(env.saveEstimateBtn.style.display, "none", "empty-estimates path does not force save button visible");
    assertEq(env.addEstimateBtn.innerHTML, '<i class="fas fa-save"></i> 견적 수정 적용', "empty-estimates path leaves add button unchanged");
}

function scenarioExistingResetButtonIsReusedWithoutDuplication() {
    const env = buildSandbox({ includeExistingResetBtn: true, confirmResult: false });

    env.run({
        id: 99,
        customer_name: "재사용 고객",
        estimate_data: {
            coupon_discount: 1000,
            shipping_cost: 3000,
            shipping_included: true,
            notes: "",
            estimates: [
                {
                    id: "saved-1",
                    productId: 1,
                    productName: "Cabinet",
                    widthMm: 1000,
                    basePrice: 100,
                    options: [],
                    additionalPrice: 0,
                    totalPrice: 100,
                    baseComponents: null,
                },
            ],
        },
    });

    assertEq(
        env.headerPrimary.children.filter((child) => child.id === "resetEstimateBtn").length,
        1,
        "existing-reset-button path keeps a single reset button"
    );
    env.ids.resetEstimateBtn.onclick();
    assertEq(env.confirms.length, 1, "existing-reset-button path keeps original confirm flow");
    assertEq(env.reloadCount, 0, "existing-reset-button path honors cancel on confirm dialog");
}

function main() {
    scenarioHappyPathHydratesSavedEstimateIntoForm();
    scenarioEmptyEstimateListOnlyHydratesHeaderAndInputs();
    scenarioExistingResetButtonIsReusedWithoutDuplication();
    console.log("wdcalculator load-saved-estimate-to-form contract checks passed");
}

main();
