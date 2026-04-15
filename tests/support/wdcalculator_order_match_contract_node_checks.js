/**
 * Contract freeze: order-match legacy UI cluster in static/js/wdcalculator/order-match-ui.js
 * (`.match-order-btn` delegated click, `showOrderSelectionModal`, `matchEstimateToOrder`).
 *
 * Runs the extracted helper in a Node vm with DOM stubs so structure-only extraction preserves:
 * - `/api/wdcalculator/search-orders` request shape and direct-match branch
 * - `#orderSelectionModal` creation + `.select-order-btn` modal selection flow
 * - `/api/wdcalculator/match-order` POST payload and success alert behavior
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

function buildSandbox(spec = {}) {
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
            if (this.id) ids[this.id] = this;
        }

        appendChild(child) {
            child.parentEl = this;
            this.children.push(child);
            if (child.id) ids[child.id] = child;
            return child;
        }

        remove() {
            if (this.parentEl) {
                this.parentEl.children = this.parentEl.children.filter((child) => child !== this);
            }
            if (this.id) {
                delete ids[this.id];
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

        get innerHTML() {
            return this._innerHTML;
        }

        set innerHTML(next) {
            this._innerHTML = next === undefined || next === null ? "" : String(next);
        }

        get textContent() {
            return this._textContent;
        }

        set textContent(next) {
            this._textContent = next === undefined || next === null ? "" : String(next);
        }

        insertAdjacentHTML(position, html) {
            this._innerHTML += html;
            parseInsertedHtml(html, this);
        }
    }

    const body = new El("body");
    const fetchCalls = [];
    const alerts = [];
    const modalInstances = [];
    const searchOrdersResponses = (spec.searchOrdersResponses || []).map(clone);
    const matchOrderResponses = (spec.matchOrderResponses || []).map(clone);

    function parseInsertedHtml(html, parent) {
        if (!html.includes('id="orderSelectionModal"')) {
            return;
        }
        const modalEl = new El("div", { id: "orderSelectionModal", className: "modal fade" });
        parent.appendChild(modalEl);
        const buttonRe =
            /class="list-group-item list-group-item-action select-order-btn"[\s\S]*?data-estimate-id="([^"]+)" data-order-id="([^"]+)"/g;
        let match;
        while ((match = buttonRe.exec(html)) !== null) {
            modalEl.appendChild(
                new El("button", {
                    className: "list-group-item list-group-item-action select-order-btn",
                    dataset: {
                        estimateId: String(match[1]),
                        orderId: String(match[2]),
                    },
                })
            );
        }
    }

    const document = {
        _listeners: {},
        body,
        addEventListener(type, fn) {
            if (!this._listeners[type]) this._listeners[type] = [];
            this._listeners[type].push(fn);
        },
        dispatchEvent(event) {
            const evt = event || {};
            evt.type = evt.type || "";
            const handlers = this._listeners[evt.type] || [];
            handlers.forEach((fn) => fn.call(this, evt));
            return true;
        },
        getElementById(id) {
            return ids[id] || null;
        },
        querySelector(sel) {
            return body.querySelector(sel);
        },
        querySelectorAll(sel) {
            return body.querySelectorAll(sel);
        },
        createElement(tag) {
            return new El(tag);
        },
    };

    const bootstrap = {
        Modal: function Modal(el) {
            this.el = el;
            this.showCount = 0;
            this.hideCount = 0;
            modalInstances.push(this);
        },
    };
    bootstrap.Modal.prototype.show = function show() {
        this.showCount += 1;
    };
    bootstrap.Modal.prototype.hide = function hide() {
        this.hideCount += 1;
    };

    const fetch = (url, options = {}) => {
        fetchCalls.push({
            url,
            options: {
                method: options.method || "GET",
                headers: options.headers ? { ...options.headers } : {},
                body: options.body !== undefined ? options.body : null,
            },
        });
        if (String(url).startsWith("/api/wdcalculator/search-orders")) {
            const payload = searchOrdersResponses.shift();
            if (!payload) {
                throw new Error(`No queued search-orders response for ${url}`);
            }
            return Promise.resolve({
                ok: true,
                status: 200,
                statusText: "OK",
                json: () => Promise.resolve(clone(payload)),
            });
        }
        if (url === "/api/wdcalculator/match-order") {
            const payload = matchOrderResponses.shift();
            if (!payload) {
                throw new Error("No queued match-order response");
            }
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
        document,
        bootstrap,
        fetch,
        alert(message) {
            alerts.push(String(message));
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

    const manualButton = new El("button", {
        className: "match-order-btn",
        dataset: {
            estimateId: String(spec.initialEstimateId || 7),
            customerName: spec.customerName || "홍길동",
        },
    });
    body.appendChild(manualButton);

    vm.createContext(sandbox);
    vm.runInContext(helperSrc, sandbox, { filename: helperPath });
    vm.runInContext(
        [
            "this.showOrderSelectionModal = WdCalculatorOrderMatchUI.showOrderSelectionModal;",
            "this.matchEstimateToOrder = WdCalculatorOrderMatchUI.matchEstimateToOrder;",
            "this.handleMatchOrderButtonClick = WdCalculatorOrderMatchUI.handleMatchOrderButtonClick;",
            "WdCalculatorOrderMatchUI.bindOrderMatchButtons();",
        ].join("\n"),
        sandbox,
        { filename: helperPath }
    );

    return { sandbox, document, body, alerts, fetchCalls, modalInstances, manualButton };
}

async function flushPromises(turns = 6) {
    for (let i = 0; i < turns; i++) {
        await new Promise((resolve) => setImmediate(resolve));
    }
}

async function scenarioSingleOrderDirectlyMatches() {
    const env = buildSandbox({
        customerName: "홍길동",
        initialEstimateId: 7,
        searchOrdersResponses: [
            {
                success: true,
                orders: [
                    {
                        id: 44,
                        customer_name: "홍길동",
                        phone: "010-1111-2222",
                        product: "Wardrobe",
                        status: "RECEIVED",
                    },
                ],
                count: 1,
            },
        ],
        matchOrderResponses: [
            {
                success: true,
                message: "견적과 주문이 매칭되었습니다.",
                match_id: 901,
            },
        ],
    });

    env.document.dispatchEvent({ type: "click", target: env.manualButton });
    await flushPromises();

    assertEq(env.fetchCalls.length, 2, "single-order path performs search then match");
    assertEq(
        env.fetchCalls[0].url,
        `/api/wdcalculator/search-orders?customer_name=${encodeURIComponent("홍길동")}`,
        "single-order path keeps search-orders URL contract"
    );
    assertEq(env.fetchCalls[1].url, "/api/wdcalculator/match-order", "single-order path keeps match-order URL contract");
    assertEq(env.fetchCalls[1].options.method, "POST", "match-order request uses POST");
    assertDeepEqual(
        JSON.parse(env.fetchCalls[1].options.body),
        { estimate_id: 7, order_id: 44 },
        "single-order path posts estimate/order ids"
    );
    assertEq(env.document.getElementById("orderSelectionModal"), null, "single-order path skips modal creation");
    assertDeepEqual(env.alerts, ["견적과 주문이 매칭되었습니다."], "single-order path alerts backend success message");
}

async function scenarioMultipleOrdersRequireSelectionModal() {
    const env = buildSandbox({
        customerName: "멀티 고객",
        initialEstimateId: 8,
        searchOrdersResponses: [
            {
                success: true,
                orders: [
                    {
                        id: 51,
                        customer_name: "멀티 고객",
                        phone: "010-1000-1000",
                        product: "Wardrobe",
                        status: "RECEIVED",
                    },
                    {
                        id: 52,
                        customer_name: "멀티 고객",
                        phone: "010-2000-2000",
                        product: "Kitchen",
                        status: "DRAWING",
                    },
                ],
                count: 2,
            },
        ],
        matchOrderResponses: [
            {
                success: true,
                message: "견적과 주문이 매칭되었습니다.",
                match_id: 902,
            },
        ],
    });

    env.document.dispatchEvent({ type: "click", target: env.manualButton });
    await flushPromises();

    assertEq(env.fetchCalls.length, 1, "multi-order path only searches before user selection");
    assertEq(env.modalInstances.length, 1, "multi-order path creates one bootstrap modal");
    assertEq(env.modalInstances[0].showCount, 1, "multi-order path shows the modal");
    const modal = env.document.getElementById("orderSelectionModal");
    assertEq(Boolean(modal), true, "multi-order path inserts orderSelectionModal");
    const selectButtons = env.document.querySelectorAll(".select-order-btn");
    assertEq(selectButtons.length, 2, "multi-order path renders select-order buttons for each order");
    assertDeepEqual(
        selectButtons.map((button) => button.dataset.orderId),
        ["51", "52"],
        "multi-order modal preserves order ids on select buttons"
    );

    selectButtons[1].dispatchEvent({ type: "click", target: selectButtons[1] });
    await flushPromises();

    assertEq(env.fetchCalls.length, 2, "selecting an order triggers match-order request");
    assertDeepEqual(
        JSON.parse(env.fetchCalls[1].options.body),
        { estimate_id: 8, order_id: 52 },
        "modal selection posts chosen order id"
    );
    assertEq(env.modalInstances[0].hideCount, 1, "modal selection hides the modal after click");
}

async function scenarioNoOrdersAlertsAndSkipsMatch() {
    const env = buildSandbox({
        customerName: "없는 고객",
        initialEstimateId: 9,
        searchOrdersResponses: [
            {
                success: true,
                orders: [],
                count: 0,
            },
        ],
        matchOrderResponses: [],
    });

    env.document.dispatchEvent({ type: "click", target: env.manualButton });
    await flushPromises();

    assertEq(env.fetchCalls.length, 1, "no-order path only calls search-orders");
    assertEq(env.fetchCalls[0].url, `/api/wdcalculator/search-orders?customer_name=${encodeURIComponent("없는 고객")}`, "no-order path keeps search-orders URL contract");
    assertDeepEqual(env.alerts, ["해당 고객명의 주문이 없습니다."], "no-order path alerts legacy empty-result message");
}

async function scenarioSearchOrdersFailureAlertsMessage() {
    const env = buildSandbox({
        customerName: "실패 고객",
        initialEstimateId: 10,
        searchOrdersResponses: [
            {
                success: false,
                message: "주문 검색 실패",
                orders: [],
                count: 0,
            },
        ],
        matchOrderResponses: [],
    });

    env.document.dispatchEvent({ type: "click", target: env.manualButton });
    await flushPromises();

    assertEq(env.fetchCalls.length, 1, "search failure path only calls search-orders");
    assertDeepEqual(env.alerts, ["주문 검색 실패"], "search failure path alerts backend message");
}

async function scenarioMatchOrderFailureAlertsMessage() {
    const env = buildSandbox({
        customerName: "매칭 실패 고객",
        initialEstimateId: 11,
        searchOrdersResponses: [],
        matchOrderResponses: [
            {
                success: false,
                message: "이미 매칭된 주문입니다.",
            },
        ],
    });

    env.sandbox.matchEstimateToOrder(11, 77);
    await flushPromises();

    assertEq(env.fetchCalls.length, 1, "match failure path only calls match-order");
    assertDeepEqual(
        JSON.parse(env.fetchCalls[0].options.body),
        { estimate_id: 11, order_id: 77 },
        "match failure path keeps POST payload shape"
    );
    assertDeepEqual(env.alerts, ["이미 매칭된 주문입니다."], "match failure path alerts backend message");
}

(async function run() {
    await scenarioSingleOrderDirectlyMatches();
    await scenarioMultipleOrdersRequireSelectionModal();
    await scenarioNoOrdersAlertsAndSkipsMatch();
    await scenarioSearchOrdersFailureAlertsMessage();
    await scenarioMatchOrderFailureAlertsMessage();
    process.stdout.write("wdcalculator_order_match_contract_node_checks: ok\n");
})().catch((error) => {
    process.stderr.write(`${error.stack || error}\n`);
    process.exitCode = 1;
});
