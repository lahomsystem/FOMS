/**
 * Contract freeze: in-session estimates list view (`renderEstimatesList`) in
 * static/js/wdcalculator/render-estimates-list.js.
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
    "render-estimates-list.js"
);
const helperSrc = fs.readFileSync(helperPath, "utf8");
const templatePath = helperPath;
const templateSrc = helperSrc;

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

function buildStyle() {
    return {
        setProperty(name, value) {
            this[name] = value;
        },
    };
}

function parseFlatChildren(html, parent, ids) {
    const tagRegex = /<([a-zA-Z0-9-]+)([^>]*)>/g;
    let match;
    while ((match = tagRegex.exec(html))) {
        const tagName = match[1];
        const attrs = match[2] || "";
        const idMatch = attrs.match(/\sid="([^"]+)"/);
        const classMatch = attrs.match(/\sclass="([^"]+)"/);
        const dataEstimateIdMatch = attrs.match(/\sdata-estimate-id="([^"]+)"/);
        const el = new El(tagName, {
            id: idMatch ? idMatch[1] : "",
            className: classMatch ? classMatch[1] : "",
            dataset: dataEstimateIdMatch ? { estimateId: dataEstimateIdMatch[1] } : {},
            ids,
        });
        parent.appendChild(el);
    }
}

class El {
    constructor(tag, opts = {}) {
        this.tagName = String(tag).toUpperCase();
        this.id = opts.id || "";
        this.className = opts.className || "";
        this.dataset = opts.dataset ? { ...opts.dataset } : {};
        this.children = [];
        this.parentEl = null;
        this.listeners = {};
        this._innerHTML = opts.innerHTML || "";
        this._textContent = opts.textContent || "";
        this.style = buildStyle();
        this._ids = opts.ids || {};
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
        parseFlatChildren(this._innerHTML, this, this._ids);
    }

    get innerHTML() {
        return this._innerHTML;
    }

    set textContent(value) {
        this._textContent = String(value);
    }

    get textContent() {
        return this._textContent;
    }
}

function buildSandbox(spec = {}) {
    const ids = {};
    const container = new El("div", { id: "estimatesListContainer", ids });
    const saveEstimateBtn = new El("button", { id: "saveEstimateBtn", ids });
    saveEstimateBtn.style.display = spec.initialSaveDisplay || "none";

    const document = {
        getElementById(id) {
            return ids[id] || null;
        },
        querySelector(sel) {
            return container.querySelector(sel);
        },
        querySelectorAll(sel) {
            return container.querySelectorAll(sel);
        },
    };

    const aggregateCalls = [];
    const sandbox = {
        window: null,
        globalThis: null,
        document,
        estimates: JSON.parse(JSON.stringify(spec.estimates || [])),
        calculateTotalEstimates() {
            aggregateCalls.push("calculateTotalEstimates");
        },
        formatNumber(num) {
            return Math.round(Number(num) || 0).toLocaleString("ko-KR");
        },
        escapeHtml(value) {
            return String(value)
                .replace(/&/g, "&amp;")
                .replace(/</g, "&lt;")
                .replace(/>/g, "&gt;")
                .replace(/"/g, "&quot;")
                .replace(/'/g, "&#39;");
        },
        formatNotesText(notes) {
            if (!notes || !notes.trim()) return "";
            return notes
                .split("\n")
                .map((line) => line.trim())
                .join("\n");
        },
        console: {
            log() {},
            warn() {},
            error() {},
        },
        setTimeout(fn) {
            fn();
            return 1;
        },
        clearTimeout() {},
    };
    sandbox.window = sandbox;
    sandbox.globalThis = sandbox;

    vm.createContext(sandbox);
    vm.runInContext(
        [
            helperSrc,
            `
            WdCalculatorRenderEstimatesList.configure({
                getEstimates: function () { return estimates; },
                formatNumber: formatNumber,
                escapeHtml: escapeHtml,
                formatNotesText: formatNotesText,
                onRenderComplete: calculateTotalEstimates,
                documentRef: document,
                setTimeoutImpl: setTimeout,
            });
            renderEstimatesList = WdCalculatorRenderEstimatesList.renderEstimatesList;
            `,
        ].join("\n\n"),
        sandbox,
        { filename: templatePath }
    );

    return {
        sandbox,
        container,
        saveEstimateBtn,
        aggregateCalls,
        ids,
    };
}

function scenarioEmptyStateReturnsWithoutAggregateCall() {
    const env = buildSandbox({ estimates: [] });

    env.sandbox.renderEstimatesList();

    assertIncludes(env.container.innerHTML, "추가된 견적이 없습니다.", "empty state keeps legacy message");
    assertEq(env.aggregateCalls.length, 0, "empty state skips aggregate recalculation");
    assertEq(env.saveEstimateBtn.style.display, "none", "empty state keeps save button hidden");
}

function scenarioSingleEstimateRendersSummaryAndStyles() {
    const env = buildSandbox({
        estimates: [
            {
                id: "a-1",
                productName: "Wardrobe",
                widthMm: 600,
                basePrice: 100000,
                additionalPrice: 20000,
                totalPrice: 120000,
                options: [],
                notes: "",
            },
        ],
    });

    env.sandbox.renderEstimatesList();

    assertIncludes(env.container.innerHTML, 'data-estimate-id="a-1"', "single estimate keeps card data-estimate-id");
    assertIncludes(env.container.innerHTML, "Wardrobe 600mm", "single estimate uses legacy display-name fallback");
    assertIncludes(env.container.innerHTML, "추가 옵션 합계", "single estimate keeps options section title");
    assertIncludes(env.container.innerHTML, 'id="totalEstimatesSummary"', "single estimate renders summary container");
    assertEq(env.ids.totalAllPrice, undefined, "single estimate omits totalAllPrice legacy id");
    assertEq(env.aggregateCalls.length, 1, "single estimate triggers aggregate recalculation once");
    assertEq(env.saveEstimateBtn.style.display, "block", "single estimate shows save button");
    const headerBase = env.container.querySelector(".estimate-header-base");
    assertEq(headerBase.style.color, "#0d6efd", "single estimate applies header base forced style");
    const totalPrice = env.container.querySelector(".estimate-total-price");
    assertEq(totalPrice.style["font-weight"], "800", "single estimate applies total price forced style");
}

function scenarioTwoEstimatesKeepBreakAndEscapedDetails() {
    const env = buildSandbox({
        estimates: [
            {
                id: 10,
                productName: "Closet",
                displayName: 'Closet <A>',
                widthMm: 800,
                basePrice: 150000,
                additionalPrice: 1000,
                totalPrice: 151000,
                options: [{ name: "<Metal>", quantity: 2, price: 500 }],
                notes: " first \n\n<script>alert(1)</script> ",
            },
            {
                id: 11,
                productName: "Cabinet",
                displayName: "Cabinet B",
                widthMm: 500,
                basePrice: 90000,
                additionalPrice: 0,
                totalPrice: 90000,
                options: [],
                notes: "",
            },
        ],
    });

    env.sandbox.renderEstimatesList();

    assertIncludes(env.container.innerHTML, "w-100 d-none d-lg-block", "two estimates keep legacy lg-only line break");
    assertIncludes(env.container.innerHTML, 'id="totalAllPrice"', "two estimates render totalAllPrice in combined summary");
    assertIncludes(env.container.innerHTML, "&lt;Metal&gt; × 2 (1,000원)", "two estimates escape option text and keep amount format");
    assertIncludes(env.container.innerHTML, "&lt;script&gt;alert(1)&lt;/script&gt;", "two estimates escape notes text");
    assertIncludes(env.container.innerHTML, "estimate-display-name", "two estimates keep display-name selector for downstream delegation");
    assertEq(env.aggregateCalls.length, 1, "two estimates trigger aggregate recalculation once");
}

try {
    scenarioEmptyStateReturnsWithoutAggregateCall();
    scenarioSingleEstimateRendersSummaryAndStyles();
    scenarioTwoEstimatesKeepBreakAndEscapedDetails();
    process.stdout.write("wdcalculator_render_list_contract_node_checks: ok\n");
} catch (error) {
    process.stderr.write(`${error.stack || error}\n`);
    process.exitCode = 1;
}
