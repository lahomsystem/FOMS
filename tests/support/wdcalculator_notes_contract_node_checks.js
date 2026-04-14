/**
 * Freezes the runtime contract for WDCalculator notes helpers from
 * static/js/wdcalculator/primary-form.js (notes-ui band inside W5-B3 chunk).
 *
 * Extracts named notes helpers from the merged file, strips renderAllNotes() calls so
 * tests exercise notesList state without a full DOM, then runs assertions in Node's vm.
 */
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const repoRoot = path.join(__dirname, "..", "..");
const primaryFormPath = path.join(repoRoot, "static", "js", "wdcalculator", "primary-form.js");

const templateSrc = fs.readFileSync(primaryFormPath, "utf8");

/**
 * Extract `function name(...) { ... }` while skipping strings/comments/template literals
 * so braces inside template strings do not break balancing.
 */
function extractFunctionSource(src, name) {
    const needle = `function ${name}(`;
    const start = src.indexOf(needle);
    if (start === -1) {
        throw new Error(`Function ${name} not found in ${primaryFormPath}`);
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
    throw new Error(`Unbalanced braces for ${name}`);
}

const extracted = [
    "loadNotesCategories",
    "checkIfOptionExists",
    "loadNotes",
    "collectNotes",
    "formatNumbersInText",
    "formatNotesText",
]
    .map((fn) => extractFunctionSource(templateSrc, fn))
    .join("\n");

/** Same escaping intent as static/js/wdcalculator/shared.js escapeHtml without needing DOM. */
function escapeHtmlStatic(text) {
    if (!text) return "";
    return String(text)
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#039;");
}

// Drop render calls so loadNotes only mutates notesList (no DOM dependency).
const withoutRenderCalls = extracted.replace(/\n\s*renderAllNotes\(\);\s*/g, "\n");

const preamble = `
var wdNotesCategories = [];
var notesCategories = [];
var notesList = [];
var escapeHtml = escapeHtmlStatic;
`;

const sandbox = {
    console,
    escapeHtmlStatic,
    setTimeout: function (fn, _delay) {
        fn();
        return 0;
    },
    clearTimeout: function () {},
};
sandbox.globalThis = sandbox;

vm.createContext(sandbox);
vm.runInContext(preamble + "\n" + withoutRenderCalls, sandbox);

const loadNotesCategories = sandbox.loadNotesCategories;
const loadNotes = sandbox.loadNotes;
const collectNotes = sandbox.collectNotes;
const formatNumbersInText = sandbox.formatNumbersInText;
const formatNotesText = sandbox.formatNotesText;

if (typeof loadNotes !== "function" || typeof collectNotes !== "function") {
    throw new Error("notes helpers not defined after template extract");
}

function assertEq(actual, expected, label) {
    if (actual !== expected) {
        throw new Error((label || "assert") + ": expected " + JSON.stringify(expected) + ", got " + JSON.stringify(actual));
    }
}

/** Representative wdNotesCategories shape (matches app clean_categories_data style). */
const SAMPLE_WD_NOTES = [
    {
        name: "기본 비고",
        options: [{ name: "기본 비고 문구", price: 0 }],
    },
    {
        name: "배송",
        options: [
            { name: "당일", price: 0 },
            { name: "익일", price: 0 },
        ],
    },
];

function seedCategories(categories) {
    sandbox.wdNotesCategories = categories;
    sandbox.notesCategories = [];
    loadNotesCategories();
}

function roundtrip(savedString) {
    loadNotes(savedString);
    return collectNotes();
}

// --- 1) wdNotesCategories / loadNotesCategories contract ---
seedCategories(SAMPLE_WD_NOTES);
assertEq(sandbox.notesCategories === sandbox.wdNotesCategories, true, "notesCategories aliases wdNotesCategories");
assertEq(sandbox.notesCategories.length, 2, "notesCategories length");

seedCategories([]);
assertEq(Array.isArray(sandbox.notesCategories), true, "empty wdNotesCategories yields array");

// --- 2) Plain-text line ---
seedCategories(SAMPLE_WD_NOTES);
assertEq(roundtrip("직접 입력 한 줄"), "직접 입력 한 줄", "plain single line");

// --- 3) Category-backed (select) line ---
seedCategories(SAMPLE_WD_NOTES);
const optLine = "기본 비고 > 기본 비고 문구";
assertEq(roundtrip(optLine), optLine, "select option line");

// --- 4) Mixed multi-line ---
seedCategories(SAMPLE_WD_NOTES);
const mixed = "첫줄 텍스트\n" + optLine + "\n마지막 줄";
assertEq(roundtrip(mixed), mixed, "mixed plain + option + plain");

// --- 5) Blank lines: loadNotes filters empty lines, so internal blanks collapse ---
seedCategories(SAMPLE_WD_NOTES);
assertEq(roundtrip("a\n\nb"), "a\nb", "blank lines between notes are dropped on load");

// --- 6) Empty / whitespace-only input ---
seedCategories(SAMPLE_WD_NOTES);
assertEq(roundtrip(""), "", "empty string");
assertEq(roundtrip("   "), "", "whitespace-only string");
assertEq(roundtrip("\n\n  \n"), "", "only blank lines");

// --- 7) Numeric formatting helper (blur path behavior; 4+ digit runs) ---
assertEq(formatNumbersInText("금액 12345원"), "금액 12,345원", "formatNumbersInText ko-KR 5 digits");
assertEq(formatNumbersInText("123"), "123", "formatNumbersInText ignores &lt;4 digit runs");
assertEq(formatNumbersInText("1234"), "1,234", "formatNumbersInText 4 digits");

// --- 8) formatNotesText trims each line (blank middle lines preserved) ---
assertEq(formatNotesText(" a \n\nb "), "a\n\nb", "formatNotesText per-line trim");

process.exit(0);
