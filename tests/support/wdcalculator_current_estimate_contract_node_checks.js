/**
 * Contract freeze: current-estimate orchestration keeps calculate/render and snapshot
 * outputs aligned after extraction out of wdcalculator_scripts.html.
 * Runs current-estimate-orchestration.js in VM with DOM stubs; read helpers are extracted from
 * static/js/wdcalculator/primary-form.js (W5-B3 merged chunk; replaces separate notes/base/additional/coupon files).
 */
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const repoRoot = path.join(__dirname, "..", "..");
const orchestrationPath = path.join(
    repoRoot,
    "static",
    "js",
    "wdcalculator",
    "current-estimate-orchestration.js"
);
const sharedPath = path.join(repoRoot, "static", "js", "wdcalculator", "shared.js");

const orchestrationSrc = fs.readFileSync(orchestrationPath, "utf8");
const sharedSrc = fs.readFileSync(sharedPath, "utf8");
const currentEstimateMathPath = path.join(
    repoRoot,
    "static",
    "js",
    "wdcalculator",
    "current-estimate-math.js"
);
const currentEstimateMathSrc = fs.readFileSync(currentEstimateMathPath, "utf8");
const calculationResolversPath = path.join(
    repoRoot,
    "static",
    "js",
    "wdcalculator",
    "calculation-resolvers.js"
);
const calculationResolversSrc = fs.readFileSync(calculationResolversPath, "utf8");
const primaryFormPath = path.join(repoRoot, "static", "js", "wdcalculator", "primary-form.js");
const primaryFormSrc = fs.readFileSync(primaryFormPath, "utf8");

/**
 * Extract `function name(...) { ... }` while skipping strings/comments/template literals
 * so braces inside template strings do not break balancing.
 */
function extractFunctionSource(src, name, pathForError) {
    const label = pathForError || orchestrationPath;
    const needle = `function ${name}(`;
    const start = src.indexOf(needle);
    if (start === -1) {
        throw new Error(`Function ${name} not found in ${label}`);
    }
    let i = src.indexOf("{", start);
    if (i < 0) throw new Error(`Opening brace not found for ${name}`);
    let depth = 0;
    let state = "code";

    const scanExprClosing = (from) => {
        let j = from;
        let d = 1;
        while (d > 0 && j < src.length) {
            const ch = src[j];
            if (ch === "{") d++;
            else if (ch === "}") d--;
            j++;
        }
        return j - 1;
    };

    for (; i < src.length; i++) {
        const c = src[i];
        const next = src[i + 1];

        if (state === "code") {
            if (c === "/" && next === "/") {
                state = "lineComment";
                i++;
                continue;
            }
            if (c === "/" && next === "*") {
                state = "blockComment";
                i++;
                continue;
            }
            if (c === "'") {
                state = "single";
                continue;
            }
            if (c === '"') {
                state = "double";
                continue;
            }
            if (c === "`") {
                state = "template";
                continue;
            }
            if (c === "{") depth++;
            else if (c === "}") {
                depth--;
                if (depth === 0) {
                    return src.slice(start, i + 1);
                }
            }
        } else if (state === "lineComment") {
            if (c === "\n" || c === "\r") state = "code";
        } else if (state === "blockComment") {
            if (c === "*" && next === "/") {
                state = "code";
                i++;
            }
        } else if (state === "single") {
            if (c === "\\") {
                i++;
                continue;
            }
            if (c === "'") state = "code";
        } else if (state === "double") {
            if (c === "\\") {
                i++;
                continue;
            }
            if (c === '"') state = "code";
        } else if (state === "template") {
            if (c === "\\") {
                i++;
                continue;
            }
            if (c === "`") {
                state = "code";
                continue;
            }
            if (c === "$" && next === "{") {
                const close = scanExprClosing(i + 2);
                i = close;
                continue;
            }
        }
    }
    throw new Error(`Unbalanced braces for ${name}`);
}

function assertEq(actual, expected, label) {
    if (actual !== expected) {
        throw new Error(`${label}: expected ${JSON.stringify(expected)}, got ${JSON.stringify(actual)}`);
    }
}

function assertClose(actual, expected, label, eps = 0.01) {
    if (Math.abs(actual - expected) > eps) {
        throw new Error(`${label}: expected ~${expected}, got ${actual}`);
    }
}

function parseWonText(text) {
    if (!text) return 0;
    const digits = String(text).replace(/[^\d]/g, "");
    return digits ? parseInt(digits, 10) : 0;
}

/** Minimal DOM tree for WD calculator contract scenarios */
function createDocumentMock() {
    const ids = {};

    class El {
        constructor(tag, opts = {}) {
            this.tagName = String(tag).toUpperCase();
            this.id = opts.id || "";
            if (this.id) ids[this.id] = this;
            this.className = opts.className || "";
            this.dataset = opts.dataset ? { ...opts.dataset } : {};
            /** @type {Record<string, string>} */
            this.attr = opts.attr || {};
            this.value = opts.value !== undefined ? String(opts.value) : "";
            this.textContent = "";
            this.style = {
                display: opts.display !== undefined ? opts.display : "",
                setProperty() {},
                removeProperty() {},
            };
            this.children = [];
            this.parentEl = null;
        }
        getAttribute(name) {
            return this.attr[name] !== undefined ? this.attr[name] : null;
        }
        appendChild(ch) {
            ch.parentEl = this;
            this.children.push(ch);
            return ch;
        }
        querySelector(sel) {
            if (matchSel(this, sel)) return this;
            for (const ch of this.children) {
                const r = ch.querySelector(sel);
                if (r) return r;
            }
            return null;
        }
        querySelectorAll(sel) {
            const out = [];
            const walk = (n) => {
                if (matchSel(n, sel)) out.push(n);
                n.children.forEach(walk);
            };
            walk(this);
            return out;
        }
    }

    function matchSel(el, sel) {
        if (sel.startsWith("#")) return el.id === sel.slice(1);
        if (sel.startsWith(".")) {
            const c = sel.slice(1);
            return el.className.split(/\s+/).filter(Boolean).includes(c);
        }
        if (sel.startsWith("[") && sel.endsWith("]")) {
            const key = sel.slice(1, -1);
            return Object.prototype.hasOwnProperty.call(el.attr, key);
        }
        return el.tagName === sel.toUpperCase();
    }

    const root = new El("div");

    const document = {
        getElementById(id) {
            return ids[id] || null;
        },
        querySelectorAll(sel) {
            return root.querySelectorAll(sel);
        },
        createElement() {
            return new El("div");
        },
    };

    return { document, ids, root, El };
}

function buildBaseRow(El, mode, fields) {
    const row = new El("div", { className: "base-component-row", dataset: { mode } });
    const w = new El("input", { className: "base-width-input", value: fields.widthMm ?? 0 });
    row.appendChild(w);

    if (mode === "select") {
        const sel = new El("select", { className: "base-product-select", value: fields.productId ?? "" });
        row.appendChild(sel);
    } else {
        const pt = new El("select", { className: "base-manual-pricing-type", value: fields.pricingType || "30cm" });
        row.appendChild(pt);
        row.appendChild(
            new El("input", { className: "base-manual-price30", value: fields.price30 ?? "" })
        );
        row.appendChild(new El("input", { className: "base-manual-price1", value: fields.price1 ?? "" }));
        row.appendChild(new El("input", { className: "base-manual-price1m", value: fields.price1m ?? "" }));
    }

    const feeList = new El("div", { className: "base-additional-fees-list" });
    (fields.additionalFees || []).forEach((fee) => {
        const item = new El("div", { className: "base-additional-fee-item" });
        item.appendChild(new El("input", { className: "base-additional-fee-name", value: fee.name || "" }));
        item.appendChild(
            new El("input", { className: "base-additional-fee-amount", value: fee.amount ?? "" })
        );
        feeList.appendChild(item);
    });
    row.appendChild(feeList);
    return row;
}

function buildOptionItem(El, opt) {
    const item = new El("div", { className: "additional-option-item" });
    const useSelect = opt.useSelect !== false;
    const sel = new El("select", {
        className: "form-select category-option-select",
        value: opt.selectValue || "",
        display: useSelect ? "block" : "none",
        attr: { "data-category-option-select": "" },
    });
    item.appendChild(sel);
    const nameInput = new El("input", {
        className: "option-name-input",
        value: opt.nameInputValue || "",
        display: opt.useNameInput ? "block" : "none",
        attr: { "data-option-name": "" },
    });
    item.appendChild(nameInput);
    item.appendChild(
        new El("input", {
            className: "option-price-input",
            value: opt.price != null ? String(opt.price) : "",
            attr: { "data-option-price": "" },
        })
    );
    item.appendChild(
        new El("input", {
            className: "option-quantity-input",
            value: String(opt.quantity != null ? opt.quantity : 1),
            attr: { "data-option-quantity": "" },
        })
    );
    return item;
}

function wireUi(ids, root, El, layout) {
    const baseC = new El("div", { id: "baseComponentsContainer" });
    layout.baseRows.forEach((spec) => {
        baseC.appendChild(buildBaseRow(El, spec.mode, spec));
    });
    root.appendChild(baseC);

    const addOpt = new El("div", { id: "additionalOptionsContainer" });
    (layout.optionItems || []).forEach((o) => addOpt.appendChild(buildOptionItem(El, o)));
    root.appendChild(addOpt);

    [
        "baseEstimateSection",
        "totalBasePrice",
        "totalAdditionalPrice",
        "totalPrice",
        "finalPrice",
        "baseEstimateDetail",
        "additionalOptionsDetail",
        "basePriceDisplay",
        "couponInfo",
        "addEstimateBtn",
        "saveEstimateBtn",
        "globalCouponValue",
    ].forEach((id) => {
        const e = new El("div", { id });
        if (id === "globalCouponValue") e.value = layout.couponValue != null ? String(layout.couponValue) : "0";
        if (id === "baseEstimateSection") e.style.display = "block";
        root.appendChild(e);
        ids[id] = e;
    });
}

/**
 * @param {object} [expectShape]
 * @param {(collected: object, name: string) => void} [expectShape.assert]
 */
function runScenario(name, layout, products, editingEstimateId, estimates, expectShape) {
    const { document, ids, root, El } = createDocumentMock();
    wireUi(ids, root, El, layout);

    const sandbox = {
        console,
        document,
        window: null,
        globalThis: null,
        products,
        editingEstimateId,
        estimates,
        notesList: [],
        DEFAULT_COUPON_VALUE: 11000,
        parseInt,
        parseFloat,
        Math,
        Number,
        isNaN,
        Array,
        Map,
        String,
        Object,
        JSON,
    };
    sandbox.window = sandbox;
    sandbox.globalThis = sandbox;

    vm.createContext(sandbox);
    vm.runInContext(sharedSrc, sandbox);
    vm.runInContext(currentEstimateMathSrc, sandbox);
    vm.runInContext(calculationResolversSrc, sandbox);
    vm.runInContext(primaryFormSrc, sandbox);
    vm.runInContext(
        `
        WdCalculatorCouponDisplayHelpers.configure({ defaultCouponValue: DEFAULT_COUPON_VALUE });
        var getCouponValue = WdCalculatorCouponDisplayHelpers.getCouponValue;
        var applyFinalPriceStyle = WdCalculatorCouponDisplayHelpers.applyFinalPriceStyle;
        var applyCouponDiscountStyle = WdCalculatorCouponDisplayHelpers.applyCouponDiscountStyle;
        var documentRef = document;
        var resolveWdcCurrentEstimateMath = window.WdCalculatorCalculationResolvers.resolveCurrentEstimateMath;
        `,
        sandbox
    );

    const readBaseComponentsSrc = extractFunctionSource(
        primaryFormSrc,
        "readBaseComponentsFromUI",
        primaryFormPath
    );
    const readAdditionalOptionRowsSrc = extractFunctionSource(
        primaryFormSrc,
        "readAdditionalOptionRowsFromUI",
        primaryFormPath
    );
    const extracted = [
        readBaseComponentsSrc,
        readAdditionalOptionRowsSrc,
        extractFunctionSource(primaryFormSrc, "collectNotes", primaryFormPath),
    ].join("\n");

    vm.runInContext(extracted, sandbox);
    vm.runInContext(orchestrationSrc, sandbox);
    vm.runInContext(
        `
        WdCalculatorCurrentEstimateOrchestration.configure({
            getProducts: function () { return products; },
            getEditingEstimateId: function () { return editingEstimateId; },
            getEstimates: function () { return estimates; },
            readBaseComponentsFromUI: readBaseComponentsFromUI,
            readAdditionalOptionRowsFromUI: readAdditionalOptionRowsFromUI,
            resolveCurrentEstimateMath: resolveWdcCurrentEstimateMath,
            getCouponValue: getCouponValue,
            formatNumber: formatNumber,
            applyFinalPriceStyle: applyFinalPriceStyle,
            applyCouponDiscountStyle: applyCouponDiscountStyle,
            collectNotes: collectNotes,
            documentRef: document,
            alertImpl: function (message) {
                throw new Error("Unexpected alert: " + message);
            },
            consoleRef: console,
        });
        this.calculateEstimate = WdCalculatorCurrentEstimateOrchestration.calculateEstimate;
        this.collectCurrentEstimate = WdCalculatorCurrentEstimateOrchestration.collectCurrentEstimate;
        `,
        sandbox
    );

    if (Array.isArray(layout.notesListSeed)) {
        sandbox.notesList = layout.notesListSeed;
    }

    sandbox.calculateEstimate();
    const domBase = parseWonText(ids.totalBasePrice.textContent);
    const domAdd = parseWonText(ids.totalAdditionalPrice.textContent);
    const domTotal = parseWonText(ids.totalPrice.textContent);
    const domFinal = parseWonText(ids.finalPrice.textContent);
    const couponValue = Number(layout.couponValue || 0);

    const collected = sandbox.collectCurrentEstimate();
    if (!collected) {
        throw new Error(`${name}: collectCurrentEstimate returned null`);
    }

    assertClose(collected.basePrice, domBase, `${name} basePrice vs DOM totalBasePrice`);
    assertClose(collected.additionalPrice, domAdd, `${name} additionalPrice vs DOM totalAdditionalPrice`);
    assertClose(collected.totalPrice, domTotal, `${name} totalPrice vs DOM totalPrice`);
    assertClose(domFinal, Math.max(0, domTotal - couponValue), `${name} finalPrice DOM reflects coupon`);
    assertEq(
        ids.couponInfo.textContent,
        couponValue > 0 ? `${sandbox.formatNumber(couponValue)}원 할인` : "쿠폰가 미적용",
        `${name} coupon info text`
    );
    assertEq(ids.baseEstimateSection.style.display, "block", `${name} baseEstimateSection visible`);

    if (editingEstimateId) {
        assertEq(ids.addEstimateBtn.style.display, "block", `${name} edit mode keeps add button visible`);
    } else {
        assertEq(ids.addEstimateBtn.style.display, "block", `${name} calculate shows add button`);
        assertEq(ids.saveEstimateBtn.style.display, "block", `${name} calculate shows save button`);
    }

    // Snapshot shape
    assertEq(Array.isArray(collected.baseComponents), true, `${name} baseComponents is array`);
    assertEq(Array.isArray(collected.options), true, `${name} options is array`);
    collected.options.forEach((o, idx) => {
        assertEq(typeof o.name, "string", `${name} options[${idx}].name string`);
        assertEq(typeof o.price, "number", `${name} options[${idx}].price number`);
        assertEq(typeof o.quantity, "number", `${name} options[${idx}].quantity number`);
    });
    collected.baseComponents.forEach((bc, idx) => {
        assertEq(typeof bc.mode, "string", `${name} baseComponents[${idx}].mode`);
    });

    if (expectShape && typeof expectShape.assert === "function") {
        expectShape.assert(collected, name);
    }
}

function runEmptyBaseResetScenario() {
    const { document, ids, root, El } = createDocumentMock();
    wireUi(ids, root, El, {
        couponValue: 0,
        baseRows: [],
        optionItems: [],
    });

    const sandbox = {
        console,
        document,
        window: null,
        globalThis: null,
        products: [],
        editingEstimateId: null,
        estimates: [],
        notesList: [],
        DEFAULT_COUPON_VALUE: 11000,
        parseInt,
        parseFloat,
        Math,
        Number,
        isNaN,
        Array,
        Map,
        String,
        Object,
        JSON,
    };
    sandbox.window = sandbox;
    sandbox.globalThis = sandbox;

    vm.createContext(sandbox);
    vm.runInContext(sharedSrc, sandbox);
    vm.runInContext(currentEstimateMathSrc, sandbox);
    vm.runInContext(calculationResolversSrc, sandbox);
    vm.runInContext(primaryFormSrc, sandbox);
    vm.runInContext(orchestrationSrc, sandbox);
    vm.runInContext(
        `
        WdCalculatorCouponDisplayHelpers.configure({ defaultCouponValue: DEFAULT_COUPON_VALUE });
        WdCalculatorCurrentEstimateOrchestration.configure({
            getProducts: function () { return products; },
            getEditingEstimateId: function () { return editingEstimateId; },
            getEstimates: function () { return estimates; },
            readBaseComponentsFromUI: function () { return []; },
            readAdditionalOptionRowsFromUI: function () { return []; },
            resolveCurrentEstimateMath: function () { throw new Error("should not run"); },
            getCouponValue: WdCalculatorCouponDisplayHelpers.getCouponValue,
            formatNumber: formatNumber,
            applyFinalPriceStyle: WdCalculatorCouponDisplayHelpers.applyFinalPriceStyle,
            applyCouponDiscountStyle: WdCalculatorCouponDisplayHelpers.applyCouponDiscountStyle,
            collectNotes: function () { return ""; },
            documentRef: document,
            alertImpl: function (message) {
                throw new Error("Unexpected alert: " + message);
            },
            consoleRef: console,
        });
        this.calculateEstimate = WdCalculatorCurrentEstimateOrchestration.calculateEstimate;
        `,
        sandbox
    );

    sandbox.calculateEstimate();

    assertEq(ids.baseEstimateSection.style.display, "none", "empty_base hides baseEstimateSection");
    assertEq(ids.totalBasePrice.textContent, "0원", "empty_base resets totalBasePrice");
    assertEq(ids.totalAdditionalPrice.textContent, "0원", "empty_base resets totalAdditionalPrice");
    assertEq(ids.totalPrice.textContent, "0원", "empty_base resets totalPrice");
    assertEq(ids.finalPrice.textContent, "0원", "empty_base resets finalPrice");
    assertEq(ids.baseEstimateDetail.textContent, "", "empty_base clears baseEstimateDetail");
    assertEq(ids.additionalOptionsDetail.textContent, "", "empty_base clears option detail");
}

// --- Scenarios ---

const products30 = [
    {
        id: 1,
        name: "Contract Product 30cm",
        pricing_type: "30cm",
        price_30cm: 187000,
        price_1cm: 6230,
    },
];

// Product + option rows (dropdown selection path)
runScenario(
    "product_and_options",
    {
        couponValue: 0,
        baseRows: [
            {
                mode: "select",
                widthMm: 4470,
                productId: 1,
                additionalFees: [],
            },
        ],
        optionItems: [
            {
                useSelect: true,
                selectValue: "가구|서랍장A|5000",
                price: 5000,
                quantity: 2,
            },
        ],
    },
    products30,
    null,
    [],
    {
        assert(collected, scenarioName) {
            assertEq(collected.baseComponents.length, 1, `${scenarioName} one base component`);
            assertEq(collected.baseComponents[0].mode, "select", `${scenarioName} select mode`);
            assertEq(collected.baseComponents[0].productId, 1, `${scenarioName} productId`);
            assertEq(collected.options.length, 1, `${scenarioName} one option row`);
            assertEq(collected.options[0].name, "가구 > 서랍장A", `${scenarioName} option name from dropdown`);
            assertEq(collected.options[0].quantity, 2, `${scenarioName} option qty`);
        },
    }
);

// Manual 30cm path (readBaseComponentsFromUI fills price_1cm via computeAutoPrice1cmFrom30cm)
runScenario(
    "manual_30cm",
    {
        couponValue: 0,
        baseRows: [
            {
                mode: "manual",
                widthMm: 4470,
                pricingType: "30cm",
                price30: 187000,
                price1: "",
                additionalFees: [],
            },
        ],
        optionItems: [],
    },
    products30,
    null,
    [],
    {
        assert(collected, scenarioName) {
            assertEq(collected.baseComponents.length, 1, `${scenarioName} one base component`);
            assertEq(collected.baseComponents[0].mode, "manual", `${scenarioName} manual mode`);
            assertEq(collected.baseComponents[0].manualPricing.pricing_type, "30cm", `${scenarioName} 30cm pricing`);
            assertEq(collected.options.length, 0, `${scenarioName} no options`);
        },
    }
);

// Additional-fee-only base row (width 0, fees drive base price)
runScenario(
    "additional_fee_only_base",
    {
        couponValue: 0,
        baseRows: [
            {
                mode: "select",
                widthMm: 0,
                productId: "",
                additionalFees: [{ name: "현장조정", amount: 150000 }],
            },
        ],
        optionItems: [],
    },
    products30,
    null,
    [],
    {
        assert(collected, scenarioName) {
            assertEq(collected.baseComponents.length, 1, `${scenarioName} one normalized row`);
            assertEq(collected.baseComponents[0].widthMm, 0, `${scenarioName} width 0`);
            assertEq(
                Array.isArray(collected.baseComponents[0].additionalFees),
                true,
                `${scenarioName} additionalFees array`
            );
            assertEq(collected.options.length, 0, `${scenarioName} no options`);
        },
    }
);

// Width > 0 but unresolved base price with fees must still collect consistently
runScenario(
    "width_positive_fee_only_without_base",
    {
        couponValue: 0,
        baseRows: [
            {
                mode: "select",
                widthMm: 1200,
                productId: "",
                additionalFees: [{ name: "현장조정", amount: 150000 }],
            },
        ],
        optionItems: [],
    },
    products30,
    null,
    [],
    {
        assert(collected, scenarioName) {
            assertEq(collected.basePrice, 150000, `${scenarioName} collects fee-only base price`);
            assertEq(collected.totalPrice, 150000, `${scenarioName} collects fee-only total price`);
            assertEq(collected.baseComponents.length, 1, `${scenarioName} one normalized row`);
            assertEq(collected.baseComponents[0].widthMm, 1200, `${scenarioName} width kept`);
            assertEq(collected.baseComponents[0].productId, null, `${scenarioName} unresolved product kept null`);
        },
    }
);

// Manual mode with unresolved base unit price but fees must also collect consistently
runScenario(
    "manual_width_positive_fee_only_without_base",
    {
        couponValue: 0,
        baseRows: [
            {
                mode: "manual",
                widthMm: 1800,
                pricingType: "30cm",
                price30: "",
                price1: "",
                additionalFees: [{ name: "시공보정", amount: 90000 }],
            },
        ],
        optionItems: [],
    },
    products30,
    null,
    [],
    {
        assert(collected, scenarioName) {
            assertEq(collected.basePrice, 90000, `${scenarioName} collects fee-only manual base price`);
            assertEq(collected.totalPrice, 90000, `${scenarioName} collects fee-only manual total`);
            assertEq(collected.baseComponents.length, 1, `${scenarioName} one normalized row`);
            assertEq(collected.baseComponents[0].mode, "manual", `${scenarioName} manual mode kept`);
            assertEq(collected.baseComponents[0].widthMm, 1800, `${scenarioName} width kept`);
            assertEq(
                collected.baseComponents[0].manualPricing.pricing_type,
                "30cm",
                `${scenarioName} manual pricing kept`
            );
        },
    }
);

// Direct-input option path (name input visible, select hidden)
runScenario(
    "option_direct_input",
    {
        couponValue: 0,
        baseRows: [
            {
                mode: "select",
                widthMm: 3000,
                productId: 1,
                additionalFees: [],
            },
        ],
        optionItems: [
            {
                useSelect: false,
                useNameInput: true,
                nameInputValue: "직접 > 옵션명",
                price: 12000,
                quantity: 1,
            },
        ],
        notesListSeed: [{ type: "input", value: "현장 메모 1줄" }],
    },
    products30,
    null,
    [],
    {
        assert(collected, scenarioName) {
            assertEq(collected.options.length, 1, `${scenarioName} one option`);
            assertEq(collected.options[0].name, "직접 > 옵션명", `${scenarioName} direct option name`);
            assertEq(collected.options[0].price, 12000, `${scenarioName} option unit price`);
            assertEq(collected.notes, "현장 메모 1줄", `${scenarioName} notes snapshot`);
        },
    }
);

runScenario(
    "editing_mode_coupon_render",
    {
        couponValue: 11000,
        baseRows: [
            {
                mode: "select",
                widthMm: 3000,
                productId: 1,
                additionalFees: [],
            },
        ],
        optionItems: [],
    },
    products30,
    "edit-1",
    [],
    {
        assert(collected, scenarioName) {
            assertEq(collected.baseComponents.length, 1, `${scenarioName} one base component`);
        },
    }
);

runEmptyBaseResetScenario();

process.exit(0);
