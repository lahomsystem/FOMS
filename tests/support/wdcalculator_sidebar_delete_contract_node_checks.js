/**
 * Contract freeze: sidebar saved-estimate delete must call
 * DELETE /api/wdcalculator/estimate/:id (blueprint SSOT).
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

function assertIncludes(text, fragment, label) {
    if (!String(text).includes(fragment)) {
        throw new Error(`${label}: expected source to include ${JSON.stringify(fragment)}`);
    }
}

function assertNotIncludes(text, fragment, label) {
    if (String(text).includes(fragment)) {
        throw new Error(`${label}: source must not include ${JSON.stringify(fragment)}`);
    }
}

function extractSidebarBlock(src) {
    const startMarker = "/* --- included: sidebar-estimates.js --- */";
    const endMarker = "/* --- included: search-results-load.js --- */";
    const start = src.indexOf(startMarker);
    const end = src.indexOf(endMarker);
    if (start === -1 || end === -1 || end <= start) {
        throw new Error("sidebar-estimates block markers not found in estimate-lifecycle.js");
    }
    return src.slice(start, end);
}

function buildSandbox() {
    const fetchCalls = [];
    const alerts = [];

    const document = {
        getElementById() {
            return null;
        },
        createElement() {
            return {
                className: "",
                style: {},
                textContent: "",
                appendChild() {},
                addEventListener() {},
                setAttribute() {},
            };
        },
    };

    const fetchImpl = (url, options) => {
        fetchCalls.push({ url, options: options || {} });
        return Promise.resolve({
            ok: true,
            status: 200,
            json: () => Promise.resolve({ success: true }),
        });
    };

    const sandbox = {
        window: {},
        document,
        fetch: fetchImpl,
        confirm() {
            return true;
        },
        alert(message) {
            alerts.push(String(message));
        },
        matchMedia() {
            return { matches: false };
        },
        loadEstimateToForm() {},
        formatNumber(num) {
            return String(num);
        },
        Promise,
        JSON,
        Math,
        Number,
        String,
        Array,
        Date,
        encodeURIComponent,
        setTimeout(fn) {
            fn();
            return 1;
        },
        clearTimeout() {},
    };
    sandbox.window = sandbox;

    vm.createContext(sandbox);
    vm.runInContext(helperSrc, sandbox, { filename: helperPath });

    const api = sandbox.initWdCalculatorSidebarEstimates({
        loadEstimateToForm: sandbox.loadEstimateToForm,
        formatNumber: sandbox.formatNumber,
        fetchImpl,
        confirmImpl: sandbox.confirm,
        alertImpl: sandbox.alert,
        matchMediaImpl: sandbox.matchMedia,
        documentRef: document,
    });

    sandbox.deleteEstimate = api.deleteEstimate;

    return { sandbox, fetchCalls, alerts };
}

function scenarioSourceUsesBlueprintDeleteEndpoint() {
    const sidebarBlock = extractSidebarBlock(helperSrc);
    assertIncludes(
        sidebarBlock,
        '"/api/wdcalculator/estimate/" + estimateId',
        "sidebar delete fetch URL"
    );
    assertNotIncludes(
        sidebarBlock,
        "/api/wdcalculator/delete-estimate/",
        "sidebar delete must not use obsolete delete-estimate path"
    );
}

async function scenarioDeleteEstimateCallsBlueprintEndpoint() {
    const env = buildSandbox();
    await env.sandbox.deleteEstimate(753);

    assertEq(env.fetchCalls.length, 1, "deleteEstimate performs one fetch");
    assertEq(
        env.fetchCalls[0].url,
        "/api/wdcalculator/estimate/753",
        "deleteEstimate keeps blueprint DELETE URL"
    );
    assertEq(env.fetchCalls[0].options.method, "DELETE", "deleteEstimate uses DELETE method");
    assertEq(env.alerts.length, 0, "delete success does not alert");
}

async function flushPromises(turns = 4) {
    for (let i = 0; i < turns; i++) {
        await new Promise((resolve) => setImmediate(resolve));
    }
}

async function main() {
    scenarioSourceUsesBlueprintDeleteEndpoint();
    await scenarioDeleteEstimateCallsBlueprintEndpoint();
    await flushPromises();
    process.stdout.write("wdcalculator_sidebar_delete_contract_node_checks: ok\n");
}

main().catch((error) => {
    console.error(error);
    process.exit(1);
});
