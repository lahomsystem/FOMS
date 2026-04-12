/**
 * Contract freeze: additional-options rows UI in static/js/wdcalculator/additional-options-ui.js
 * (`appendAdditionalOptionRow`, `setOptionMode`, `readAdditionalOptionRowsFromUI`).
 *
 * Runs in Node vm with DOM stubs + lightweight HTML fragment parsing.
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
    "additional-options-ui.js"
);
const sharedPath = path.join(repoRoot, "static", "js", "wdcalculator", "shared.js");

const helperSrc = fs.readFileSync(helperPath, "utf8");
const sharedSrc = fs.readFileSync(sharedPath, "utf8");

function assertEq(actual, expected, label) {
    if (actual !== expected) {
        throw new Error(`${label}: expected ${JSON.stringify(expected)}, got ${JSON.stringify(actual)}`);
    }
}

function assertDeepEqual(actual, expected, label) {
    const a = JSON.stringify(actual);
    const b = JSON.stringify(expected);
    if (a !== b) {
        throw new Error(`${label}: expected ${b}, got ${a}`);
    }
}

function extractFunctionSource(src, name, label) {
    const needle = `function ${name}(`;
    const start = src.indexOf(needle);
    if (start === -1) {
        throw new Error(`Function ${name} not found in ${label}`);
    }
    let i = src.indexOf("{", start);
    if (i < 0) throw new Error(`Opening brace not found for ${name}`);
    let depth = 0;
    let state = "code";

    const scanExprClosing = (from) => {
        let j = from;
        let d = 1;
        while (d > 0 && j < src.length) {
            const ch = src[j];
            if (ch === "{") d++;
            else if (ch === "}") d--;
            j++;
        }
        return j - 1;
    };

    for (; i < src.length; i++) {
        const c = src[i];
        const next = src[i + 1];

        if (state === "code") {
            if (c === "/" && next === "/") {
                state = "lineComment";
                i++;
                continue;
            }
            if (c === "/" && next === "*") {
                state = "blockComment";
                i++;
                continue;
            }
            if (c === "'") {
                state = "single";
                continue;
            }
            if (c === '"') {
                state = "double";
                continue;
            }
            if (c === "`") {
                state = "template";
                continue;
            }
            if (c === "{") depth++;
            else if (c === "}") {
                depth--;
                if (depth === 0) {
                    return src.slice(start, i + 1);
                }
            }
        } else if (state === "lineComment") {
            if (c === "\n" || c === "\r") state = "code";
        } else if (state === "blockComment") {
            if (c === "*" && next === "/") {
                state = "code";
                i++;
            }
        } else if (state === "single") {
            if (c === "\\") {
                i++;
                continue;
            }
            if (c === "'") state = "code";
        } else if (state === "double") {
            if (c === "\\") {
                i++;
                continue;
            }
            if (c === '"') state = "code";
        } else if (state === "template") {
            if (c === "\\") {
                i++;
                continue;
            }
            if (c === "`") {
                state = "code";
                continue;
            }
            if (c === "$" && next === "{") {
                const close = scanExprClosing(i + 2);
                i = close;
                continue;
            }
        }
    }

    throw new Error(`Unbalanced braces for ${name} in ${label}`);
}

function extractBlockBetween(src, startNeedle, endNeedle, label) {
    const start = src.indexOf(startNeedle);
    if (start === -1) {
        throw new Error(`Start block not found: ${startNeedle} in ${label}`);
    }
    const bodyStart = src.indexOf("\n", start);
    const end = src.indexOf(endNeedle, bodyStart);
    if (end === -1) {
        throw new Error(`End block not found: ${endNeedle} in ${label}`);
    }
    return src.slice(bodyStart + 1, end).trim();
}

const VOID_TAGS = new Set([
    "INPUT",
    "BR",
    "IMG",
    "META",
    "LINK",
    "AREA",
    "BASE",
    "COL",
    "EMBED",
    "HR",
    "PARAM",
    "SOURCE",
    "TRACK",
    "WBR",
]);

function parseHtmlFragment(html) {
    const root = { type: "fragment", children: [], parent: null };
    const stack = [root];
    let i = 0;
    while (i < html.length) {
        const lt = html.indexOf("<", i);
        if (lt === -1) break;
        let j = lt + 1;
        let inSingle = false;
        let inDouble = false;
        while (j < html.length) {
            const ch = html[j];
            if (ch === "'" && !inDouble) {
                inSingle = !inSingle;
            } else if (ch === '"' && !inSingle) {
                inDouble = !inDouble;
            } else if (ch === ">" && !inSingle && !inDouble) {
                break;
            }
            j++;
        }
        if (j >= html.length) break;
        const tagContent = html.slice(lt + 1, j).trim();
        i = j + 1;
        if (!tagContent) continue;
        const isClose = tagContent.startsWith("/");
        const normalized = isClose ? tagContent.slice(1).trim() : tagContent;
        const spaceIdx = normalized.search(/\s/);
        const tagRaw = spaceIdx === -1 ? normalized : normalized.slice(0, spaceIdx);
        const attrStr = spaceIdx === -1 ? "" : normalized.slice(spaceIdx + 1);
        const tag = tagRaw.toLowerCase();
        if (isClose) {
            if (stack.length > 1) stack.pop();
            continue;
        }
        const el = createElFromTag(tag, attrStr);
        stack[stack.length - 1].children.push(el);
        el.parent = stack[stack.length - 1];
        if (!VOID_TAGS.has(tagRaw.toUpperCase())) {
            stack.push(el);
        }
    }
    return root;
}

function parseAttrs(attrStr) {
    const attr = {};
    const re = /([\w-]+)(?:="([^"]*)")?/g;
    let m;
    while ((m = re.exec(attrStr)) !== null) {
        attr[m[1]] = m[2] !== undefined ? m[2] : "";
    }
    return attr;
}

function parseStyleAttr(styleStr) {
    const style = { display: "" };
    if (!styleStr) return style;
    String(styleStr)
        .split(";")
        .map((part) => part.trim())
        .filter(Boolean)
        .forEach((part) => {
            const idx = part.indexOf(":");
            if (idx === -1) return;
            const key = part.slice(0, idx).trim();
            const value = part.slice(idx + 1).trim();
            style[key] = value;
        });
    return style;
}

function createStyleObject(initialStyle) {
    const style = parseStyleAttr(initialStyle);
    style.setProperty = function (name, value) {
        this[name] = value == null ? "" : String(value);
    };
    style.removeProperty = function (name) {
        delete this[name];
        if (name === "display") this.display = "";
    };
    return style;
}

function createElFromTag(tag, attrStr) {
    const attr = parseAttrs(attrStr);
    const className = attr.class || "";
    const dataset = {};
    Object.keys(attr).forEach((k) => {
        if (k.startsWith("data-")) {
            dataset[k.slice(5)] = attr[k];
        }
    });
    const el = {
        tagName: tag.toUpperCase(),
        className,
        id: attr.id || "",
        attr: { ...attr },
        dataset,
        children: [],
        parent: null,
        parentEl: null,
        listeners: {},
        style: createStyleObject(attr.style || ""),
        _value: attr.value !== undefined ? String(attr.value) : "",
        _innerHTML: "",
        selectionStart: 0,
        selectionEnd: 0,
    };
    return el;
}

function flattenElements(node, out = []) {
    if (!node) return out;
    if (node.tagName) {
        out.push(node);
    }
    (node.children || []).forEach((child) => flattenElements(child, out));
    return out;
}

function syncSelectValuesFromOptions(all) {
    all.forEach((el) => {
        if (el.tagName !== "SELECT") return;
        const options = (el.children || []).filter((child) => child.tagName === "OPTION");
        const selectedOption = options.find(
            (opt) => opt.attr && Object.prototype.hasOwnProperty.call(opt.attr, "selected")
        );
        const pick = selectedOption || options[0];
        if (pick && pick.attr && pick.attr.value !== undefined) {
            el._value = String(pick.attr.value);
        }
    });
}

function wireDomTree(fragmentRoot) {
    const all = flattenElements(fragmentRoot, []);
    const ids = {};

    all.forEach((el) => {
        if (el.id) ids[el.id] = el;

        Object.defineProperty(el, "value", {
            get() {
                return this._value != null ? String(this._value) : "";
            },
            set(v) {
                this._value = v == null ? "" : String(v);
                this.selectionStart = this.value.length;
                this.selectionEnd = this.value.length;
            },
            configurable: true,
        });

        Object.defineProperty(el, "innerHTML", {
            get() {
                return this._innerHTML || "";
            },
            set(v) {
                this._innerHTML = v == null ? "" : String(v);
            },
            configurable: true,
        });

        Object.defineProperty(el, "lastElementChild", {
            get() {
                return this.children.length ? this.children[this.children.length - 1] : null;
            },
            configurable: true,
        });

        el.classList = {
            contains(c) {
                return el.className.split(/\s+/).filter(Boolean).includes(c);
            },
            add() {
                const existing = new Set(el.className.split(/\s+/).filter(Boolean));
                Array.from(arguments).forEach((token) => existing.add(token));
                el.className = Array.from(existing).join(" ");
            },
            remove() {
                const removeSet = new Set(Array.from(arguments));
                el.className = el.className
                    .split(/\s+/)
                    .filter(Boolean)
                    .filter((token) => !removeSet.has(token))
                    .join(" ");
            },
        };

        el.addEventListener = function (type, fn) {
            if (!this.listeners[type]) this.listeners[type] = [];
            this.listeners[type].push(fn);
        };
        el.querySelector = function (sel) {
            return querySelectorList(this, sel, false);
        };
        el.querySelectorAll = function (sel) {
            return querySelectorList(this, sel, true);
        };
        el.closest = function (sel) {
            let n = this;
            while (n) {
                if (matchSel(n, sel)) return n;
                n = n.parentEl;
            }
            return null;
        };
        el.remove = function () {
            if (!this.parentEl || !this.parentEl.children) return;
            const idx = this.parentEl.children.indexOf(this);
            if (idx >= 0) this.parentEl.children.splice(idx, 1);
            this.parentEl = null;
        };
        el.appendChild = function (child) {
            child.parentEl = this;
            child.parent = this;
            this.children.push(child);
            return child;
        };
        el.insertAdjacentHTML = function (_position, html) {
            const frag = parseHtmlFragment(String(html));
            const children = frag.children || [];
            children.forEach((child) => {
                child.parentEl = this;
                child.parent = this;
                this.children.push(child);
            });
            wireDomTree({ type: "fragment", children, parent: this });
        };
        el.setSelectionRange = function (start, end) {
            this.selectionStart = start;
            this.selectionEnd = end;
        };
    });

    const wireParent = (node) => {
        (node.children || []).forEach((child) => {
            child.parentEl = node.tagName ? node : child.parentEl;
            wireParent(child);
        });
    };
    wireParent(fragmentRoot);
    syncSelectValuesFromOptions(all);
    return { all, ids };
}

function matchSel(el, sel) {
    if (!el || !el.tagName) return false;
    if (sel.startsWith("#")) return el.id === sel.slice(1);
    if (sel.startsWith(".")) {
        return el.className.split(/\s+/).filter(Boolean).includes(sel.slice(1));
    }
    if (sel.startsWith("[") && sel.endsWith("]")) {
        const m = sel.match(/^\[([^=\]]+)(?:="([^"]*)")?\]$/);
        if (!m) return false;
        const attrName = m[1];
        const attrValue = m[2];
        if (!Object.prototype.hasOwnProperty.call(el.attr, attrName)) return false;
        return attrValue === undefined ? true : String(el.attr[attrName]) === attrValue;
    }
    return el.tagName === sel.toUpperCase();
}

function querySel(root, sel, all) {
    const out = [];
    const walk = (node) => {
        if (!node) return;
        if (!node.tagName) {
            (node.children || []).forEach(walk);
            return;
        }
        if (matchSel(node, sel)) {
            if (all) out.push(node);
            else {
                out.push(node);
                return;
            }
        }
        (node.children || []).forEach(walk);
    };
    walk(root);
    return all ? out : out[0] || null;
}

function querySelectorList(root, sel, all) {
    const parts = String(sel)
        .split(",")
        .map((s) => s.trim())
        .filter(Boolean);
    if (parts.length <= 1) {
        return querySel(root, parts[0] || sel, all);
    }
    if (all) {
        const seen = new Set();
        const out = [];
        parts.forEach((part) => {
            querySel(root, part, true).forEach((node) => {
                if (!seen.has(node)) {
                    seen.add(node);
                    out.push(node);
                }
            });
        });
        return out;
    }
    for (const part of parts) {
        const hit = querySel(root, part, false);
        if (hit) return hit;
    }
    return null;
}

function bubbleEvent(target, type, extra = {}) {
    const chain = [];
    let node = target;
    while (node) {
        chain.push(node);
        node = node.parentEl;
    }
    const ev = { type, target, bubbles: true, ...extra };
    chain.forEach((current) => {
        ev.currentTarget = current;
        const listeners = current.listeners && current.listeners[type];
        if (!listeners) return;
        listeners.forEach((fn) => fn.call(current, ev));
    });
}

function createDocument(ids, rootGetter) {
    const doc = {
        listeners: {},
        addEventListener(type, fn) {
            if (!this.listeners[type]) this.listeners[type] = [];
            this.listeners[type].push(fn);
        },
        getElementById(id) {
            return ids[id] || null;
        },
        querySelector(sel) {
            return rootGetter().querySelector(sel);
        },
        querySelectorAll(sel) {
            return rootGetter().querySelectorAll(sel);
        },
        createElement(tag) {
            const el = createElFromTag(tag, "");
            let text = "";
            Object.defineProperty(el, "textContent", {
                get() {
                    return text;
                },
                set(v) {
                    text = v == null ? "" : String(v);
                },
                configurable: true,
            });
            Object.defineProperty(el, "innerHTML", {
                get() {
                    return text
                        .replace(/&/g, "&amp;")
                        .replace(/</g, "&lt;")
                        .replace(/>/g, "&gt;")
                        .replace(/"/g, "&quot;");
                },
                configurable: true,
            });
            return el;
        },
    };
    return doc;
}

function runAll() {
    const sandbox = {
        console,
        window: null,
        globalThis: null,
        Math,
        Number,
        String,
        Object,
        Array,
        JSON,
        parseInt,
        parseFloat,
        isNaN,
        Date: {
            now: (() => {
                let i = 1700000000000;
                return function () {
                    i += 1;
                    return i;
                };
            })(),
        },
        setTimeout: function (fn) {
            fn();
            return 0;
        },
        clearTimeout: function () {},
        wdCalculatorCategories: [
            {
                name: "손잡이",
                options: [{ name: "무광 손잡이", price: 15000 }],
            },
            {
                name: "화장대",
                options: [{ name: "화장대A", price: 33000 }],
            },
        ],
    };
    sandbox.window = sandbox;
    sandbox.globalThis = sandbox;

    const fragmentRoot = { type: "fragment", children: [], parent: null, parentEl: null };
    const root = createElFromTag("div", "");
    const additionalOptionsContainer = createElFromTag("div", 'id="additionalOptionsContainer"');
    root.children.push(additionalOptionsContainer);
    additionalOptionsContainer.parent = root;
    fragmentRoot.children.push(root);
    root.parent = fragmentRoot;

    const wired = wireDomTree(fragmentRoot);
    const ids = { ...wired.ids, additionalOptionsContainer };
    const document = createDocument(ids, () => root);
    root.parentEl = document;
    additionalOptionsContainer.parentEl = root;

    let calculateCalls = 0;
    sandbox.document = document;
    sandbox.calculateEstimate = function () {
        calculateCalls += 1;
    };

    vm.createContext(sandbox);
    vm.runInContext(sharedSrc, sandbox);
    vm.runInContext(helperSrc, sandbox);
    const additionalOptionsUi = sandbox.WdCalculatorAdditionalOptionsUI;
    additionalOptionsUi.configure({
        getCategories: () => sandbox.wdCalculatorCategories,
        getCalculateEstimate: () => sandbox.calculateEstimate,
    });

    // --- Add row path ---
    additionalOptionsUi.appendAdditionalOptionRow(additionalOptionsContainer, {
        forceMode: "select",
        formatPriceOnInput: false,
    });
    assertEq(
        additionalOptionsContainer.querySelectorAll(".additional-option-item").length,
        1,
        "appendAdditionalOptionRow creates one option row"
    );
    assertEq(calculateCalls, 0, "adding blank option row does not calculate immediately");

    const item = additionalOptionsContainer.querySelector(".additional-option-item");
    const select = item.querySelector("[data-category-option-select]");
    const nameInput = item.querySelector("[data-option-name]");
    const priceInput = item.querySelector("[data-option-price]");
    const quantityInput = item.querySelector("[data-option-quantity]");
    const toggleBtn = item.querySelector("[data-toggle-direct-input]");
    const removeBtn = item.querySelector(".remove-option-btn");

    assertEq(!!select, true, "row has category-option select");
    assertEq(!!nameInput, true, "row has option-name input");
    assertEq(!!priceInput, true, "row has option-price input");
    assertEq(!!quantityInput, true, "row has option-quantity input");
    assertEq(!!toggleBtn, true, "row has direct-input toggle");
    assertEq(!!removeBtn, true, "row has remove button");
    assertEq(select.style.display, "block", "new row starts in select mode");
    assertEq(nameInput.style.display, "none", "name input hidden in select mode");
    assertEq(toggleBtn.innerHTML, '<i class="fas fa-keyboard"></i>', "new row toggle icon");
    assertEq(quantityInput.value, "1", "new row default quantity");

    // --- Toggle to direct input mode ---
    calculateCalls = 0;
    bubbleEvent(toggleBtn, "click");
    assertEq(select.style.display, "none", "toggle hides select");
    assertEq(nameInput.style.display, "block", "toggle shows name input");
    assertEq(toggleBtn.innerHTML, '<i class="fas fa-list"></i>', "toggle switches icon to list");
    assertEq(calculateCalls, 1, "toggle triggers calculateEstimate once");

    // --- Direct input price formatting + readAdditionalOptionRowsFromUI ---
    calculateCalls = 0;
    nameInput.value = "직접 옵션";
    priceInput.value = "12345";
    priceInput.selectionStart = priceInput.value.length;
    bubbleEvent(priceInput, "input");
    assertEq(priceInput.value, "12345", "newly added row keeps raw price input text");
    assertEq(calculateCalls, 1, "price input triggers calculateEstimate once");
    quantityInput.value = "2";
    assertDeepEqual(
        additionalOptionsUi.readAdditionalOptionRowsFromUI(),
        [{ name: "직접 옵션", price: 12345, quantity: 2 }],
        "readAdditionalOptionRowsFromUI reads direct-input row"
    );

    // --- Toggle back + dropdown selection path ---
    calculateCalls = 0;
    bubbleEvent(toggleBtn, "click");
    assertEq(select.style.display, "block", "toggle back shows select");
    assertEq(nameInput.style.display, "none", "toggle back hides name input");
    assertEq(toggleBtn.innerHTML, '<i class="fas fa-keyboard"></i>', "toggle back icon");
    assertEq(calculateCalls, 1, "toggle back triggers calculateEstimate once");

    calculateCalls = 0;
    quantityInput.value = "";
    select.value = "손잡이|무광 손잡이|15000";
    bubbleEvent(select, "change");
    assertEq(nameInput.value, "손잡이 > 무광 손잡이", "select change hydrates option name");
    assertEq(priceInput.value, "15,000", "select change hydrates formatted price");
    assertEq(quantityInput.value, "1", "select change restores default quantity");
    assertEq(calculateCalls, 1, "select change triggers calculateEstimate once");
    assertDeepEqual(
        additionalOptionsUi.readAdditionalOptionRowsFromUI(),
        [{ name: "손잡이 > 무광 손잡이", price: 15000, quantity: 1 }],
        "readAdditionalOptionRowsFromUI reads dropdown row"
    );

    // --- Blank / invalid rows are filtered out ---
    priceInput.value = "";
    assertDeepEqual(
        additionalOptionsUi.readAdditionalOptionRowsFromUI(),
        [],
        "readAdditionalOptionRowsFromUI filters blank price rows"
    );

    // --- Delegated remove path stays single-call ---
    calculateCalls = 0;
    bubbleEvent(removeBtn, "click");
    assertEq(
        additionalOptionsContainer.querySelectorAll(".additional-option-item").length,
        0,
        "remove-option-btn removes row"
    );
    assertEq(calculateCalls, 1, "remove-option-btn triggers calculateEstimate once");
}

try {
    runAll();
} catch (error) {
    console.error(error);
    process.exit(1);
}
