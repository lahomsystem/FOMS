/**
 * Contract freeze: baseComponentsContainer live interactions in
 * static/js/wdcalculator/primary-form.js (base-components-ui band, W5-B3).
 */
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const repoRoot = path.join(__dirname, "..", "..");
const helperPath = path.join(repoRoot, "static", "js", "wdcalculator", "primary-form.js");
const helperSrc = fs.readFileSync(helperPath, "utf8");
const sharedSrc = fs.readFileSync(
    path.join(repoRoot, "static", "js", "wdcalculator", "shared.js"),
    "utf8"
);
const templatePath = helperPath;
const templateSrc = helperSrc;

function assertEq(actual, expected, label) {
    if (actual !== expected) {
        throw new Error(`${label}: expected ${JSON.stringify(expected)}, got ${JSON.stringify(actual)}`);
    }
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

function extractStatementBlock(src, needle, label) {
    const sourceLabel = label || templatePath;
    const start = src.indexOf(needle);
    if (start === -1) {
        throw new Error(`Needle ${needle} not found in ${sourceLabel}`);
    }
    const block = extractBalancedBlock(src, start, sourceLabel, `statement block ${needle}`);
    const stmtEnd = src.indexOf(");", start + block.length);
    if (stmtEnd === -1) {
        throw new Error(`Closing ); not found for ${needle} in ${sourceLabel}`);
    }
    return src.slice(start, stmtEnd + 2);
}

function matchSel(el, sel) {
    if (!el || !el.tagName) return false;
    if (sel.startsWith("#")) return el.id === sel.slice(1);
    if (sel.startsWith(".")) {
        return el.classList.contains(sel.slice(1));
    }
    return el.tagName === sel.toUpperCase();
}

function walk(node, cb) {
    if (!node) return;
    cb(node);
    (node.children || []).forEach((child) => walk(child, cb));
}

class ClassList {
    constructor(el) {
        this.el = el;
    }

    _getSet() {
        return new Set(String(this.el.className || "").split(/\s+/).filter(Boolean));
    }

    _setFrom(set) {
        this.el.className = Array.from(set).join(" ");
    }

    contains(name) {
        return this._getSet().has(name);
    }

    add(...names) {
        const set = this._getSet();
        names.forEach((name) => set.add(name));
        this._setFrom(set);
    }

    remove(...names) {
        const set = this._getSet();
        names.forEach((name) => set.delete(name));
        this._setFrom(set);
    }
}

function buildStyle() {
    return {
        setProperty(name, value) {
            this[name] = value;
        },
    };
}

class El {
    constructor(tag, opts = {}) {
        this.tagName = String(tag).toUpperCase();
        this.id = opts.id || "";
        this.className = opts.className || "";
        this.classList = new ClassList(this);
        this.dataset = opts.dataset ? { ...opts.dataset } : {};
        this.children = [];
        this.parentEl = null;
        this.listeners = {};
        this.style = buildStyle();
        this.value = opts.value || "";
        this._ids = opts.ids || {};
        this._innerHTML = "";
        if (this.id) {
            this._ids[this.id] = this;
        }
    }

    appendChild(child) {
        child.parentEl = this;
        this.children.push(child);
        if (child.id) {
            this._ids[child.id] = child;
        }
        return child;
    }

    remove() {
        if (this.parentEl) {
            this.parentEl.children = this.parentEl.children.filter((child) => child !== this);
        }
        if (this.id) {
            delete this._ids[this.id];
        }
        this.parentEl = null;
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

    closest(sel) {
        let node = this;
        while (node) {
            if (matchSel(node, sel)) return node;
            node = node.parentEl;
        }
        return null;
    }

    querySelector(sel) {
        let found = null;
        walk(this, (node) => {
            if (found || node === this) return;
            if (matchSel(node, sel)) found = node;
        });
        return found;
    }

    querySelectorAll(sel) {
        const out = [];
        walk(this, (node) => {
            if (node !== this && matchSel(node, sel)) out.push(node);
        });
        return out;
    }

    set innerHTML(value) {
        this._innerHTML = String(value);
        this.children = [];
        if (this.classList.contains("base-additional-fee-item")) {
            this.appendChild(new El("input", { className: "base-additional-fee-name", ids: this._ids }));
            this.appendChild(new El("input", { className: "base-additional-fee-amount", ids: this._ids }));
            this.appendChild(new El("button", { className: "base-remove-fee-btn", ids: this._ids }));
        }
    }

    get innerHTML() {
        return this._innerHTML;
    }

    insertAdjacentHTML(_position, html) {
        if (html === "__BASE_COMPONENT_ROW__" || String(html).includes("base-component-row")) {
            this.appendChild(createBaseComponentRow(this._ids, { mode: "select" }));
        }
    }
}

function createBaseAdditionalFeesList(ids) {
    return new El("div", { className: "base-additional-fees-list", ids });
}

function createBaseComponentRow(ids, opts = {}) {
    const mode = opts.mode || "select";
    const manualPricingType = opts.manualPricingType || "30cm";
    const row = new El("div", {
        className: "base-component-row",
        dataset: { mode },
        ids,
    });

    const selectArea = row.appendChild(new El("div", { className: "base-select-area", ids }));
    selectArea.style.display = mode === "select" ? "" : "none";

    const manualArea = row.appendChild(new El("div", { className: "base-manual-area", ids }));
    manualArea.style.display = mode === "manual" ? "" : "none";

    const widthCol = row.appendChild(new El("div", { className: "base-width-col", ids }));
    widthCol.style.display = mode === "direct" ? "none" : "";

    row.appendChild(new El("select", { className: "base-mode-select", value: mode, ids }));

    row.appendChild(
        new El("button", {
            className: `base-mode-btn ${mode === "select" ? "btn-info" : "btn-outline-info"}`,
            dataset: { mode: "select" },
            ids,
        })
    );
    row.appendChild(
        new El("button", {
            className: `base-mode-btn ${mode === "manual" ? "btn-warning" : "btn-outline-warning"}`,
            dataset: { mode: "manual" },
            ids,
        })
    );
    row.appendChild(
        new El("button", {
            className: `base-mode-btn ${mode === "direct" ? "btn-secondary" : "btn-outline-secondary"}`,
            dataset: { mode: "direct" },
            ids,
        })
    );
    row.appendChild(new El("button", { className: "base-remove-btn", ids }));
    row.appendChild(new El("input", { className: "base-width-input", ids }));
    row.appendChild(
        new El("select", {
            className: "base-manual-pricing-type",
            value: manualPricingType,
            ids,
        })
    );

    const col30 = row.appendChild(new El("div", { className: "base-manual-30cm-col", ids }));
    col30.style.display = manualPricingType === "1m" ? "none" : "";
    const col1 = row.appendChild(new El("div", { className: "base-manual-1cm-col", ids }));
    col1.style.display = manualPricingType === "1m" ? "none" : "";
    const col1m = row.appendChild(new El("div", { className: "base-manual-1m-col", ids }));
    col1m.style.display = manualPricingType === "1m" ? "" : "none";

    row.appendChild(new El("input", { className: "base-manual-price30", value: "3000", ids }));
    row.appendChild(new El("input", { className: "base-manual-price1", value: "100", ids }));
    row.appendChild(new El("input", { className: "base-manual-price1m", value: "0", ids }));
    row.appendChild(new El("button", { className: "base-add-fee-btn", ids }));
    row.appendChild(createBaseAdditionalFeesList(ids));

    return row;
}

function buildSandbox(spec = {}) {
    const ids = {};
    const calculateCalls = [];
    const computeCalls = [];

    const addBaseComponentBtn = new El("button", { id: "addBaseComponentBtn", ids });
    const baseComponentsContainer = new El("div", { id: "baseComponentsContainer", ids });

    const initialRowCount = spec.initialRowCount || 1;
    for (let i = 0; i < initialRowCount; i += 1) {
        baseComponentsContainer.appendChild(createBaseComponentRow(ids, {}));
    }

    const document = {
        getElementById(id) {
            return ids[id] || null;
        },
        createElement(tag) {
            return new El(tag, { ids });
        },
    };

    const sandbox = {
        window: null,
        globalThis: null,
        document,
        calculateEstimate() {
            calculateCalls.push("calculateEstimate");
        },
        computeAutoPrice1cmFrom30cm(price30) {
            computeCalls.push(price30);
            return Math.round((Number(price30) || 0) / 3);
        },
        escapeHtml(value) {
            return String(value);
        },
        console: {
            log() {},
            warn() {},
            error() {},
        },
        Number,
        String,
        Array,
    };
    sandbox.window = sandbox;
    sandbox.globalThis = sandbox;

    vm.createContext(sandbox);
    vm.runInContext(
        [
            sharedSrc,
            helperSrc,
            `
            WdCalculatorBaseComponentsUI.configure({
                getProducts: function () { return []; },
                getCalculateEstimate: function () { return calculateEstimate; },
                documentRef: document,
            });
            WdCalculatorBaseComponentsUI.initBaseComponentsLiveInteractions();
            `,
        ].join("\n\n"),
        sandbox,
        { filename: templatePath }
    );

    return {
        addBaseComponentBtn,
        baseComponentsContainer,
        calculateCalls,
        computeCalls,
    };
}

function scenarioAddBaseComponentAddsRowAndRecalculates() {
    const env = buildSandbox({});
    const before = env.baseComponentsContainer.querySelectorAll(".base-component-row").length;

    env.addBaseComponentBtn.dispatchEvent({ type: "click", target: env.addBaseComponentBtn });

    assertEq(
        env.baseComponentsContainer.querySelectorAll(".base-component-row").length,
        before + 1,
        "add base component appends one row"
    );
    assertEq(env.calculateCalls.length, 1, "add base component recalculates once");
}

function scenarioAddAndRemoveFeeButtonsRecalculate() {
    const env = buildSandbox({});
    const row = env.baseComponentsContainer.querySelector(".base-component-row");
    const feesList = row.querySelector(".base-additional-fees-list");
    const addFeeBtn = row.querySelector(".base-add-fee-btn");

    env.baseComponentsContainer.dispatchEvent({ type: "click", target: addFeeBtn });
    assertEq(feesList.querySelectorAll(".base-additional-fee-item").length, 1, "add fee button appends fee item");
    assertEq(env.calculateCalls.length, 1, "add fee recalculates once");

    const removeFeeBtn = feesList.querySelector(".base-remove-fee-btn");
    env.baseComponentsContainer.dispatchEvent({ type: "click", target: removeFeeBtn });
    assertEq(feesList.querySelectorAll(".base-additional-fee-item").length, 0, "remove fee button removes fee item");
    assertEq(env.calculateCalls.length, 2, "remove fee recalculates once");
}

function scenarioModeToggleUpdatesAreasAndClasses() {
    const env = buildSandbox({});
    const row = env.baseComponentsContainer.querySelector(".base-component-row");
    const manualBtn = row.querySelectorAll(".base-mode-btn").find((btn) => btn.dataset.mode === "manual");

    env.baseComponentsContainer.dispatchEvent({ type: "click", target: manualBtn });

    assertEq(row.dataset.mode, "manual", "mode toggle updates row dataset");
    assertEq(row.querySelector(".base-select-area").style.display, "none", "mode toggle hides select area");
    assertEq(row.querySelector(".base-manual-area").style.display, "", "mode toggle shows manual area");
    assertEq(row.querySelector(".base-mode-select").value, "manual", "mode toggle syncs base-mode-select");
    assertEq(manualBtn.classList.contains("btn-warning"), true, "mode toggle promotes manual button style");
    assertEq(env.calculateCalls.length, 1, "mode toggle recalculates once");
}

function scenarioModeSelectChangeUpdatesAreas() {
    const env = buildSandbox({});
    const row = env.baseComponentsContainer.querySelector(".base-component-row");
    const modeSelect = row.querySelector(".base-mode-select");
    const manualBtn = row.querySelectorAll(".base-mode-btn").find((btn) => btn.dataset.mode === "manual");

    modeSelect.value = "manual";
    env.baseComponentsContainer.dispatchEvent({ type: "change", target: modeSelect });

    assertEq(row.dataset.mode, "manual", "mode select change updates row dataset");
    assertEq(row.querySelector(".base-select-area").style.display, "none", "mode select hides select area");
    assertEq(row.querySelector(".base-manual-area").style.display, "", "mode select shows manual area");
    assertEq(manualBtn.classList.contains("btn-warning"), true, "mode select promotes manual hook button style");
    assertEq(env.calculateCalls.length, 1, "mode select change recalculates once");
}

function scenarioRemoveButtonKeepsMinimumOneRow() {
    const envSingle = buildSandbox({});
    const onlyRemoveBtn = envSingle.baseComponentsContainer.querySelector(".base-remove-btn");
    envSingle.baseComponentsContainer.dispatchEvent({ type: "click", target: onlyRemoveBtn });
    assertEq(
        envSingle.baseComponentsContainer.querySelectorAll(".base-component-row").length,
        1,
        "remove button keeps minimum one row"
    );
    assertEq(envSingle.calculateCalls.length, 0, "minimum-row guard skips recalculation");

    const envMulti = buildSandbox({ initialRowCount: 2 });
    const removeBtn = envMulti.baseComponentsContainer.querySelector(".base-remove-btn");
    envMulti.baseComponentsContainer.dispatchEvent({ type: "click", target: removeBtn });
    assertEq(
        envMulti.baseComponentsContainer.querySelectorAll(".base-component-row").length,
        1,
        "remove button deletes row when more than one exists"
    );
    assertEq(envMulti.calculateCalls.length, 1, "row removal recalculates once");
}

function scenarioManualPrice30InputAutoSyncsPrice1() {
    const env = buildSandbox({});
    const row = env.baseComponentsContainer.querySelector(".base-component-row");
    const price30 = row.querySelector(".base-manual-price30");
    const price1 = row.querySelector(".base-manual-price1");
    price30.value = "3300";

    env.baseComponentsContainer.dispatchEvent({ type: "input", target: price30 });

    assertEq(env.computeCalls.length, 1, "manual price30 input calls auto-price helper once");
    assertEq(env.computeCalls[0], 3300, "manual price30 input passes numeric value to helper");
    assertEq(price1.value, "1,100", "manual price30 input auto-syncs 1cm price (T5 콤마 표시)");
    assertEq(env.calculateCalls.length, 1, "manual price30 input recalculates once");
}

function scenarioPricingTypeChangeTogglesColumnsAndResyncsAutoPrice() {
    const env = buildSandbox({});
    const row = env.baseComponentsContainer.querySelector(".base-component-row");
    const pricingType = row.querySelector(".base-manual-pricing-type");
    const col30 = row.querySelector(".base-manual-30cm-col");
    const col1 = row.querySelector(".base-manual-1cm-col");
    const col1m = row.querySelector(".base-manual-1m-col");
    const price30 = row.querySelector(".base-manual-price30");
    const price1 = row.querySelector(".base-manual-price1");

    pricingType.value = "1m";
    env.baseComponentsContainer.dispatchEvent({ type: "change", target: pricingType });
    assertEq(col30.style.display, "none", "pricing type 1m hides 30cm column");
    assertEq(col1.style.display, "none", "pricing type 1m hides 1cm column");
    assertEq(col1m.style.display, "", "pricing type 1m shows 1m column");
    assertEq(env.calculateCalls.length, 1, "pricing type 1m recalculates once");

    pricingType.value = "30cm";
    price30.value = "3600";
    env.baseComponentsContainer.dispatchEvent({ type: "change", target: pricingType });
    assertEq(col30.style.display, "", "pricing type 30cm restores 30cm column");
    assertEq(col1.style.display, "", "pricing type 30cm restores 1cm column");
    assertEq(col1m.style.display, "none", "pricing type 30cm hides 1m column");
    assertEq(price1.value, "1,200", "pricing type 30cm resyncs 1cm price from 30cm input (T5 콤마 표시)");
    assertEq(env.calculateCalls.length, 2, "pricing type 30cm recalculates once");
}

try {
    scenarioAddBaseComponentAddsRowAndRecalculates();
    scenarioAddAndRemoveFeeButtonsRecalculate();
    scenarioModeToggleUpdatesAreasAndClasses();
    scenarioModeSelectChangeUpdatesAreas();
    scenarioRemoveButtonKeepsMinimumOneRow();
    scenarioManualPrice30InputAutoSyncsPrice1();
    scenarioPricingTypeChangeTogglesColumnsAndResyncsAutoPrice();
    process.stdout.write("wdcalculator_base_live_events_contract_node_checks: ok\n");
} catch (error) {
    process.stderr.write(`${error.stack || error}\n`);
    process.exitCode = 1;
}
