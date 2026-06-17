/**
 * Contract freeze: base-components cluster in static/js/wdcalculator/primary-form.js
 * (base-components-ui band: getProductsOptionsHtml, renderBaseComponentRow, ensureBaseComponentsUI,
 * readBaseComponentsFromUI, bindAdditionalFeeEvents).
 *
 * Runs in Node vm with DOM stubs + lightweight HTML fragment parser for innerHTML.
 * Invoked by pytest via `node`.
 */
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const repoRoot = path.join(__dirname, "..", "..");
const primaryFormPath = path.join(repoRoot, "static", "js", "wdcalculator", "primary-form.js");
const sharedPath = path.join(repoRoot, "static", "js", "wdcalculator", "shared.js");
const specWidthEvalPath = path.join(repoRoot, "static", "js", "wdcalculator", "spec-width-eval.js");

const baseComponentsUiSrc = fs.readFileSync(primaryFormPath, "utf8");
const sharedSrc = fs.readFileSync(sharedPath, "utf8");
const specWidthEvalSrc = fs.readFileSync(specWidthEvalPath, "utf8");

function assertEq(actual, expected, label) {
    if (actual !== expected) {
        throw new Error(`${label}: expected ${JSON.stringify(expected)}, got ${JSON.stringify(actual)}`);
    }
}

function assertDeepEqual(a, b, label) {
    const aj = JSON.stringify(a);
    const bj = JSON.stringify(b);
    if (aj !== bj) {
        throw new Error(`${label}: expected ${bj}, got ${aj}`);
    }
}

const VOID_TAGS = new Set([
    "INPUT",
    "BR",
    "IMG",
    "META",
    "LINK",
    "AREA",
    "BASE",
    "COL",
    "EMBED",
    "HR",
    "PARAM",
    "SOURCE",
    "TRACK",
    "WBR",
]);

/**
 * Minimal HTML fragment parser (no `>` inside attribute values).
 * Builds El tree for WD calculator base-component markup.
 */
function parseHtmlFragment(html) {
    const tagRe = /<(\/?)([a-zA-Z][\w-]*)([^>]*)>/g;
    const root = { type: "fragment", children: [], parent: null };
    const stack = [root];
    let m;
    while ((m = tagRe.exec(html)) !== null) {
        const isClose = m[1] === "/";
        const tagRaw = m[2];
        const tag = tagRaw.toLowerCase();
        const attrStr = m[3] || "";
        if (isClose) {
            if (stack.length <= 1) continue;
            stack.pop();
            continue;
        }
        const el = createElFromTag(tag, attrStr);
        stack[stack.length - 1].children.push(el);
        el.parent = stack[stack.length - 1];
        const upper = tagRaw.toUpperCase();
        if (!VOID_TAGS.has(upper)) {
            stack.push(el);
        }
    }
    return root;
}

function parseAttrs(attrStr) {
    const attr = {};
    const re = /([\w-]+)(?:="([^"]*)")?/g;
    let mm;
    while ((mm = re.exec(attrStr)) !== null) {
        attr[mm[1]] = mm[2] !== undefined ? mm[2] : "";
    }
    return attr;
}

function createElFromTag(tag, attrStr) {
    const attr = parseAttrs(attrStr);
    const className = attr.class || "";
    const id = attr.id || "";
    const dataset = {};
    Object.keys(attr).forEach((k) => {
        if (k.startsWith("data-")) {
            dataset[k.slice(5)] = attr[k];
        }
    });
    const el = {
        tagName: tag.toUpperCase(),
        className,
        id,
        attr: { ...attr },
        dataset,
        children: [],
        parent: null,
        style: { display: "" },
        listeners: {},
        _value: "",
        textContent: "",
    };
    if (attr.value !== undefined) el._value = String(attr.value);
    if (tag === "button" || tag === "input") {
        el.inputType = attr.type || "";
    }
    return el;
}

function flattenElements(node, out = []) {
    if (node.tagName) {
        out.push(node);
        node.children.forEach((c) => flattenElements(c, out));
    } else if (node.children) {
        node.children.forEach((c) => flattenElements(c, out));
    }
    return out;
}

function wireDomTree(fragmentRoot) {
    const all = flattenElements(fragmentRoot, []);
    const ids = {};
    all.forEach((el) => {
        if (el.id) ids[el.id] = el;
        el.parentEl = null;
    });
    function wireParent(n) {
        if (!n.children) return;
        n.children.forEach((ch) => {
            if (ch.tagName) {
                ch.parentEl = n.tagName ? n : null;
                wireParent(ch);
            }
        });
    }
    wireParent(fragmentRoot);

    all.forEach((el) => {
        Object.defineProperty(el, "value", {
            get() {
                if (el.tagName === "SELECT") {
                    return el._value !== undefined && el._value !== null ? String(el._value) : "";
                }
                return el._value !== undefined ? String(el._value) : "";
            },
            set(v) {
                el._value = v === undefined || v === null ? "" : String(v);
            },
            configurable: true,
        });
        el.classList = {
            contains(c) {
                return el.className.split(/\s+/).filter(Boolean).includes(c);
            },
        };
        el.getAttribute = (name) =>
            el.attr[name] !== undefined ? el.attr[name] : null;
        el.hasAttribute = (name) => Object.prototype.hasOwnProperty.call(el.attr, name);
        el.setAttribute = (name, val) => {
            el.attr[name] = val === undefined || val === null ? "" : String(val);
        };
        el.querySelector = function (sel) {
            return querySelectorList(this, sel, false);
        };
        el.querySelectorAll = function (sel) {
            return querySelectorList(this, sel, true);
        };
        el.appendChild = function (ch) {
            ch.parentEl = this;
            this.children.push(ch);
            return ch;
        };
        el.remove = function () {
            if (!this.parentEl || !this.parentEl.children) return;
            const i = this.parentEl.children.indexOf(this);
            if (i >= 0) this.parentEl.children.splice(i, 1);
            this.parentEl = null;
        };
        el.addEventListener = function (type, fn) {
            if (!this.listeners[type]) this.listeners[type] = [];
            this.listeners[type].push(fn);
        };
        el.closest = function (sel) {
            let n = this;
            while (n) {
                if (matchSel(n, sel)) return n;
                n = n.parentEl;
            }
            return null;
        };
    });
    syncSelectValuesFromOptions(all);
    return { all, ids };
}

/**
 * Mirror browser behavior: <select>.value follows the <option selected> child.
 */
function syncSelectValuesFromOptions(all) {
    all.forEach((el) => {
        if (el.tagName !== "SELECT") return;
        const opts = (el.children || []).filter((c) => c.tagName === "OPTION");
        const selectedOpt = opts.find(
            (o) => o.attr && Object.prototype.hasOwnProperty.call(o.attr, "selected")
        );
        const pick = selectedOpt || opts[0];
        if (pick && pick.attr && pick.attr.value !== undefined) {
            el._value = String(pick.attr.value);
        }
    });
}

function matchSel(el, sel) {
    if (sel.startsWith("#")) return el.id === sel.slice(1);
    if (sel.startsWith(".")) {
        const c = sel.slice(1);
        return el.className.split(/\s+/).filter(Boolean).includes(c);
    }
    return el.tagName === sel.toUpperCase();
}

function querySel(root, sel, all) {
    const out = [];
    const walk = (n) => {
        if (!n) return;
        if (!n.tagName) {
            (n.children || []).forEach(walk);
            return;
        }
        if (matchSel(n, sel)) {
            if (all) out.push(n);
            else {
                out.push(n);
                return;
            }
        }
        n.children.forEach(walk);
    };
    walk(root);
    return all ? out : out[0] || null;
}

function querySelectorList(root, sel, all) {
    const parts = String(sel)
        .split(",")
        .map((s) => s.trim())
        .filter(Boolean);
    if (parts.length <= 1) {
        return querySel(root, parts[0] || sel, all);
    }
    if (all) {
        const seen = new Set();
        const out = [];
        for (const p of parts) {
            for (const n of querySel(root, p, true)) {
                if (!seen.has(n)) {
                    seen.add(n);
                    out.push(n);
                }
            }
        }
        return out;
    }
    for (const p of parts) {
        const hit = querySel(root, p, false);
        if (hit) return hit;
    }
    return null;
}

function bubbleEvent(target, type, extra = {}) {
    const chain = [];
    let n = target;
    while (n) {
        chain.push(n);
        n = n.parentEl;
    }
    const ev = { type, target, bubbles: true, ...extra };
    for (const node of chain) {
        ev.currentTarget = node;
        const list = node.listeners && node.listeners[type];
        if (!list) continue;
        for (const fn of list) fn(ev);
    }
}

function createDocument(ids, rootGetter) {
    return {
        getElementById(id) {
            return ids[id] || null;
        },
        createElement(tag) {
            const el = createElFromTag(tag, "");
            const frag = { type: "fragment", children: [el], parent: null };
            wireDomTree(frag);
            return el;
        },
        querySelectorAll(sel) {
            return rootGetter().querySelectorAll(sel);
        },
    };
}

function assertMarkupContract(html, scenario) {
    const checks = [
        ["base-component-row", html.includes("base-component-row")],
        ["base-width-input", html.includes("base-width-input")],
        ["base-width-preview", html.includes("base-width-preview")],
        ["base-width text input", html.includes('type="text" class="form-control form-control-sm base-width-input"')],
        ["base-additional-fees-list", html.includes("base-additional-fees-list")],
        ["base-mode-btn", html.includes("base-mode-btn")],
    ];
    for (const [name, ok] of checks) {
        assertEq(ok, true, `${scenario}: markup includes ${name}`);
    }
}

function runAll() {
    const products = [
        { id: 1, name: "Prod A" },
        { id: 2, name: "Prod B" },
    ];

    const sandbox = {
        console,
        window: null,
        globalThis: null,
        products,
        Math,
        Number,
        isNaN,
        parseInt,
        parseFloat,
        String,
        Object,
        Array,
        JSON,
    };
    sandbox.window = sandbox;
    sandbox.globalThis = sandbox;

    const fragmentRoot = { type: "fragment", children: [], parent: null };
    const baseContainer = createElFromTag("div", 'id="baseComponentsContainer"');
    baseContainer.id = "baseComponentsContainer";
    baseContainer.attr.id = "baseComponentsContainer";
    fragmentRoot.children.push(baseContainer);
    baseContainer.parent = fragmentRoot;

    const { ids, all: wiredAll } = wireDomTree(fragmentRoot);
    ids.baseComponentsContainer = baseContainer;

    const rootEl = {
        type: "element",
        tagName: "DIV",
        className: "",
        children: [baseContainer],
        querySelectorAll(sel) {
            return querySelectorList(this, sel, true);
        },
        querySelector(sel) {
            return querySelectorList(this, sel, false);
        },
    };
    baseContainer.parentEl = rootEl;

    let calculateCalls = 0;
    function calculateEstimate() {
        calculateCalls++;
    }

    sandbox.document = createDocument(ids, () => rootEl);
    sandbox.calculateEstimate = calculateEstimate;

    vm.createContext(sandbox);
    vm.runInContext(sharedSrc, sandbox);
    vm.runInContext(specWidthEvalSrc, sandbox);

    /** Mirror escapeHtml's need for createElement + textContent + innerHTML */
    vm.runInContext(
        `
    const _ce = document.createElement.bind(document);
    document.createElement = function(tag) {
      const el = _ce(tag);
      Object.defineProperty(el, 'textContent', {
        get() { return el._text || ''; },
        set(v) { el._text = String(v); },
        configurable: true
      });
      Object.defineProperty(el, 'innerHTML', {
        get() {
          const t = el._text || '';
          return t
            .replace(/&/g,'&amp;')
            .replace(/</g,'&lt;')
            .replace(/>/g,'&gt;')
            .replace(/"/g,'&quot;');
        },
        configurable: true
      });
      return el;
    };
    `,
        sandbox
    );

    vm.runInContext(baseComponentsUiSrc, sandbox);
    vm.runInContext(
        `
        WdCalculatorBaseComponentsUI.configure({
            getProducts: function () { return products; },
            getCalculateEstimate: function () { return calculateEstimate; },
        });
        `,
        sandbox
    );

    const render = sandbox.WdCalculatorBaseComponentsUI.renderBaseComponentRow;
    const ensure = sandbox.WdCalculatorBaseComponentsUI.ensureBaseComponentsUI;
    const read = sandbox.WdCalculatorBaseComponentsUI.readBaseComponentsFromUI;
    const bindFees = sandbox.WdCalculatorBaseComponentsUI.bindAdditionalFeeEvents;

    // --- 1) Markup / selector contract (render output) ---
    const htmlSelect = render({ mode: "select", widthMm: 4470, productId: 2, additionalFees: [] });
    assertMarkupContract(htmlSelect, "render_select");
    assertEq(htmlSelect.includes('data-mode="select"'), true, "render_select data-mode select");
    assertEq(htmlSelect.includes("base-product-select"), true, "render_select product select");
    assertEq(htmlSelect.includes('value="1"'), true, "render_select option id 1");
    assertEq(htmlSelect.includes("base-select-area"), true, "render_select base-select-area");
    assertEq(htmlSelect.includes("base-manual-area"), true, "render_select base-manual-area");

    const htmlManual30 = render({
        mode: "manual",
        widthMm: 1800,
        manualPricing: { pricing_type: "30cm", price_30cm: 187000, price_1cm: 6230 },
        additionalFees: [],
    });
    assertMarkupContract(htmlManual30, "render_manual_30");
    assertEq(htmlManual30.includes('data-mode="manual"'), true, "render_manual_30 data-mode");
    assertEq(htmlManual30.includes("base-manual-pricing-type"), true, "render_manual_30 pricing type");
    assertEq(htmlManual30.includes("base-manual-price30"), true, "render_manual_30 price30");
    assertEq(htmlManual30.includes("base-manual-1m-col"), true, "render_manual_30 has 1m col (hidden in 30cm)");

    const htmlManual1m = render({
        mode: "manual",
        widthMm: 2400,
        manualPricing: { pricing_type: "1m", price_1m: 330000 },
        additionalFees: [],
    });
    assertMarkupContract(htmlManual1m, "render_manual_1m");
    assertEq(htmlManual1m.includes('option value="1m"'), true, "render_manual_1m 1m option");
    assertEq(htmlManual1m.includes("base-manual-price1m"), true, "render_manual_1m price1m");

    const htmlFees = render({
        mode: "select",
        widthMm: 0,
        additionalFees: [
            { name: "feeA", amount: 1000 },
            { name: "feeB", amount: 2000 },
        ],
    });
    assertEq(
        (htmlFees.match(/base-additional-fee-item/g) || []).length >= 2,
        true,
        "render_fees two fee rows"
    );

    // --- innerHTML: parse rendered HTML into live nodes ---
    Object.defineProperty(baseContainer, "innerHTML", {
        get() {
            return "";
        },
        set(v) {
            baseContainer.children = [];
            if (!v || !String(v).trim()) return;
            const frag = parseHtmlFragment(String(v));
            wireDomTree(frag);
            const children = frag.children || [];
            children.forEach((ch) => {
                baseContainer.children.push(ch);
                ch.parentEl = baseContainer;
            });
            const w = wireDomTree({
                type: "fragment",
                children: [baseContainer],
                parent: null,
            });
            Object.assign(ids, w.ids);
        },
        configurable: true,
    });

    // Re-wire base container after innerHTML descriptor
    wireDomTree({ type: "fragment", children: [baseContainer], parent: null });

    // --- 2) ensureBaseComponentsUI restores productId on select ---
    ensure([
        { mode: "select", productId: 2, widthMm: 3000, additionalFees: [] },
    ]);
    const sel = baseContainer.querySelector(".base-product-select");
    assertEq(sel ? sel.value : "", "2", "ensure restores productId 2 on select");

    // --- 3) readBaseComponentsFromUI normalized shape (select) ---
    const snapSelect = read();
    assertEq(Array.isArray(snapSelect), true, "read returns array");
    assertEq(snapSelect.length, 1, "read one row");
    assertDeepEqual(
        snapSelect[0],
        {
            mode: "select",
            widthInput: "3000",
            widthMm: 3000,
            additionalFees: [],
            productId: 2,
        },
        "read select snapshot"
    );

    // --- manual 30cm snapshot (readBaseComponentsFromUI fills price_1cm) ---
    calculateCalls = 0;
    ensure([
        {
            mode: "manual",
            widthMm: 4470,
            manualPricing: { pricing_type: "30cm", price_30cm: 187000 },
            additionalFees: [],
        },
    ]);
    const snapManual30 = read();
    assertEq(snapManual30[0].mode, "manual", "read manual mode");
    assertEq(snapManual30[0].manualPricing.pricing_type, "30cm", "read 30cm pricing");
    assertEq(snapManual30[0].widthMm, 4470, "read width");
    assertEq(
        typeof snapManual30[0].manualPricing.price_1cm,
        "number",
        "read price_1cm number"
    );

    // --- manual 1m ---
    ensure([
        {
            mode: "manual",
            widthMm: 2000,
            manualPricing: { pricing_type: "1m", price_1m: 400000 },
            additionalFees: [],
        },
    ]);
    const snap1m = read();
    assertDeepEqual(
        snap1m[0],
        {
            mode: "manual",
            widthInput: "2000",
            widthMm: 2000,
            additionalFees: [],
            manualPricing: { pricing_type: "1m", price_1m: 400000 },
        },
        "read manual 1m snapshot"
    );

    // --- additional fees DOM -> snapshot ---
    ensure([
        {
            mode: "select",
            productId: 1,
            widthMm: 100,
            additionalFees: [
                { name: "현장", amount: 50000 },
                { name: "", amount: 0 },
            ],
        },
    ]);
    const snapFees = read();
    assertEq(snapFees[0].additionalFees.length, 1, "read skips empty name+zero amount fee");
    assertDeepEqual(
        snapFees[0].additionalFees[0],
        { name: "현장", amount: 50000 },
        "read fee shape"
    );

    // --- 4) Host delegated input listener remains the single calculate hook ---
    sandbox.computeAutoPrice1cmFrom30cm = sandbox.computeAutoPrice1cmFrom30cm || function () {};
    const compute = sandbox.computeAutoPrice1cmFrom30cm;
    baseContainer.addEventListener("input", function (e) {
        const rowEl = e.target && e.target.closest ? e.target.closest(".base-component-row") : null;
        if (!rowEl) return;
        if (e.target.classList && e.target.classList.contains("base-manual-price30")) {
            const price30 = Number(e.target.value) || 0;
            const auto1 = compute(price30);
            const price1El = rowEl.querySelector(".base-manual-price1");
            if (price1El) price1El.value = String(auto1);
        }
        calculateEstimate();
    });

    calculateCalls = 0;
    ensure([{ mode: "select", productId: "", widthMm: 100, additionalFees: [{ name: "x", amount: 1 }] }]);
    bindFees();
    const feeAmt = baseContainer.querySelector(".base-additional-fee-amount");
    assertEq(feeAmt ? true : false, true, "fee amount input exists");
    feeAmt.value = "5000";
    bubbleEvent(feeAmt, "input");
    assertEq(calculateCalls, 1, "fee input triggers calculateEstimate once via delegated handler");

    ensure([
        {
            mode: "manual",
            widthMm: 1000,
            manualPricing: { pricing_type: "30cm", price_30cm: 90000 },
            additionalFees: [],
        },
    ]);
    calculateCalls = 0;
    const wInput = baseContainer.querySelector(".base-width-input");
    wInput.value = "2000";
    bubbleEvent(wInput, "input");
    assertEq(calculateCalls, 1, "delegated input on width triggers calculateEstimate once");

    calculateCalls = 0;
    wInput.value = "4120+4121+2354";
    bubbleEvent(wInput, "input");
    assertEq(calculateCalls, 1, "composite width input triggers calculateEstimate once");
    const snapComposite = read();
    assertEq(snapComposite[0].widthInput, "4120+4121+2354", "read composite widthInput");
    assertEq(snapComposite[0].widthMm, 10595, "read composite widthMm sum");

    const p30 = baseContainer.querySelector(".base-manual-price30");
    if (p30) {
        calculateCalls = 0;
        p30.value = "150000";
        bubbleEvent(p30, "input");
        assertEq(calculateCalls, 1, "delegated input on manual price30 triggers calculateEstimate once");
        const p1 = baseContainer.querySelector(".base-manual-price1");
        assertEq(p1 ? Number(p1.value) > 0 : false, true, "price1 auto-updated after price30 input");
    }

    process.exit(0);
}

try {
    runAll();
} catch (e) {
    console.error(e);
    process.exit(1);
}
