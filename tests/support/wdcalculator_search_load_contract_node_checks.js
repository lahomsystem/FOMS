/**
 * Contract freeze: search results + load-to-form bridge in
 * static/js/wdcalculator/search-results-load.js.
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
const templateSrc = helperSrc;

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

function extractStatementBlockAfterAnchor(src, anchor, needle, label) {
    const sourceLabel = label || templatePath;
    const anchorIdx = src.indexOf(anchor);
    if (anchorIdx === -1) {
        throw new Error(`Anchor ${anchor} not found in ${sourceLabel}`);
    }
    const start = src.indexOf(needle, anchorIdx);
    if (start === -1) {
        throw new Error(`Needle ${needle} not found after ${anchor} in ${sourceLabel}`);
    }

    if (needle.startsWith("const ")) {
        const ifStart = src.indexOf("if (", start);
        if (ifStart === -1) {
            throw new Error(`if block not found for ${needle} in ${sourceLabel}`);
        }
        const ifBlock = extractBalancedBlock(src, ifStart, sourceLabel, `if block for ${needle}`);
        return src.slice(start, ifStart + ifBlock.length);
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

function parseSearchResultsHtml(html, parent) {
    const buttonRegex = /<button class="([^"]*?(?:load-estimate-btn|match-order-btn)[^"]*)"([^>]*)>/g;
    let match;
    while ((match = buttonRegex.exec(html))) {
        const attrs = match[2] || "";
        const button = new El("button", { className: match[1] });
        const estimateIdMatch = attrs.match(/data-estimate-id="([^"]+)"/);
        if (estimateIdMatch) {
            button.dataset.estimateId = estimateIdMatch[1];
        }
        const customerNameMatch = attrs.match(/data-customer-name="([^"]+)"/);
        if (customerNameMatch) {
            button.dataset.customerName = customerNameMatch[1];
        }
        parent.appendChild(button);
    }
}

const ids = {};

class El {
    constructor(tag, opts = {}) {
        this.tagName = String(tag).toUpperCase();
        this.id = opts.id || "";
        this.className = opts.className || "";
        this.dataset = opts.dataset ? { ...opts.dataset } : {};
        this.children = [];
        this.parentEl = null;
        this.listeners = {};
        this.style = {};
        this._innerHTML = opts.innerHTML || "";
        this._textContent = opts.textContent || "";
        this.value = opts.value || "";
        if (this.id) ids[this.id] = this;
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
        if (this._innerHTML) {
            parseSearchResultsHtml(this._innerHTML, this);
        }
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
    Object.keys(ids).forEach((key) => delete ids[key]);
    const body = new El("body", { id: "body" });
    const documentListeners = {};
    const alerts = [];
    const fetchCalls = [];
    const loadCalls = [];

    const searchEstimateBtn = body.appendChild(new El("button", { id: "searchEstimateBtn" }));
    const searchCustomerName = body.appendChild(
        new El("input", { id: "searchCustomerName", value: spec.customerName || "" })
    );
    const searchResults = body.appendChild(new El("div", { id: "searchResults" }));
    searchResults.style.display = "none";
    const searchResultsList = body.appendChild(new El("div", { id: "searchResultsList" }));

    const document = {
        body,
        getElementById(id) {
            return ids[id] || null;
        },
        addEventListener(type, fn) {
            if (!documentListeners[type]) documentListeners[type] = [];
            documentListeners[type].push(fn);
        },
        dispatchEvent(event) {
            const evt = event || {};
            evt.type = evt.type || "";
            evt.target = evt.target || body;
            evt.currentTarget = document;
            (documentListeners[evt.type] || []).forEach((fn) => fn.call(document, evt));
            return true;
        },
        querySelector(sel) {
            return body.querySelector(sel);
        },
        querySelectorAll(sel) {
            return body.querySelectorAll(sel);
        },
    };

    const fetchState = {
        searchEstimatesResponses: (spec.searchEstimatesResponses || []).map(clone),
    };

    const fetch = (url) => {
        fetchCalls.push({ url });
        if (String(url).startsWith("/api/wdcalculator/search-estimates")) {
            const payload =
                fetchState.searchEstimatesResponses.length > 0
                    ? fetchState.searchEstimatesResponses.shift()
                    : { success: true, estimates: [] };
            return Promise.resolve({
                ok: true,
                status: 200,
                statusText: "OK",
                json: () => Promise.resolve(clone(payload)),
            });
        }
        throw new Error(`Unexpected fetch: ${url}`);
    };

    const sandbox = {
        window: null,
        globalThis: null,
        document,
        fetch,
        alert(message) {
            alerts.push(String(message));
        },
        loadEstimateToForm(estimate) {
            loadCalls.push(clone(estimate));
        },
        formatNumber(num) {
            return Math.round(Number(num) || 0).toLocaleString("ko-KR");
        },
        console: {
            log() {},
            warn() {},
            error() {},
        },
        Promise,
        JSON,
        Math,
        Number,
        String,
        Array,
        parseInt,
        parseFloat,
        encodeURIComponent,
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
            WdCalculatorSearchResultsLoad.configure({
                loadEstimateToForm: loadEstimateToForm,
                formatNumber: formatNumber,
                fetchImpl: fetch,
                alertImpl: alert,
                documentRef: document,
            });
            WdCalculatorSearchResultsLoad.initSearchResultsLoadBridge();
            displaySearchResults = WdCalculatorSearchResultsLoad.displaySearchResults;
            `,
        ].join("\n\n"),
        sandbox,
        { filename: templatePath }
    );

    return {
        sandbox,
        body,
        document,
        alerts,
        fetchCalls,
        loadCalls,
        searchEstimateBtn,
        searchCustomerName,
        searchResults,
        searchResultsList,
    };
}

async function flushPromises(turns = 6) {
    for (let i = 0; i < turns; i++) {
        await new Promise((resolve) => setImmediate(resolve));
    }
}

async function scenarioBlankCustomerAlertsBeforeSearch() {
    const env = buildSandbox({ customerName: "" });

    env.searchEstimateBtn.dispatchEvent({ type: "click", target: env.searchEstimateBtn });
    await flushPromises();

    assertEq(env.fetchCalls.length, 0, "blank customer blocks search fetch");
    assertDeepEqual(env.alerts, ["고객명을 입력해주세요."], "blank customer keeps legacy alert message");
}

async function scenarioSearchSuccessRendersResultsMarkup() {
    const env = buildSandbox({
        customerName: "WD Search",
        searchEstimatesResponses: [
            {
                success: true,
                estimates: [
                    {
                        id: 71,
                        customer_name: "WD Search",
                        created_at: "2026-04-12",
                        estimate_data: {
                            basePrice: 10000,
                            additionalPrice: 5000,
                            totalPrice: 15000,
                        },
                    },
                ],
            },
        ],
    });

    env.searchEstimateBtn.dispatchEvent({ type: "click", target: env.searchEstimateBtn });
    await flushPromises();

    assertEq(env.fetchCalls.length, 1, "search success performs one fetch");
    assertEq(
        env.fetchCalls[0].url,
        `/api/wdcalculator/search-estimates?customer_name=${encodeURIComponent("WD Search")}`,
        "search success keeps search-estimates URL contract"
    );
    assertEq(env.searchResults.style.display, "block", "search success shows result container");
    assertIncludes(env.searchResultsList.innerHTML, "load-estimate-btn", "search success renders load button markup");
    assertIncludes(env.searchResultsList.innerHTML, "match-order-btn", "search success renders match button markup");
    assertIncludes(env.searchResultsList.innerHTML, 'data-customer-name="WD Search"', "search success keeps customer-name dataset for order-match bridge");
    const loadButtons = env.searchResultsList.querySelectorAll(".load-estimate-btn");
    const matchButtons = env.searchResultsList.querySelectorAll(".match-order-btn");
    assertEq(loadButtons.length, 1, "search success creates one load button");
    assertEq(loadButtons[0].dataset.estimateId, "71", "search success preserves estimate id on load button");
    assertEq(matchButtons[0].dataset.customerName, "WD Search", "search success preserves customer name on match button");
}

async function scenarioSearchEmptyResultsShowsLegacyMessage() {
    const env = buildSandbox({
        customerName: "No Results",
        searchEstimatesResponses: [
            {
                success: true,
                estimates: [],
            },
        ],
    });

    env.searchEstimateBtn.dispatchEvent({ type: "click", target: env.searchEstimateBtn });
    await flushPromises();

    assertEq(env.fetchCalls.length, 1, "empty search still performs fetch");
    assertIncludes(env.searchResultsList.innerHTML, "검색 결과가 없습니다.", "empty search keeps legacy empty-result message");
    assertEq(env.searchResults.style.display, "block", "empty search still shows result container");
}

async function scenarioLoadButtonReFetchesAndCallsLoadBridge() {
    const estimate = {
        id: 88,
        customer_name: "Reload Customer",
        created_at: "2026-04-13",
        estimate_data: {
            basePrice: 20000,
            additionalPrice: 4000,
            totalPrice: 24000,
        },
    };
    const env = buildSandbox({
        customerName: "Reload Customer",
        searchEstimatesResponses: [
            {
                success: true,
                estimates: [estimate],
            },
        ],
    });

    env.sandbox.displaySearchResults([estimate]);
    const loadButton = env.searchResultsList.querySelector(".load-estimate-btn");
    env.document.dispatchEvent({ type: "click", target: loadButton });
    await flushPromises();

    assertEq(env.fetchCalls.length, 1, "load button performs one re-fetch");
    assertEq(
        env.fetchCalls[0].url,
        `/api/wdcalculator/search-estimates?customer_name=${encodeURIComponent("Reload Customer")}`,
        "load button keeps re-fetch URL contract"
    );
    assertEq(env.loadCalls.length, 1, "load button calls loadEstimateToForm bridge once");
    assertDeepEqual(env.loadCalls[0], estimate, "load button passes matched estimate object to bridge");
}

async function scenarioLoadButtonAlertsWhenEstimateMissing() {
    const env = buildSandbox({
        customerName: "Missing Estimate",
        searchEstimatesResponses: [
            {
                success: true,
                estimates: [],
            },
        ],
    });

    env.sandbox.displaySearchResults([
        {
            id: 99,
            customer_name: "Missing Estimate",
            created_at: "2026-04-13",
            estimate_data: {
                basePrice: 1,
                additionalPrice: 2,
                totalPrice: 3,
            },
        },
    ]);
    const loadButton = env.searchResultsList.querySelector(".load-estimate-btn");
    env.document.dispatchEvent({ type: "click", target: loadButton });
    await flushPromises();

    assertEq(env.loadCalls.length, 0, "missing estimate path does not call load bridge");
    assertDeepEqual(env.alerts, ["견적을 찾을 수 없습니다."], "missing estimate path keeps legacy alert");
}

(async function run() {
    await scenarioBlankCustomerAlertsBeforeSearch();
    await scenarioSearchSuccessRendersResultsMarkup();
    await scenarioSearchEmptyResultsShowsLegacyMessage();
    await scenarioLoadButtonReFetchesAndCallsLoadBridge();
    await scenarioLoadButtonAlertsWhenEstimateMissing();
    process.stdout.write("wdcalculator_search_load_contract_node_checks: ok\n");
})().catch((error) => {
    process.stderr.write(`${error.stack || error}\n`);
    process.exitCode = 1;
});
