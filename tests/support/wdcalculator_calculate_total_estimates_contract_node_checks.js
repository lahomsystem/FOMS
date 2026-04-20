/**
 * Contract freeze: aggregate summary display orchestration inside
 * static/js/wdcalculator/pricing-core.js.
 */
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const repoRoot = path.join(__dirname, "..", "..");
const helperPath = path.join(repoRoot, "static", "js", "wdcalculator", "pricing-core.js");
const helperSrc = fs.readFileSync(helperPath, "utf8");

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

function createElement(id, opts = {}) {
    return {
        id,
        textContent: opts.textContent || "",
        value: opts.value || "",
        checked: !!opts.checked,
        style: { display: opts.display || "" },
    };
}

function clone(value) {
    return JSON.parse(JSON.stringify(value));
}

function buildSandbox(spec = {}) {
    const events = [];
    const alerts = [];
    const errors = [];
    const ids = {
        totalBasePrice: createElement("totalBasePrice", { textContent: spec.prefillTotalBasePrice || "" }),
        totalAdditionalPrice: createElement("totalAdditionalPrice", {
            textContent: spec.prefillTotalAdditionalPrice || "",
        }),
        totalPrice: createElement("totalPrice", { textContent: spec.prefillTotalPrice || "" }),
        finalPrice: createElement("finalPrice", { textContent: spec.prefillFinalPrice || "" }),
        baseEstimateDetail: createElement("baseEstimateDetail", {
            textContent: spec.prefillBaseEstimateDetail || "",
        }),
        additionalOptionsDetail: createElement("additionalOptionsDetail", {
            textContent: spec.prefillAdditionalOptionsDetail || "",
        }),
        shippingCost: createElement("shippingCost", { value: spec.shippingCostValue || "0" }),
        shippingIncluded: createElement("shippingIncluded", {
            checked: spec.shippingIncluded === undefined ? true : !!spec.shippingIncluded,
        }),
        couponInfo: createElement("couponInfo", { textContent: spec.prefillCouponInfo || "" }),
        totalEstimatesSummary: createElement("totalEstimatesSummary", {
            display: spec.prefillTotalEstimatesSummaryDisplay || "none",
        }),
        totalAllBasePrice: createElement("totalAllBasePrice", {
            textContent: spec.prefillTotalAllBasePrice || "",
        }),
        totalAllAdditionalPrice: createElement("totalAllAdditionalPrice", {
            textContent: spec.prefillTotalAllAdditionalPrice || "",
        }),
        totalAllFinalPrice: createElement("totalAllFinalPrice", {
            textContent: spec.prefillTotalAllFinalPrice || "",
        }),
        totalAllCouponInfo: createElement("totalAllCouponInfo", {
            textContent: spec.prefillTotalAllCouponInfo || "",
        }),
        notesDisplaySection: createElement("notesDisplaySection", {
            display: spec.prefillNotesDisplaySectionDisplay || "none",
        }),
        notesDisplay: createElement("notesDisplay", { textContent: spec.prefillNotesDisplay || "" }),
    };
    if (spec.withTotalAllPrice !== false) {
        ids.totalAllPrice = createElement("totalAllPrice", { textContent: spec.prefillTotalAllPrice || "" });
    }

    const document = {
        getElementById(id) {
            return ids[id] || null;
        },
    };

    function resolveAggregateTotals(estimatesList, couponValue, shippingCost, shippingIncluded) {
        events.push([
            "resolveAggregateTotals",
            clone(estimatesList),
            couponValue,
            shippingCost,
            shippingIncluded,
        ]);
        if (spec.aggregateError) {
            throw spec.aggregateError;
        }
        return clone(
            spec.aggregateResult || {
                totalBasePrice: 0,
                totalAdditionalPrice: 0,
                totalPrice: 0,
                finalPrice: 0,
            }
        );
    }

    const sandbox = {
        window: {},
        document,
        resolveAggregateTotals,
        getCouponValue() {
            events.push(["getCouponValue"]);
            return spec.couponValue === undefined ? 0 : spec.couponValue;
        },
        collectNotes() {
            events.push(["collectNotes"]);
            return spec.notes === undefined ? "" : spec.notes;
        },
        formatNumber(value) {
            return `fmt:${value}`;
        },
        applyFinalPriceStyle(el) {
            events.push(["applyFinalPriceStyle", el.id]);
        },
        applyCouponDiscountStyle(el, enabled) {
            events.push(["applyCouponDiscountStyle", el.id, enabled]);
        },
        consoleRef: {
            error(...args) {
                errors.push(args.map(String).join(" "));
            },
        },
        alertImpl(message) {
            alerts.push(String(message));
        },
        estimatesState: clone(spec.estimates || []),
        editingEstimateIdState:
            spec.editingEstimateId === undefined ? null : spec.editingEstimateId,
        Map,
        Array,
        globalThis: null,
    };
    sandbox.globalThis = sandbox;

    vm.createContext(sandbox);
    vm.runInContext(
        [
            helperSrc,
            `
            window.WdCalculatorTotalEstimatesDisplay.configure({
                getEstimates: function () {
                    return estimatesState;
                },
                getEditingEstimateId: function () {
                    return editingEstimateIdState;
                },
                getCouponValue: getCouponValue,
                resolveAggregateTotals: resolveAggregateTotals,
                collectNotes: collectNotes,
                formatNumber: formatNumber,
                applyFinalPriceStyle: applyFinalPriceStyle,
                applyCouponDiscountStyle: applyCouponDiscountStyle,
                documentRef: document,
                alertImpl: alertImpl,
                consoleRef: consoleRef
            });
            `,
        ].join("\n\n"),
        sandbox,
        { filename: helperPath }
    );

    return {
        ids,
        events,
        alerts,
        errors,
        invoke() {
            vm.runInContext("window.WdCalculatorTotalEstimatesDisplay.calculateTotalEstimates();", sandbox, {
                filename: helperPath,
            });
        },
    };
}

function scenarioZeroStateResetsVisibleSummary() {
    const env = buildSandbox({
        estimates: [],
        prefillTotalBasePrice: "keep-base",
        prefillTotalAdditionalPrice: "keep-additional",
        prefillTotalPrice: "keep-total",
        prefillFinalPrice: "keep-final",
        prefillBaseEstimateDetail: "keep-detail",
        prefillAdditionalOptionsDetail: "keep-options",
    });

    env.invoke();

    assertEq(env.ids.totalBasePrice.textContent, "0원", "zero-state resets totalBasePrice");
    assertEq(env.ids.totalAdditionalPrice.textContent, "0원", "zero-state resets totalAdditionalPrice");
    assertEq(env.ids.totalPrice.textContent, "0원", "zero-state resets totalPrice");
    assertEq(env.ids.finalPrice.textContent, "0원", "zero-state resets finalPrice");
    assertEq(env.ids.baseEstimateDetail.textContent, "", "zero-state clears baseEstimateDetail");
    assertEq(env.ids.additionalOptionsDetail.textContent, "", "zero-state clears additionalOptionsDetail");
}

function scenarioNonEditingPathUpdatesCurrentAndOverallSummary() {
    const env = buildSandbox({
        estimates: [
            {
                id: "est-1",
                productName: "Wardrobe",
                widthMm: 1000,
                options: [
                    { name: "LED", quantity: 1, price: 5000 },
                    { name: "Hook", quantity: 2, price: 1000 },
                ],
            },
            {
                id: "est-2",
                productName: "Closet",
                widthMm: 1200,
                options: [{ name: "LED", quantity: 2, price: 5000 }],
            },
        ],
        couponValue: 11000,
        shippingCostValue: "3000",
        shippingIncluded: false,
        notes: "비고 메모",
        withTotalAllPrice: false,
        aggregateResult: {
            totalBasePrice: 200000,
            totalAdditionalPrice: 17000,
            totalPrice: 220000,
            finalPrice: 209000,
        },
    });

    env.invoke();

    assertDeepEqual(
        env.events[1],
        [
            "resolveAggregateTotals",
            [
                {
                    id: "est-1",
                    productName: "Wardrobe",
                    widthMm: 1000,
                    options: [
                        { name: "LED", quantity: 1, price: 5000 },
                        { name: "Hook", quantity: 2, price: 1000 },
                    ],
                },
                {
                    id: "est-2",
                    productName: "Closet",
                    widthMm: 1200,
                    options: [{ name: "LED", quantity: 2, price: 5000 }],
                },
            ],
            11000,
            3000,
            false,
        ],
        "aggregate helper receives estimates plus coupon/shipping DOM values"
    );
    assertEq(env.ids.totalBasePrice.textContent, "fmt:200000원", "non-editing path updates current totalBasePrice");
    assertEq(env.ids.totalAdditionalPrice.textContent, "fmt:17000원", "non-editing path updates current totalAdditionalPrice");
    assertEq(env.ids.totalPrice.textContent, "fmt:220000원", "non-editing path updates current totalPrice");
    assertEq(env.ids.finalPrice.textContent, "fmt:209000원", "non-editing path updates current finalPrice");
    assertEq(env.ids.couponInfo.textContent, "fmt:11000원 할인", "non-editing path updates couponInfo");
    assertEq(
        env.ids.baseEstimateDetail.textContent,
        "Wardrobe fmt:1000mm, Closet fmt:1200mm",
        "non-editing path aggregates base detail text"
    );
    assertEq(
        env.ids.additionalOptionsDetail.textContent,
        "LED × 3 (fmt:15000원), Hook × 2 (fmt:2000원)",
        "non-editing path aggregates additional option details"
    );
    assertEq(env.ids.notesDisplay.textContent, "비고 메모", "non-editing path writes notes display");
    assertEq(env.ids.notesDisplaySection.style.display, "block", "non-editing path shows notes section");
    assertEq(env.ids.totalEstimatesSummary.style.display, "block", "non-editing path shows total summary section");
    assertEq(env.ids.totalAllBasePrice.textContent, "fmt:200000원", "non-editing path updates overall base total");
    assertEq(env.ids.totalAllAdditionalPrice.textContent, "fmt:17000원", "non-editing path updates overall additional total");
    assertEq(env.ids.totalAllFinalPrice.textContent, "fmt:209000원", "non-editing path updates overall final total");
    assertEq(
        env.ids.totalAllCouponInfo.textContent,
        "fmt:11000할인(쿠폰적용)",
        "non-editing path updates overall coupon info"
    );
    assertEq(
        env.events.some((entry) => entry[0] === "applyFinalPriceStyle" && entry[1] === "finalPrice"),
        true,
        "non-editing path applies current final price style"
    );
    assertEq(
        env.events.some((entry) => entry[0] === "applyFinalPriceStyle" && entry[1] === "totalAllFinalPrice"),
        true,
        "non-editing path applies overall final price style"
    );
}

function scenarioEditingGuardPreservesCurrentSummaryButUpdatesOverallSummary() {
    const env = buildSandbox({
        estimates: [{ id: "est-1", productName: "Wardrobe", widthMm: 900, options: [] }],
        editingEstimateId: "est-1",
        prefillTotalBasePrice: "keep-base",
        prefillTotalAdditionalPrice: "keep-additional",
        prefillTotalPrice: "keep-total",
        prefillFinalPrice: "keep-final",
        prefillCouponInfo: "keep-coupon",
        prefillBaseEstimateDetail: "keep-base-detail",
        prefillAdditionalOptionsDetail: "keep-options-detail",
        prefillNotesDisplaySectionDisplay: "sentinel",
        prefillNotesDisplay: "keep-notes",
        aggregateResult: {
            totalBasePrice: 90000,
            totalAdditionalPrice: 0,
            totalPrice: 90000,
            finalPrice: 90000,
        },
    });

    env.invoke();

    assertEq(env.ids.totalBasePrice.textContent, "keep-base", "editing guard preserves current totalBasePrice");
    assertEq(env.ids.totalAdditionalPrice.textContent, "keep-additional", "editing guard preserves current totalAdditionalPrice");
    assertEq(env.ids.totalPrice.textContent, "keep-total", "editing guard preserves current totalPrice");
    assertEq(env.ids.finalPrice.textContent, "keep-final", "editing guard preserves current finalPrice");
    assertEq(env.ids.couponInfo.textContent, "keep-coupon", "editing guard preserves current couponInfo");
    assertEq(
        env.ids.baseEstimateDetail.textContent,
        "keep-base-detail",
        "editing guard preserves base detail text"
    );
    assertEq(
        env.ids.additionalOptionsDetail.textContent,
        "keep-options-detail",
        "editing guard preserves additional detail text"
    );
    assertEq(env.ids.notesDisplaySection.style.display, "sentinel", "editing guard preserves notes section display");
    assertEq(env.ids.notesDisplay.textContent, "keep-notes", "editing guard preserves notes text");
    assertEq(env.ids.totalAllBasePrice.textContent, "fmt:90000원", "editing guard still updates overall base total");
    assertEq(env.ids.totalAllFinalPrice.textContent, "fmt:90000원", "editing guard still updates overall final total");
}

function scenarioAggregateHelperErrorAlertsAndStopsDomWrites() {
    const env = buildSandbox({
        estimates: [{ id: "est-1", productName: "Wardrobe", widthMm: 900, options: [] }],
        prefillTotalAllBasePrice: "keep-total-all-base",
        aggregateError: new Error("aggregate broken"),
    });

    env.invoke();

    assertEq(env.alerts[0], "aggregate broken", "aggregate helper errors surface via alert");
    assertEq(
        env.ids.totalAllBasePrice.textContent,
        "keep-total-all-base",
        "aggregate helper error stops downstream DOM writes"
    );
    assertEq(env.errors.length > 0, true, "aggregate helper error is logged");
}

function main() {
    scenarioZeroStateResetsVisibleSummary();
    scenarioNonEditingPathUpdatesCurrentAndOverallSummary();
    scenarioEditingGuardPreservesCurrentSummaryButUpdatesOverallSummary();
    scenarioAggregateHelperErrorAlertsAndStopsDomWrites();
    console.log("wdcalculator calculateTotalEstimates contract checks passed");
}

main();
