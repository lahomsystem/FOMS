/**
 * WD/ERP 공통 가로(mm) 복합 표기 평가 — Python eval_spec_width_mm SSOT와 동일 규칙.
 * 지원: 단일값, 4120+4121+2354, 5700,4512,2300, 5700(2402+1864+1638) 등.
 */
var evalSpecWidthMm =
    window.evalSpecWidthMm ||
    function evalSpecWidthMm(value) {
        if (value == null || value === "") {
            return 0;
        }
        var s = String(value).trim();
        if (!s) {
            return 0;
        }
        s = s.replace(/\([^)]*\)/g, "");
        var total = 0;
        var matched = false;
        var terms = s.split(/[+,]/);
        for (var i = 0; i < terms.length; i++) {
            var m = terms[i].match(/[\d.]+/);
            if (!m) {
                continue;
            }
            var n = parseFloat(m[0]);
            if (isNaN(n)) {
                continue;
            }
            total += n;
            matched = true;
        }
        return matched ? total : 0;
    };
window.evalSpecWidthMm = evalSpecWidthMm;

var resolveBaseWidthFromInput =
    window.resolveBaseWidthFromInput ||
    function resolveBaseWidthFromInput(raw) {
        var widthInput = String(raw == null ? "" : raw).trim();
        var widthMm = Math.round(evalSpecWidthMm(widthInput));
        return { widthInput: widthInput, widthMm: widthMm };
    };
window.resolveBaseWidthFromInput = resolveBaseWidthFromInput;

var formatBaseWidthDisplay =
    window.formatBaseWidthDisplay ||
    function formatBaseWidthDisplay(comp, formatNumberFn) {
        var fmt =
            typeof formatNumberFn === "function" ? formatNumberFn : window.formatNumber;
        var w = Number(comp && comp.widthMm) || 0;
        if (w <= 0) {
            return "";
        }
        var raw = String((comp && comp.widthInput) || "").trim();
        if (raw && (raw.indexOf("+") >= 0 || raw.indexOf(",") >= 0)) {
            return raw + " (" + fmt(w) + "mm)";
        }
        return fmt(w) + "mm";
    };
window.formatBaseWidthDisplay = formatBaseWidthDisplay;

var updateBaseWidthPreview =
    window.updateBaseWidthPreview ||
    function updateBaseWidthPreview(rowEl) {
        if (!rowEl) {
            return;
        }
        var input = rowEl.querySelector(".base-width-input");
        var preview = rowEl.querySelector(".base-width-preview");
        if (!input || !preview) {
            return;
        }
        var resolved = resolveBaseWidthFromInput(input.value);
        function setPreviewDanger(isDanger) {
            if (!preview.classList) {
                return;
            }
            if (typeof preview.classList.add !== "function") {
                return;
            }
            if (isDanger) {
                preview.classList.add("text-danger");
            } else if (typeof preview.classList.remove === "function") {
                preview.classList.remove("text-danger");
            }
        }
        if (!resolved.widthInput) {
            preview.textContent = "";
            setPreviewDanger(false);
            return;
        }
        if (resolved.widthMm <= 0) {
            preview.textContent = "가로(mm) 형식을 확인하세요";
            setPreviewDanger(true);
            return;
        }
        if (resolved.widthInput.indexOf("+") >= 0 || resolved.widthInput.indexOf(",") >= 0) {
            preview.textContent = "= " + formatNumber(resolved.widthMm) + "mm";
            setPreviewDanger(false);
            return;
        }
        preview.textContent = "";
        setPreviewDanger(false);
    };
window.updateBaseWidthPreview = updateBaseWidthPreview;
