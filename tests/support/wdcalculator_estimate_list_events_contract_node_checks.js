/**
 * Contract freeze: #estimatesListContainer delegated interactions in
 * static/js/wdcalculator/estimate-list-events.js.
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
    "estimate-list-events.js"
);
const helperSrc = fs.readFileSync(helperPath, "utf8");
const templatePath = helperPath;

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
    if (value === undefined) {
        return undefined;
    }
    return JSON.parse(JSON.stringify(value));
}

function hasClass(el, className) {
    return String(el.className || "")
        .split(/\s+/)
        .filter(Boolean)
        .includes(className);
}

function matchesSelector(el, selector) {
    if (!el) {
        return false;
    }
    if (selector === "button") {
        return el.tagName === "BUTTON";
    }
    if (selector === ".card[data-estimate-id]") {
        return hasClass(el, "card") && !!(el.dataset && el.dataset.estimateId);
    }
    if (selector.startsWith(".")) {
        return hasClass(el, selector.slice(1));
    }
    return false;
}

class El {
    constructor(tag, opts = {}) {
        this.tagName = String(tag).toUpperCase();
        this.id = opts.id || "";
        this.className = opts.className || "";
        this.dataset = opts.dataset ? { ...opts.dataset } : {};
        this.innerHTML = opts.innerHTML || "";
        this.textContent = opts.textContent || "";
        this.value = opts.value || "";
        this.type = opts.type || "";
        this.title = opts.title || "";
        this.children = [];
        this.parentNode = null;
        this.listeners = {};
        this.focusCalls = 0;
        this.selectCalls = 0;
        this.style = { display: opts.display || "" };
        this._ids = opts.ids || {};
        if (this.id) {
            this._ids[this.id] = this;
        }
    }

    appendChild(child) {
        child.parentNode = this;
        this.children.push(child);
        if (child.id) {
            this._ids[child.id] = child;
        }
        return child;
    }

    insertAdjacentElement(position, element) {
        if (position !== "afterend" || !this.parentNode) {
            return element;
        }
        const siblings = this.parentNode.children;
        const index = siblings.indexOf(this);
        if (index === -1) {
            return element;
        }
        element.parentNode = this.parentNode;
        siblings.splice(index + 1, 0, element);
        if (element.id) {
            this._ids[element.id] = element;
        }
        return element;
    }

    remove() {
        if (!this.parentNode) {
            return;
        }
        const siblings = this.parentNode.children;
        const index = siblings.indexOf(this);
        if (index >= 0) {
            siblings.splice(index, 1);
        }
        this.parentNode = null;
    }

    addEventListener(type, fn) {
        if (!this.listeners[type]) {
            this.listeners[type] = [];
        }
        this.listeners[type].push(fn);
    }

    dispatchEvent(event) {
        const evt = event || {};
        evt.type = evt.type || "";
        evt.target = evt.target || this;
        evt.currentTarget = this;
        evt._stopped = false;
        evt._defaultPrevented = false;
        evt.stopPropagation = evt.stopPropagation || function () {
            this._stopped = true;
        };
        evt.preventDefault = evt.preventDefault || function () {
            this._defaultPrevented = true;
        };
        const handlers = this.listeners[evt.type] || [];
        handlers.forEach((fn) => fn.call(this, evt));
        return evt;
    }

    contains(node) {
        let current = node;
        while (current) {
            if (current === this) {
                return true;
            }
            current = current.parentNode;
        }
        return false;
    }

    closest(selector) {
        let current = this;
        while (current) {
            if (matchesSelector(current, selector)) {
                return current;
            }
            current = current.parentNode;
        }
        return null;
    }

    querySelector(selector) {
        for (let i = 0; i < this.children.length; i += 1) {
            const child = this.children[i];
            if (matchesSelector(child, selector)) {
                return child;
            }
            const nested = child.querySelector(selector);
            if (nested) {
                return nested;
            }
        }
        return null;
    }

    focus() {
        this.focusCalls += 1;
    }

    select() {
        this.selectCalls += 1;
    }
}

function buildSandbox(spec = {}) {
    const ids = {};
    const events = [];
    const confirms = [];
    const errors = [];
    const timers = [];

    const documentListeners = {};

    const document = {
        getElementById(id) {
            return ids[id] || null;
        },
        createElement(tag) {
            return new El(tag, { ids });
        },
        addEventListener(type, fn) {
            if (!documentListeners[type]) {
                documentListeners[type] = [];
            }
            documentListeners[type].push(fn);
        },
    };

    const container = new El("div", { id: "estimatesListContainer", ids });
    const card = container.appendChild(
        new El("div", {
            className: "card",
            dataset: { estimateId: spec.cardEstimateId || "est-1" },
            ids,
        })
    );
    const cardHeader = card.appendChild(new El("div", { className: "card-header", ids }));
    const nameWrap = cardHeader.appendChild(new El("div", { className: "name-wrap", ids }));
    const nameSpan = nameWrap.appendChild(
        new El("span", {
            className: "estimate-display-name",
            textContent: spec.initialDisplayName || "기존 이름",
            ids,
        })
    );
    const editNameBtn = nameWrap.appendChild(
        new El("button", {
            className: "edit-estimate-name-btn",
            dataset: { estimateId: spec.cardEstimateId || "est-1" },
            ids,
        })
    );
    const buttonWrap = cardHeader.appendChild(new El("div", { className: "button-wrap", ids }));
    const editBtn = buttonWrap.appendChild(
        new El("button", {
            className: "edit-estimate-btn",
            dataset: { estimateId: spec.cardEstimateId || "est-1" },
            ids,
        })
    );
    const deleteBtn = buttonWrap.appendChild(
        new El("button", {
            className: "delete-estimate-btn",
            dataset: { estimateId: spec.cardEstimateId || "est-1" },
            ids,
        })
    );
    const cardBody = card.appendChild(new El("div", { className: "card-body", ids }));
    const addEstimateBtn = new El("button", {
        id: "addEstimateBtn",
        innerHTML: spec.initialAddButtonHtml || '<i class="fas fa-save"></i> 견적 수정 적용',
        ids,
    });

    const state = {
        loadingState: !!spec.loadingState,
        editingEstimateId:
            spec.initialEditingEstimateId === undefined ? null : spec.initialEditingEstimateId,
        estimates: clone(
            spec.estimates || [
                {
                    id: spec.cardEstimateId || "est-1",
                    productName: "Wardrobe",
                    widthMm: 1000,
                    displayName: spec.initialDisplayName || "기존 이름",
                },
            ]
        ),
    };

    function getLoadingState() {
        return state.loadingState;
    }

    function getEstimates() {
        return state.estimates;
    }

    function setEstimates(next) {
        state.estimates = clone(next);
        events.push(["setEstimates", clone(next)]);
    }

    function getEditingEstimateId() {
        return state.editingEstimateId;
    }

    function setEditingEstimateId(next) {
        state.editingEstimateId = next;
        events.push(["setEditingEstimateId", next]);
    }

    function loadEstimateToInputForm(estimateId) {
        events.push(["loadEstimateToInputForm", estimateId]);
    }

    function renderEstimatesList() {
        events.push(["renderEstimatesList"]);
    }

    function formatNumber(value) {
        return `fmt:${value}`;
    }

    function normalizeId(value) {
        events.push(["normalizeId", value]);
        if (spec.normalizeIdResult !== undefined) {
            return spec.normalizeIdResult;
        }
        if (value === null || value === undefined || value === "") {
            return null;
        }
        return String(value);
    }

    function isSameId(left, right) {
        events.push(["isSameId", left, right]);
        return String(left) === String(right);
    }

    function confirmImpl(message) {
        confirms.push(message);
        return spec.confirmResult === undefined ? true : !!spec.confirmResult;
    }

    function setTimeoutImpl(fn, delay) {
        timers.push({ fn, delay });
        return timers.length;
    }

    const consoleRef = {
        error(...args) {
            errors.push(args.join(" "));
        },
    };

    const sandbox = {
        window: {},
        globalThis: null,
        document,
        getLoadingState,
        getEstimates,
        setEstimates,
        getEditingEstimateId,
        setEditingEstimateId,
        loadEstimateToInputForm,
        renderEstimatesList,
        formatNumber,
        normalizeId,
        isSameId,
        confirmImpl,
        setTimeoutImpl,
        consoleRef,
    };
    sandbox.globalThis = sandbox;

    vm.createContext(sandbox);
    vm.runInContext(
        [
            helperSrc,
            `
            window.WdCalculatorEstimateListEvents.configure({
                getLoadingState: getLoadingState,
                getEstimates: getEstimates,
                setEstimates: setEstimates,
                getEditingEstimateId: getEditingEstimateId,
                setEditingEstimateId: setEditingEstimateId,
                loadEstimateToInputForm: loadEstimateToInputForm,
                renderEstimatesList: renderEstimatesList,
                formatNumber: formatNumber,
                normalizeId: normalizeId,
                isSameId: isSameId,
                documentRef: document,
                confirmImpl: confirmImpl,
                consoleRef: consoleRef,
                setTimeoutImpl: setTimeoutImpl
            });
            `,
        ].join("\n\n"),
        sandbox,
        { filename: templatePath }
    );

    return {
        ids,
        state,
        events,
        confirms,
        errors,
        timers,
        container,
        card,
        cardBody,
        nameSpan,
        editNameBtn,
        editBtn,
        deleteBtn,
        addEstimateBtn,
        documentListeners,
        init() {
            vm.runInContext("window.WdCalculatorEstimateListEvents.initEstimateListEvents();", sandbox, {
                filename: templatePath,
            });
        },
        dispatchClick(target) {
            const evt = {
                type: "click",
                target,
                _stopped: false,
                _defaultPrevented: false,
                stopPropagation() {
                    this._stopped = true;
                },
                preventDefault() {
                    this._defaultPrevented = true;
                },
            };
            (documentListeners.click || []).forEach((fn) => fn.call(document, evt));
            return evt;
        },
        flushTimers(delay) {
            let executed = false;
            for (let i = 0; i < timers.length; ) {
                if (timers[i].delay === delay) {
                    const timer = timers.splice(i, 1)[0];
                    timer.fn();
                    executed = true;
                } else {
                    i += 1;
                }
            }
            return executed;
        },
        handleKeydown(el, key) {
            return el.dispatchEvent({
                type: "keydown",
                key,
                preventDefault() {
                    this._defaultPrevented = true;
                },
                stopPropagation() {},
            });
        },
        triggerBlur(el) {
            el.dispatchEvent({ type: "blur" });
        },
    };
}

function scenarioInitAndEditButtonDelegatesToLoadHelper() {
    const env = buildSandbox();

    env.init();
    assertEq(env.documentListeners.click.length, 1, "init registers one document click listener");

    const evt = env.dispatchClick(env.editBtn);
    assertDeepEqual(env.events[0], ["loadEstimateToInputForm", "est-1"], "edit button delegates to loadEstimateToInputForm");
    assertEq(evt._stopped, true, "edit button stops propagation");
    assertEq(evt._defaultPrevented, true, "edit button prevents default");
}

function scenarioLoadingGuardSkipsDelegatedInteractions() {
    const env = buildSandbox({ loadingState: true });

    env.init();
    env.dispatchClick(env.editBtn);

    assertEq(env.events.length, 0, "loading guard skips all delegated interactions");
}

function scenarioInlineNameEditSaveRerendersAfterTenMs() {
    const env = buildSandbox({
        estimates: [{ id: "est-1", productName: "Wardrobe", widthMm: 1000, displayName: "기존 이름" }],
    });

    env.init();
    const evt = env.dispatchClick(env.editNameBtn);

    const input = env.card.querySelector(".estimate-display-name-input");
    const saveBtn = env.card.querySelector(".estimate-display-name-save-btn");
    const cancelBtn = env.card.querySelector(".estimate-display-name-cancel-btn");
    assertEq(!!input, true, "name edit click inserts input");
    assertEq(!!saveBtn, true, "name edit click inserts save button");
    assertEq(!!cancelBtn, true, "name edit click inserts cancel button");
    assertEq(env.nameSpan.style.display, "none", "name edit click hides display span");
    assertEq(env.editNameBtn.style.display, "none", "name edit click hides edit button");
    assertEq(env.timers[0].delay, 0, "name edit click schedules immediate focus");
    env.flushTimers(0);
    assertEq(input.focusCalls, 1, "name edit click focuses input after timer");
    assertEq(input.selectCalls, 1, "name edit click selects input text after timer");

    input.value = "새 이름";
    const saveEvt = saveBtn.dispatchEvent({
        type: "click",
        stopPropagation() {
            this._stopped = true;
        },
        preventDefault() {
            this._defaultPrevented = true;
        },
    });

    assertEq(saveEvt._stopped, true, "save click stops propagation");
    assertEq(saveEvt._defaultPrevented, true, "save click prevents default");
    assertEq(env.state.estimates[0].displayName, "새 이름", "save click updates displayName immediately");
    assertEq(env.card.querySelector(".estimate-display-name-input"), null, "save click cleans up input before rerender");
    assertEq(env.nameSpan.style.display, "", "save click restores display span");
    assertEq(env.editNameBtn.style.display, "", "save click restores edit button");
    assertEq(env.events.some((entry) => entry[0] === "renderEstimatesList"), false, "save click defers rerender");
    assertEq(env.timers.some((timer) => timer.delay === 10), true, "save click schedules 10ms rerender");
    env.flushTimers(10);
    assertEq(env.events.some((entry) => entry[0] === "renderEstimatesList"), true, "save click rerenders after 10ms");
}

function scenarioInlineNameEditBlurCommitsAfterTwoHundredMs() {
    const env = buildSandbox();

    env.init();
    env.dispatchClick(env.editNameBtn);
    env.flushTimers(0);

    const input = env.card.querySelector(".estimate-display-name-input");
    input.value = "블러 저장";
    env.triggerBlur(input);

    assertEq(env.timers.some((timer) => timer.delay === 200), true, "blur schedules delayed auto-save");
    assertEq(env.events.some((entry) => entry[0] === "renderEstimatesList"), false, "blur does not rerender immediately");
    env.flushTimers(200);
    assertEq(env.state.estimates[0].displayName, "블러 저장", "blur commit updates displayName after 200ms");
    env.flushTimers(10);
    assertEq(env.events.some((entry) => entry[0] === "renderEstimatesList"), true, "blur commit rerenders after follow-up 10ms timer");
}

function scenarioDeleteConfirmResetsEditingStateAndRerenders() {
    const env = buildSandbox({
        initialEditingEstimateId: "est-1",
        estimates: [
            { id: "est-1", displayName: "삭제 대상" },
            { id: "est-2", displayName: "남는 견적" },
        ],
    });

    env.init();
    const evt = env.dispatchClick(env.deleteBtn);

    assertEq(evt._stopped, true, "delete click stops propagation");
    assertEq(evt._defaultPrevented, true, "delete click prevents default");
    assertEq(
        env.confirms[0],
        "이 견적을 삭제하시겠습니까?\n\n⚠️ 삭제된 견적은 복구할 수 없습니다.",
        "delete click uses the current confirm message"
    );
    assertDeepEqual(
        env.events[3],
        ["setEstimates", [{ id: "est-2", displayName: "남는 견적" }]],
        "delete click filters estimates and stores the next list"
    );
    assertDeepEqual(env.events[5], ["setEditingEstimateId", null], "delete click clears editing state when deleting active estimate");
    assertEq(env.addEstimateBtn.innerHTML, '<i class="fas fa-plus"></i> 견적 추가', "delete click restores add button label");
    assertDeepEqual(env.events[6], ["renderEstimatesList"], "delete click rerenders list");
}

function scenarioCardClickLoadsUnlessTargetIsButton() {
    const env = buildSandbox();

    env.init();
    env.dispatchClick(env.cardBody);
    assertDeepEqual(env.events[0], ["loadEstimateToInputForm", "est-1"], "card body click enters edit mode");

    const secondEnv = buildSandbox();
    secondEnv.init();
    secondEnv.dispatchClick(secondEnv.editNameBtn);
    assertEq(
        secondEnv.events.some((entry) => entry[0] === "loadEstimateToInputForm"),
        false,
        "button target does not also trigger card click load"
    );
}

function main() {
    scenarioInitAndEditButtonDelegatesToLoadHelper();
    scenarioLoadingGuardSkipsDelegatedInteractions();
    scenarioInlineNameEditSaveRerendersAfterTenMs();
    scenarioInlineNameEditBlurCommitsAfterTwoHundredMs();
    scenarioDeleteConfirmResetsEditingStateAndRerenders();
    scenarioCardClickLoadsUnlessTargetIsButton();
    console.log("wdcalculator estimate-list-events contract checks passed");
}

main();
