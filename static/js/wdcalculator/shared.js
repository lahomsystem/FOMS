var syncWdCalculatorViewportLayout =
    window.syncWdCalculatorViewportLayout ||
    function syncWdCalculatorViewportLayout() {
        var container = document.querySelector(".wdcalculator-container");
        var shell = document.querySelector(".wdcalculator-shell");
        if (!container || !shell) return;

        if (window.innerWidth < 992) {
            container.style.removeProperty("--wdcalculator-shell-height");
            return;
        }

        var shellTop = shell.getBoundingClientRect().top;
        var bottomGap = 16;
        var availableHeight = Math.max(
            520,
            Math.floor(window.innerHeight - shellTop - bottomGap)
        );
        container.style.setProperty("--wdcalculator-shell-height", availableHeight + "px");
    };
window.syncWdCalculatorViewportLayout = syncWdCalculatorViewportLayout;

var requestWdCalculatorLayoutSync =
    window.requestWdCalculatorLayoutSync ||
    function requestWdCalculatorLayoutSync() {
        window.requestAnimationFrame(syncWdCalculatorViewportLayout);
    };
window.requestWdCalculatorLayoutSync = requestWdCalculatorLayoutSync;

var ceilToTens =
    window.ceilToTens ||
    function ceilToTens(value) {
        var v = Number(value) || 0;
        return Math.ceil(v / 10) * 10;
    };
window.ceilToTens = ceilToTens;

var computeAutoPrice1cmFrom30cm =
    window.computeAutoPrice1cmFrom30cm ||
    function computeAutoPrice1cmFrom30cm(price30) {
        return ceilToTens((Number(price30) || 0) / 30);
    };
window.computeAutoPrice1cmFrom30cm = computeAutoPrice1cmFrom30cm;

var generateEstimateId =
    window.generateEstimateId ||
    function generateEstimateId() {
        return "est_" + Date.now() + "_" + Math.random().toString(36).substr(2, 9);
    };
window.generateEstimateId = generateEstimateId;

var isSameId =
    window.isSameId ||
    function isSameId(id1, id2) {
        return String(id1) === String(id2);
    };
window.isSameId = isSameId;

var normalizeId =
    window.normalizeId ||
    function normalizeId(id) {
        if (!id) return null;
        return String(id);
    };
window.normalizeId = normalizeId;

var formatPrice =
    window.formatPrice ||
    function formatPrice(value) {
        if (!value) return "";
        var numValue = value.toString().replace(/[^\d]/g, "");
        if (!numValue) return "";
        return parseInt(numValue, 10).toLocaleString("ko-KR");
    };
window.formatPrice = formatPrice;

var parsePrice =
    window.parsePrice ||
    function parsePrice(value) {
        if (!value) return 0;
        var numValue = value.toString().replace(/[^\d]/g, "");
        return parseFloat(numValue) || 0;
    };
window.parsePrice = parsePrice;

var escapeHtml =
    window.escapeHtml ||
    function escapeHtml(text) {
        if (!text) return "";
        var div = document.createElement("div");
        div.textContent = String(text);
        return div.innerHTML;
    };
window.escapeHtml = escapeHtml;

var formatNumber =
    window.formatNumber ||
    function formatNumber(num) {
        return Math.round(num).toLocaleString("ko-KR");
    };
window.formatNumber = formatNumber;
