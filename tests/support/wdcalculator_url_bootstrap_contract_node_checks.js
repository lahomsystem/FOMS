/**
 * Contract freeze: URL/deep-link bootstrap in
 * static/js/wdcalculator/url-bootstrap.js.
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
    "url-bootstrap.js"
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

function extractSnippet(src, startNeedle, endNeedle) {
    const start = src.indexOf(startNeedle);
    if (start === -1) {
        throw new Error(`Start needle not found: ${startNeedle}`);
    }
    const end = src.indexOf(endNeedle, start);
    if (end === -1) {
        throw new Error(`End needle not found: ${endNeedle}`);
    }
    return src.slice(start, end);
}

class El {
    constructor(tag, opts = {}) {
        this.tagName = String(tag).toUpperCase();
        this.id = opts.id || "";
        this.className = opts.className || "";
        this.href = opts.href || "";
        this.innerHTML = opts.innerHTML || "";
        this.children = [];
        this.parentElement = null;
        this._ids = opts.ids || {};
        if (this.id) {
            this._ids[this.id] = this;
        }
    }

    appendChild(child) {
        child.parentElement = this;
        this.children.push(child);
        if (child.id) {
            this._ids[child.id] = child;
        }
        return child;
    }
}

function buildSandbox(spec = {}) {
    const ids = {};
    const saveBtnContainer = new El("div", { id: "saveEstimateBtnContainer", ids });
    const saveEstimateBtn = saveBtnContainer.appendChild(new El("button", { id: "saveEstimateBtn", ids }));

    const alerts = [];
    const fetchCalls = [];
    const loadEstimateCalls = [];
    const loadSidebarCalls = [];
    const warns = [];
    const intervals = [];
    const timeouts = [];
    let timerSeq = 1;

    const document = {
        getElementById(id) {
            return ids[id] || null;
        },
        createElement(tag) {
            return new El(tag, { ids });
        },
    };

    const fetchQueue = (spec.fetchResponses || []).map((item) => ({ ...item }));
    const sandbox = {
        window: {
            location: {
                search: spec.search || "",
            },
        },
        globalThis: null,
        document,
        products: spec.products || [],
        loadEstimateToForm(estimate) {
            loadEstimateCalls.push(estimate);
        },
        loadSidebarEstimates() {
            loadSidebarCalls.push("loadSidebarEstimates");
        },
        fetch(url) {
            fetchCalls.push(url);
            const next = fetchQueue.shift();
            if (!next) {
                throw new Error(`Unexpected fetch: ${url}`);
            }
            if (next.reject) {
                return Promise.reject(next.reject);
            }
            return Promise.resolve({
                ok: next.ok !== false,
                status: next.status || 200,
                statusText: next.statusText || "OK",
                json: () => Promise.resolve(next.body),
            });
        },
        alert(message) {
            alerts.push(String(message));
        },
        console: {
            log() {},
            warn(message) {
                warns.push(String(message));
            },
            error() {},
        },
        URLSearchParams,
        setInterval(fn, delay) {
            const id = timerSeq++;
            intervals.push({ id, fn, delay, cleared: false });
            return id;
        },
        clearInterval(id) {
            const target = intervals.find((item) => item.id === id);
            if (target) {
                target.cleared = true;
            }
        },
        setTimeout(fn, delay) {
            const id = timerSeq++;
            timeouts.push({ id, fn, delay, cleared: false });
            return id;
        },
        clearTimeout(id) {
            const target = timeouts.find((item) => item.id === id);
            if (target) {
                target.cleared = true;
            }
        },
        Promise,
    };
    sandbox.globalThis = sandbox;

    vm.createContext(sandbox);
    vm.runInContext(
        [
            helperSrc,
            `
            window.WdCalculatorUrlBootstrap.configure({
                getProducts: function () { return products; },
                loadEstimateToForm: loadEstimateToForm,
                loadSidebarEstimates: loadSidebarEstimates,
                fetchImpl: fetch,
                alertImpl: alert,
                documentRef: document,
                windowRef: window,
                consoleRef: console,
                setTimeoutImpl: setTimeout,
                setIntervalImpl: setInterval,
                clearIntervalImpl: clearInterval,
            });
            window.WdCalculatorUrlBootstrap.initUrlBootstrap();
            `,
        ].join("\n\n"),
        sandbox,
        { filename: templatePath }
    );

    return {
        sandbox,
        saveBtnContainer,
        alerts,
        fetchCalls,
        loadEstimateCalls,
        loadSidebarCalls,
        warns,
        intervals,
        timeouts,
        getById(id) {
            return ids[id] || null;
        },
    };
}

async function flushPromises(turns = 6) {
    for (let i = 0; i < turns; i += 1) {
        await new Promise((resolve) => setImmediate(resolve));
    }
}

function runTimeout(env, delay) {
    env.timeouts
        .filter((timer) => !timer.cleared && timer.delay === delay)
        .forEach((timer) => {
            timer.cleared = true;
            timer.fn();
        });
}

function runActiveIntervals(env, delay) {
    env.intervals
        .filter((timer) => !timer.cleared && timer.delay === delay)
        .forEach((timer) => {
            timer.fn();
        });
}

async function scenarioOrderIdAddsBackButton() {
    const env = buildSandbox({
        search: "?order_id=321",
    });

    const backBtn = env.getById("backToOrderBtn");
    assertEq(Boolean(backBtn), true, "order_id adds back-to-order button");
    assertEq(backBtn.href, "/edit/321", "order_id preserves legacy edit link");
    assertIncludes(backBtn.innerHTML, "주문으로 돌아가기", "order_id keeps button text");
}

async function scenarioEstimateIdLoadsImmediatelyWhenProductsReady() {
    const env = buildSandbox({
        search: "?estimate_id=77",
        products: [{ id: 1, name: "Wardrobe" }],
        fetchResponses: [
            {
                body: {
                    success: true,
                    estimate: { id: 77, customer_name: "URL Customer" },
                },
            },
        ],
    });

    await flushPromises();
    runTimeout(env, 500);

    assertEq(env.fetchCalls.length, 1, "estimate_id ready path performs one fetch");
    assertEq(env.fetchCalls[0], "/api/wdcalculator/estimate/77", "estimate_id ready path keeps fetch URL");
    assertEq(env.loadEstimateCalls.length, 1, "estimate_id ready path loads estimate into form");
    assertEq(env.loadEstimateCalls[0].id, 77, "estimate_id ready path passes fetched estimate");
    assertEq(env.loadSidebarCalls.length, 1, "estimate_id ready path refreshes sidebar after load");
}

async function scenarioEstimateIdWaitsForProductsThenLoads() {
    const env = buildSandbox({
        search: "?estimate_id=88",
        products: [],
        fetchResponses: [
            {
                body: {
                    success: true,
                    estimate: { id: 88, customer_name: "Deferred Customer" },
                },
            },
        ],
    });

    assertEq(env.fetchCalls.length, 0, "deferred load waits before fetching");
    assertEq(env.intervals.length, 1, "deferred load starts polling interval");
    assertEq(env.intervals[0].delay, 100, "deferred load keeps 100ms poll interval");
    assertEq(env.timeouts.some((timer) => timer.delay === 5000), true, "deferred load keeps 5s timeout guard");

    env.sandbox.products.push({ id: 1, name: "Loaded Later" });
    runActiveIntervals(env, 100);
    await flushPromises();

    assertEq(env.fetchCalls.length, 1, "deferred load fetches after products appear");
    assertEq(env.intervals[0].cleared, true, "deferred load clears interval after products appear");
}

async function scenarioEstimateResponseWithoutProductsRetriesAfter1sThenAlerts() {
    const env = buildSandbox({
        search: "?estimate_id=99",
        products: [{ id: 1, name: "Loaded" }],
        fetchResponses: [
            {
                body: {
                    success: true,
                    estimate: { id: 99, customer_name: "Retry Customer" },
                },
            },
        ],
    });

    env.sandbox.products.length = 0;
    await flushPromises();

    assertEq(env.timeouts.some((timer) => timer.delay === 1000), true, "empty products response keeps 1s retry guard");
    runTimeout(env, 1000);

    assertEq(env.loadEstimateCalls.length, 0, "empty products retry path skips form load when products stay empty");
    assertEq(
        env.alerts[0],
        "제품 목록을 불러올 수 없어 견적을 로드할 수 없습니다. 페이지를 새로고침해주세요.",
        "empty products retry path keeps legacy alert"
    );
}

async function scenarioEstimateFailureShowsAlert() {
    const env = buildSandbox({
        search: "?estimate_id=55",
        products: [{ id: 1, name: "Loaded" }],
        fetchResponses: [
            {
                body: {
                    success: false,
                    message: "권한 없음",
                },
            },
        ],
    });

    await flushPromises();

    assertEq(
        env.alerts[0],
        "견적을 불러오는 중 오류가 발생했습니다: 권한 없음",
        "failed estimate response keeps legacy alert"
    );
}

async function scenarioProductWaitTimeoutFallsBackToFetch() {
    const env = buildSandbox({
        search: "?estimate_id=66",
        products: [],
        fetchResponses: [
            {
                body: {
                    success: false,
                    message: "없음",
                },
            },
        ],
    });

    runTimeout(env, 5000);
    await flushPromises();

    assertEq(env.fetchCalls.length, 1, "timeout fallback still attempts estimate fetch");
    assertIncludes(env.warns[0], "시간 초과", "timeout fallback keeps warning text");
}

(async function run() {
    await scenarioOrderIdAddsBackButton();
    await scenarioEstimateIdLoadsImmediatelyWhenProductsReady();
    await scenarioEstimateIdWaitsForProductsThenLoads();
    await scenarioEstimateResponseWithoutProductsRetriesAfter1sThenAlerts();
    await scenarioEstimateFailureShowsAlert();
    await scenarioProductWaitTimeoutFallsBackToFetch();
    process.stdout.write("wdcalculator_url_bootstrap_contract_node_checks: ok\n");
})().catch((error) => {
    process.stderr.write(`${error.stack || error}\n`);
    process.exitCode = 1;
});
