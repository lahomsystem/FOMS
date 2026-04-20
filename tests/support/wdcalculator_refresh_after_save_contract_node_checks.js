/**
 * Contract freeze: post-save refresh/highlight helper in
 * static/js/wdcalculator/refresh-after-save.js.
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

function assertEq(actual, expected, label) {
    if (actual !== expected) {
        throw new Error(`${label}: expected ${JSON.stringify(expected)}, got ${JSON.stringify(actual)}`);
    }
}

function assertTruthy(value, label) {
    if (!value) {
        throw new Error(`${label}: expected truthy value, got ${JSON.stringify(value)}`);
    }
}

function walk(node, cb) {
    if (!node) {
        return;
    }
    cb(node);
    (node.children || []).forEach((child) => walk(child, cb));
}

function matchSel(node, selector) {
    if (!node) {
        return false;
    }
    if (selector.startsWith("#")) {
        return node.id === selector.slice(1);
    }
    if (selector.startsWith(".")) {
        const compoundMatch = selector.match(/^\.([^\[]+)\[data-estimate-id="([^"]+)"\]$/);
        if (compoundMatch) {
            const className = compoundMatch[1];
            const estimateId = compoundMatch[2];
            return (
                node.className.split(/\s+/).filter(Boolean).includes(className) &&
                String((node.dataset || {}).estimateId || "") === estimateId
            );
        }
        const className = selector.slice(1);
        return node.className.split(/\s+/).filter(Boolean).includes(className);
    }
    return node.tagName === String(selector).toUpperCase();
}

class El {
    constructor(tag, opts = {}) {
        this.tagName = String(tag).toUpperCase();
        this.id = opts.id || "";
        this.className = opts.className || "";
        this.dataset = opts.dataset ? { ...opts.dataset } : {};
        this.textContent = opts.textContent || "";
        this.children = [];
        this.parentElement = null;
        this.style = {};
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

    removeChild(child) {
        const idx = this.children.indexOf(child);
        if (idx >= 0) {
            this.children.splice(idx, 1);
            child.parentElement = null;
        }
        return child;
    }

    remove() {
        if (this.parentElement) {
            this.parentElement.removeChild(this);
        }
    }

    querySelector(selector) {
        let found = null;
        walk(this, (node) => {
            if (found || node === this) {
                return;
            }
            if (matchSel(node, selector)) {
                found = node;
            }
        });
        return found;
    }

    querySelectorAll(selector) {
        const matches = [];
        walk(this, (node) => {
            if (node !== this && matchSel(node, selector)) {
                matches.push(node);
            }
        });
        return matches;
    }
}

function buildSandbox(spec = {}) {
    const ids = {};
    const events = [];
    const state = {
        estimates: ["draft"],
    };
    const loadSidebarCalls = [];
    const errors = [];
    const timeouts = [];
    let timerSeq = 1;

    const savedEstimatesList = spec.includeSidebarList === false
        ? null
        : new El("div", { id: "savedEstimatesList", ids });
    let savedRow = null;
    let nameEl = null;
    if (savedEstimatesList && spec.includeSavedRow !== false) {
        savedRow = savedEstimatesList.appendChild(
            new El("div", {
                className: "saved-estimate-row",
                dataset: { estimateId: String(spec.rowEstimateId || 42) },
                ids,
            })
        );
        if (spec.includeNameEl !== false) {
            nameEl = savedRow.appendChild(
                new El("div", {
                    className: "saved-estimate-customer-name",
                    ids,
                })
            );
        }
    }

    const document = {
        getElementById(id) {
            return ids[id] || null;
        },
        createElement(tag) {
            return new El(tag, { ids });
        },
    };

    const sidebarResults = (spec.sidebarResults || [{ resolve: null }]).map((item) => ({ ...item }));
    function loadSidebarEstimates() {
        loadSidebarCalls.push(loadSidebarCalls.length + 1);
        const next = sidebarResults.shift() || { resolve: null };
        if (next.reject) {
            return Promise.reject(next.reject);
        }
        return Promise.resolve(next.resolve);
    }

    function setTimeoutImpl(fn, delay) {
        const id = timerSeq++;
        timeouts.push({ id, fn, delay, cleared: false });
        return id;
    }

    function setEstimates(next) {
        state.estimates = next;
        events.push("setEstimates");
    }

    function resetInputFormKeepCustomerName() {
        events.push("resetInputFormKeepCustomerName");
        if (spec.resetThrows) {
            throw new Error("reset failed");
        }
    }

    function resetInputFormToNewEstimate() {
        events.push("resetInputFormToNewEstimate");
        if (spec.resetThrows) {
            throw new Error("reset failed");
        }
    }

    function renderEstimatesList() {
        events.push("renderEstimatesList");
    }

    const sandbox = {
        window: {},
        globalThis: null,
        document,
        console: {
            error(...args) {
                errors.push(args.join(" "));
            },
        },
        setTimeout: setTimeoutImpl,
        Promise,
        setEstimates,
        resetInputFormKeepCustomerName,
        resetInputFormToNewEstimate,
        renderEstimatesList,
        loadSidebarEstimates,
    };
    sandbox.globalThis = sandbox;

    vm.createContext(sandbox);
    vm.runInContext(
        [
            helperSrc,
            `
            window.WdCalculatorRefreshAfterSave.configure({
                setEstimates: setEstimates,
                resetInputFormKeepCustomerName: resetInputFormKeepCustomerName,
                resetInputFormToNewEstimate: resetInputFormToNewEstimate,
                renderEstimatesList: renderEstimatesList,
                loadSidebarEstimates: loadSidebarEstimates,
                documentRef: document,
                consoleRef: console,
                setTimeoutImpl: setTimeout,
            });
            `,
        ].join("\n\n"),
        sandbox,
        { filename: templatePath }
    );

    return {
        sandbox,
        events,
        state,
        loadSidebarCalls,
        errors,
        timeouts,
        savedEstimatesList,
        savedRow,
        nameEl,
        callRefresh(savedId) {
            sandbox.__savedId = savedId;
            vm.runInContext(
                "window.WdCalculatorRefreshAfterSave.refreshAfterSave(__savedId);",
                sandbox,
                { filename: templatePath }
            );
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

async function scenarioHappyPathHighlightsSavedRow() {
    const env = buildSandbox({
        rowEstimateId: 42,
    });

    env.callRefresh(42);

    assertEq(env.events[0], "setEstimates", "happy path clears estimates first");
    assertEq(
        env.events[1],
        "resetInputFormToNewEstimate",
        "happy path full-resets form after clearing estimates"
    );
    assertEq(env.state.estimates.length, 0, "happy path leaves local estimates empty");
    assertEq(env.loadSidebarCalls.length, 0, "happy path does not refresh sidebar before timers");

    runTimeout(env, 50);
    assertEq(env.events[2], "renderEstimatesList", "happy path rerenders after 50ms");
    assertEq(env.loadSidebarCalls.length, 0, "happy path still defers sidebar refresh until nested timer");

    runTimeout(env, 200);
    await flushPromises();

    assertEq(env.loadSidebarCalls.length, 1, "happy path refreshes sidebar once");
    assertEq(env.savedRow.style.boxShadow, "0 0 0 3px #28a745aa", "happy path highlights saved row");
    assertEq(env.savedRow.style.borderColor, "#28a745", "happy path sets saved row border");
    assertEq(env.savedRow.style.transition, "box-shadow 0.3s, border-color 0.3s", "happy path sets transition");
    assertEq(env.nameEl.children.length, 1, "happy path appends completion badge");
    assertEq(env.nameEl.children[0].className, "badge bg-success ms-1", "happy path keeps badge classes");
    assertEq(env.nameEl.children[0].textContent, "저장 완료", "happy path keeps badge text");

    runTimeout(env, 3000);

    assertEq(env.savedRow.style.boxShadow, "", "happy path clears highlight after 3s");
    assertEq(env.savedRow.style.borderColor, "", "happy path clears border after 3s");
    assertEq(env.nameEl.children.length, 0, "happy path removes badge after 3s");
}

async function scenarioMissingNameElementStillClearsStyles() {
    const env = buildSandbox({
        rowEstimateId: 55,
        includeNameEl: false,
    });

    env.callRefresh(55);
    runTimeout(env, 50);
    runTimeout(env, 200);
    await flushPromises();

    assertEq(
        env.savedRow.style.boxShadow,
        "0 0 0 3px #28a745aa",
        "missing-name path still highlights saved row"
    );
    assertEq(env.savedRow.children.length, 0, "missing-name path does not append badge");

    runTimeout(env, 3000);

    assertEq(env.savedRow.style.boxShadow, "", "missing-name path clears highlight after 3s");
    assertEq(env.savedRow.style.borderColor, "", "missing-name path clears border after 3s");
}

async function scenarioSidebarFailureRetriesOnce() {
    const env = buildSandbox({
        rowEstimateId: 77,
        sidebarResults: [
            { reject: new Error("sidebar failed") },
            { resolve: { success: true } },
        ],
    });

    env.callRefresh(77);
    runTimeout(env, 50);
    runTimeout(env, 200);
    await flushPromises();

    assertEq(env.loadSidebarCalls.length, 2, "retry path calls sidebar refresh twice");
    assertEq(Boolean(env.nameEl.querySelector(".badge")), false, "retry path does not append badge");
    assertEq(Boolean(env.savedRow.style.boxShadow), false, "retry path does not keep highlight styling");
}

async function scenarioOuterCatchFallsBackToImmediateRender() {
    const env = buildSandbox({
        resetThrows: true,
    });

    env.callRefresh(42);

    assertEq(env.events[0], "setEstimates", "fallback path clears estimates before reset");
    assertEq(env.events[1], "resetInputFormToNewEstimate", "fallback path still attempts reset");
    assertEq(env.events[2], "setEstimates", "fallback path clears estimates again inside catch");
    assertEq(env.events[3], "resetInputFormToNewEstimate", "fallback path retries reset inside inner catch");
    assertEq(env.events[4], "renderEstimatesList", "fallback path rerenders immediately");
    assertEq(env.loadSidebarCalls.length, 0, "fallback path defers sidebar refresh to 300ms");
    assertTruthy(env.errors.length > 0, "fallback path logs refresh error");

    runTimeout(env, 300);
    await flushPromises();

    assertEq(env.loadSidebarCalls.length, 1, "fallback path refreshes sidebar once after 300ms");
}

async function main() {
    await scenarioHappyPathHighlightsSavedRow();
    await scenarioMissingNameElementStillClearsStyles();
    await scenarioSidebarFailureRetriesOnce();
    await scenarioOuterCatchFallsBackToImmediateRender();
    console.log("wdcalculator refresh-after-save contract checks passed");
}

main().catch((error) => {
    console.error(error);
    process.exit(1);
});
