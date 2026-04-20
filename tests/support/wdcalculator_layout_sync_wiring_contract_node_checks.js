/**
 * Contract freeze: layout sync wiring in
 * static/js/wdcalculator/layout-sync-wiring.js.
 */
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const repoRoot = path.join(__dirname, "..", "..");
const helperPath = path.join(repoRoot, "static", "js", "wdcalculator", "layout-sync-wiring.js");
const helperSrc = fs.readFileSync(helperPath, "utf8");

function assertEq(actual, expected, label) {
    if (actual !== expected) {
        throw new Error(`${label}: expected ${JSON.stringify(expected)}, got ${JSON.stringify(actual)}`);
    }
}

function buildSandbox(spec = {}) {
    const events = [];
    const listeners = [];
    const windowRef =
        spec.withWindowRef === false
            ? null
            : {
                  addEventListener(name, handler) {
                      listeners.push({ name, handler });
                  },
              };

    const sandbox = {
        window: {},
        windowRef,
        requestLayoutSync() {
            events.push("requestLayoutSync");
        },
        globalThis: null,
    };
    sandbox.globalThis = sandbox;

    vm.createContext(sandbox);
    vm.runInContext(
        [
            helperSrc,
            `
            window.WdCalculatorLayoutSyncWiring.configure({
                windowRef: windowRef,
                requestLayoutSync: requestLayoutSync
            });
            `,
        ].join("\n\n"),
        sandbox,
        { filename: helperPath }
    );

    return {
        events,
        listeners,
        init() {
            vm.runInContext("window.WdCalculatorLayoutSyncWiring.initLayoutSyncWiring();", sandbox, {
                filename: helperPath,
            });
        },
    };
}

function scenarioInitRegistersResizeAndLoadListeners() {
    const env = buildSandbox();
    env.init();
    assertEq(env.listeners.length, 2, "init registers two window listeners");
    assertEq(env.listeners[0].name, "resize", "first listener keeps resize contract");
    assertEq(env.listeners[1].name, "load", "second listener keeps load contract");
    assertEq(
        env.listeners[0].handler === env.listeners[1].handler,
        true,
        "resize and load listeners share the same sync handler"
    );
}

function scenarioInitRequestsImmediateSyncOnce() {
    const env = buildSandbox();
    env.init();
    assertEq(env.events.length, 1, "init requests an immediate layout sync once");
    assertEq(env.events[0], "requestLayoutSync", "init preserves requestWdCalculatorLayoutSync bridge");
}

function scenarioMissingWindowRefSkipsBindingAndSync() {
    const env = buildSandbox({ withWindowRef: false });
    env.init();
    assertEq(env.listeners.length, 0, "missing windowRef skips listener binding");
    assertEq(env.events.length, 0, "missing windowRef skips immediate layout sync");
}

function main() {
    scenarioInitRegistersResizeAndLoadListeners();
    scenarioInitRequestsImmediateSyncOnce();
    scenarioMissingWindowRefSkipsBindingAndSync();
    console.log("wdcalculator layout-sync-wiring contract checks passed");
}

main();
