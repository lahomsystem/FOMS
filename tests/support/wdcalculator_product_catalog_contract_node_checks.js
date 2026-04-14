/**
 * Contract freeze: product catalog legacy UI cluster in static/js/wdcalculator/primary-form.js
 * (product-catalog-ui band: loadProducts, updateProductSelect, showProductInfo, productSelect change handler).
 *
 * Runs the extracted helper in a Node vm with DOM stubs so the host-script extraction preserves:
 * - GET /api/wdcalculator/products payload shape assumptions
 * - products -> base-components sync order
 * - legacy productSelect change side effects
 */
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const repoRoot = path.join(__dirname, "..", "..");
const helperPath = path.join(repoRoot, "static", "js", "wdcalculator", "primary-form.js");
const sharedPath = path.join(repoRoot, "static", "js", "wdcalculator", "shared.js");

const helperSrc = fs.readFileSync(helperPath, "utf8");
const sharedSrc = fs.readFileSync(sharedPath, "utf8");

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
    return JSON.parse(JSON.stringify(value));
}

function escapeHtmlText(text) {
    return String(text)
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#39;");
}

function extractFunctionSource(src, name, label) {
    const sourceLabel = label || helperPath;
    const needle = `function ${name}(`;
    const start = src.indexOf(needle);
    if (start === -1) {
        throw new Error(`Function ${name} not found in ${sourceLabel}`);
    }
    let i = src.indexOf("{", start);
    if (i < 0) {
        throw new Error(`Opening brace not found for ${name} in ${sourceLabel}`);
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

    throw new Error(`Unbalanced braces for ${name} in ${sourceLabel}`);
}

function extractStatementBlock(src, needle, label) {
    const sourceLabel = label || helperPath;
    const start = src.indexOf(needle);
    if (start === -1) {
        throw new Error(`Needle ${needle} not found in ${sourceLabel}`);
    }
    let i = src.indexOf("{", start);
    if (i < 0) {
        throw new Error(`Opening brace not found after ${needle} in ${sourceLabel}`);
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

    throw new Error(`Unbalanced braces for statement block ${needle} in ${sourceLabel}`);
}

function matchSel(el, sel) {
    if (!el || !el.tagName) return false;
    if (sel.startsWith("#")) return el.id === sel.slice(1);
    if (sel.startsWith(".")) {
        const cls = sel.slice(1);
        return el.className.split(/\s+/).filter(Boolean).includes(cls);
    }
    return el.tagName === sel.toUpperCase();
}

function walk(node, cb) {
    if (!node) return;
    cb(node);
    (node.children || []).forEach((child) => walk(child, cb));
}

function createDocumentMock(spec = {}) {
    const ids = {};

    class El {
        constructor(tag, opts = {}) {
            this.tagName = String(tag).toUpperCase();
            this.id = opts.id || "";
            this.className = opts.className || "";
            this.dataset = opts.dataset ? { ...opts.dataset } : {};
            this.attr = opts.attr ? { ...opts.attr } : {};
            this.style = {
                display: opts.display !== undefined ? opts.display : "",
                setProperty() {},
                removeProperty() {},
            };
            this.children = [];
            this.parentEl = null;
            this.listeners = {};
            this._value = opts.value !== undefined ? String(opts.value) : "";
            this._innerHTML = opts.innerHTML || "";
            this._textContent = "";
            this._innerText = "";
            this.textContent = opts.textContent || "";
            if (this.id) ids[this.id] = this;
        }

        get value() {
            return this._value;
        }

        set value(next) {
            this._value = next === undefined || next === null ? "" : String(next);
        }

        get innerHTML() {
            return this._innerHTML || "";
        }

        set innerHTML(next) {
            this._innerHTML = next === undefined || next === null ? "" : String(next);
            if (this.tagName === "SELECT") {
                this.children = [];
                const optionRe = /<option value="([^"]*)">([\s\S]*?)<\/option>/g;
                let m;
                while ((m = optionRe.exec(this._innerHTML)) !== null) {
                    const option = new El("option", { value: m[1] });
                    option.textContent = m[2];
                    this.appendChild(option);
                }
                return;
            }
            if (this._innerHTML === "") {
                this.children = [];
            }
        }

        get textContent() {
            return this._textContent;
        }

        set textContent(next) {
            const value = next === undefined || next === null ? "" : String(next);
            this._textContent = value;
            this._innerText = value;
            this._innerHTML = escapeHtmlText(value);
        }

        get innerText() {
            return this._innerText;
        }

        set innerText(next) {
            this.textContent = next;
        }

        appendChild(child) {
            child.parentEl = this;
            this.children.push(child);
            if (child.id) ids[child.id] = child;
            return child;
        }

        addEventListener(type, fn) {
            if (!this.listeners[type]) this.listeners[type] = [];
            this.listeners[type].push(fn);
        }

        dispatchEvent(event) {
            const evt = event || {};
            evt.type = evt.type || "";
            evt.target = evt.target || this;
            evt.currentTarget = this;
            const handlers = this.listeners[evt.type] || [];
            handlers.forEach((fn) => fn.call(this, evt));
            return true;
        }

        querySelector(sel) {
            let found = null;
            walk(this, (node) => {
                if (found || node === this) return;
                if (matchSel(node, sel)) {
                    found = node;
                }
            });
            return found;
        }

        querySelectorAll(sel) {
            const out = [];
            walk(this, (node) => {
                if (node !== this && matchSel(node, sel)) {
                    out.push(node);
                }
            });
            return out;
        }
    }

    const root = new El("div", { className: "wdcalculator-root" });

    function addToRoot(el) {
        root.appendChild(el);
        return el;
    }

    if (spec.includeBaseComponentsContainer !== false) {
        const baseComponentsContainer = addToRoot(
            new El("div", { id: "baseComponentsContainer" })
        );
        const rowCount = spec.baseRowCount || 0;
        for (let i = 0; i < rowCount; i++) {
            baseComponentsContainer.appendChild(
                new El("div", { className: "base-component-row" })
            );
        }
    }

    if (spec.includeProductSelect) {
        addToRoot(new El("select", { id: "productSelect" }));
    }

    const additionalOptionsContainer = addToRoot(
        new El("div", { id: "additionalOptionsContainer" })
    );
    if (spec.additionalOptionsInnerHTML !== undefined) {
        additionalOptionsContainer.innerHTML = spec.additionalOptionsInnerHTML;
    }

    const productInfo = addToRoot(
        new El("div", {
            id: "productInfo",
            display:
                spec.productInfoDisplay !== undefined
                    ? spec.productInfoDisplay
                    : "none",
        })
    );
    productInfo.appendChild(new El("div", { id: "productInfoContent" }));

    addToRoot(
        new El("div", {
            id: "baseEstimateSection",
            display:
                spec.baseEstimateDisplay !== undefined
                    ? spec.baseEstimateDisplay
                    : "none",
        })
    );

    const document = {
        getElementById(id) {
            return ids[id] || null;
        },
        querySelector(sel) {
            return root.querySelector(sel);
        },
        querySelectorAll(sel) {
            return root.querySelectorAll(sel);
        },
        createElement(tag) {
            return new El(tag);
        },
    };

    return { document, root, ids, El };
}

function syncBindings(sandbox, names) {
    const code = names.map((name) => `${name} = this.${name};`).join("\n");
    vm.runInContext(code, sandbox);
}

function readSelectOptions(selectEl) {
    return (selectEl.children || [])
        .filter((child) => child.tagName === "OPTION")
        .map((child) => ({ value: child.value, text: child.textContent }));
}

function createProduct(id, name, overrides = {}) {
    return {
        id,
        name,
        pricing_type: "30cm",
        additional_options: [],
        coupon_type: "percentage",
        coupon_value: 0,
        price_30cm: 1000,
        price_1cm: 34,
        ...overrides,
    };
}

function buildSandbox(spec = {}) {
    const { document, ids, root, El } = createDocumentMock(spec.dom || {});
    const consoleMessages = [];
    const sandbox = {
        window: null,
        document,
        console: {
            warn(...args) {
                consoleMessages.push({ type: "warn", text: args.join(" ") });
            },
            error(...args) {
                consoleMessages.push({ type: "error", text: args.join(" ") });
            },
            log() {},
            info() {},
        },
        requestWdCalculatorLayoutSync() {},
        requestAnimationFrame(fn) {
            return fn();
        },
        innerWidth: 1280,
        innerHeight: 900,
        fetch:
            spec.fetch ||
            (() =>
                Promise.resolve({
                    json: () => Promise.resolve({ success: true, products: [] }),
                })),
        products: clone(spec.products || []),
        updateBaseProductSelectOptions() {},
        ensureBaseComponentsUI() {},
        calculateEstimate() {},
        Promise,
        Math,
        Number,
        String,
        Array,
        JSON,
        parseInt,
        parseFloat,
        Date,
        RegExp,
        setTimeout,
        clearTimeout,
    };
    sandbox.window = sandbox;

    vm.createContext(sandbox);
    vm.runInContext(
        [
            "var products = this.products;",
            "var calculateEstimate = this.calculateEstimate;",
        ].join("\n"),
        sandbox
    );
    vm.runInContext(sharedSrc, sandbox, { filename: sharedPath });
    sandbox.escapeHtml = escapeHtmlText;
    sandbox.formatNumber = function (num) {
        return Math.round(num).toLocaleString("ko-KR");
    };
    vm.runInContext(
        helperSrc,
        sandbox,
        { filename: helperPath }
    );
    vm.runInContext(
        [
            "WdCalculatorProductCatalogUI.configure({",
            "    getProducts: () => this.products,",
            "    setProducts: (nextProducts) => { this.products = nextProducts; },",
            "    getCalculateEstimate: () => this.calculateEstimate,",
            "    updateBaseProductSelectOptions: () => this.updateBaseProductSelectOptions(),",
            "    ensureBaseComponentsUI: () => this.ensureBaseComponentsUI(),",
            "});",
            "this.loadProducts = WdCalculatorProductCatalogUI.loadProducts;",
            "this.updateProductSelect = WdCalculatorProductCatalogUI.updateProductSelect;",
            "this.showProductInfo = WdCalculatorProductCatalogUI.showProductInfo;",
            "this.bindProductSelect = WdCalculatorProductCatalogUI.bindProductSelect;",
            "this.handleProductSelectChange = WdCalculatorProductCatalogUI.handleProductSelectChange;",
        ].join("\n"),
        sandbox,
        { filename: helperPath }
    );

    return { sandbox, ids, root, El, consoleMessages };
}

async function flushPromises() {
    await new Promise((resolve) => setImmediate(resolve));
    await new Promise((resolve) => setImmediate(resolve));
}

async function scenarioLoadProductsSyncsBaseComponentsWhenNoRows() {
    const fetchedProducts = [
        createProduct(1, "Alpha"),
        createProduct(2, "Beta", { pricing_type: "1m", price_1m: 7777 }),
    ];
    const events = [];
    let fetchedUrl = null;
    const env = buildSandbox({
        products: [createProduct(99, "Old Product")],
        dom: {
            includeBaseComponentsContainer: true,
            includeProductSelect: false,
            baseRowCount: 0,
        },
    });

    env.sandbox.fetch = (url) => {
        fetchedUrl = url;
        return Promise.resolve({
            json: () => Promise.resolve({ success: true, products: fetchedProducts }),
        });
    };

    const actualUpdateProductSelect = env.sandbox.WdCalculatorProductCatalogUI.updateProductSelect;
    env.sandbox.WdCalculatorProductCatalogUI.updateProductSelect = function () {
        events.push({ type: "updateProductSelect" });
        return actualUpdateProductSelect.apply(this, arguments);
    };
    env.sandbox.updateBaseProductSelectOptions = function () {
        events.push({
            type: "updateBaseProductSelectOptions",
            products: clone(env.sandbox.products),
        });
    };
    env.sandbox.ensureBaseComponentsUI = function () {
        events.push({
            type: "ensureBaseComponentsUI",
            products: clone(env.sandbox.products),
        });
    };
    env.sandbox.loadProducts();
    await flushPromises();

    assertEq(fetchedUrl, "/api/wdcalculator/products", "loadProducts fetch url");
    assertDeepEqual(env.sandbox.products, fetchedProducts, "loadProducts stores fetched products");
    assertDeepEqual(
        events.map((event) => event.type),
        ["updateProductSelect", "updateBaseProductSelectOptions", "ensureBaseComponentsUI"],
        "loadProducts sync order without existing rows"
    );
    assertEq(
        events[1].products.length,
        2,
        "base-component option refresh sees fetched products"
    );
    assertEq(
        events[2].products.length,
        2,
        "ensureBaseComponentsUI sees fetched products"
    );
}

async function scenarioLoadProductsSkipsEnsureWhenRowsAlreadyExist() {
    const events = [];
    const env = buildSandbox({
        products: [],
        dom: {
            includeBaseComponentsContainer: true,
            includeProductSelect: false,
            baseRowCount: 1,
        },
    });

    env.sandbox.fetch = () =>
        Promise.resolve({
            json: () =>
                Promise.resolve({ success: true, products: [createProduct(5, "Existing Row Product")] }),
        });

    const actualUpdateProductSelect = env.sandbox.WdCalculatorProductCatalogUI.updateProductSelect;
    env.sandbox.WdCalculatorProductCatalogUI.updateProductSelect = function () {
        events.push({ type: "updateProductSelect" });
        return actualUpdateProductSelect.apply(this, arguments);
    };
    env.sandbox.updateBaseProductSelectOptions = function () {
        events.push({ type: "updateBaseProductSelectOptions" });
    };
    env.sandbox.ensureBaseComponentsUI = function () {
        events.push({ type: "ensureBaseComponentsUI" });
    };
    env.sandbox.loadProducts();
    await flushPromises();

    assertDeepEqual(
        events.map((event) => event.type),
        ["updateProductSelect", "updateBaseProductSelectOptions"],
        "existing base rows skip ensureBaseComponentsUI"
    );
}

async function scenarioLoadProductsIgnoresNonSuccessPayload() {
    const initialProducts = [createProduct(11, "Keep Me")];
    const events = [];
    const env = buildSandbox({
        products: initialProducts,
        dom: {
            includeBaseComponentsContainer: true,
            includeProductSelect: false,
            baseRowCount: 0,
        },
    });

    const actualUpdateProductSelect = env.sandbox.WdCalculatorProductCatalogUI.updateProductSelect;
    env.sandbox.WdCalculatorProductCatalogUI.updateProductSelect = function () {
        events.push({ type: "updateProductSelect" });
        return actualUpdateProductSelect.apply(this, arguments);
    };
    env.sandbox.updateBaseProductSelectOptions = function () {
        events.push({ type: "updateBaseProductSelectOptions" });
    };
    env.sandbox.ensureBaseComponentsUI = function () {
        events.push({ type: "ensureBaseComponentsUI" });
    };
    env.sandbox.fetch = () =>
        Promise.resolve({
            json: () =>
                Promise.resolve({
                    success: false,
                    products: [createProduct(12, "Ignored")],
                }),
        });
    env.sandbox.loadProducts();
    await flushPromises();

    assertDeepEqual(env.sandbox.products, initialProducts, "non-success payload leaves products untouched");
    assertDeepEqual(events, [], "non-success payload does not refresh product or base-component UI");
}

function scenarioUpdateProductSelectBuildsLegacyOptions() {
    const env = buildSandbox({
        products: [
            createProduct(1, "Alpha"),
            createProduct(2, "Beta"),
        ],
        dom: {
            includeBaseComponentsContainer: false,
            includeProductSelect: true,
        },
    });

    env.sandbox.updateProductSelect();

    assertDeepEqual(
        readSelectOptions(env.ids.productSelect),
        [
            { value: "", text: "제품을 선택하세요" },
            { value: "1", text: "Alpha" },
            { value: "2", text: "Beta" },
        ],
        "updateProductSelect builds placeholder plus product options"
    );
}

function scenarioProductSelectChangeShowsInfoAndRecalculates() {
    const selectedProduct = createProduct(7, "Desk <Premium>", {
        pricing_type: "1m",
        price_1m: 3333,
        additional_options: [{ name: "옵션 <A>", price: 1234 }],
    });
    const events = [];
    const env = buildSandbox({
        products: [selectedProduct],
        dom: {
            includeBaseComponentsContainer: false,
            includeProductSelect: true,
            additionalOptionsInnerHTML: "<div>stale option</div>",
            productInfoDisplay: "none",
            baseEstimateDisplay: "block",
        },
    });

    env.sandbox.calculateEstimate = function () {
        events.push({
            type: "calculateEstimate",
            additionalOptionsInnerHTML: env.ids.additionalOptionsContainer.innerHTML,
            productInfoDisplay: env.ids.productInfo.style.display,
            baseEstimateDisplay: env.ids.baseEstimateSection.style.display,
            productInfoHtml: env.ids.productInfoContent.innerHTML,
        });
    };
    env.sandbox.bindProductSelect();

    env.ids.productSelect.value = "7";
    env.ids.productSelect.dispatchEvent({ type: "change" });

    assertDeepEqual(
        events.map((event) => event.type),
        ["calculateEstimate"],
        "valid product change triggers a single recalculation"
    );
    assertEq(
        env.ids.additionalOptionsContainer.innerHTML,
        "",
        "valid product change clears legacy additionalOptionsContainer"
    );
    assertEq(env.ids.productInfo.style.display, "block", "showProductInfo reveals product info");
    assertEq(
        events[0].additionalOptionsInnerHTML,
        "",
        "calculateEstimate sees cleared additionalOptionsContainer"
    );
    assertEq(
        events[0].productInfoDisplay,
        "block",
        "calculateEstimate runs after product info display update"
    );
    assertIncludes(
        events[0].productInfoHtml,
        "Desk &lt;Premium&gt;",
        "product info escapes product name"
    );
    assertIncludes(
        events[0].productInfoHtml,
        "1m 비용: 3,333원",
        "product info renders 1m price"
    );
    assertIncludes(
        events[0].productInfoHtml,
        "옵션 &lt;A&gt;: 1,234원",
        "product info renders escaped additional option names"
    );
}

function scenarioProductSelectChangeClearsLegacyPanelsWhenSelectionRemoved() {
    const selectedProduct = createProduct(9, "Desk");
    const events = [];
    const env = buildSandbox({
        products: [selectedProduct],
        dom: {
            includeBaseComponentsContainer: false,
            includeProductSelect: true,
            additionalOptionsInnerHTML: "<div>stale option</div>",
            productInfoDisplay: "block",
            baseEstimateDisplay: "block",
        },
    });

    env.sandbox.calculateEstimate = function () {
        events.push({
            type: "calculateEstimate",
            productInfoDisplay: env.ids.productInfo.style.display,
            baseEstimateDisplay: env.ids.baseEstimateSection.style.display,
            additionalOptionsInnerHTML: env.ids.additionalOptionsContainer.innerHTML,
        });
    };
    env.sandbox.bindProductSelect();

    env.ids.productSelect.value = "";
    env.ids.productSelect.dispatchEvent({ type: "change" });

    assertDeepEqual(
        events.map((event) => event.type),
        ["calculateEstimate"],
        "empty legacy selection recalculates once"
    );
    assertEq(env.ids.productInfo.style.display, "none", "empty selection hides product info");
    assertEq(
        env.ids.baseEstimateSection.style.display,
        "none",
        "empty selection hides base estimate section before recalc"
    );
    assertEq(
        events[0].productInfoDisplay,
        "none",
        "calculateEstimate sees hidden product info"
    );
    assertEq(
        events[0].baseEstimateDisplay,
        "none",
        "calculateEstimate sees hidden base estimate section"
    );
    assertEq(
        events[0].additionalOptionsInnerHTML,
        "",
        "calculateEstimate sees cleared additional options container"
    );
}

(async () => {
    await scenarioLoadProductsSyncsBaseComponentsWhenNoRows();
    await scenarioLoadProductsSkipsEnsureWhenRowsAlreadyExist();
    await scenarioLoadProductsIgnoresNonSuccessPayload();
    scenarioUpdateProductSelectBuildsLegacyOptions();
    scenarioProductSelectChangeShowsInfoAndRecalculates();
    scenarioProductSelectChangeClearsLegacyPanelsWhenSelectionRemoved();
    process.stdout.write("wdcalculator product catalog contract OK\n");
})().catch((error) => {
    process.stderr.write(String(error && error.stack ? error.stack : error) + "\n");
    process.exit(1);
});
